"""
Build_SignTypeLibrary_PolygonalFaceSet.py

Creates IfcTrafficSignLibrary_PolygonalFaceSet.ifc using IfcPolygonalFaceSet
and IfcStyledItem.  Color and geometry are sourced from the SVG files that
are co-located with (and share the same root name as) the PNG sign-face images.

Key differences from Build_SignTypeLibrary_TextureMapping.py:
  - No IfcImageTexture / IfcIndexedTriangleTextureMap / IfcTextureVertexList
  - Each unique fill color in the SVG becomes its own IfcPolygonalFaceSet
    with an IfcSurfaceStyle (IfcSurfaceStyleShading + IfcColourRgb) applied
    via IfcStyledItem
  - The SVG paths are tessellated with Shapely's Delaunay triangulator
"""

import ifcopenshell
import ifcopenshell.api.context
import ifcopenshell.api.unit
import ifcopenshell.api.pset
import math
import os
import re
import xml.etree.ElementTree as ET

import shapely
from shapely.geometry import Polygon as ShapelyPolygon

# ── configuration ──────────────────────────────────────────────────────────

BEZIER_SAMPLES  = 8           # line segments per cubic/quadratic Bezier curve
MIN_DEDUPE_DIST = 2.0         # SVG units – collapse closer-than-this points
MIN_POLY_AREA   = 4.0         # SVG units² – skip degenerate micro-polygons
GRAPHIC_Z_OFFSET = -0.01      # inches – lifts graphic layer above background to prevent z-fighting

SVG_ROOT  = "../SignFaces/"
OUT_FILE  = "..\\IfcTrafficSignLibrary_PolygonalFaceSet.ifc"

no_dimensions = []

# ── general utilities ──────────────────────────────────────────────────────

def get_stem(path):
    return os.path.splitext(os.path.basename(path))[0]

def extract_dims(filename):
    m = re.search(r'(\d+(?:\.\d+)?)[xX](\d+(?:\.\d+)?)', filename)
    if m:
        return float(m.group(1)), float(m.group(2))
    no_dimensions.append(filename)
    return None

def hex_to_rgb(h):
    """'#rrggbb' → (r, g, b) in [0, 1]."""
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0

def poly_signed_area_2d(pts):
    n = len(pts)
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return a / 2.0

# ── SVG parsing ────────────────────────────────────────────────────────────

_NS_RE = re.compile(r'\{[^}]*\}')

def local_tag(tag):
    return _NS_RE.sub('', tag)

def parse_viewbox(s):
    return tuple(float(x) for x in s.replace(',', ' ').split()[:4])

def parse_style_str(s):
    d = {}
    for part in s.split(';'):
        if ':' in part:
            k, v = part.split(':', 1)
            d[k.strip()] = v.strip()
    return d

def parse_css_class_fills(tree):
    """Extract .classname → fill-color mappings from embedded <style> elements."""
    class_fills = {}
    for elem in tree.iter():
        if local_tag(elem.tag) == 'style':
            text = elem.text or ''
            for m in re.finditer(r'\.(\w+)\s*\{([^}]*)\}', text, re.DOTALL):
                cls = m.group(1)
                body = m.group(2)
                fm = re.search(r'\bfill\s*:\s*([^;}\s]+)', body)
                if fm:
                    v = fm.group(1).strip().lower()
                    if v not in ('none', 'transparent'):
                        class_fills[cls] = v
    return class_fills

def get_fill(elem, parent_fill=None, class_fills=None):
    """Return normalised fill hex (or None) for this element."""
    style_str = elem.get('style', '')
    if style_str:
        sd = parse_style_str(style_str)
        if 'fill' in sd:
            v = sd['fill'].lower()
            return None if v in ('none', 'transparent') else v
    fill = elem.get('fill')
    if fill is not None:
        fill = fill.lower()
        return None if fill in ('none', 'transparent') else fill
    if class_fills:
        for cls in elem.get('class', '').split():
            if cls in class_fills:
                return class_fills[cls]
    return parent_fill

# ── SVG shape helpers ──────────────────────────────────────────────────────

