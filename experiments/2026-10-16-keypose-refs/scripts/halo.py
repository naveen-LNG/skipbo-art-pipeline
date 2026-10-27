"""How much the outgoing legs show outside the incoming ones during the hybrid's hand-overs: per frame where both
the painting (legs_a) and the trousers mesh are partly visible, the area of mesh-and-boots pixels outside the
painting's outline, weighted by the mesh's opacity there, as a share of the painting's area; the sum over the
hand-over frames ("halo-frames") and the worst frame.

  uv run --with numpy --with pillow scripts/halo.py <rig.json> [anim ...]
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_alpha as ra  # noqa: E402
q = ra.q
rig = q.Rig(Path(sys.argv[1]))
MORPHED = any("attachments" in a for a in rig.data["animations"].values())


def morphed_masks(rig, cv, anim, t, al):
    """Recompute the hips slot's mask with the deform keys applied (spine_qa's own masks ignore them)."""
    orig = q.Rig.mesh_world

    def patched(self, slot, att, world_):
        off = ra.deform_at(self, anim, slot, att, t)
        return orig(self, slot, att, world_) if off is None else ra.mesh_world_deformed(self, slot, att, world_, off)
    q.Rig.mesh_world = patched
    try:
        _, _, _, al2 = q.render(rig, cv, anim, t)
    finally:
        q.Rig.mesh_world = orig
    return al2
cv = q.Canvas(rig, 520)
for anim in sys.argv[2:] or ["squat", "jump_hurdle"]:
    n = int(round(rig.duration(anim) * 30)) + 1
    tot, worst = 0.0, 0.0
    for i in range(n):
        t = i / 30
        am = ra.slot_alpha(rig, anim, "hips", t)
        ad = ra.slot_alpha(rig, anim, "legs_a", t)
        _, _, active, al = q.render(rig, cv, anim, t)
        if MORPHED:                                   # the trousers mesh as drawn, with its deform keys
            al = morphed_masks(rig, cv, anim, t, al)
        if not active.get("legs_a") or am < 0.01 or ad < 0.01:
            continue
        m = np.logical_or.reduce([al[s] for s in ("hips", "boot_l", "boot_r") if s in al])
        d = al["legs_a"]
        h = am * (m & ~d).sum() / max(d.sum(), 1) * 100
        tot += h
        worst = max(worst, h)
    print(f"{Path(sys.argv[1]).parent.name:16s} {anim:12s} halo-frames {tot:6.1f}%  worst frame {worst:5.1f}%")
