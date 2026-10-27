"""qa_constraints.py - the Spine 4.2 constructs spine_pro.py emits, evaluated for spine_qa's renderer.

spine_qa.Rig hands over to this module only when a skeleton uses one of them (extended()), so legacy rigs take
exactly the old code path. Ported from spine-ts 4.2 (Bone.updateWorldTransformWith, IkConstraint.apply1,
TransformConstraint.applyAbsoluteWorld, Skeleton.updateCache):

  bone inherit     "normal", "onlyTranslation", "noRotationOrReflection", "noScale", "noScaleOrReflection"
  ik               one-bone IK (rotate the bone at the target; compress / stretch / uniform; mix), applied in order
  transform        absolute world transform constraints (mixRotate, mixX, mixY, mixScaleX, mixScaleY; offsets)
  slot colour      setup "color" and "rgba" timelines (linear / stepped), multiplied into the drawn layer
  linkedmesh       resolved to a copy of its parent mesh (same slot, as Spine requires) at load

Constraint order: Spine sorts constraints by their "order" and updates each constrained bone's descendants after
it. Here every bone is first posed hierarchically, then the constraints are applied in order, each followed by a
re-pose of the constrained bones' descendants. That equals Spine's update cache whenever no constraint's target
descends from a bone another (later) constraint moves, which spine_pro guarantees (targets hang off `character`).

Decor slots (`shadow`, and `<slot>_under` underfills drawn below their part) are composited into the frame but not
returned as part masks: they are insurance, not parts, so the joint/occlusion/seam checks judge the real parts.
"""
from __future__ import annotations

import math

import numpy as np

INHERITS = ("normal", "onlyTranslation", "noRotationOrReflection", "noScale", "noScaleOrReflection")


def extended(data: dict) -> bool:
    """Does this skeleton need the extended pose (inherit modes or constraints)?"""
    return bool(data.get("ik") or data.get("transform")
                or any(b.get("inherit", "normal") != "normal" for b in data["bones"]))


def decor_slots(rig) -> set:
    """Slots drawn but never judged as parts: the ground shadow and underfills (<slot>_under below <slot>)."""
    names = {s["name"] for s in rig.slots}
    return {n for n in names if n == "shadow" or (n.endswith("_under") and n[: -len("_under")] in names)}


def resolve_linked(skin: dict) -> None:
    """Replace every linkedmesh attachment by a mesh copy of its parent (in the same slot), in place."""
    for slot, atts in skin.items():
        for name, A in list(atts.items()):
            if A.get("type") == "linkedmesh":
                P = atts[A["parent"]]
                atts[name] = {**{k: v for k, v in P.items() if k in ("uvs", "triangles", "vertices", "hull", "edges")},
                              "type": "mesh", "width": A.get("width", P.get("width")),
                              "height": A.get("height", P.get("height"))}


# ------------------------------------------------------------------ bones

def _local(b: dict, tl: dict, t: float, interp) -> list:
    x, y, rot = b.get("x", 0.0), b.get("y", 0.0), b.get("rotation", 0.0)
    sx, sy = b.get("scaleX", 1.0), b.get("scaleY", 1.0)
    r = interp(tl.get("rotate", []), t, ("value",), (0.0,))
    if r:
        rot += r[0]
    tr = interp(tl.get("translate", []), t, ("x", "y"), (0.0, 0.0))
    if tr:
        x, y = x + tr[0], y + tr[1]
    sc = interp(tl.get("scale", []), t, ("x", "y"), (1.0, 1.0))
    if sc:
        sx, sy = sx * sc[0], sy * sc[1]
    return [x, y, rot, sx, sy]