def parse_polygon_points(points_str):
    """Parse SVG <polygon> points attribute into a list of (x, y) tuples."""
    nums = [float(v) for v in re.split(r'[\s,]+', points_str.strip()) if v]
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]

def rect_to_points(elem, n_corner=6):
    """Convert <rect> element to a polygon point list, approximating rx/ry corners."""
    x = float(elem.get('x', 0))
    y = float(elem.get('y', 0))
    w = float(elem.get('width', 0))
    h = float(elem.get('height', 0))
    rx_s = elem.get('rx'); ry_s = elem.get('ry')
    if rx_s is None and ry_s is None:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    rx = float(rx_s) if rx_s is not None else float(ry_s)
    ry = float(ry_s) if ry_s is not None else rx
    rx = min(rx, w / 2); ry = min(ry, h / 2)

    def arc(cx, cy, start_a, end_a):
        return [(cx + rx * math.cos(start_a + (end_a - start_a) * i / n_corner),
                 cy + ry * math.sin(start_a + (end_a - start_a) * i / n_corner))
                for i in range(1, n_corner + 1)]

    pts = []
    pts.extend(arc(x + rx,     y + ry,     math.pi,         3 * math.pi / 2))
    pts.extend(arc(x + w - rx, y + ry,     3 * math.pi / 2, 2 * math.pi))
    pts.extend(arc(x + w - rx, y + h - ry, 0,               math.pi / 2))
    pts.extend(arc(x + rx,     y + h - ry, math.pi / 2,     math.pi))
    return pts

# ── Bezier approximation ───────────────────────────────────────────────────

def _cubic_pts(p0, p1, p2, p3, n):
    pts = []
    for i in range(1, n + 1):
        t = i / n; mt = 1 - t
        pts.append((
            mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0],
            mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1],
        ))
    return pts

def _quad_pts(p0, p1, p2, n):
    pts = []
    for i in range(1, n + 1):
        t = i / n; mt = 1 - t
        pts.append((
            mt**2*p0[0] + 2*mt*t*p1[0] + t**2*p2[0],
            mt**2*p0[1] + 2*mt*t*p1[1] + t**2*p2[1],
        ))
    return pts

# ── SVG path parser ────────────────────────────────────────────────────────

_TOK_RE = re.compile(
    r'([MmLlCcSsQqTtAaHhVvZz])'
    r'|([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)'
)

