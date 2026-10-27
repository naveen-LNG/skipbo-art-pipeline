# /// script
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""The poses sheet's tilted tiptoe clog (bear-poses-parts/02) with the rest clogs' hidden honey-fur ankle stub
(make_parts.py section 4), sized by the tiptoe's sheet scale against the rest clog (area ratio ~0.725):
<bear dir>/runs/bear-tiptoe-parts/tiptoe_00.png. Without the stub the tiptoe overlaps the trousers a third as much
as the stubbed rest clog (variant_misfit 0.34). Used by verify_tiptoe.sh.  uv run tools/make_tiptoe.py <bear dir>"""
import glob
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(sys.argv[1])
c = Image.open(glob.glob(str(HERE / "runs/bear-poses-parts/*_02.png"))[0]).convert("RGBA")
w, h = c.size
K = 1 / 0.725                                  # rest clog px -> tiptoe px
sw, ext = 160.0, round(0.55 * 222 * K)        # stub width (inside the tilted opening), lift as the rest clogs'
cx, open_y = 0.36 * w, 0.06 * h               # heel opening (top rim) in the tiptoe image
FUR = np.array([214, 138, 62], np.float32)
H2 = h + ext
yy, xx = np.mgrid[0:H2, 0:w]
u = (xx - cx) / (sw / 2)
top_r = sw / 2
inside = (np.abs(u) <= 1) & (yy <= ext + open_y + 0.03 * h) & ((yy >= top_r) | ((u ** 2 + ((yy - top_r) / top_r) ** 2) <= 1))
canvas = np.zeros((H2, w, 4), np.float32)
canvas[..., :3] = np.clip(FUR * (1.08 - 0.25 * (u + 1) / 2)[..., None], 0, 255)
canvas[..., 3] = 255 * np.clip(ndimage.gaussian_filter(inside.astype(np.float32), 1.0) * 2 - 0.5, 0, 1)
out = Image.fromarray(canvas.astype(np.uint8), "RGBA")
out.alpha_composite(c, (0, ext))
d = HERE / "runs/bear-tiptoe-parts"
d.mkdir(parents=True, exist_ok=True)
out.save(d / "tiptoe_00.png")
ay = ext + open_y - 0.171 * 344 * K           # the rest clog's pivot: 0.171 of its piece above the heel opening
print(f"size {out.size}  ankle ({cx / w:.3f}, {ay / H2:.3f})  ground (0.66, {(ext + 0.985 * h) / H2:.3f})")
