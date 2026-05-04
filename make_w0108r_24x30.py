from pathlib import Path

base = Path(
    r"C:\Users\BriceR\OneDrive - Washington State Department of Transportation"
    r"\BIM for Infrastructure\Signs\MUTCD\Graphics\W01-08 Chevron Alignment"
)
src = base / "W01-08L Chevron Alignment 24x30.svg"
dst = base / "W01-08R Chevron Alignment 24x30.svg"

text = src.read_text(encoding="utf-8")

# Find the end of the <svg ...> opening tag
svg_tag_start = text.index("<svg ")
svg_open_end = text.index(">", svg_tag_start) + 1
svg_close_start = text.rindex("</svg>")

header = text[:svg_open_end]
content = text[svg_open_end:svg_close_start]
footer = text[svg_close_start:]

# viewBox width is 1728; mirror = translate(width,0) scale(-1,1)
mirror = 'translate(1728, 0) scale(-1, 1)'
text = header + f'\n  <g transform="{mirror}">' + content + "  </g>\n" + footer

dst.write_text(text, encoding="utf-8")
print(f"Written: {dst}")

# Validate
import xml.etree.ElementTree as ET
try:
    ET.parse(dst)
    print("Valid XML")
except ET.ParseError as e:
    print(f"Parse error: {e}")