def world_with(parent_w, local: list, inherit: str) -> tuple:
    """One bone's world matrix (a, b, c, d, x, y) from its parent's and its local (x, y, rot, sx, sy); no shear,
    skeleton scale 1. Mirrors spine-ts Bone.updateWorldTransformWith."""
    x, y, rotation, scaleX, scaleY = local
    if parent_w is None:
        rx, ry = math.radians(rotation), math.radians(rotation + 90)
        return (math.cos(rx) * scaleX, math.cos(ry) * scaleY, math.sin(rx) * scaleX, math.sin(ry) * scaleY, x, y)
    pa, pb, pc, pd, px, py = parent_w
    wx, wy = pa * x + pb * y + px, pc * x + pd * y + py
    if inherit == "normal":
        rx, ry = math.radians(rotation), math.radians(rotation + 90)
        la, lb, lc, ld = math.cos(rx) * scaleX, math.cos(ry) * scaleY, math.sin(rx) * scaleX, math.sin(ry) * scaleY
        return (pa * la + pb * lc, pa * lb + pb * ld, pc * la + pd * lc, pc * lb + pd * ld, wx, wy)
    if inherit == "onlyTranslation":
        rx, ry = math.radians(rotation), math.radians(rotation + 90)
        return (math.cos(rx) * scaleX, math.cos(ry) * scaleY, math.sin(rx) * scaleX, math.sin(ry) * scaleY, wx, wy)
    if inherit == "noRotationOrReflection":
        s = pa * pa + pc * pc
        if s > 0.0001:
            s = abs(pa * pd - pb * pc) / s
            pb, pd = pc * s, pa * s
            prx = math.degrees(math.atan2(pc, pa))
        else:
            pa = pc = 0.0
            prx = 90 - math.degrees(math.atan2(pd, pb))
        rx, ry = math.radians(rotation - prx), math.radians(rotation - prx + 90)
        la, lb, lc, ld = math.cos(rx) * scaleX, math.cos(ry) * scaleY, math.sin(rx) * scaleX, math.sin(ry) * scaleY
        return (pa * la - pb * lc, pa * lb - pb * ld, pc * la + pd * lc, pc * lb + pd * ld, wx, wy)
    # noScale / noScaleOrReflection
    r = math.radians(rotation)
    cos, sin = math.cos(r), math.sin(r)
    za, zc = pa * cos + pb * sin, pc * cos + pd * sin
    s = math.sqrt(za * za + zc * zc)
    if s > 0.00001:
        s = 1 / s
    za, zc = za * s, zc * s
    s = math.sqrt(za * za + zc * zc)
    if inherit == "noScale" and (pa * pd - pb * pc < 0):
        s = -s
    r = math.pi / 2 + math.atan2(zc, za)
    zb, zd = math.cos(r) * s, math.sin(r) * s
    la, lb, lc, ld = scaleX, 0.0, 0.0, scaleY          # shear 0: cos(0)*sx, cos(90)*sy, sin(0)*sx, sin(90)*sy
    return (za * la + zb * lc, za * lb + zb * ld, zc * la + zd * lc, zc * lb + zd * ld, wx, wy)


def _children(bones: list) -> dict:
    out = {}
    for b in bones:
        if "parent" in b:
            out.setdefault(b["parent"], []).append(b["name"])
    return out


def _descendants(name: str, kids: dict) -> list:
    out, stack = [], list(kids.get(name, []))
    while stack:
        n = stack.pop(0)
        out.append(n)
        stack.extend(kids.get(n, []))
    return out


def _ik1(world: dict, local: dict, bone: dict, target_w, c: dict, inherit: str) -> list:
    """spine-ts IkConstraint.apply1 for the 'normal' / noScale inherits; returns the bone's new local."""
    pa, pb, pc, pd, px, py = world[bone["parent"]]
    ax, ay, arot, sx, sy = local[bone["name"]]
    tx_w, ty_w = target_w[4], target_w[5]
    x, y = tx_w - px, ty_w - py
    d = pa * pd - pb * pc
    if abs(d) <= 0.0001:
        tx = ty = 0.0
    else:
        tx, ty = (x * pd - y * pb) / d - ax, (y * pa - x * pc) / d - ay
    rot_ik = -arot + math.degrees(math.atan2(ty, tx))
    if sx < 0:
        rot_ik += 180
    if rot_ik > 180:
        rot_ik -= 360
    elif rot_ik < -180:
        rot_ik += 360
    alpha = c.get("mix", 1.0)
    compress, stretch, uniform = c.get("compress", False), c.get("stretch", False), c.get("uniform", False)
    if compress or stretch:
        if inherit in ("noScale", "noScaleOrReflection"):
            bw = world[bone["name"]]
            tx, ty = tx_w - bw[4], ty_w - bw[5]
        bl = bone.get("length", 0.0) * sx
        if bl > 0.0001:
            dd = tx * tx + ty * ty
            if (compress and dd < bl * bl) or (stretch and dd > bl * bl):
                s = (math.sqrt(dd) / bl - 1) * alpha + 1
                sx *= s
                if uniform:
                    sy *= s
    return [ax, ay, arot + rot_ik * alpha, sx, sy]


