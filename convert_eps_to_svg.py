"""
convert_eps_to_svg.py

For each SVG in SignFaces/, finds a matching EPS in the MUTCD source
directories and converts it to SVG using a two-step process:
  1. Ghostscript: EPS → single-page PDF (-dEPSCrop clips to the bounding box)
  2. Inkscape:    PDF → SVG

EPS is preferred over PDF because PDFs from the MUTCD source often contain
multiple pages (layouts, title blocks, etc.) while EPS files are single
isolated sign faces.

Two-pass lookup per SVG (case-insensitive):
  1. Dimension-less match: find "{base_name}.eps" (no size in name)
  2. Exact-name match:     find "{base_name} {dim}.eps"
  PDF is used as a fallback when no EPS is found.

Usage:
    python convert_eps_to_svg.py            # dry run – shows what would happen
    python convert_eps_to_svg.py --execute  # converts files in place
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────

SIGN_FACES = Path(__file__).parent / "SignFaces"

SOURCE_ROOTS = [
    Path(r"C:\Users\BriceR\OneDrive - Washington State Department of Transportation"
         r"\BIM for Infrastructure\Signs\MUTCD\Signs"),
    Path(r"C:\Users\BriceR\OneDrive - Washington State Department of Transportation"
         r"\BIM for Infrastructure\Signs\MUTCD\Graphics"),
]

INKSCAPE  = Path(r"C:\Program Files\Inkscape\bin\inkscape.exe")
GHOSTSCRIPT = Path(r"C:\Program Files\gs\gs10.07.0\bin\gswin64c.exe")

# ── helpers ────────────────────────────────────────────────────────────────

DIM_RE = re.compile(r"^(.*?)\s*(\d+(?:\.\d+)?(?:[xX]\d+(?:\.\d+)?){1,2})", re.IGNORECASE)


def build_source_indices(roots):
    """
    Index EPS and PDF files under each root into two dicts keyed by lowercased
    stem.  EPS is preferred over PDF for the same stem — EPS files are single
    isolated sign faces while PDFs may contain multiple pages.
      no_dim   – stems without a dimension suffix
      with_dim – stems with  a dimension suffix
    """
    no_dim   = {}
    with_dim = {}
    for root in roots:
        if not root.exists():
            print(f"WARNING: source root not found: {root}")
            continue
        for src in root.rglob("*"):
            if src.suffix.lower() not in ('.eps', '.pdf'):
                continue
            key    = src.stem.lower()
            target = with_dim if DIM_RE.match(src.stem) else no_dim
            existing = target.get(key)
            if existing is None:
                target[key] = src
            elif existing.suffix.lower() == '.pdf' and src.suffix.lower() == '.eps':
                target[key] = src   # upgrade PDF → EPS
    return no_dim, with_dim


def convert(src_path, dest_svg):
    """
    Convert one EPS or PDF source file to SVG.
    For EPS: Ghostscript crops to bounding box → temp PDF, then Inkscape → SVG.
    For PDF: Inkscape → SVG directly (first page only).
    Returns (returncode, stderr_text).
    """
    if src_path.suffix.lower() == '.eps':
        tmp_fd, tmp_pdf = tempfile.mkstemp(suffix='.pdf')
        os.close(tmp_fd)
        try:
            r1 = subprocess.run(
                [str(GHOSTSCRIPT),
                 '-dNOPAUSE', '-dBATCH', '-dEPSCrop',
                 '-sDEVICE=pdfwrite',
                 f'-sOutputFile={tmp_pdf}',
                 str(src_path)],
                capture_output=True, text=True, timeout=60,
            )
            if r1.returncode != 0:
                return r1.returncode, r1.stderr.strip()
            r2 = subprocess.run(
                [str(INKSCAPE), tmp_pdf,
                 '--export-type=svg',
                 f'--export-filename={dest_svg}'],
                capture_output=True, text=True, timeout=60,
            )
            return r2.returncode, r2.stderr.strip()
        finally:
            if os.path.exists(tmp_pdf):
                os.unlink(tmp_pdf)
    else:
        # PDF fallback — first page only
        r = subprocess.run(
            [str(INKSCAPE), str(src_path),
             '--export-type=svg',
             '--pdf-page=1',
             f'--export-filename={dest_svg}'],
            capture_output=True, text=True, timeout=60,
        )
        return r.returncode, r.stderr.strip()


# ── main ───────────────────────────────────────────────────────────────────

def main():
    dry_run = "--execute" not in sys.argv

    for exe, name in [(INKSCAPE, 'Inkscape'), (GHOSTSCRIPT, 'Ghostscript')]:
        if not exe.exists():
            print(f"ERROR: {name} not found at {exe}")
            sys.exit(1)

    if dry_run:
        print("DRY RUN — pass --execute to actually convert files\n")

    no_dim, with_dim = build_source_indices(SOURCE_ROOTS)
    print(f"Indexed {len(no_dim)} dimension-less and "
          f"{len(with_dim)} dimension-bearing source file(s).\n")

    svgs = sorted(SIGN_FACES.rglob("*.svg"))

    converted = skipped = not_found = errors = 0

    for svg_path in svgs:
        m = DIM_RE.match(svg_path.stem)
        if not m:
            print(f"SKIP (no size in name): {svg_path.name}")
            skipped += 1
            continue

        base_name, dim = m.group(1).strip(), m.group(2)

        # Pass 1: dimension-less source
        source = no_dim.get(base_name.lower())
        if source is not None:
            label = f"{source.name}  (dimension-less)"
        else:
            # Pass 2: dimension-bearing source
            full_key = f"{base_name} {dim}".lower()
            source = with_dim.get(full_key)
            if source is not None:
                label = f"{source.name}  (dimension-bearing)"

        if source is None:
            print(f"NOT FOUND: '{base_name} {dim}'")
            not_found += 1
            continue

        if dry_run:
            print(f"WOULD CONVERT: {label}")
            print(f"           TO: {svg_path.relative_to(SIGN_FACES)}")
            converted += 1
        else:
            rc, stderr = convert(source, svg_path)
            if rc != 0:
                print(f"ERROR: {svg_path.name}")
                if stderr:
                    print(f"  {stderr[:200]}")
                errors += 1
            else:
                print(f"CONVERTED: {svg_path.name}  <-  {source.name}")
                converted += 1

    verb = "Would convert" if dry_run else "Converted"
    print(f"\n{verb}: {converted}  |  Not found: {not_found}  "
          f"|  Skipped: {skipped}  |  Errors: {errors}")


if __name__ == "__main__":
    main()
