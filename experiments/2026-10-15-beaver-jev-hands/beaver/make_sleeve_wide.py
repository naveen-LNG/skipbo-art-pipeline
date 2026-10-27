# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Round 6: the master's sleeves are fatter than the sleeve sheet's at the forearm and cuff (width fit measured master /
drawing = 1.32 on the lower half, and the fit only ever narrows), so the cuff came out narrower than the mitten and the
hand read as bigger than its joint. Widen the drawing across, tapered: unchanged above the elbow (a uniformly wider
sleeve, 1.3x or 1.45x, folded the mesh at hold_card's -103 deg elbow bend: fold-free only to -84 deg), then ramping to
K at the cuff. The mesh's width fit then narrows the lower half to the master's measured thickness.
Writes runs/beaver-sleeves3-parts/sleeve_01.png from beaver-sleeves2-parts/01 and prints the moved annotation x's."""
import glob
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).parent; K = 1.32; Y0, Y1 = 0.55, 0.78        # ramp from just below the elbow (0.52) to the cuff
im = np.asarray(Image.open(glob.glob(str(HERE / "runs/beaver-sleeves2-parts/*_01.png"))[0]).convert("RGBA")).astype(np.float32)
h, w, _ = im.shape; W = int(round(w * K)); out = np.zeros((h, W, 4), np.float32)
xs = np.arange(W) + 0.5
for y in range(h):
    k = 1 + (K - 1) * float(np.clip((y / h - Y0) / (Y1 - Y0), 0, 1))
    src = (xs - W / 2) / k + w / 2 - 0.5                               # inverse map about the centre line
    i0 = np.clip(np.floor(src).astype(int), 0, w - 1); i1 = np.clip(i0 + 1, 0, w - 1); f = (src - np.floor(src))[:, None]
    row = im[y, i0] * (1 - f) + im[y, i1] * f
    row[(src < -0.5) | (src > w - 0.5)] = 0
    out[y] = row
d = HERE / "runs/beaver-sleeves3-parts"; d.mkdir(parents=True, exist_ok=True)
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(d / "sleeve_01.png")


def moved(x, y):            # an annotation point of sleeves2/01 in the new image's fractions
    k = 1 + (K - 1) * float(np.clip((y - Y0) / (Y1 - Y0), 0, 1))
    return round(0.5 + (x - 0.5) * w * k / W, 3), y
print({n: moved(*p) for n, p in {"shoulder": (0.66, 0.08), "elbow": (0.59, 0.52), "wrist": (0.52, 0.97)}.items()})
