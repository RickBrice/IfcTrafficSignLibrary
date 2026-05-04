import ifcopenshell
import ifcopenshell.api.context
import ifcopenshell.api.unit
import ifcopenshell.api.georeference
import math
import os
import re
from platformdirs import user_desktop_path

sign_thickness = 1.

image_root = "../SignFaces/"
uri_root = "https://raw.githubusercontent.com/RickBrice/IfcTrafficSignLibrary/main/SignFaces/"

no_dimensions = []

def get_root_filename(path):
    """
    Returns the filename without its extension.
    Example: '/path/to/image_12x34.png' → 'image_12x34'
    """
    base = os.path.basename(path)          # image_12x34.png
    root, _ = os.path.splitext(base)       # ('image_12x34', '.png')
    return root

def get_extensions(path):
    """
    Returns the filename without its extension.
    Example: '/path/to/image_12x34.png' → 'image_12x34'
    """
    base = os.path.basename(path)          # image_12x34.png
    _, ext = os.path.splitext(base)       # ('image_12x34', '.png')
    return ext

def extract_mutcd_code(filename: str) -> str:
    """
    Extracts the leading code from a filename.
    The code is assumed to be the first token before the first space.
    """
    return filename.split(" ", 1)[0]

def generate_polygon(width,height,sides,start_angle,dim):
    angle_step = 2*math.pi/sides
    X = 0.5*width/math.cos(math.pi/sides)
    Y = 0.5*height/math.cos(math.pi/sides)
    if dim == 2:
        points = [
            (
                X*math.cos(start_angle + i*angle_step),
                Y*math.sin(start_angle + i*angle_step)
            )
            for i in range(sides)
        ]

        points.insert(0,(0.,0.))
    else:
        points = [
            (
                X*math.cos(start_angle + i*angle_step),
                Y*math.sin(start_angle + i*angle_step),
                0.
            )
            for i in range(sides)
        ]

        points.insert(0,(0.,0.,0.))

    return points

from typing import List, Tuple

def polygon_area(points):
    n = len(points)
    area_sum = 0.0
    for i in range(n):
        x1, y1, z1 = points[i]
        x2, y2, z2 = points[(i + 1) % n]  # Wrap around to first point
        area_sum += (x1 * y2) - (x2 * y1)

    return area_sum / 2.0


