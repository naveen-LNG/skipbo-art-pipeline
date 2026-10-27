# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Round 2: the body sheet's torso has an open, dark armhole on its picture-left shoulder (the character's right),
painted like a sleeve's opening. With the sleeve drawn under the torso (upperarm: under_torso) the hole showed as a
dark green disc on the shoulder (joints.png, shoulder_r). The picture-right shoulder is a closed rounded shirt
shoulder, so the torso is made symmetric: the right half mirrored onto the left about the neck stub's centre line.
Writes runs/rabbit-torso-parts/torso_00.png (same size as rabbit-body-parts/12)."""
import glob
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).parent
a = np.asarray(Image.open(glob.glob(str(HERE / "runs/rabbit-body-parts/*_12.png"))[0]).convert("RGBA")).copy()
h, w = a.shape[:2]
row = np.nonzero(a[int(0.06 * h), :, 3] > 128)[0]
c = (row.min() + row.max()) / 2                       # the neck stub's centre column
for x in range(w):
    xm = int(round(2 * c - x))
    if x < c and 0 <= xm < w:
        a[:, x] = a[:, xm]
    elif x < c:
        a[:, x] = 0
d = HERE / "runs/rabbit-torso-parts"; d.mkdir(parents=True, exist_ok=True)
Image.fromarray(a, "RGBA").save(d / "torso_00.png")
print("centre", c / w)
