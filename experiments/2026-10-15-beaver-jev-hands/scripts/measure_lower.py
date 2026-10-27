# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Colour-class runs (turquoise sweater, mustard trousers, red boots) per row, master vs the rig's setup pose rendered
in the master's pixel frame. uv run measure_lower.py <char> <rig dir> <annotations.json> [rows as fractions...]"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).parents[3] / "plugin/skills/skipbo-art/scripts"))
sys.path.insert(0, str(Path(__file__).parent))
import joint_crops as jc  # noqa: E402  (the experiment's: render_master_frame)
import spine_qa as q  # noqa: E402
char, rigdir, annp = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
rows = [float(x) for x in sys.argv[4:]] or [0.58, 0.59, 0.60, 0.61, 0.62, 0.66, 0.72, 0.77, 0.79, 0.80, 0.81, 0.82, 0.84]
ann = json.load(open(annp)); m = Image.open(annp.parent / ann["master"]["image"]).convert("RGB"); W, H = m.size
rig = q.Rig(rigdir / f"{char}.json"); mf = json.load(open(rigdir / "report.json"))["master_frame"]
fr, *_ = jc.render_master_frame(rig, mf, (W, H))


def masks(img):
    a = np.asarray(img).astype(int); r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return {"turq": (g > 140) & (b > 140) & (r < 130), "must": (r > 170) & (g > 110) & (g < 205) & (b < 110),
            "red": (r > 140) & (g < 90) & (b < 90)}


def runs(row):
    xs = np.nonzero(row)[0]
    if not len(xs):
        return "-"
    rr = [x for x in np.split(xs, np.nonzero(np.diff(xs) > 3)[0] + 1) if len(x) > 8]
    return " ".join(f"{x[0] / W:.3f}-{x[-1] / W:.3f}" for x in rr)


M, R = masks(m), masks(fr)
for y in rows:
    Y = int(y * H)
    print(f"{y:.3f} " + " | ".join(f"{k}: M {runs(M[k][Y]):28s} R {runs(R[k][Y]):28s}" for k in ("turq", "must", "red")))
for k in ("turq", "must", "red"):
    ym, yr = np.nonzero(M[k][int(0.5 * H):].any(1))[0], np.nonzero(R[k][int(0.5 * H):].any(1))[0]
    print(k, "bottom row  M", round((ym.max() + 0.5 * H) / H, 3), " R", round((yr.max() + 0.5 * H) / H, 3))
