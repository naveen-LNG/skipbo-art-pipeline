# /// script
# dependencies = ["pillow"]
# ///
"""One image (or a crop of it) on a 0.05 grid with labels, for reading annotation points by eye.
  uv run tools/grid_image.py <img> <out.png> [x0 y0 x1 y1 (fractions)] [--size 1100]"""
import sys
from PIL import Image, ImageDraw
im = Image.open(sys.argv[1]).convert("RGBA"); W, H = im.size
box = [float(v) for v in sys.argv[3:7]] if len(sys.argv) >= 7 else [0, 0, 1, 1]
c = im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))
s = 1100 / max(c.size); c = c.resize((int(c.width * s), int(c.height * s)))
bg = Image.new("RGBA", c.size, (205, 210, 220, 255)); bg.alpha_composite(c); d = ImageDraw.Draw(bg)
step = 0.05 if box[2] - box[0] > 0.3 else 0.02
k = 0
while k <= 1.0001:
    for v, horiz in ((k, False), (k, True)):
        if horiz and box[1] <= v <= box[3]:
            y = (v - box[1]) * H * s; d.line([0, y, c.width, y], fill=(255, 0, 0) if round(v / step) % 2 == 0 else (255, 170, 170)); d.text((2, y + 1), f"{v:.2f}", fill="blue")
        if not horiz and box[0] <= v <= box[2]:
            x = (v - box[0]) * W * s; d.line([x, 0, x, c.height], fill=(255, 0, 0) if round(v / step) % 2 == 0 else (255, 170, 170)); d.text((x + 2, 2), f"{v:.2f}", fill="blue")
    k += step
bg.convert("RGB").save(sys.argv[2]); print(sys.argv[2])
