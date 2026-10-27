# /// script
# dependencies = ["pillow"]
# ///
"""Each split piece on a 0.1 grid (labels every 0.2), for reading rough annotation points by eye.
  uv run grid_pieces.py <split dir> <out.png> [NN,NN,...]"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
fs = sorted(Path(sys.argv[1]).glob("*_[0-9][0-9].png"))
if len(sys.argv) > 3:
    keep = sys.argv[3].split(","); fs = [f for f in fs if f.stem[-2:] in keep]
T = 300; cols = 4
sheet = Image.new("RGB", (cols * (T + 10), ((len(fs) + cols - 1) // cols) * (T + 24)), "white")
for i, f in enumerate(fs):
    im = Image.open(f).convert("RGBA"); s = T / max(im.size); im = im.resize((int(im.width * s), int(im.height * s)))
    c = Image.new("RGBA", im.size, (205, 210, 220, 255)); c.alpha_composite(im); d = ImageDraw.Draw(c)
    for k in range(1, 10):
        col = (255, 0, 0) if k % 2 == 0 else (255, 170, 170)
        d.line([im.width * k / 10, 0, im.width * k / 10, im.height], fill=col); d.line([0, im.height * k / 10, im.width, im.height * k / 10], fill=col)
    x, y = (i % cols) * (T + 10), (i // cols) * (T + 24)
    sheet.paste(c.convert("RGB"), (x, y + 20)); ImageDraw.Draw(sheet).text((x + 2, y + 4), f"{f.stem[-2:]}  {im.width}x{im.height}", fill="black")
sheet.save(sys.argv[2]); print(sys.argv[2])
