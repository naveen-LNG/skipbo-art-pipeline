# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Colour-class runs per row of an image (x as 0..1): olive trousers, mustard jacket, brown boots/belt, dark hands.
  uv run measure_master.py <image> [rows ...]"""
import sys
import numpy as np
from PIL import Image
a = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(int); H, W, _ = a.shape
r, g, b = a[..., 0], a[..., 1], a[..., 2]
M = {"olive": (g > 95) & (r < 155) & (b < 105) & (abs(r - g) < 22) & (g - b > 25),
     "must": (r > 165) & (g > 115) & (b < 115) & (r - g > 30) & (g - b > 50),
     "brown": (r > 95) & (r < 175) & (g > 55) & (g < 115) & (b < 85) & (r - g > 35),
     "dark": (r < 115) & (g < 70) & (b < 60)}
def runs(row):
    xs = np.nonzero(row)[0]
    if not len(xs): return "-"
    rr = [s for s in np.split(xs, np.nonzero(np.diff(xs) > 4)[0] + 1) if len(s) > 8]
    return " ".join(f"{s[0]/W:.3f}-{s[-1]/W:.3f}" for s in rr)
rows = [float(x) for x in sys.argv[2:]] or [0.55, 0.57, 0.58, 0.59, 0.60, 0.62, 0.65, 0.68, 0.70, 0.72, 0.75, 0.78, 0.79, 0.80, 0.81, 0.83, 0.86, 0.90, 0.92]
for y in rows:
    print(f"y={y:.3f} " + "  ".join(f"{k}:[{runs(m[int(y*H)])}]" for k, m in M.items()))
