"""How much the legs pop at drawing swaps: per frame, the share of lower-body pixels that change from the last frame
(rendered with slot alpha), at the frames where a legs drawing changes against the frames around them.

  uv run --with numpy --with pillow python scripts/pops.py <rig.json> <anim> ...
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_alpha as ra  # noqa: E402

q = ra.q
rig = q.Rig(Path(sys.argv[1]))
cv = q.Canvas(rig, 420)
gy = int(cv.oy * cv.S)
for anim in sys.argv[2:]:
    n = int(round(rig.duration(anim) * 30)) + 1
    fr = [np.asarray(ra.render(rig, cv, anim, i / 30)[0].convert("RGB")).astype(np.int16)[int(gy * 0.55):gy + 10] for i in range(n)]
    ch = np.array([(np.abs(fr[i + 1] - fr[i]).sum(2) > 45).mean() * 100 for i in range(n - 1)])
    sl = rig.data["animations"][anim]["slots"]
    sw = sorted({round(k["time"] * 30) for s in ("legs", "legs_a", "legs_b", "hips") if s in sl for k in sl[s]["attachment"]} - {0, n - 1})
    exc = [ch[f - 1] - np.median(ch[max(0, f - 4):f - 1].tolist() + ch[f:f + 3].tolist()) for f in sw if 1 <= f <= n - 1]
    print(f"{anim:12s} swaps {len(sw):2d}  worst swap excess {max(exc):5.2f}%  mean {np.mean(exc):5.2f}%  (frame change median {np.median(ch):.2f}%)")
