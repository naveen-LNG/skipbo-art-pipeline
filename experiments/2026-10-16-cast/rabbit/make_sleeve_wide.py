# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Round 1: the master's sleeves are much fatter than the sleeve sheet's below the elbow (rig width fit, master /
drawing: lower half 1.66 left, 1.74 right; upper 1.13), and the fit only ever narrows, so the rolled cuff came out
narrower than the paw. Widen each drawing across, tapered (the beaver's make_sleeve_wide.py): unchanged above the
elbow, ramping to K at the cuff; the mesh's width fit then narrows it back to the master's measured thickness.
Writes runs/rabbit-sleeves-wide-parts/sleeve_0N.png from rabbit-sleeves-parts/0N."""
import glob
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).parent; Y0, Y1 = 0.58, 0.86           # ramp from just below the elbow (0.57) to the cuff
K = {"00": 2.05, "01": 2.25}    # round 5: 1.70 / 1.78 still left the lower half 1.24 / 1.30 thinner than the master's
d = HERE / "runs/rabbit-sleeves-wide-parts"; d.mkdir(parents=True, exist_ok=True)
for n, k_max in K.items():
    im = np.asarray(Image.open(glob.glob(str(HERE / f"runs/rabbit-sleeves-parts/*_{n}.png"))[0]).convert("RGBA")).astype(np.float32)
    h, w, _ = im.shape; W = int(round(w * k_max)); out = np.zeros((h, W, 4), np.float32)
    xs = np.arange(W) + 0.5
    for y in range(h):
        k = 1 + (k_max - 1) * float(np.clip((y / h - Y0) / (Y1 - Y0), 0, 1))
        src = (xs - W / 2) / k + w / 2 - 0.5
        i0 = np.clip(np.floor(src).astype(int), 0, w - 1); i1 = np.clip(i0 + 1, 0, w - 1); f = (src - np.floor(src))[:, None]
        row = im[y, i0] * (1 - f) + im[y, i1] * f
        row[(src < -0.5) | (src > w - 0.5)] = 0
        out[y] = row
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(d / f"sleeve_{n}.png")
    print(n, w, "->", W)
