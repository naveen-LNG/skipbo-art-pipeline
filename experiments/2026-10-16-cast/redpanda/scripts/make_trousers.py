# /// script
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""One trousers piece from the body sheet's hips (redpanda-body-parts/09), which is the whole trousers at the master's
length (belt to hem) but differs from the master in three ways (onion sheet, rounds 1-2):
  - its crotch sits at 0.58 of its height where the master's is at ~0.50, and its leg gap is narrower: cut the gap up
    to TOP with a rounded top (half-width HALF of the piece, centred on its own gap at 0.506), and shade the new inner
    leg edges a little darker, as the painted ones are;
  - its legs taper into rounded hems where the master's run straight down, so boot tops peeked beside the cuffs: below
    0.78 each leg's outer edge is carried straight down (edge pixels repeated outward) to 0.91;
  - its belt top meets the jacket hem edge to edge, a weak torso/hips joint; with the torso low enough to overlap it,
    the jacket covered half the belt: add E px of belt colour above the belt, hidden under the jacket.
Writes runs/redpanda-trousers-parts/trousers_00.png and points.json (hips waist/hip points, torso waist)."""
import glob, json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
HERE = Path(__file__).resolve().parents[1]
CX, HALF, TOP, SHADE, DARK = 0.506, 0.078, 0.56, 12, 0.80
E, SCALE, MW, MH = 60, 1.307, 1792, 2400        # SCALE: the rig's master px per part px (rig/report.json)
WAIST_UP_PX = 0.005 * MH / SCALE                # the master's waist (0.570) is 0.005 above its belt top (0.575)
a = np.asarray(Image.open(glob.glob(str(HERE / "runs/redpanda-body-parts/*_09.png"))[0]).convert("RGBA")).astype(np.float32)
h, w, _ = a.shape
op = a[..., 3] > 128
# 1. straight legs: carry each leg's outer edge at y0 down to y1
y0, y1 = int(0.78 * h), int(0.91 * h)    # to 0.95 left square corners at the hems
xs0 = np.nonzero(op[y0])[0]; L0, R1 = xs0.min(), xs0.max()
for y in range(y0 + 1, y1):
    xs = np.nonzero(op[y])[0]
    if not len(xs):
        continue
    if xs.min() > L0:
        a[y, L0:xs.min()] = a[y, xs.min() + 2]; a[y, L0:xs.min(), 3] = 255
    if xs.max() < R1:
        a[y, xs.max() + 1:R1 + 1] = a[y, xs.max() - 2]; a[y, xs.max() + 1:R1 + 1, 3] = 255
# 2. crotch slot
yy, xx = np.mgrid[0:h, 0:w]
r = HALF * w; cy = TOP * h + r
slot = ((np.abs(xx - CX * w) <= r) & (yy >= cy)) | ((xx - CX * w) ** 2 + (yy - cy) ** 2 <= r * r)
keep = np.clip(ndimage.distance_transform_edt(~slot) / 1.5, 0, 1)
removed = (a[..., 3] > 128) & slot
near = ndimage.distance_transform_edt(~removed)
sh = np.where((near <= SHADE) & ~slot, DARK + (1 - DARK) * np.clip(near / SHADE, 0, 1), 1.0)
a[..., :3] *= sh[..., None]; a[..., 3] *= keep
# 3. hidden belt-coloured band above the belt
op = a[..., 3] > 128
top_c = int(np.nonzero(op[:, int(0.5 * w)])[0].min())          # belt top at the centre (it dips there)
full = int(0.12 * h); span = np.nonzero(op[full])[0]
belt = np.median(a[int(0.06 * h):int(0.10 * h), int(0.15 * w):int(0.35 * w), :3].reshape(-1, 3), 0)
out = np.zeros((h + E, w, 4), np.float32); out[E:] = a
band = np.zeros((h + E, w), bool); band[:E + full, span.min() + 6:span.max() - 5] = True
fill = band & (out[..., 3] < 250)
out[fill, :3] = belt; out[fill, 3] = 255
d = HERE / "runs/redpanda-trousers-parts"; d.mkdir(parents=True, exist_ok=True)
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(d / "trousers_00.png")
H2 = h + E
ys = np.nonzero(out[..., 3] > 128)[0]; bot = ys.max()
pts = {"waist": [0.5, round((E + top_c - WAIST_UP_PX) / H2, 4)],
       "hip_l": [0.76, round((bot - 0.05 * h) / H2, 4)], "hip_r": [0.24, round((bot - 0.05 * h) / H2, 4)]}
t = np.asarray(Image.open(glob.glob(str(HERE / "runs/redpanda-body-parts/*_10.png"))[0]).convert("RGBA"))[..., 3] > 128
th = t.shape[0]; hem = np.nonzero(t[:, t.shape[1] // 2])[0].max()
pts["torso_waist"] = [0.5, round((hem - WAIST_UP_PX - 1) / th, 4)]
(d / "points.json").write_text(json.dumps(pts)); print(pts)
