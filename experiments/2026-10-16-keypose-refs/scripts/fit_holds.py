"""Fit the bent mesh to each held key pose's painted drawing (for leg_bones.corrected): per key pose, the knee
nudge, shin length and thigh / shin thickness that make the mesh-and-boots outline overlap the drawing's best (IoU)
at the hold, by coordinate descent over small steps. Writes legs/hold_fit.json; rebuild the rig afterwards.

  KP_LEGS=bones KP_HYBRID=1 KP_NOFIT=1 uv run --with numpy --with pillow --with scipy scripts/fit_holds.py <base rig dir>
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kp_rig  # noqa: E402

q = kp_rig.q if hasattr(kp_rig, "q") else None
sys.path.insert(0, str(HERE.parents[2] / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402

HOLDS = {"s5": ("squat", kp_rig.squat, 1.0), "j5": ("jump_hurdle", kp_rig.jump_hurdle, 1.41)}
STEPS = {"thigh_sy": [0.7, 0.8, 0.9, 1.0, 1.1, 1.2], "shin_sy": [0.7, 0.8, 0.9, 1.0, 1.1, 1.2],
         "shin_len": [0.7, 0.8, 0.9, 1.0, 1.1, 1.2], "kdx": [-40, -20, 0, 20, 40], "kdy": [-40, -20, 0, 20, 40]}


def main(base: Path):
    tmp = Path(tempfile.mkdtemp(prefix="fit_holds_"))
    br = kp_rig.Bridge(base, tmp / "rig")
    br.legs(); br.flag()
    rest = kp_rig.rest_angles(br)
    br.save()
    rig = q.Rig(br.path)
    rig.data = br.rig                                   # evaluate against the in-memory skeleton
    cv = q.Canvas(rig, 520)
    out = {}
    for v, (anim, fn, t) in HOLDS.items():
        def score(f):
            br.lb.fix[v] = f
            rig.data["animations"][anim] = fn(br, rest)
            _, _, active, al = q.render(rig, cv, anim, t)
            m = np.logical_or.reduce([al[s] for s in ("hips", "boot_l", "boot_r") if s in al])
            d = al.get("legs_a")
            return float((m & d).sum() / max((m | d).sum(), 1)) if d is not None else 0.0
        f = dict(br.lb.FIX0)
        best = score(f)
        print(v, "start IoU", round(best, 3))
        for sweep in range(3):
            changed = False
            for k, vals in STEPS.items():
                for x in vals:
                    g = dict(f, **{k: x})
                    sc = score(g)
                    if sc > best + 1e-4:
                        best, f, changed = sc, g, True
            print(v, "sweep", sweep, round(best, 3), f)
            if not changed:
                break
        out[v] = f
    (kp_rig.EXP / "legs/hold_fit.json").write_text(json.dumps(out, indent=1))
    print("wrote legs/hold_fit.json")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
