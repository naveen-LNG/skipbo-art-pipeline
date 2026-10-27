"""rig_props.py - props that are not in the master: a held flag, a hurdle on the ground (spine_rig.py stage 4c).

The master shows the character empty-handed, so a prop can't be placed by matching it onto the master the way a hat
or a tail is. Instead its points are given in a small file (`spine_rig.py --props props.json`) and the prop hangs
from a bone of its own, hidden in the setup pose; only the animation that uses it shows it (rig_anim: wave_flag,
jump_hurdle).

  {"flag":   {"image": "flag.png", "kind": "held", "grip": [x, y], "tip": [x, y], "length": 0.45},
   "hurdle": {"image": "hurdle.png", "kind": "ground", "base": [x, y], "height": 0.16, "front": 0.04}}

  {"can":    {"image": "can.png", "kind": "held", "grip": [x, y], "tip": [x, y], "length": 0.5, "use": "water"},
   "stream": {"image": "stream.png", "kind": "attached", "on": "can", "at": [x, y], "top": [x, y], "use": "water"},
   "plant":  {"stages": ["seed.png", "sprout.png", ...], "kind": "ground", "width": 0.3, "x": 0.5, "front": 0.03,
              "behind": true, "use": "grow"}}

Points are 0..1 of the prop image. A held prop: `grip` is where the fist closes on it, `tip` the far end of its stick;
`length` is grip-to-tip as a share of body height. Its bone `prop_<name>` is a child of the character's left hand
(the right without one) at the middle of the fist, pointing from grip to tip; its slot is drawn just behind the
hand, so the fist closes over the stick. A ground prop: `base` is its bottom middle, `height` its height as a share
of body height, `front` how far in front of the character it stands (share of body height, drawn that much lower);
its bone `prop_<name>` hangs from the root, and its slot is the last (in front), so an animation can move it behind
with a drawOrder key. Optional for a ground prop: `x` (share of body height to the viewer's right), `behind` (slot
first: drawn behind the character), and `stages` in place of `image`: images that replace each other on the one
slot (attachments `prop_<name>`, `prop_<name>_1`, ...), each placed at the middle of its bottom edge and scaled so
the base it stands on (the bottom tenth of the painting) is `width` wide; a growing plant on one soil mound.
An attached prop (a water stream on a can's spout): its bone hangs from the bone of the prop named by `on` at that
prop's image point `at`, with the prop's own image point `top` there, at the same scale as that prop (one sheet);
it keeps world-upright whatever the prop does (inherit noRotationOrReflection), so a stream always falls straight;
`fall` (default 1) is its length while it pours, as a share of the painting (water: it ends on the soil).
`use` names the animation a prop belongs to (rig_anim: water, grow); wave_flag and jump_hurdle take props without.

  props = rig_props.add(ex, bones, world, props_json, body_h_units, joints, bone_dir, unit)   # {name: info}
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from rig_image import solidify


def _angle(a, b) -> float:
    """World angle (degrees, y up) of image points a -> b (image y down)."""
    return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))


def add(ex, bones: list, world: dict, props_path: Path | None, body_h: float, joints: dict, bone_dir: dict,
        unit: float) -> dict:
    """Add each prop's bone, slot (no attachment at rest) and region attachment. bones / world as rig_bones.skeleton
    returns them (appended to); body_h: body height in Spine units; joints / bone_dir: master px (the hand's length);
    unit: Spine units per master px. Returns {name: {"kind", "bone", "slot", "parent", "attachment", ...}}."""
    if not props_path:
        return {}
    spec = json.loads(Path(props_path).read_text(encoding="utf-8"))
    out = {}
    names = [b["name"] for b in bones]
    base_dir = Path(props_path).parent
    for name, p in sorted(spec.items(), key=lambda kv: kv[1].get("kind") == "attached"):   # attached after their prop
        bone, slot, att = f"prop_{name}", f"prop_{name}", f"{ex.prefix}prop_{name}"
        if p.get("stages"):
            out[name] = _staged(ex, bones, world, p, base_dir, body_h, bone, slot, att)
            print(f"  prop {name}: {len(p['stages'])} stages on bone {bone} (hidden at rest)")
            continue
        # a held prop crosses the body: its whole anti-aliased rim takes the prop's own colour (trust 255), or the
        # sheet's grey left in it reads as a hairline over the sweater
        img = solidify(Image.open(base_dir / p["image"]), trust=255 if p.get("kind") in ("held", "attached") else None)
        W, H = img.size
        if p.get("kind") == "attached":
            on = out.get(p.get("on"))
            if on is None:
                print(f"  props: {name} needs the prop {p.get('on')}; skipped")
                continue
            s = on["scale"]
            ox, oy = (p["at"][0] - 0.5) * on["size"][0] * s, -(p["at"][1] - 0.5) * on["size"][1] * s   # parent image
            r = math.radians(on["region"]["rotation"])                       # centre -> the point, in its bone's frame
            bx, by = on["region"]["x"] + ox * math.cos(r) - oy * math.sin(r), on["region"]["y"] + ox * math.sin(r) + oy * math.cos(r)
            bones.append({"name": bone, "parent": on["bone"], "x": round(bx, 2), "y": round(by, 2), "rotation": 0.0,
                          "length": 0.0, "inherit": "noRotationOrReflection"})
            world[bone] = world[on["bone"]]
            t_ = [p["top"][0] * W, p["top"][1] * H]
            region = {"x": round((W / 2 - t_[0]) * s, 2), "y": round(-(H / 2 - t_[1]) * s, 2), "scaleX": round(s, 4),
                      "scaleY": round(s, 4), "rotation": 0.0, "width": W, "height": H}
            at = next(i for i, s_ in enumerate(ex.slots) if s_["name"] == on["slot"])
            ex.slots.insert(at, {"name": slot, "bone": bone})                 # just behind the prop it pours from
            out[name] = {"kind": "attached", "bone": bone, "slot": slot, "attachment": att, "on": p["on"],
                         "length": H * s}
        elif p.get("kind") == "held":
            side = "l" if "hand_l" in names else ("r" if "hand_r" in names else None)
            if side is None:
                print(f"  props: {name} needs a hand; skipped")
                continue
            hand = f"hand_{side}"
            g, t = [p["grip"][0] * W, p["grip"][1] * H], [p["tip"][0] * W, p["tip"][1] * H]
            stick_px = math.hypot(t[0] - g[0], t[1] - g[1])
            s = p.get("length", 0.45) * body_h / max(stick_px, 1.0)           # Spine units per prop image px
            img_deg = _angle(g, t)                                           # the stick's angle in the image
            hand_len = float((bone_dir[hand] ** 2).sum() ** 0.5) * unit
            (hx, hy), hrot = world[hand]
            # the bone: at the middle of the fist, along the hand (its own rotation is keyed by the animation)
            bx = hx + 0.5 * hand_len * math.cos(math.radians(hrot))
            by = hy + 0.5 * hand_len * math.sin(math.radians(hrot))
            bones.append({"name": bone, "parent": hand, "x": round(0.5 * hand_len, 2), "y": 0.0, "rotation": 0.0,
                          "length": round(stick_px * s, 1)})
            world[bone] = ((bx, by), hrot)
            # the attachment: the grip on the bone's origin, the stick along the bone's +x
            cx, cy = (W / 2 - g[0]) * s, -(H / 2 - g[1]) * s                 # image centre from the grip, world axes
            r = math.radians(-img_deg)
            region = {"x": round(cx * math.cos(r) - cy * math.sin(r), 2), "y": round(cx * math.sin(r) + cy * math.cos(r), 2),
                      "scaleX": round(s, 4), "scaleY": round(s, 4), "rotation": round(-img_deg, 2), "width": W, "height": H}
            at = next(i for i, s_ in enumerate(ex.slots) if s_["name"] == hand)
            ex.slots.insert(at, {"name": slot, "bone": bone})                 # just behind the fist
            out[name] = {"kind": "held", "bone": bone, "slot": slot, "parent": hand, "side": side, "attachment": att,
                         "hand_rest_deg": hrot, "img_deg": img_deg, "scale": s, "size": (W, H), "region": region}
        else:
            b_ = [p["base"][0] * W, p["base"][1] * H]
            s = p.get("height", 0.16) * body_h / max(b_[1], 1.0)              # base y = the prop's painted height
            front = p.get("front", 0.04) * body_h
            gx = p.get("x", 0.0) * body_h
            bones.append({"name": bone, "parent": "root", "x": round(gx, 2), "y": round(-front, 2), "rotation": 0.0, "length": 0.0})
            world[bone] = ((gx, -front), 0.0)
            region = {"x": round((W / 2 - b_[0]) * s, 2), "y": round((b_[1] - H / 2) * s, 2), "scaleX": round(s, 4),
                      "scaleY": round(s, 4), "rotation": 0.0, "width": W, "height": H}
            _ground_slot(ex, slot, bone, p)
            out[name] = {"kind": "ground", "bone": bone, "slot": slot, "attachment": att, "front": front, "x": gx,
                         "height": p.get("height", 0.16) * body_h}
        img.save(ex.out / "images" / f"{att}.png")
        ex.images.append(att)
        ex.skin[slot] = {att: region}
        out[name]["use"], out[name]["spec"] = p.get("use"), p
        print(f"  prop {name}: bone {bone} on {out[name].get('parent', out[name].get('on', 'root'))}, slot {slot} (hidden at rest)")
    return out


def _ground_slot(ex, slot: str, bone: str, p: dict):
    if p.get("behind"):
        ex.slots.insert(0, {"name": slot, "bone": bone})                      # behind the character
    else:
        ex.slots.append({"name": slot, "bone": bone})                         # in front; animations move it behind


def _staged(ex, bones: list, world: dict, p: dict, base_dir: Path, body_h: float, bone: str, slot: str, att: str) -> dict:
    """A ground prop whose `stages` replace each other on one slot (rig_props doc); returns its info, with
    `stages`: the attachment names in order and `heights`: each stage's height in Spine units."""
    front, gx = p.get("front", 0.04) * body_h, p.get("x", 0.0) * body_h
    bones.append({"name": bone, "parent": "root", "x": round(gx, 2), "y": round(-front, 2), "rotation": 0.0, "length": 0.0})
    world[bone] = ((gx, -front), 0.0)
    _ground_slot(ex, slot, bone, p)
    names, heights, ex.skin[slot] = [], [], {}
    for i, f in enumerate(p["stages"]):
        img = solidify(Image.open(base_dir / f))
        a = np.asarray(img)[..., 3] > 128
        ys, xs = np.nonzero(a)
        y0, y1 = ys.min(), ys.max()
        foot = a[max(y0, y1 - max(2, (y1 - y0) // 10)):y1 + 1]               # the base it stands on: its bottom tenth
        fx = np.nonzero(foot.any(0))[0]
        bx, bw = (fx.min() + fx.max()) / 2, fx.max() - fx.min() + 1
        s = p.get("width", 0.3) * body_h / bw
        W, H = img.size
        name = att if i == 0 else f"{att}_{i}"
        ex.skin[slot][name] = {"x": round((W / 2 - bx) * s, 2), "y": round((y1 - H / 2) * s, 2), "scaleX": round(s, 4),
                               "scaleY": round(s, 4), "rotation": 0.0, "width": W, "height": H}
        img.save(ex.out / "images" / f"{name}.png")
        ex.images.append(name)
        names.append(name)
        heights.append(float((y1 - y0) * s))
    return {"kind": "ground", "bone": bone, "slot": slot, "attachment": names[0], "stages": names, "heights": heights,
            "front": front, "x": gx, "height": max(heights), "use": p.get("use"), "spec": p}
