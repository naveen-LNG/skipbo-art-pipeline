# /// script
# dependencies = ["pillow"]
# ///
"""One image on a 0.05 grid (labels every 0.1), for reading master points by eye. Optional crop box in 0..1.
  uv run tools/grid_image.py <img> <out.png> [x0 y0 x1 y1] [--w 1400]"""
import sys
from PIL import Image, ImageDraw
a = sys.argv[1:]; im = Image.open(a[0]).convert("RGB"); W, H = im.size
box = [float(v) for v in a[2:6]] if len(a) >= 6 else [0, 0, 1, 1]
c = im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))
s = 1400 / max(c.size); c = c.resize((int(c.width * s), int(c.height * s))); d = ImageDraw.Draw(c)
def X(v): return (v - box[0]) * W * s
def Y(v): return (v - box[1]) * H * s
k = 0
while k <= 100:
    v = k / 100
    col = (255, 0, 0) if k % 10 == 0 else (255, 180, 180)
    if box[0] <= v <= box[2]:
        d.line([X(v), 0, X(v), c.height], fill=col)
        if k % 10 == 0: d.text((X(v) + 2, 2), f"{v:.1f}", fill=(200, 0, 0))
    if box[1] <= v <= box[3]:
        d.line([0, Y(v), c.width, Y(v)], fill=col)
        if k % 10 == 0: d.text((2, Y(v) + 2), f"{v:.1f}", fill=(200, 0, 0))
    k += 5 if (box[2] - box[0]) > 0.4 else 1
c.save(a[1]); print(a[1])
