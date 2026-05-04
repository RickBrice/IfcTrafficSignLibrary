import re
from pathlib import Path

base = Path(
    r"C:\Users\BriceR\OneDrive - Washington State Department of Transportation"
    r"\BIM for Infrastructure\Signs\MUTCD\Graphics\R04-02 Pass With Care"
)
src = base / "R04-02 Pass With Care 24x30.svg"
dst = base / "R04-02 Pass With Care 48x60.svg"

text = src.read_text(encoding="utf-8")

# Scale viewBox from 24x30 (1728x2160) to 48x60 (3456x4320)
text = text.replace('viewBox="0 0 1728 2160"', 'viewBox="0 0 3456 4320"', 1)

# Wrap all SVG content in a scale(2) group
# Find the end of the <svg ...> opening tag (not the XML declaration)
svg_tag_start = text.index("<svg ")
svg_open_end = text.index(">", svg_tag_start) + 1
svg_close_start = text.rindex("</svg>")
header = text[:svg_open_end]
content = text[svg_open_end:svg_close_start]
footer = text[svg_close_start:]

text = header + '\n  <g transform="scale(2)">' + content + "  </g>\n" + footer

dst.write_text(text, encoding="utf-8")
print(f"Written: {dst}")

check = dst.read_text(encoding="utf-8")
vb = re.search(r'viewBox="[^"]+"', check).group()
tr = re.search(r'transform="[^"]+"', check).group()
print(f"viewBox : {vb}")
print(f"transform: {tr}")