def normalize_image_points(points):
    min_x = min(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_x = max(p[0] for p in points)
    max_y = max(p[1] for p in points)
    dx = max_x - min_x
    dy = max_y - min_y
    
    image_points = []
    for p in points:
        ip = ((p[0]-min_x)/dx,(p[1]-min_y)/dy)
        image_points.append(ip)
        
    return image_points
    
import re

no_dimensions = []

def extract_dimensions(filename):
    """
    Extracts width and height from patterns like '12.5x34', '5x9.2', or '120.75x300.1'.
    Returns (width, height) as floats, or None if no valid pattern is found.
    """
    # Matches integers or floats: 12, 12.5, .5, 0.75
    pattern = r'(\d+(?:\.\d+)?)[xX](\d+(?:\.\d+)?)'
    match = re.search(pattern, filename)

    if match:
        width = float(match.group(1))
        height = float(match.group(2))
        return width, height

    no_dimensions.append(filename)
    return None

def process_signs(root_folder,model,body_model_context):
    sign_types = []
    for dirpath, dirnames, filenames in os.walk(root_folder):
        folder_name = os.path.basename(dirpath)
        for filename in filenames:
            if filename.lower().endswith(".png"):
                full_path = os.path.join(dirpath, filename)
                
                sign_type = create_signtype(full_path,model,body_model_context,folder_name)
                
                if sign_type:
                    sign_types.append(sign_type)
    
    return sign_types

def append_backface_points(points,offset=-sign_thickness):
    npoints = len(points)
    
    p = (points[0][0],points[0][1],points[0][2] + offset)
    points.append(p)
    
    for i in reversed(range(1,npoints)):
        p = (points[i][0],points[i][1],points[i][2] + offset)
        points.append(p)
        

def generate_indicies(points):
    indices = []
    npoints = int(len(points)/2)
    
    # front face
    for i in range(2,npoints):
        indices.append((1,i,i+1))
        
    indices.append((1,npoints,2))
    
    # back face
    for i in range(npoints+2,len(points)):
        indices.append((npoints+1,i+1,i))
        
    indices.append((npoints+1,npoints+2,len(points)))

    # sides
    for i in range(0,npoints-2):
        indices.append((2+i,len(points)-i,len(points)-1-i))
        indices.append((2+i,len(points)-1-i,3+i))
        
    indices.append((npoints,npoints+2,len(points)))
    indices.append((npoints,len(points),2))
    
    return indices

def handle_rectangle(w,h):
    sign_points = generate_polygon(w,h,4,math.pi/4,3)
    image_points = normalize_image_points(sign_points)
    append_backface_points(sign_points)
    indices = generate_indicies(sign_points)
    return image_points, sign_points, indices
    

def handle_triangle(w,h):
    sign_points = generate_polygon(w,h/math.cos(math.pi/6),3,math.pi/6,3)
    image_points = normalize_image_points(sign_points)
    append_backface_points(sign_points)
    indices = generate_indicies(sign_points)
    return image_points, sign_points, indices

def handle_octagon(w,h):
    sign_points = generate_polygon(w,h,8,math.pi/8.,3)
    image_points = normalize_image_points(sign_points)
    append_backface_points(sign_points)
    indices = generate_indicies(sign_points)
    return image_points, sign_points, indices

def handle_diamond(w,h):
    sign_points = generate_polygon(w,h,4,0.,3)
    image_points = normalize_image_points(sign_points)
    append_backface_points(sign_points)
    indices = generate_indicies(sign_points)
    return image_points, sign_points, indices

def handle_pentagon(w,h):
    sign_points = [(0.,0.,0.), (w/2.,-h/2.,0.),(w/2.,0.,0.),(0.,h/2.,0.),(-w/2.,0.,0.),(-w/2.,-h/2.,0.)]
    image_points = normalize_image_points(sign_points)
    append_backface_points(sign_points)
    indices = generate_indicies(sign_points)
    return image_points, sign_points, indices

def handle_crossbuck(a,b):
    angle = math.pi/4.
    p0 = (0.,0.,0.)
    p1 = (0.,-0.5*b/math.sin(angle),0.)
    p2 = (0.5*(a-b)*math.cos(angle), -0.5*b/math.sin(angle) - 0.5*(a-b)*math.sin(angle),0.)
    p3 = (p2[0] + b*math.cos(angle), p2[1]+b*math.sin(angle), 0.)
    p4 = (0.5*b/math.cos(angle), 0., 0.)
    p5 = (p4[0]+0.5*(a-b)*math.cos(angle), 0.5*(a-b)*math.sin(angle), 0.)
    p6 = (p5[0]-b*math.cos(angle), p5[1] + b*math.sin(angle), 0.)
    p7 = (0., 0.5*b/math.sin(angle), 0.)
    p8 = (-p6[0], p6[1], p6[2])
    p9 = (-p5[0], p5[1], p5[2])
    p10 = (-p4[0], p4[1], p4[2])
    p11 = (-p3[0], p3[1], p3[2])
    p12 = (-p2[0], p2[1], p2[2])
    
    sign_points = [p0,p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p12]
    image_points = normalize_image_points(sign_points)
    append_backface_points(sign_points)
    indices = generate_indicies(sign_points)
    return image_points, sign_points, indices
        
SHAPE_HANDLERS = {
    "Rectangle": handle_rectangle,
    "Triangle": handle_triangle,
    "Octagon": handle_octagon,
    "Diamond": handle_diamond,
    "Pentagon": handle_pentagon,
    "CrossBuck": handle_crossbuck
}

def create_signtype(file_path,model,body_model_context,shape_name):
    #
    # create IfcSignType that acts as a predefined cell
    #

    name = get_root_filename(file_path)
    code = extract_mutcd_code(name)
    ext = get_extensions(file_path)
    
    dims = extract_dimensions(file_path)
    if dims == None:
        return None
        
    w,h = dims

    sign_points = []
    image_points = []
    indices = []
    
    
    if shape_name in SHAPE_HANDLERS:
        handler = SHAPE_HANDLERS[shape_name]
        print(f"Processing {get_root_filename(file_path)}")
        image_points,sign_points,indices = handler(w,h)
    else:
        print(f"No handler for folder '{shape_name}', skipping {file_path}")
        return None
    
    point_list = model.createIfcCartesianPointList3d(CoordList=sign_points)

    sign_panel = model.createIfcTriangulatedFaceSet(Coordinates=point_list,CoordIndex=indices)
    shape_representation = model.createIfcShapeRepresentation(ContextOfItems=body_model_context,RepresentationIdentifier="Body",RepresentationType="Tessellation",Items=[sign_panel])

    # define the sign face image
    image_texture = model.createIfcImageTexture(
        RepeatS = False,
        RepeatT = False,
        Mode = "DIFFUSE",
        URLReference = uri_root + shape_name + "/" + name + ext
    )

    texture_vertex_list = model.createIfcTextureVertexList(TexCoordsList=image_points)
    indexed_triangule_texture_map = model.createIfcIndexedTriangleTextureMap(
        Maps=[image_texture],
        MappedTo=sign_panel,
        TexCoords=texture_vertex_list,
        TexCoordIndex=indices[:len(image_points)-1]
    )

    shading = model.createIfcSurfaceStyleRendering(
        SurfaceColour = model.createIfcColourRgb(Red=0.,Green=0.,Blue=0.),
        ReflectanceMethod="NOTDEFINED"
    )

    surface_with_texture = model.createIfcSurfaceStyleWithTextures(
        Textures=[image_texture]
    )
        
    surface_style = model.createIfcSurfaceStyle(
        Name=name,
        Side="POSITIVE",
        Styles=[shading,surface_with_texture]
    )

    styled_item = model.createIfcStyledItem(
        Item=sign_panel,
        Styles=[surface_style]
    )

    # the geometric representation is reusable and is placed in an IfcRepresentationMap. Use (0,0,0) as a simple origin
    origin =  model.createIfcAxis2Placement3D(Location=model.createIfcCartesianPoint((0.,0.,0.)),Axis=model.createIfcDirection((0.,-1.,0.)),RefDirection=model.createIfcDirection((1.,0.,0.)))
    rep_map = model.createIfcRepresentationMap(MappingOrigin=origin,MappedRepresentation=shape_representation)

    # create the IfcSignType
    # Per https://ifc43-docs.standards.buildingsmart.org/IFC/RELEASE/IFC4x3/HTML/lexical/Pset_SignCommon.htm Pset_SignCommon.Reference is deprecated and the refereince ID,
    # which is the MUTCD code in this case, the Name attribute of the relating type is to be used. The relating type is the IfcSignType. For this reason,
    # Name=code. However, code is not descriptive, so for stop signs there will be three R01-01 entires which isn't very helpful. For this reason, the name is used.
    sign_type = model.createIfcSignType(GlobalId=ifcopenshell.guid.new(),Name=name,Description=name,PredefinedType="PICTORAL",RepresentationMaps=[rep_map])
    
    # add properties to the sign type that are common for all instances of this type
    sign_base_quantities = ifcopenshell.api.pset.add_pset(model,product=sign_type,name="Qset_SignBaseQuantities")
    ifcopenshell.api.pset.edit_pset(model,pset=sign_base_quantities,properties={"Height":h})
    ifcopenshell.api.pset.edit_pset(model,pset=sign_base_quantities,properties={"Width":w})

    area = polygon_area(sign_points[1:int(len(sign_points)/2.)])
    pictorial_sign_quantities = ifcopenshell.api.pset.add_pset(model,product=sign_type,name="Qset_PictorialSignQuantities")
    ifcopenshell.api.pset.edit_pset(model,pset=pictorial_sign_quantities,properties={"Area":area})
    ifcopenshell.api.pset.edit_pset(model,pset=pictorial_sign_quantities,properties={"SignArea":area})
    
    return sign_type


def create_ifc():
    # create IFC model
    model = ifcopenshell.file(schema="IFC4X3")

    # basic model setup for project and site
    project = model.createIfcProject(GlobalId=ifcopenshell.guid.new(),Name="Traffic Sign Library")

    # set up system of units (must be done after IfcProject is created)
    length_unit = ifcopenshell.api.unit.add_conversion_based_unit(model,name="inch")
    ifcopenshell.api.unit.assign_unit(model,units=[length_unit])

    # set up geometric representation context
    geometric_representation_context = ifcopenshell.api.context.add_context(model,context_type="Model")
    body_model_context = ifcopenshell.api.context.add_context(model,context_type="Model",context_identifier="Body",target_view="MODEL_VIEW",parent=geometric_representation_context)

    # create the sign library
    sign_library = model.createIfcProjectLibrary(GlobalId=ifcopenshell.guid.new(),Name="Traffic Signs", Description="Based on Standard Highway Signs, 2004 Edition", RepresentationContexts=[body_model_context])

    # relate the library to the project
    model.createIfcRelDeclares(GlobalId=ifcopenshell.guid.new(),RelatingContext=project,RelatedDefinitions=[sign_library]) 
    
    # generate the IfcSignType entities
    sign_types = process_signs(image_root,model,body_model_context)
    
    # relate sign types to the library
    model.createIfcRelDeclares(GlobalId=ifcopenshell.guid.new(),RelatingContext=sign_library,RelatedDefinitions=sign_types) 

    output_file = "..\\IfcTrafficSignLibrary_TextureMapping.ifc"
    print(output_file)
    model.write(output_file)

    # lists of sign file names that did not contain encoded dimentions
    # and thus did not generate an IfcSignType    
    if len(no_dimensions) != 0:
        print("")
        print("Signs without dimensions")
        for v in no_dimensions:
            print(v)
    


if __name__ == "__main__":
    create_ifc()
