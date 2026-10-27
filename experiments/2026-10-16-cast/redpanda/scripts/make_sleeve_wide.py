# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""The master's lower sleeves are fatter than the sleeves-pair drawing (rig doubt sleeve_too_thin, master / drawing
1.32 on the lower half both sides; a first ramp 0.60-0.85 at 1.32 left 1.22-1.26, since the fit samples 25-45% below the elbow; the width fit only ever narrows), so the cuff came out narrower than the mitten.
Widen each drawing across, tapered (the beaver's make_sleeve_wide.py): unchanged above the elbow (0.58), ramping to K
at the cuff, about each row's own centre (these sleeves bend, so the column centre moves down the sleeve).
Writes runs/redpanda-sleeves-wide-parts/sleeve_00.png, sleeve_01.png and prints the moved annotation points."""
import glob
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parents[1]; K = 1.36; Y0, Y1 = 0.58, 0.76
PTS = {"00": {"shoulder": (0.38, 0.17), "elbow": (0.65, 0.58), "wrist": (0.60, 0.965)},
       "01": {"shoulder": (0.58, 0.17), "elbow": (0.39, 0.58), "wrist": (0.50, 0.965)}}
d = HERE / "runs/redpanda-sleeves-wide-parts"; d.mkdir(parents=True, exist_ok=True); allpts = {}
for n, pts in PTS.items():
    im = np.asarray(Image.open(glob.glob(str(HERE / f"runs/redpanda-sleeves-parts/*_{n}.png"))[0]).convert("RGBA")).astype(np.float32)
    h, w, _ = im.shape; W = int(round(w * K)); pad = (W - w) / 2
    out = np.zeros((h, W, 4), np.float32); xs = np.arange(W) + 0.5
    cen = {}
    for y in range(h):
        k = 1 + (K - 1) * float(np.clip((y / h - Y0) / (Y1 - Y0), 0, 1))
        op = np.nonzero(im[y, :, 3] > 128)[0]
        c = (op.min() + op.max() + 1) / 2 if len(op) else w / 2
        cen[y] = c
        src = (xs - pad - c) / k + c - 0.5
        i0 = np.clip(np.floor(src).astype(int), 0, w - 1); i1 = np.clip(i0 + 1, 0, w - 1); f = (src - np.floor(src))[:, None]
        row = im[y, i0] * (1 - f) + im[y, i1] * f
        row[(src < -0.5) | (src > w - 0.5)] = 0
        out[y] = row
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(d / f"sleeve_{n}.png")
    moved = {}
    for name, (x, y) in pts.items():
        yy = min(h - 1, int(y * h)); k = 1 + (K - 1) * float(np.clip((y - Y0) / (Y1 - Y0), 0, 1))
        moved[name] = (round((pad + cen[yy] + (x * w - cen[yy]) * k) / W, 3), y)
    print(n, moved); allpts[n] = {k: [float(v[0]), v[1]] for k, v in moved.items()}
import json; (d / "points.json").write_text(json.dumps(allpts))
