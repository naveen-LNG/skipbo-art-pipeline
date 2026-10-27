"""spine_qa's renderer plus slot alpha and deform keys: Spine's `rgba` slot timelines (linear between keys), which kp_rig's
cross-fades between legs drawings use and spine_qa (as of 2026-10-16) ignores. Same signature as spine_qa.render;
the masks it returns are spine_qa's (alpha ignored), only the picture fades.

  from render_alpha import render
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402


def slot_alpha(rig: q.Rig, anim: str | None, slot: str, t: float) -> float:
    keys = rig.data["animations"].get(anim, {}).get("slots", {}).get(slot, {}).get("rgba", []) if anim else []
    if not keys:
        return 1.0
    a = [(k.get("time", 0.0), int(k["color"][6:8], 16) / 255) for k in keys]
    if t <= a[0][0]:
        return a[0][1]
    for (t0, v0), (t1, v1) in zip(a, a[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(t1 - t0, 1e-9)
    return a[-1][1]


def deform_at(rig, anim, slot, att, t):
    """Spine deform keys (animations.<a>.attachments.default.<slot>.<att>.deform): offsets, linear between keys."""
    if not anim:
        return None
    keys = rig.data["animations"].get(anim, {}).get("attachments", {}).get("default", {}).get(slot, {}).get(att, {}).get("deform")
    if not keys:
        return None
    n = max(len(k.get("vertices", [])) for k in keys)
    def full(k):
        v = np.zeros(n)
        vs = k.get("vertices", [])
        v[k.get("offset", 0):k.get("offset", 0) + len(vs)] = vs
        return v
    if t <= keys[0]["time"]:
        return full(keys[0])
    for a, b in zip(keys, keys[1:]):
        if a["time"] <= t <= b["time"]:
            u = (t - a["time"]) / max(b["time"] - a["time"], 1e-9)
            return full(a) * (1 - u) + full(b) * u
    return full(keys[-1])


def mesh_world_deformed(rig, slot, att, world, off):
    A = rig.skin[slot][att]
    v, n = A["vertices"], len(A["uvs"]) // 2
    out, k, j = np.zeros((n, 2)), 0, 0
    for i in range(n):
        cnt = int(v[k]); k += 1
        for _ in range(cnt):
            bi, bx, by, w = int(v[k]), v[k + 1], v[k + 2], v[k + 3]
            k += 4
            if off is not None and len(off):
                bx, by = bx + off[2 * j], by + off[2 * j + 1]
            j += 1
            a_, b_, c_, d_, x_, y_ = world[rig.bones[bi]["name"]]
            out[i] += w * np.array([a_ * bx + b_ * by + x_, c_ * bx + d_ * by + y_])
    return out


def render(rig, canvas, anim, t, bg=(214, 214, 214, 255), override=None):
    world, active = rig.pose(anim, t, override)
    orig = q.Rig.mesh_world

    def patched(self, slot, att, world_):
        off = deform_at(self, anim, slot, att, t)
        if off is None or not self.mesh_weighted(slot, att):
            return orig(self, slot, att, world_)
        return mesh_world_deformed(self, slot, att, world_, off)
    q.Rig.mesh_world = patched
    frame = Image.new("RGBA", (canvas.W, canvas.H), bg)
    by_name = {s["name"]: s for s in rig.slots}
    for s in (by_name[n] for n in rig.draw_order(anim, t)):
        att = active.get(s["name"])
        if not att:
            continue
        if rig.is_mesh(s["name"], att) and rig.mesh_weighted(s["name"], att):
            lay = canvas.mesh_layer(rig, s["name"], att, world, np.full((canvas.H, canvas.W), -1, np.int32))
        else:
            lay = canvas.layer(rig, s["name"], att, world)
        k = slot_alpha(rig, anim, s["name"], t)
        if k < 0.999:
            a = np.asarray(lay).copy()
            a[..., 3] = (a[..., 3].astype(np.float32) * k).astype(np.uint8)
            lay = Image.fromarray(a, "RGBA")
        frame.alpha_composite(lay)
    q.Rig.mesh_world = orig
    return frame, world, active, None
