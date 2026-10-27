# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Round 2 (and 6, the tail, below): the body sheet's trousers (rabbit-body-parts/11) end in leg openings painted from below, a dark ellipse
each. The master's trouser legs go into the boots, so the openings must vanish under the boots' front lip; the dark
ellipses showed above the boot rims (joints.png, ankles). And the legs were wider than the master's (onion.png: cyan
fringe along both legs). So: carry the cloth just above each opening down over its dark inside, and narrow the trousers
across, TOP down to the belly (0.45 of the height), tapering to LEG at the hems, about the centre line.
Writes runs/rabbit-trousers-parts/trousers_00.png (same size) and prints the moved hip points."""
import glob
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).parent
TOP, LEG, Y0 = 1.0, 0.92, 0.45   # round 10 tried 0.95 / 0.86 (onion looked ~6% too wide): setup IoU fell 0.854 -> 0.845, reverted
im = np.asarray(Image.open(glob.glob(str(HERE / "runs/rabbit-body-parts/*_11.png"))[0]).convert("RGBA")).astype(np.float32)
h, w, _ = im.shape
Y_OPEN = int(0.83 * h)                                # the openings start just below this row
ys, xs = np.nonzero(im[Y_OPEN:, :, 3] > 0)
for y, x in zip(ys + Y_OPEN, xs):                     # the cloth just above the opening, carried down to the hem
    im[y, x, :3] = im[Y_OPEN, x, :3] if im[Y_OPEN, x, 3] > 200 else im[y, x, :3]
out = np.zeros_like(im); X = np.arange(w) + 0.5
for y in range(h):
    k = TOP + (LEG - TOP) * float(np.clip((y / h - Y0) / (1 - Y0), 0, 1))
    src = (X - w / 2) / k + w / 2 - 0.5
    i0 = np.clip(np.floor(src).astype(int), 0, w - 1); i1 = np.clip(i0 + 1, 0, w - 1); f = (src - np.floor(src))[:, None]
    r = im[y, i0] * (1 - f) + im[y, i1] * f
    r[(src < -0.5) | (src > w - 0.5)] = 0
    out[y] = r
# round 6: the cotton tail. The matcher could not place the ball: its rim is painted in the background's own grey and
# the paw covers half of it, so it landed on the cheek, then the paw, then just outside the trousers (pivot outside
# the hips, overlap 1 px). Paint it into the trousers piece instead, behind the cloth, where the master shows it:
# ball centre (0.341, 0.7175) of the master, radius 117 master px, at the rig's scale (1.353 master px per part px,
# hips waist (0.5, 0.226) on the master's waist (0.51, 0.64)). The canvas grows PAD px on the left for it.
G, PAD = 1.353, 90
tr = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")
ball = Image.open(glob.glob(str(HERE / "runs/rabbit-body-parts/*_10.png"))[0]).convert("RGBA")
ba = np.asarray(ball)[..., 3] > 128; bys, bxs = np.nonzero(ba)
dia = max(bxs.max() - bxs.min(), bys.max() - bys.min()) + 1
k = 2 * 117 / G / dia
ball = ball.resize((round(ball.width * k), round(ball.height * k)), Image.LANCZOS)
cx = 0.5 * w + (0.341 - 0.51) * 1792 / G + PAD
cy = 0.226 * h + (0.7175 - 0.64) * 2400 / G
canvas = Image.new("RGBA", (w + PAD, h))
canvas.alpha_composite(ball, (round(cx - ball.width / 2), round(cy - ball.height / 2)))
canvas.alpha_composite(tr, (PAD, 0))
d = HERE / "runs/rabbit-trousers-parts"; d.mkdir(parents=True, exist_ok=True)
canvas.save(d / "trousers_00.png")
X = lambda x: round((x * w + PAD) / (w + PAD), 3)
print("filled", len(ys), "px; points:", {"waist_x": X(0.5), "hip_l_x": X(0.5 + 0.27 * LEG), "hip_r_x": X(0.5 - 0.28 * LEG)})