def _transform(world: dict, bone: str, target_w, c: dict) -> None:
    """spine-ts TransformConstraint.applyAbsoluteWorld (no shear mix), in place on world[bone]."""
    ta, tb, tc, td, tx_, ty_ = target_w
    a, b, cc, d, wx, wy = world[bone]
    reflect = 1.0 if ta * td - tb * tc > 0 else -1.0
    mix_r = c.get("mixRotate", 1.0)
    mix_x = c.get("mixX", 1.0)
    mix_y = c.get("mixY", mix_x)
    mix_sx = c.get("mixScaleX", 1.0)
    mix_sy = c.get("mixScaleY", mix_sx)
    if mix_r != 0:
        r = math.atan2(tc, ta) - math.atan2(cc, a) + math.radians(c.get("rotation", 0.0)) * reflect
        if r > math.pi:
            r -= 2 * math.pi
        elif r < -math.pi:
            r += 2 * math.pi
        r *= mix_r
        cos, sin = math.cos(r), math.sin(r)
        a, b, cc, d = cos * a - sin * cc, cos * b - sin * d, sin * a + cos * cc, sin * b + cos * d
    if mix_x != 0 or mix_y != 0:
        ox, oy = c.get("x", 0.0), c.get("y", 0.0)
        px, py = ta * ox + tb * oy + tx_, tc * ox + td * oy + ty_
        wx += (px - wx) * mix_x
        wy += (py - wy) * mix_y
    if mix_sx != 0:
        s = math.hypot(a, cc)
        if s != 0:
            s = (s + (math.hypot(ta, tc) - s + c.get("scaleX", 0.0)) * mix_sx) / s
        a, cc = a * s, cc * s
    if mix_sy != 0:
        s = math.hypot(b, d)
        if s != 0:
            s = (s + (math.hypot(tb, td) - s + c.get("scaleY", 0.0)) * mix_sy) / s
        b, d = b * s, d * s
    world[bone] = (a, b, cc, d, wx, wy)


def pose_world(data: dict, anim: str | None, t: float, interp) -> dict:
    """World matrices per bone with inherit modes, IK (one-bone) and transform constraints."""
    bones = data["bones"]
    a = data["animations"].get(anim, {}) if anim else {}
    by = {b["name"]: b for b in bones}
    local = {b["name"]: _local(b, a.get("bones", {}).get(b["name"], {}), t, interp) for b in bones}
    world: dict = {}

    def pose(name):
        b = by[name]
        world[name] = world_with(world[b["parent"]] if "parent" in b else None, local[name], b.get("inherit", "normal"))
    for b in bones:
        pose(b["name"])
    kids = _children(bones)
    cons = [("ik", c) for c in data.get("ik", [])] + [("transform", c) for c in data.get("transform", [])]
    cons.sort(key=lambda kc: kc[1].get("order", 0))
    for kind, c in cons:
        tw = world[c["target"]]
        for bn in c["bones"]:
            if kind == "ik":
                if len(c["bones"]) != 1:
                    raise ValueError(f"ik {c['name']}: only one-bone IK is supported by spine_qa")
                local[bn] = _ik1(world, local, by[bn], tw, c, by[bn].get("inherit", "normal"))
                pose(bn)
            else:
                _transform(world, bn, tw, c)
            for dn in _descendants(bn, kids):
                pose(dn)
    return world


# ------------------------------------------------------------------ slot colours

def _rgba(hexs: str) -> tuple:
    return tuple(int(hexs[i:i + 2], 16) / 255 for i in (0, 2, 4, 6))


def slot_color(data: dict, slot: dict, anim: str | None, t: float):
    """(r, g, b, a) 0..1 for the slot at time t, or None when the slot has no colour at all (legacy: untouched)."""
    keys = data["animations"].get(anim, {}).get("slots", {}).get(slot["name"], {}).get("rgba", []) if anim else []
    if not keys and "color" not in slot:
        return None
    if not keys:
        return _rgba(slot["color"])
    times = [k.get("time", 0.0) for k in keys]
    if t <= times[0]:
        return _rgba(keys[0]["color"])
    for i in range(len(keys) - 1):
        if times[i] <= t < times[i + 1]:
            c0 = _rgba(keys[i]["color"])
            if keys[i].get("curve") == "stepped":
                return c0
            c1 = _rgba(keys[i + 1]["color"])
            u = (t - times[i]) / (times[i + 1] - times[i])
            return tuple(p + (q - p) * u for p, q in zip(c0, c1))
    return _rgba(keys[-1]["color"])


def tint(layer, color):
    """An RGBA PIL layer multiplied by a slot colour."""
    from PIL import Image
    if color is None or all(abs(c - 1) < 1e-6 for c in color):
        return layer
    arr = np.asarray(layer, dtype=np.float32) * np.array(color, dtype=np.float32)
    return Image.fromarray(np.clip(np.round(arr), 0, 255).astype(np.uint8), "RGBA")
