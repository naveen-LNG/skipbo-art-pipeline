# /// script
# dependencies = ["pillow"]
# ///
"""One image on a 0.05 grid (labels every 0.1), optionally cropped to a box of fractions, for reading points by eye.
  uv run grid_image.py <in.png> <out.png> [x0 y0 x1 y1] [--size 1000]"""
import sys
from PIL import Image, ImageDraw
a = [x for x in sys.argv[1:] if not x.startswith("--")]
size = 1000
im = Image.open(a[0]).convert("RGBA")
bg = Image.new("RGBA", im.size, (205, 210, 220, 255)); bg.alpha_composite(im); im = bg
x0, y0, x1, y1 = (float(v) for v in a[2:6]) if len(a) >= 6 else (0, 0, 1, 1)
W, H = im.size
c = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
s = size / max(c.size); c = c.resize((int(c.width * s), int(c.height * s))).convert("RGB")
d = ImageDraw.Draw(c)
for k in range(0, 101):
    f = k / 100
    for (lo, hi, n, horiz) in ((x0, x1, c.width, False), (y0, y1, c.height, True)):
        if lo <= f <= hi and k % 5 == 0:
            p = (f - lo) / (hi - lo) * n
            col = (255, 0, 0) if k % 10 == 0 else (255, 160, 160)
            if horiz:
                d.line([0, p, c.width, p], fill=col); d.text((2, p + 1), f"{f:.2f}", fill=(0, 0, 160)) if k % 10 == 0 else None
            else:
                d.line([p, 0, p, c.height], fill=col); d.text((p + 2, 2), f"{f:.2f}", fill=(0, 0, 160)) if k % 10 == 0 else None
c.save(a[1]); print(a[1], c.size)
