"""Size-matched hand-overs for the hybrid legs (rig_hybrid): while the bent mesh and the painted drawing overlap, the
drawing is stretched to the mesh's exact outline box, so the two never show as two shapes of different sizes; once
the mesh has faded out, the drawing eases back to its own size during the hold; before the mesh fades back in, it
eases to the mesh's size again.

  uv run --with numpy --with pillow scripts/match_handover.py rig_hybrid/beaver.json [anim ...]

Per frame where the drawing shows: render the rig (spine_qa) and take the pixel boxes of the drawing (legs_a) and of
the mesh and the rig's boots (hips, boot_l, boot_r) at their natural placement; k(t) is 1 while the mesh is visible
and eases to 0 over RELAX s away from it; the drawing's box goes to lerp(its own box, the mesh's box, k), anchored
on the soles. Written as scale and translate keys on the legs_a bone (on top of the existing height stretch).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402

RELAX = 0.25        # s: how long the drawing takes to ease from the mesh's size to its own (and back)
CANVAS_H = 1400     # render height for measuring


def alpha_at(keys: list, t: float) -> float:
    if not keys:
        return 1.0
    a = [(k.get("time", 0.0), int(k["color"][6:8], 16) / 255) for k in keys]
    if t <= a[0][0]:
        return a[0][1]
    for (t0, v0), (t1, v1) in zip(a, a[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(t1 - t0, 1e-9)
    return a[-1][1]


def box(mask: np.ndarray, cv) -> tuple | None:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    # canvas px -> world (y up): x0, x1, y0 (bottom), y1 (top)
    return (xs.min() / cv.S + cv.ox, (xs.max() + 1) / cv.S + cv.ox, cv.oy - (ys.max() + 1) / cv.S, cv.oy - ys.min() / cv.S)


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


def main(path: Path, anims: list):
    rig = q.Rig(path)
    data = json.loads(path.read_text())
    cv = q.Canvas(rig, CANVAS_H)
    hips = next(b for b in data["bones"] if b["name"] == "hips")
    hr = math.radians(hips["rotation"])
    Hinv = np.array([[math.cos(-hr), -math.sin(-hr)], [math.sin(-hr), math.cos(-hr)]])   # world delta -> hips-local
    for anim in anims:
        an = data["animations"][anim]
        sl = an.get("slots", {})
        if "legs_a" not in sl:
            continue
        T = rig.duration(anim)
        ts = [round(i / 30, 4) for i in range(int(round(T * 30)) + 1)]
        mesh_vis = [alpha_at(sl["hips"].get("rgba", []), t) > 0.01 for t in ts]
        vis_t = [t for t, v in zip(ts, mesh_vis) if v]
        old = {k["time"]: k for k in an["bones"]["legs_a"]["scale"]}
        sc, tr = [], []
        for t, mv in zip(ts, mesh_vis):
            s0 = old.get(t, {"x": 1.0, "y": 1.0})
            _, world, active, alphas = q.render(rig, cv, anim, t)
            if not active.get("legs_a"):
                sc.append({"time": t, "x": 1.0, "y": s0["y"]}); tr.append({"time": t, "x": 0.0, "y": 0.0})
                continue
            bd = box(alphas["legs_a"], cv)
            parts = [alphas[s] for s in ("hips", "boot_l", "boot_r") if s in alphas]
            bm = box(np.logical_or.reduce(parts), cv) if parts else None
            dist = min((abs(t - v) for v in vis_t), default=99.0)
            k = 1.0 if mv else 1 - smooth(dist / RELAX)
            if bd is None or bm is None or k <= 0:
                sc.append({"time": t, "x": 1.0, "y": s0["y"]}); tr.append({"time": t, "x": 0.0, "y": 0.0})
                continue
            want = [a + (b - a) * k for a, b in zip(bd, bm)]
            sx = (want[1] - want[0]) / (bd[1] - bd[0])
            sy = (want[3] - want[2]) / (bd[3] - bd[2])
            bx_, by_ = world["legs_a"][4], world["legs_a"][5]           # the bone's origin (the buckle), world
            cxn, cxd = 0.5 * (bd[0] + bd[1]), 0.5 * (want[0] + want[1])
            Tw = np.array([cxd + (bx_ - cxn) * sx - bx_, want[2] + (by_ - bd[2]) * sy - by_])
            Tl = Hinv @ Tw
            sc.append({"time": t, "x": round(sx, 4), "y": round(s0["y"] * sy, 4)})
            tr.append({"time": t, "x": round(float(Tl[0]), 2), "y": round(float(Tl[1]), 2)})
        an["bones"]["legs_a"] = {"scale": sc, "translate": tr}
        print(f"{anim}: matched {sum(1 for s in sc if abs(s['x'] - 1) > 1e-3)} frames")
    path.write_text(json.dumps(data, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:] or ["squat", "plant_seed", "jump_hurdle"])
