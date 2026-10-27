# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Where would rig_snap put a rough point? uv run tools/try_snap.py <piece.png> round|open x y [px py partner]"""
import sys
sys.path.insert(0, "../../../plugin/skills/skipbo-art/scripts")
import numpy as np
from PIL import Image
import rig_snap
a = np.asarray(Image.open(sys.argv[1]).convert("RGBA"))[..., 3] > 128
h, w = a.shape
kind, x, y = sys.argv[2], float(sys.argv[3]) * w, float(sys.argv[4]) * h
rad = rig_snap.search_radius(a) if hasattr(rig_snap, "search_radius") else 0.6 * w
if kind == "round":
    r = rig_snap.snap_round_end(a, (x, y), rad)
else:
    px, py = float(sys.argv[5]) * w, float(sys.argv[6]) * h
    r = rig_snap.snap_opening(a, (x, y), (px - x, py - y), rad)
print("radius", round(rad, 1), "->", None if r is None else (round(r.at[0] / w, 3), round(r.at[1] / h, 3), "width", round(r.width, 1), "moved", round(np.hypot(r.at[0] - x, r.at[1] - y), 1)))