def parse_path_d(d_str):
    """
    Parse an SVG path 'd' attribute into a list of closed subpaths.
    Each subpath is a list of (x, y) floats.
    Handles M/m  L/l  H/h  V/v  C/c  S/s  Q/q  Z/z.
    A subpath is appended to the list at each Z command, and at each M
    command that follows a non-empty current path.
    """
    tokens = _TOK_RE.findall(d_str)
    cmds = []
    cur_cmd = None; cur_args = []
    for letter, num in tokens:
        if letter:
            if cur_cmd is not None:
                cmds.append((cur_cmd, cur_args))
            cur_cmd = letter; cur_args = []
        elif num:
            cur_args.append(float(num))
    if cur_cmd is not None:
        cmds.append((cur_cmd, cur_args))

    subpaths = []
    cur = []
    cx = cy = sx = sy = 0.0
    last_c2 = None  # second control point of previous C/S for smooth continuation

    for cmd, args in cmds:
        rel = cmd.islower()
        C = cmd.upper()

        def A(dx, dy):
            return (cx + dx, cy + dy) if rel else (dx, dy)

        if C == 'M':
            if cur:
                subpaths.append(cur); cur = []
            i = 0
            while i + 1 <= len(args) - 1:
                x, y = A(args[i], args[i + 1]); i += 2
                if not cur:
                    cx, cy = x, y; sx, sy = cx, cy; cur.append((cx, cy))
                else:   # implicit L after first pair
                    cx, cy = x, y; cur.append((cx, cy))
            last_c2 = None

        elif C == 'L':
            i = 0
            while i + 1 <= len(args) - 1:
                cx, cy = A(args[i], args[i + 1]); i += 2
                cur.append((cx, cy))
            last_c2 = None

        elif C == 'H':
            for v in args:
                cx = (cx + v) if rel else v
                cur.append((cx, cy))
            last_c2 = None

        elif C == 'V':
            for v in args:
                cy = (cy + v) if rel else v
                cur.append((cx, cy))
            last_c2 = None

        elif C == 'C':
            i = 0
            while i + 5 <= len(args) - 1:
                p0 = (cx, cy)
                p1 = A(args[i],     args[i + 1])
                p2 = A(args[i + 2], args[i + 3])
                p3 = A(args[i + 4], args[i + 5])
                i += 6
                cur.extend(_cubic_pts(p0, p1, p2, p3, BEZIER_SAMPLES))
                cx, cy = p3; last_c2 = p2

        elif C == 'S':
            i = 0
            while i + 3 <= len(args) - 1:
                p0 = (cx, cy)
                p1 = (2*cx - last_c2[0], 2*cy - last_c2[1]) if last_c2 else p0
                p2 = A(args[i],     args[i + 1])
                p3 = A(args[i + 2], args[i + 3])
                i += 4
                cur.extend(_cubic_pts(p0, p1, p2, p3, BEZIER_SAMPLES))
                cx, cy = p3; last_c2 = p2

        elif C == 'Q':
            i = 0
            while i + 3 <= len(args) - 1:
                p0 = (cx, cy)
                p1 = A(args[i],     args[i + 1])
                p2 = A(args[i + 2], args[i + 3])
                i += 4
                cur.extend(_quad_pts(p0, p1, p2, BEZIER_SAMPLES))
                cx, cy = p2; last_c2 = None

        elif C == 'Z':
            if cur:
                if abs(cur[-1][0] - sx) > 1e-6 or abs(cur[-1][1] - sy) > 1e-6:
                    cur.append((sx, sy))
                subpaths.append(cur); cur = []
            cx, cy = sx, sy; last_c2 = None

    if cur:
        subpaths.append(cur)
    return subpaths


def dedupe(pts, min_d=MIN_DEDUPE_DIST):
    """Remove consecutive near-duplicate points and redundant closing vertex."""
    if not pts:
        return pts
    r = [pts[0]]
    md2 = min_d * min_d
    for p in pts[1:]:
        dx = p[0] - r[-1][0]; dy = p[1] - r[-1][1]
        if dx*dx + dy*dy >= md2:
            r.append(p)
    if len(r) > 1:
        dx = r[-1][0] - r[0][0]; dy = r[-1][1] - r[0][1]
        if dx*dx + dy*dy < 1e-6:
            r.pop()
    return r


def extract_colored_paths(svg_file):
    """
    Parse an SVG file and return:
      color_paths : {hex_color: [ [subpath0, subpath1, ...], ... ]}
                    Each list item is one <path> element's subpaths.
                    subpath0 = exterior ring; subpath1+ = potential holes.
      viewbox     : (vb_x, vb_y, vb_w, vb_h)
    Only filled paths are collected (stroke-only paths are ignored).
    clipPath contents are skipped.
    """
    tree = ET.parse(svg_file)
    root = tree.getroot()
    vb = parse_viewbox(root.get('viewBox', '0 0 100 100'))
    class_fills = parse_css_class_fills(tree)
    color_paths = {}

    def traverse(elem, parent_fill=None, in_clip=False):
        tag = local_tag(elem.tag)
        if tag == 'clipPath':
            return
        fill = get_fill(elem, parent_fill, class_fills)
        if not in_clip and fill:
            if tag == 'path':
                d = elem.get('d', '')
                if d:
                    subs = [dedupe(s) for s in parse_path_d(d)]
                    subs = [s for s in subs if len(s) >= 3]
                    if subs:
                        color_paths.setdefault(fill, []).append(subs)
            elif tag == 'polygon':
                raw = dedupe(parse_polygon_points(elem.get('points', '')))
                if len(raw) >= 3:
                    color_paths.setdefault(fill, []).append([raw])
            elif tag == 'rect':
                raw = dedupe(rect_to_points(elem))
                if len(raw) >= 3:
                    color_paths.setdefault(fill, []).append([raw])
        for child in elem:
            traverse(child, fill, in_clip)

    traverse(root)
    return color_paths, vb

