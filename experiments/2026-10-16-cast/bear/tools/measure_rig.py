# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Setup pose in the master's pixel frame: each slot's bbox (fractions of the master) and, for the clogs and the
hands, the master's own bbox by colour, to measure offsets. uv run tools/measure_rig.py rig/bear.json"""
import sys
from pathlib import Path
sys.path.insert(0, "../../../plugin/skills/skipbo-art/scripts")
import numpy as np
import joint_crops as jc
al = jc.Aligned(Path(sys.argv[1]), Path("annotations.json"))
W, H = al.master.size
def bb(m):
    ys, xs = np.nonzero(m)
    return [round(xs.min() / W, 3), round(ys.min() / H, 3), round(xs.max() / W, 3), round(ys.max() / H, 3)] if len(xs) else None
for s, a in al.alphas.items():
    if a.any():
        print(f"{s:14s}", bb(a))
m = np.asarray(al.master).astype(float)
bg = np.median(np.concatenate([m[0], m[-1]]), 0)
fg = np.linalg.norm(m - bg, axis=2) > 25
yy, xx = np.mgrid[0:H, 0:W]
dark = fg & (m.sum(2) < 300)
print("master clog_r (y>0.88)", bb(fg & (yy > 0.885 * H) & (xx < W / 2)))
print("master clog_l (y>0.88)", bb(fg & (yy > 0.885 * H) & (xx > W / 2)))
print("master mitten_r", bb(dark & (xx < 0.21 * W) & (yy > 0.5 * H) & (yy < 0.75 * H)))
print("master mitten_l", bb(dark & (xx > 0.79 * W) & (yy > 0.5 * H) & (yy < 0.75 * H)))
