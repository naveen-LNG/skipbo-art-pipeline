# /// script
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""Ears cut from the master. The body sheet painted both ears as pointed horn-like shapes turned about 150 deg
(no turn within the matcher's +-90 deg fits the master's rounded ears), and the face sheet's heads have no ears.
Each ear = master foreground in the ear's box, minus the head's dome shrunk by BAND px: the band of head fur kept
under the ear's base is hidden behind the head at rest and covers the base when the ear turns (idle 2 deg, cheer 6 deg).
Dome = an ellipse read off the gridded master (centre 0.43/0.25, half-axes 0.22 W / 0.148 H).
Writes runs/redpanda-ears-parts/ear_00.png (character's right, picture left), ear_01.png (left) and prints the roots."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
HERE = Path(__file__).resolve().parents[1]
m = np.asarray(Image.open(HERE / "redpanda_master.png").convert("RGB")).astype(float); H, W, _ = m.shape
bg = np.median(np.concatenate([m[:20].reshape(-1, 3), m[:, :20].reshape(-1, 3)]), 0)
diff = np.abs(m - bg).max(-1)
near = diff < 16                                       # background: near-grey pixels connected to the image border
lab, _ = ndimage.label(near); border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
bgm = np.isin(lab, border[border > 0])                  # (the ears' pale rim shading is near-grey too: a plain
alpha = np.where(bgm, np.clip((diff - 4) / 12, 0, 1), 1.0)   # threshold speckled it)
yy, xx = np.mgrid[0:H, 0:W]
CX, CY, A, B = 0.43 * W, 0.25 * H, 0.22 * W, 0.148 * H
BAND = 34
dome = ((xx - CX) / A) ** 2 + ((yy - CY) / B) ** 2 <= 1
inner = ndimage.binary_erosion(dome, iterations=BAND)
out = HERE / "runs/redpanda-ears-parts"; out.mkdir(parents=True, exist_ok=True)
roots = {}
for i, (x0, x1) in enumerate(((0.19, 0.36), (0.50, 0.67))):
    box = np.zeros((H, W), bool); box[int(0.06 * H):int(0.22 * H), int(x0 * W):int(x1 * W)] = True
    keep = box & ~inner & (alpha > 0)
    lab, n = ndimage.label(keep & (alpha > 0.5)); sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    main = ndimage.binary_dilation(lab == (1 + int(np.argmax(sizes))), iterations=2) & keep
    ys, xs = np.nonzero(main); y0, y1, xa, xb = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgba = np.zeros((y1 - y0, xb - xa, 4), np.uint8)
    rgba[..., :3] = m[y0:y1, xa:xb].astype(np.uint8)
    rgba[..., 3] = (alpha[y0:y1, xa:xb] * main[y0:y1, xa:xb] * 255).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(out / f"ear_{i:02d}.png")
    band = main & dome                                    # the hidden base: the root sits in its middle
    by, bx = np.nonzero(band)
    roots[f"{i:02d}"] = [round((bx.mean() - xa) / (xb - xa), 3), round((by.mean() - y0) / (y1 - y0), 3)]
    print(f"ear_{i:02d}: box x {xa / W:.3f}-{xb / W:.3f} y {y0 / H:.3f}-{y1 / H:.3f}; root {roots[f'{i:02d}']}")
(out / "roots.json").write_text(json.dumps(roots))