# ── coordinate mapping ─────────────────────────────────────────────────────

def svg_to_3d(x, y, vb, sign_w, sign_h, z=0.0):
    """Map SVG (x, y) to a centred 3-D sign-face coordinate at depth z."""
    vbx, vby, vbw, vbh = vb
    return (
        (x - (vbx + vbw / 2.0)) * (sign_w / vbw),
        -(y - (vby + vbh / 2.0)) * (sign_h / vbh),   # flip Y
        z,
    )

# ── polygon triangulation via Shapely ──────────────────────────────────────

def triangulate_path(subpath_group):
    """
    Triangulate one SVG <path> element given as a list of subpaths.

    Subpaths are grouped by spatial containment: a smaller subpath fully
    inside a larger one becomes a hole.  Independent subpaths (e.g. separate
    letters in a compound path) are triangulated as distinct exteriors.
    Uses constrained Delaunay triangulation so boundaries and holes are
    respected exactly.

    Returns a list of triangles [(x0,y0), (x1,y1), (x2,y2)] in SVG coords.
    """
    if not subpath_group:
        return []

    # Build a valid Shapely polygon for each subpath
    polys = []
    for sp in subpath_group:
        if len(sp) < 3:
            continue
        try:
            p = ShapelyPolygon(sp)
            if not p.is_valid:
                p = p.buffer(0)
            if not p.is_empty and p.area >= MIN_POLY_AREA:
                polys.append(p)
        except Exception:
            pass

    if not polys:
        return []

    # Sort largest-first so exterior polys precede their holes
    polys.sort(key=lambda p: p.area, reverse=True)

    # Group each exterior poly with the smaller polys it fully contains (holes)
    used = [False] * len(polys)
    groups = []
    for i, ext in enumerate(polys):
        if used[i]:
            continue
        used[i] = True
        holes = []
        for j in range(i + 1, len(polys)):
            if not used[j] and ext.contains(polys[j]):
                holes.append(polys[j])
                used[j] = True
        groups.append((ext, holes))

    # Triangulate each exterior+holes group with constrained Delaunay
    all_triangles = []
    for ext_poly, hole_polys in groups:
        try:
            if hole_polys:
                combined = ShapelyPolygon(
                    list(ext_poly.exterior.coords),
                    [list(h.exterior.coords) for h in hole_polys],
                )
                if not combined.is_valid:
                    combined = combined.buffer(0)
            else:
                combined = ext_poly

            if combined.is_empty or combined.area < MIN_POLY_AREA:
                continue

            raw = shapely.constrained_delaunay_triangles(combined)
            for tri in raw.geoms:
                coords = list(tri.exterior.coords)[:-1]
                if len(coords) == 3:
                    all_triangles.append(coords)
        except Exception:
            pass

    return all_triangles

# ── sign outline polygon (used for area property set) ─────────────────────

def sign_outline_2d(shape_name, w, h):
    """Return a list of (x, y) 2-D vertices for the sign's perimeter."""
    def gen(n_sides, start):
        step = 2.0 * math.pi / n_sides
        Rx = 0.5 * w / math.cos(math.pi / n_sides)
        Ry = 0.5 * h / math.cos(math.pi / n_sides)
        return [(Rx * math.cos(start + i * step),
                 Ry * math.sin(start + i * step)) for i in range(n_sides)]

    if shape_name == 'Rectangle':  return gen(4, math.pi / 4)
    if shape_name == 'Diamond':    return gen(4, 0.0)
    if shape_name == 'Triangle':   return gen(3, math.pi / 6)
    if shape_name == 'Octagon':    return gen(8, math.pi / 8)
    if shape_name == 'Pentagon':
        return [(0.,0.),(w/2,-h/2),(w/2,0.),(0.,h/2),(-w/2,0.),(-w/2,-h/2)]
    if shape_name == 'CrossBuck':
        ang = math.pi / 4
        p1 = (0., -0.5*h / math.sin(ang))
        p2 = (0.5*(w-h)*math.cos(ang), p1[1] - 0.5*(w-h)*math.sin(ang))
        p3 = (p2[0]+h*math.cos(ang), p2[1]+h*math.sin(ang))
        p4 = (0.5*h / math.cos(ang), 0.)
        p5 = (p4[0]+0.5*(w-h)*math.cos(ang), 0.5*(w-h)*math.sin(ang))
        p6 = (p5[0]-h*math.cos(ang), p5[1]+h*math.sin(ang))
        p7 = (0., 0.5*h / math.sin(ang))
        return [p1,p2,p3,p4,p5,p6,p7,
                (-p6[0],p6[1]),(-p5[0],p5[1]),(-p4[0],p4[1]),
                (-p3[0],p3[1]),(-p2[0],p2[1])]
    return None

