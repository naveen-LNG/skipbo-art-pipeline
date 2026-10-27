#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""Write what spine_qa's renderer computes for a rig, for check.html to compare against the official Spine 4.2 runtime.

  uv run runtime_check/expected.py beaver/rig_pro/beaver.json      -> beaver/rig_pro/runtime_expected.json

Per animation, at 0, 30%, 60% and 100% of its duration: every bone's world matrix, every slot's active attachment,
and the world centre of each drawn attachment (regions: image centre; meshes: mean of the deformed vertices).
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "plugin" / "skills" / "skipbo-art" / "scripts"))
import spine_qa  # noqa: E402

path = Path(sys.argv[1])
rig = spine_qa.Rig(path)
out = {}
for anim in rig.data["animations"]:
    d = rig.duration(anim)
    for f in (0.0, 0.3, 0.6, 1.0):
        t = round(d * f, 4)
        world, active = rig.pose(anim, t)
        cen = {}
        for s in rig.slots:
            att = active.get(s["name"])
            if not att:
                continue
            if rig.is_mesh(s["name"], att):
                c = rig.mesh_world(s["name"], att, world).mean(0)
            else:
                im = rig.images[att]
                c = (rig.att_matrix(s["name"], att, world) @ np.array([im.width / 2, im.height / 2, 1.0]))[:2]
            cen[s["name"]] = [round(float(c[0]), 3), round(float(c[1]), 3), att]
        out[f"{anim}@{t}"] = {"anim": anim, "t": t,
                              "bones": {n: [round(float(v), 5) for v in w] for n, w in world.items()},
                              "slots": cen}
(path.parent / "runtime_expected.json").write_text(json.dumps(out), encoding="utf-8")
print(path.parent / "runtime_expected.json", len(out), "poses")
