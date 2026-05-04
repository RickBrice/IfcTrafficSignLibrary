"""
For each PNG listed in missing_svg_list.txt, finds a matching SVG in the
MUTCD Signs/Graphics source directories that is missing the NNNxMMM size
suffix, then copies it to the same folder as the PNG with the size added.

Two-pass lookup per PNG:
  1. Dimension-less match: find "{base_name}.svg" (no size in name), copy as
     "{base_name} {dim}.svg" next to the PNG.
  2. Exact-name match: if pass 1 fails, look for "{base_name} {dim}.svg"
     already named correctly; copy it as-is next to the PNG.

Usage:
    python copy_missing_svgs.py           # dry run (shows what would be copied)
    python copy_missing_svgs.py --execute  # actually copies the files
"""

import re
import shutil
import sys
from pathlib import Path

MISSING_LIST = Path(__file__).parent / "missing_svg_list.txt"

SOURCE_ROOTS = [
    Path(r"C:\Users\BriceR\OneDrive - Washington State Department of Transportation"
         r"\BIM for Infrastructure\Signs\MUTCD\Signs"),
    Path(r"C:\Users\BriceR\OneDrive - Washington State Department of Transportation"
         r"\BIM for Infrastructure\Signs\MUTCD\Graphics"),
]

DIM_RE = re.compile(r"^(.+)\s+(\d+(?:\.\d+)?x\d+(?:\.\d+)?)$", re.IGNORECASE)


def build_svg_indices(roots: list[Path]) -> tuple[dict[str, Path], dict[str, Path]]:
    """
    Returns two dicts:
      no_dim_index  — SVG stem has no size suffix  → full path
      with_dim_index — SVG stem has a size suffix   → full path
    """
    no_dim: dict[str, Path] = {}
    with_dim: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            print(f"WARNING: source root not found: {root}")
            continue
        for svg in root.rglob("*.svg"):
            if DIM_RE.match(svg.stem):
                with_dim[svg.stem] = svg
            else:
                key = svg.stem
                if key in no_dim:
                    print(f"WARNING: duplicate dimension-less SVG '{key}'")
                    print(f"  existing : {no_dim[key]}")
                    print(f"  duplicate: {svg}")
                else:
                    no_dim[key] = svg
    return no_dim, with_dim


def main() -> None:
    dry_run = "--execute" not in sys.argv

    if dry_run:
        print("DRY RUN — pass --execute to actually copy files\n")

    no_dim_index, with_dim_index = build_svg_indices(SOURCE_ROOTS)
    print(f"Indexed {len(no_dim_index)} dimension-less and "
          f"{len(with_dim_index)} dimension-bearing SVG(s).\n")

    missing_lines = MISSING_LIST.read_text(encoding="utf-8").splitlines()
    png_paths = [Path(line.strip()) for line in missing_lines if line.strip()]

    copied = 0
    not_found = 0

    for png_path in png_paths:
        png_stem = png_path.stem  # e.g. "W19-03 FREEWAY ENDS 48x48"
        m = DIM_RE.match(png_stem)
        if not m:
            print(f"SKIP (no size in name): {png_path.name}")
            continue

        base_name, dim = m.group(1), m.group(2)
        dest_dir = png_path.parent
        dest_svg = dest_dir / f"{base_name} {dim}.svg"

        # Pass 1: dimension-less SVG → copy with size added to name
        svg_source = no_dim_index.get(base_name)
        if svg_source is not None:
            label = f"{svg_source.name}  (dimension-less, renamed)"
        else:
            # Pass 2: SVG already has the right full name (size included)
            full_stem = f"{base_name} {dim}"
            svg_source = with_dim_index.get(full_stem)
            if svg_source is not None:
                label = f"{svg_source.name}  (already correctly named, copied)"

        if svg_source is None:
            print(f"NOT FOUND: '{base_name} {dim}.svg'  (needed for {png_path.name})")
            not_found += 1
            continue

        if dry_run:
            print(f"WOULD COPY: {label}")
            print(f"        TO: {dest_svg}")
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(svg_source, dest_svg)
            print(f"COPIED: {dest_svg.name}  <-  {svg_source}")
        copied += 1

    print(f"\n{'Would copy' if dry_run else 'Copied'}: {copied}  |  Not found: {not_found}")


if __name__ == "__main__":
    main()