# ── IFC surface style cache ────────────────────────────────────────────────

def get_or_create_style(model, cache, hex_color):
    key = hex_color.lower()
    if key not in cache:
        r, g, b = hex_to_rgb(key)
        col     = model.createIfcColourRgb(None, r, g, b)
        shading = model.createIfcSurfaceStyleShading(col, None)
        cache[key] = model.createIfcSurfaceStyle(key, 'BOTH', [shading])
    return cache[key]

# ── IfcPolygonalFaceSet builder ────────────────────────────────────────────

def build_face_set(model, pts_3d, triangles_ifc):
    """
    Create IfcPolygonalFaceSet from a list of 3-D points and 1-based index triples.
    pts_3d         : [(x, y, z), ...]
    triangles_ifc  : [(i, j, k), ...] (1-based)
    """
    pt_list = model.createIfcCartesianPointList3D(CoordList=pts_3d)
    faces   = [model.createIfcIndexedPolygonalFace(CoordIndex=list(t))
               for t in triangles_ifc]
    return model.createIfcPolygonalFaceSet(
        Coordinates=pt_list, Closed=False, Faces=faces
    )

# ── main sign-type creator ─────────────────────────────────────────────────

def create_signtype(svg_path, model, body_ctx, shape_name, style_cache):
    name = get_stem(svg_path)
    dims = extract_dims(svg_path)
    if dims is None:
        return None

    w, h = dims
    outline = sign_outline_2d(shape_name, w, h)
    if outline is None:
        print(f"  No shape handler for '{shape_name}', skipping {name}")
        return None

    print(f"Processing {name}")

    # ── Parse SVG ──────────────────────────────────────────────────────────
    try:
        color_paths, vb = extract_colored_paths(svg_path)
    except Exception as e:
        print(f"  SVG parse error: {e}")
        return None

    if not color_paths:
        print(f"  No filled paths found")
        return None

    # ── Build per-color face sets ─────────────────────────────────────────
    color_face_data = []   # [(color, fset, area), ...]

    for color, path_groups in color_paths.items():
        all_pts_3d  = []
        all_tris    = []
        pt_key_map  = {}   # rounded (x, y) SVG → index into all_pts_3d

        for subpath_group in path_groups:
            triangles_2d = triangulate_path(subpath_group)
            for tri in triangles_2d:
                face_idx = []
                for x2d, y2d in tri:
                    key = (round(x2d, 3), round(y2d, 3))
                    if key not in pt_key_map:
                        pt_key_map[key] = len(all_pts_3d)
                        all_pts_3d.append(svg_to_3d(x2d, y2d, vb, w, h, z=0.0))
                    face_idx.append(pt_key_map[key] + 1)   # 1-based
                all_tris.append(tuple(face_idx))

        if all_pts_3d and all_tris:
            area = sum(
                abs(
                    (all_pts_3d[t[0]-1][0] - all_pts_3d[t[1]-1][0]) *
                    (all_pts_3d[t[0]-1][1] - all_pts_3d[t[2]-1][1]) -
                    (all_pts_3d[t[0]-1][0] - all_pts_3d[t[2]-1][0]) *
                    (all_pts_3d[t[0]-1][1] - all_pts_3d[t[1]-1][1])
                ) / 2.0
                for t in all_tris
            )
            color_face_data.append((color, all_pts_3d, all_tris, area))

    if not color_face_data:
        print(f"  No triangles generated from SVG")
        return None

    # Background = largest-area color; label everything else 'graphic'
    bg_color = max(color_face_data, key=lambda x: x[2])[0]

    items = []
    for color, pts_3d, tris, _ in color_face_data:
        if color != bg_color:
            pts_3d = [(x, y, z + GRAPHIC_Z_OFFSET) for x, y, z in pts_3d]
        fset  = build_face_set(model, pts_3d, tris)
        style = get_or_create_style(model, style_cache, color)
        label = 'background' if color == bg_color else 'graphic'
        model.createIfcStyledItem(fset, [style], label)
        items.append(fset)

    # ── Shape representation & RepresentationMap ──────────────────────────
    shape_rep = model.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier='Body',
        RepresentationType='Tessellation',
        Items=items,
    )
    origin = model.createIfcAxis2Placement3D(
        Location=model.createIfcCartesianPoint((0., 0., 0.)),
        Axis=model.createIfcDirection((0., -1., 0.)),
        RefDirection=model.createIfcDirection((1., 0., 0.)),
    )
    rep_map = model.createIfcRepresentationMap(
        MappingOrigin=origin, MappedRepresentation=shape_rep
    )

    # ── IfcSignType ────────────────────────────────────────────────────────
    sign_type = model.createIfcSignType(
        GlobalId=ifcopenshell.guid.new(),
        Name=name,
        Description=name,
        PredefinedType='PICTORAL',
        RepresentationMaps=[rep_map],
    )

    area = abs(poly_signed_area_2d(outline))
    pset_base = ifcopenshell.api.pset.add_pset(
        model, product=sign_type, name='Qset_SignBaseQuantities'
    )
    ifcopenshell.api.pset.edit_pset(
        model, pset=pset_base, properties={'Height': h, 'Width': w}
    )
    pset_pic = ifcopenshell.api.pset.add_pset(
        model, product=sign_type, name='Qset_PictorialSignQuantities'
    )
    ifcopenshell.api.pset.edit_pset(
        model, pset=pset_pic, properties={'Area': area, 'SignArea': area}
    )

    return sign_type

