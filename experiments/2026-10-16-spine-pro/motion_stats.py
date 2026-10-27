#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""How much of the character moves, legacy vs pro, per animation.

  uv run motion_stats.py beaver fox moose

Per animation: the number of drawn parts (slotted bones, plus mesh-owning helpers) whose world position moves more
than 0.3% of the body height or whose angle moves more than 1 degree, and the tail tip's / ear tip's path length per
second as a fraction of body height. Prints a markdown table.
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugin" / "skills" / "skipbo-art" / "scripts"))
import spine_qa as q  # noqa: E402

HERE = Path(__file__).resolve().parent


def stats(rig, anim):
    H = rig.data["skeleton"]["height"]
    d = rig.duration(anim)
    ts = np.linspace(0, d, max(2, int(round(d * 30)) + 1))
    names = [b["name"] for b in rig.bones if not b["name"].endswith("_ik") and b["name"] not in ("root", "character", "shadow")
             and not b["name"].startswith("prop")]
    tr = {n: [] for n in names}
    for t in ts:
        w, _ = rig.pose(anim, float(t))
        for n in names:
            a, b, c, dd, x, y = w[n]
            L = next(bb.get("length", 0) for bb in rig.bones if bb["name"] == n)
            tr[n].append((x, y, math.degrees(math.atan2(c, a)), x + a * L, y + c * L))
    moving = 0
    for n, v in tr.items():
        v = np.array(v)
        ang = np.unwrap(np.radians(v[:, 2])) * 180 / math.pi
        if np.ptp(v[:, 0]) > 0.003 * H or np.ptp(v[:, 1]) > 0.003 * H or np.ptp(ang) > 1.0:
            moving += 1
    tails = [n for n in names if n.startswith("tail")]
    tip = None
    if tails:
        v = np.array(tr[tails[-1]])
        tip = float(np.linalg.norm(np.diff(v[:, 3:5], axis=0), axis=1).sum() / max(d, 1e-6) / H)
    return moving, len(names), tip


rows = ["| character | animation | moving bones legacy | moving bones pro | tail tip travel legacy (H/s) | pro (H/s) |",
        "|---|---|---|---|---|---|"]
for ch in sys.argv[1:]:
    L = q.Rig(HERE / ch / "rig_legacy" / f"{ch}.json")
    P = q.Rig(HERE / ch / "rig_pro" / f"{ch}.json")
    for anim in P.data["animations"]:
        ml, nl, tl = stats(L, anim) if anim in L.data["animations"] else (None, None, None)
        mp, np_, tp = stats(P, anim)
        f = lambda x: "-" if x is None else f"{x:.2f}"  # noqa: E731
        rows.append(f"| {ch} | {anim} | {'-' if ml is None else f'{ml}/{nl}'} | {mp}/{np_} | {f(tl)} | {f(tp)} |")
print("\n".join(rows))