# ── walk SignFaces directory ───────────────────────────────────────────────

def process_signs(root_folder, model, body_ctx, style_cache):
    sign_types = []
    for dirpath, _, filenames in os.walk(root_folder):
        shape_name = os.path.basename(dirpath)
        for fname in sorted(filenames):
            if not fname.lower().endswith('.svg'):
                continue
            full = os.path.join(dirpath, fname)
            st = create_signtype(full, model, body_ctx, shape_name, style_cache)
            if st:
                sign_types.append(st)
    return sign_types

# ── IFC file builder ───────────────────────────────────────────────────────

def create_ifc():
    model = ifcopenshell.file(schema='IFC4X3')

    project = model.createIfcProject(
        GlobalId=ifcopenshell.guid.new(), Name='Traffic Sign Library'
    )

    length_unit = ifcopenshell.api.unit.add_conversion_based_unit(model, name='inch')
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit])

    geo_ctx  = ifcopenshell.api.context.add_context(model, context_type='Model')
    body_ctx = ifcopenshell.api.context.add_context(
        model, context_type='Model', context_identifier='Body',
        target_view='MODEL_VIEW', parent=geo_ctx,
    )

    sign_lib = model.createIfcProjectLibrary(
        GlobalId=ifcopenshell.guid.new(),
        Name='Traffic Signs',
        Description='Based on Standard Highway Signs, 2004 Edition',
        RepresentationContexts=[body_ctx],
    )
    model.createIfcRelDeclares(
        GlobalId=ifcopenshell.guid.new(),
        RelatingContext=project,
        RelatedDefinitions=[sign_lib],
    )

    style_cache = {}
    sign_types  = process_signs(SVG_ROOT, model, body_ctx, style_cache)

    model.createIfcRelDeclares(
        GlobalId=ifcopenshell.guid.new(),
        RelatingContext=sign_lib,
        RelatedDefinitions=sign_types,
    )

    print(f'\nWriting {OUT_FILE}')
    model.write(OUT_FILE)

    if no_dimensions:
        print('\nSigns without dimensions (skipped):')
        for v in no_dimensions:
            print(f'  {v}')


if __name__ == '__main__':
    create_ifc()
