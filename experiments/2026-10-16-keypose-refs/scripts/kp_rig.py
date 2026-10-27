"""Key-pose bridge: rebuild the beaver's squat, plant_seed, jump_hurdle and wave_flag toward the key-pose references.

  uv run --with numpy --with pillow --with scipy scripts/kp_rig.py <base rig dir> <out rig dir>

The beaver rig has one trousers piece and no knees, so a squat could only squash the trousers. The references
(refs/*.png, Nano Banana Pro from the master, prompts/keyposes.env) show what the poses should look like; this
script takes from them:

* whole-legs drawings (legs/*.png, scripts/cut_legs.py): rest (the master's own legs), half (knees bending), crouch,
  tuck (in the air). They go in a new `legs` slot on a `legs` bone hung at the belt, upright, scaled by belt width.
  While one shows, the rig's own trousers and boots are hidden. A swap happens where the two drawings are the same
  height: the outgoing one squashes and the incoming one starts stretched by the same amount, then settles, and the
  hips drop by exactly the legs' lost height so the soles stay on the ground.
* the arm, head and body targets of each key pose (world angles read off the references; the flag frames mirrored,
  since the model put the flag in the other paw).
* the flag's cloth trailing the stick: the flag splits into a stick and a cloth on its own bone at the hinge, which
  lags the stick's swing and flutters.

Other animations are kept; drawOrder keys are remapped onto the new slot list.
"""
import json
import math
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "plugin/skills/skipbo-art/scripts"))
sys.path.insert(0, str(HERE))
from rig_anim import FPS_KEYS, hermite, smooth, track, wrap  # noqa: E402
from spine_qa import apply_offsets  # noqa: E402

EXP = HERE.parent
UNIT = 438.5 / ((0.875 - 0.6) * 2400)         # Spine units per master px: waist 0.6 -> hips bone y, ground 0.875 -> 0
MASTER_BUCKLE = (560 + 339.5, 1400 + 60)       # legs/master.png's buckle row centre, master px (cut_legs metrics)
MASTER_BELT_W = 679.0
TAIL_OUT = -30.0                                # deg the tail swings out (away from the body) in the full crouch

SHEETS = ("squat", "jump")    # legs/<sheet>_<1..5>.png: in-between drawings painted in one sheet (cut_sheet.py)
MIDS = {"squat": [34, 45], "jump": [23, 34]}   # legs/<sheet>_<ab>.png: in-betweens painted between drawings a and b (cut_mid.py)
PREV = bool(os.environ.get("KP_PREV"))         # rebuild the previous pass for comparison: no in-betweens, no cross-fades
BONES = os.environ.get("KP_LEGS") == "bones"   # skeleton-driven legs (scripts/leg_bones.py) instead of drawing swaps


def world_of_master(px, py):
    return (px - 896) * UNIT - 0.17, (2100 - py) * UNIT


def frames(T):
    return [i / FPS_KEYS for i in range(int(round(T * FPS_KEYS)) + 1)]


class Bridge:
    def __init__(self, base: Path, out: Path):
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(base, out, ignore=shutil.ignore_patterns("qa"))
        self.out = out
        self.path = next(out.glob("*.atlas")).with_suffix(".json")
        self.rig = json.loads(self.path.read_text())
        self.bones = {b["name"]: b for b in self.rig["bones"]}
        self.skin = self.rig["skins"][0]["attachments"]
        self.old_slots = [s["name"] for s in self.rig["slots"]]
        self.atlas = []
        self.metrics = {json.loads(l)["name"]: json.loads(l) for l in (EXP / "legs/metrics.jsonl").read_text().splitlines()}
        self.H = self.rig["skeleton"]["height"]

    # ---- images and slots
    def add_image(self, name: str, img: Image.Image):
        img.save(self.out / "images" / f"{name}.png")
        self.atlas.append(f"\nimages/{name}.png\nsize: {img.width},{img.height}\nfilter: Linear,Linear\n{name}\nbounds: 0,0,{img.width},{img.height}\n")

    def insert_slot(self, name: str, bone: str, after: str):
        i = [s["name"] for s in self.rig["slots"]].index(after)
        self.rig["slots"].insert(i + 1, {"name": name, "bone": bone})

    def add_bone(self, b: dict):
        """Appended: weighted meshes (the sleeves) name their bones by index."""
        self.rig["bones"].append(b)
        self.bones[b["name"]] = b

    # ---- legs
    def legs(self):
        """The in-between legs drawings in a `legs` slot on a `legs` bone at the rig's own buckle. One scale per sheet
        (a drawing-by-drawing scale would flicker): each sheet's first drawing is the rest legs (prompted so), and it is
        fitted to cover the rig's rest trousers and boots exactly (their width and buckle-to-soles height)."""
        rest = json.loads((EXP / "legs/rig_rest.json").read_text())
        hips = self.bones["hips"]
        hr = math.radians(hips["rotation"])
        bx, by = rest["buckle_world"]
        dx, dy = bx - hips["x"], by - hips["y"]                      # buckle in the hips bone's frame
        lx, ly = dx * math.cos(-hr) - dy * math.sin(-hr), dx * math.sin(-hr) + dy * math.cos(-hr)
        for s_, after in (("legs_a", "hips"), ("legs_b", "legs_a")):    # two slots: a swap cross-fades between them
            self.add_bone({"name": s_, "parent": "hips", "x": round(lx, 2), "y": round(ly, 2), "rotation": round(-hips["rotation"], 2)})
            self.insert_slot(s_, s_, after)
            self.skin[s_] = {}
        self.leg_h = {"rig": rest["height"]}
        self.sheet_scales = {}
        for sheet in SHEETS:
            ms = {i: self.metrics[f"{sheet}_{i}"] for i in list(range(1, 6)) + MIDS[sheet]}
            sx, sy = rest["belt_w"] / ms[1]["belt_w"], rest["height"] / (ms[1]["sole_y"] - ms[1]["buckle_y"])
            self.sheet_scales[sheet] = (sx, sy)
            for i, m in ms.items():
                v = f"{sheet[0]}{i}"
                img = Image.open(EXP / f"legs/{sheet}_{i}.png")
                name = f"beaver_legs_{v}"
                self.add_image(name, img)
                cx, cy = img.width / 2, img.height / 2
                for s_ in ("legs_a", "legs_b"):
                    self.skin[s_][name] = {"x": round((cx - m["belt_top"][0]) * sx, 2), "y": round(-(cy - m["buckle_y"]) * sy, 2),
                                           "scaleX": round(sx, 5), "scaleY": round(sy, 5), "width": img.width, "height": img.height}
                self.leg_h[v] = m.get("height_px", m["sole_y"] - m["buckle_y"]) * sy
        print("leg heights (units):", {k_: round(v_, 1) for k_, v_ in self.leg_h.items()})
        if BONES:
            from leg_bones import LegBones
            self.lb = LegBones(self, self.sheet_scales)

    SEQ = {"squat": ["rig", "s3", "s34", "s4", "s45", "s5"],        # each sheet's drawings in order of progress (0 .. 1);
           "jump": ["rig", "j2", "j23", "j3", "j34", "j4", "j5"]}   # drawing 1 is the rest legs: the rig's own parts show
    if PREV:
        SEQ = {"squat": ["rig", "s3", "s4", "s5"], "jump": ["rig", "j2", "j3", "j4", "j5"]}
    if BONES:                                          # bones interpolate: only the key poses' joints, no in-betweens
        SEQ = {"squat": ["rig", "s4", "s5"], "jump": ["rig", "j34", "j5"]}

    def leg_track(self, an: dict, T: float, segs: list, lift=lambda t: 0.0, air=lambda t: 0.0):
        """Frame-by-frame legs driven by progress. segs: [(sheet, [(t, p), ...])], consecutive, each starting where
        the last ends, all at p = 0 at the joins (both sheets show the rest legs there, at the same height). Per
        sheet, p(t) runs smoothly through its keys (flat at each key: holds read as poses); the drawing shown is the
        nearest in progress, so swaps happen at evenly spaced p; the legs' height follows a smooth (Catmull-Rom)
        curve through the drawings' natural heights over p, and the shown drawing is squashed / stretched to it, by
        at most half a step. On the ground the hips drop by the lost height, so the soles stay put; in the air
        (air(t) -> 1) the body rides lift(t) alone and the legs fold under it."""
        rest_h = self.leg_h["rig"]
        curves = []
        for sheet, keys in segs:
            seq = self.SEQ[sheet]
            hs = [self.leg_h[v] for v in seq]
            n = len(seq) - 1
            pts = [(i / n, h, 0.0) for i, h in enumerate(hs)]
            for i in range(1, n):                        # Catmull-Rom slopes over p, flat where the height turns
                if (hs[i + 1] - hs[i]) * (hs[i] - hs[i - 1]) > 0:
                    pts[i] = (i / n, hs[i], 0.5 * (hs[i + 1] - hs[i - 1]) * n)
            curves.append((keys[0][0], keys[-1][0], seq, keyed(keys), hermite(pts)))

        def at(t):
            for t0, t1, seq, p, h in curves:
                if t <= t1 + 1e-9 or (t0, t1) == curves[-1][:2]:
                    pp = min(1.0, max(0.0, p(t)))
                    return seq[int(round(pp * (len(seq) - 1)))], h(pp)

        def at_p(t):
            for t0, t1, seq, p, h in curves:
                if t <= t1 + 1e-9 or (t0, t1) == curves[-1][:2]:
                    return seq, min(1.0, max(0.0, p(t)))
        if BONES:
            height = self.lb.track(an, T, segs, at_p, frames, lift, air, TAIL_OUT, track)
            return height, []
        ts = frames(T)
        shown = [at(t_)[0] for t_ in ts]
        height = lambda t: at(t)[1]
        an.setdefault("bones", {})["hips"] = {"translate": [
            {"time": round(t_, 4), "x": 0.0, "y": round((height(t_) - rest_h) * (1 - air(t_)) + lift(t_), 2)} for t_ in ts]}
        crouch_drop = rest_h - self.leg_h["s5"]               # the tail swings out flat as the body sinks
        an["bones"]["tail"] = {"rotate": track(lambda t: TAIL_OUT * min(1.0, max(0.0, rest_h - height(max(0.0, t - 0.06))) / crouch_drop), T)}
        plan = [(ts[i], v) for i, v in enumerate(shown) if i == 0 or v != shown[i - 1]]
        self.cross_fade(an, T, plan, height)
        return height, plan

    FADE = 0.0 if PREV else 2 / 30                     # s: the incoming drawing fades in over this, then the outgoing out

    def cross_fade(self, an: dict, T: float, plan: list, height):
        """Show the plan's drawings with a cross-fade at every swap: the incoming drawing (in the other legs slot, or
        the rig's own trousers and boots for "rig") fades in over FADE before the swap, then the outgoing one fades
        out over FADE after it, so one drawing is always opaque and nothing pops. Each legs slot has its own bone,
        scaled so its drawing has the legs' height at every frame."""
        groups = {"rig": ["hips", "boot_l", "boot_r"], "a": ["legs_a"], "b": ["legs_b"]}
        shows = []                                     # (group, drawing, visible from, to)
        nxt = "a"
        for i, (t0, v) in enumerate(plan):
            t1 = plan[i + 1][0] if i + 1 < len(plan) else T
            g = "rig" if v == "rig" else nxt
            if g != "rig":
                nxt = "b" if g == "a" else "a"
            shows.append([g, v, t0, t1])
        keys = {g: {"rgba": []} for g in groups}
        windows = {g: [] for g in groups}
        for i, (g, v, t0, t1) in enumerate(shows):
            d_in = 0.0 if i == 0 else min(self.FADE, 0.5 * (t0 - shows[i - 1][2]))
            d_out = 0.0 if i == len(shows) - 1 else min(self.FADE, 0.5 * (shows[i + 1][3] - t1))
            a0, a1 = max(0.0, t0 - d_in), min(T, t1 + d_out)
            windows[g].append((a0, a1, v))
            keys[g]["rgba"] += [(a0, 0.0 if d_in else 1.0), (t0, 1.0), (t1, 1.0), (a1, 0.0 if d_out else 1.0)]
        for g, slots in groups.items():
            ws = windows[g]
            att = []
            for (a0, a1, v), nxt_w in zip(ws, ws[1:] + [None]):
                att.append((a0, v))
                if nxt_w is None or nxt_w[0] > a1 + 1e-6:
                    att.append((a1, None))
            if not ws or ws[0][0] > 0:
                att.insert(0, (0.0, None))
            rgba = sorted(keys[g]["rgba"])
            for s_ in slots:
                rest_att = f"beaver_{s_}" if g == "rig" else None
                ak = [{"time": round(t_, 4), "name": (rest_att if g == "rig" else f"beaver_legs_{v}") if v else None} for t_, v in att]
                if g == "rig":
                    ak.append({"time": T, "name": rest_att})
                an.setdefault("slots", {})[s_] = {"attachment": ak,
                                                  "rgba": [{"time": round(t_, 4), "color": "ffffff%02x" % round(255 * a_)} for t_, a_ in rgba] or [{"time": 0, "color": "ffffffff"}]}
                if g == "rig":
                    an["slots"][s_]["rgba"].append({"time": T, "color": "ffffffff"})
            if g != "rig":                              # this slot's bone: its drawing at the legs' height
                def own(t_, ws=ws):
                    for a0, a1, v in ws:
                        if a0 - 1e-6 <= t_ <= a1 + 1e-6:
                            return v
                    return None
                bone = slots[0]
                an.setdefault("bones", {})[bone] = {"scale": [{"time": round(t_, 4), "x": 1.0, "y": round(height(t_) / self.leg_h[own(t_)], 4) if own(t_) else 1.0} for t_ in frames(T)]}

    # ---- flag
    def flag(self):
        att = self.skin["prop_flag"]["beaver_prop_flag"]
        img = Image.open(self.out / "images/beaver_prop_flag.png").convert("RGBA")
        a = np.asarray(img).astype(np.float32)
        r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
        mx, mn = a[..., :3].max(-1), a[..., :3].min(-1)
        sat = (mx - mn) / (mx + 1e-6)
        cloth = (al > 10) & (sat < 0.22) & (mx > 150)
        from scipy import ndimage as ndi
        cloth = ndi.binary_opening(cloth, iterations=2)
        lab, n = ndi.label(cloth)
        cloth = lab == (np.argmax(ndi.sum(cloth, lab, range(1, n + 1))) + 1)
        cloth = ndi.binary_fill_holes(cloth)
        cut_ = ndi.binary_dilation(cloth, iterations=3) & ~(sat > 0.3)          # the stick keeps its own brown edge
        cl = np.asarray(img).copy()
        st = cl.copy()
        cl[..., 3] = np.where(cloth, cl[..., 3], 0)
        st[..., 3] = np.where(cut_, 0, st[..., 3])
        self.add_image("beaver_prop_flag", Image.fromarray(st, "RGBA"))
        self.atlas.pop()                                              # already in the atlas
        self.add_image("beaver_prop_cloth", Image.fromarray(cl, "RGBA"))
        # hinge: the middle of the cloth's edge along the stick (its leftmost columns)
        ys, xs = np.nonzero(cloth)
        edge = xs < xs.min() + 0.08 * (xs.max() - xs.min())
        v = ys[edge].mean()
        row = np.nonzero((al[int(v)] > 127) & ~cloth[int(v)] & (sat[int(v)] > 0.3))[0]   # the stick at that height
        u = row.mean() if len(row) else xs[edge].mean()
        self.cloth_far = (xs.max(), ys[xs > xs.max() - 20].mean())
        rr = math.radians(att.get("rotation", 0))
        px, py = (u - att["width"] / 2) * att["scaleX"], (att["height"] / 2 - v) * att["scaleY"]
        hx, hy = att["x"] + px * math.cos(rr) - py * math.sin(rr), att["y"] + px * math.sin(rr) + py * math.cos(rr)
        self.add_bone({"name": "prop_cloth", "parent": "prop_flag", "x": round(hx, 2), "y": round(hy, 2)})
        self.insert_slot("prop_cloth", "prop_cloth", "prop_flag")
        self.skin["prop_cloth"] = {"beaver_prop_cloth": dict(att, x=round(att["x"] - hx, 2), y=round(att["y"] - hy, 2))}
        print(f"cloth hinge at {u:.0f},{v:.0f} px; bone ({hx:.0f}, {hy:.0f})")

    # ---- draw order remap
    def remap_draw_order(self, keep_new: set):
        new = [s["name"] for s in self.rig["slots"]]
        anchor = {n: new[new.index(n) - 1] for n in new if n not in self.old_slots}
        for name, an in self.rig["animations"].items():
            if name in keep_new:
                continue
            for k in an.get("drawOrder", []):
                if "offsets" not in k:
                    continue
                order = apply_offsets(self.old_slots, k["offsets"])
                for n, a_ in anchor.items():
                    order.insert(order.index(a_) + 1, n)
                k["offsets"] = [{"slot": n, "offset": order.index(n) - i} for i, n in enumerate(new) if order.index(n) != i]

    def save(self):
        self.path.write_text(json.dumps(self.rig, indent=1))
        atlas = next(self.out.glob("*.atlas"))
        atlas.write_text(atlas.read_text().rstrip("\n") + "\n" + "".join(self.atlas))


# ------------------------------------------------------------------ animations

def rest_angles(br: Bridge) -> dict:
    """World angles of the arm bones at rest (degrees, y up)."""
    out, acc = {}, {}
    for b in br.rig["bones"]:
        acc[b["name"]] = acc.get(b.get("parent"), 0.0) + b.get("rotation", 0.0)
    for s in ("l", "r"):
        for p in ("upperarm", "forearm", "hand"):
            out[f"{p}_{s}"] = acc[f"{p}_{s}"]
    out["torso"], out["head_base"] = acc["torso"], acc["head_base"]
    return out


def keyed(points):
    """A smooth curve through (time, value) keys, flat at each key (holds read as poses)."""
    return hermite([(t, v, 0.0) for t, v in points])


def arm_tracks(an, rest, side, ua_keys, fa_keys, hand_keys=None):
    """ua_keys / fa_keys: [(t, world angle or None = rest)]; rotations are deltas against the rest pose (the forearm's
    delta is relative to its parent's)."""
    ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
    du = keyed([(t, 0.0 if a is None else wrap(a - rest[ua])) for t, a in ua_keys])
    dfw = keyed([(t, 0.0 if a is None else wrap(a - rest[fa])) for t, a in fa_keys])
    T = max(t for t, _ in ua_keys)
    an["bones"][ua] = {"rotate": track(du, T)}
    an["bones"][fa] = {"rotate": track(lambda t: dfw(t) - du(t), T)}
    if hand_keys:                                     # the paw straight on the forearm (or as keyed), world deltas
        dh = keyed([(t, 0.0 if a is None else wrap(a - rest[hd])) for t, a in hand_keys])
        an["bones"][hd] = {"rotate": track(lambda t: dh(t) - dfw(t), T)}


def mirror(a):
    return None if a is None else 180.0 - a


def faces(an, keys, T):
    an.setdefault("slots", {})["head"] = {"attachment": [{"time": t, "name": f"beaver_head_{e}"} for t, e in keys] + [{"time": T, "name": "beaver_head_neutral"}]}


def squat(br: Bridge, rest: dict):
    """squat (2.0 s): knees bend out (half), sink into the crouch, hold, come back up. Arms hang down beside the
    knees in the crouch (hurdle_crouch), head level."""
    T = 2.0
    an = {"bones": {}}
    br.leg_track(an, T, [("squat", [(0, 0), (0.08, 0), (0.7, 1), (1.3, 1), (1.9, 0), (T, 0)])])
    down = [(0, None), (0.35, None), (0.75, -56.0), (1.3, -56.0), (1.75, None), (T, None)]       # paws beside the
    fdown = [(0, None), (0.35, None), (0.75, -80.0), (1.3, -80.0), (1.75, None), (T, None)]      # knees, clear of the body
    arm_tracks(an, rest, "l", down, fdown)
    arm_tracks(an, rest, "r", [(t, mirror(a)) for t, a in down], [(t, mirror(a)) for t, a in fdown])
    an["bones"]["head_base"] = {"rotate": track(keyed([(0, 0), (0.7, -2.5), (1.35, -2.5), (1.9, 0), (T, 0)]), T)}
    return an


def plant_seed(br: Bridge, rest: dict):
    """plant_seed (2.8 s, plant_mid / plant_low): knees bend, a seed pinched in the left paw (picture right), sink
    into a deep crouch, the arm reaches down and out to the soil and presses the seed in, the other paw on its knee,
    eyes on the spot; back up, delighted."""
    T = 2.8
    an = {"bones": {}}
    br.leg_track(an, T, [("squat", [(0, 0), (0.1, 0), (0.8, 1), (1.85, 1), (2.5, 0), (T, 0)])])
    # working arm: out and down to the mound (plant_low: upper arm -60, forearm -75), a little press at 1.3 s
    arm_tracks(an, rest, "l", [(0, None), (0.3, -55.0), (0.85, -58.0), (1.3, -62.0), (1.6, -58.0), (2.25, None), (T, None)],
               [(0, None), (0.3, -60.0), (0.85, -72.0), (1.3, -82.0), (1.6, -74.0), (2.25, None), (T, None)])
    # other arm: elbow out, paw on the knee (plant_low: upper arm out-left a little down, forearm down-right)
    arm_tracks(an, rest, "r", [(0, None), (0.4, None), (0.85, -142.0), (1.75, -142.0), (2.2, None), (T, None)],
               [(0, None), (0.4, None), (0.85, -74.0), (1.75, -74.0), (2.2, None), (T, None)])   # the sleeve mesh folds to ~70 deg
    an["bones"]["head_base"] = {"rotate": track(keyed([(0, 0), (0.6, -5.0), (1.75, -6.5), (2.3, 0), (T, 0)]), T)}
    an["bones"]["torso"] = {"rotate": track(keyed([(0, 0), (0.7, -2.0), (1.75, -2.0), (2.3, 0), (T, 0)]), T)}
    an["slots"]["hand_l"] = {"attachment": [{"time": 0, "name": "beaver_hand_l"}, {"time": 0.25, "name": "beaver_hand_l_grip"},
                                            {"time": 1.35, "name": "beaver_hand_l_open"}, {"time": 2.2, "name": "beaver_hand_l"}]}
    faces(an, [(0, "neutral"), (0.3, "happy"), (1.4, "laugh"), (2.4, "happy")], T)
    # the tail lies out flat behind while down (plant_low), further than the squat's: the torso leans over it
    an["bones"]["tail"] = {"rotate": track(keyed([(0, 0), (0.85, 1.35 * TAIL_OUT), (1.85, 1.35 * TAIL_OUT), (2.35, 0), (T, 0)]), T)}
    an["events"] = [{"time": 1.3, "name": "seed"}]
    return an


def jump_hurdle(br: Bridge, rest: dict):
    """jump_hurdle (2.9 s, hurdle_crouch / hurdle_air / hurdle_land): sink into a crouch behind the hurdle with the
    arms down and hold it a beat, spring (legs straight), tuck the knees up into a diamond over the bar with the arms
    flung up, reach the legs down, land in a deep crouch on the near side (a little lower and bigger), arms out at
    shoulder height, recover. A plan entry repeating the drawing is a hold."""
    T, apex = (3.1 if BONES else 2.9), 1.32
    an = {"bones": {}}
    H = br.H
    jump = hermite([(0, 0, 0), (0.8, 0, 0), (apex, 0.2 * H, 0), (1.82, 0, 0), (T, 0, 0)])
    near = hermite([(0, 0, 0), (0.85, 0, 0), (1.82, 1, 0), (T, 1, 0)])
    segs = [("squat", [(0, 0), (0.06, 0), (0.5, 1), (0.6, 1), (1.02, 0)]),           # sink, hold, rise to straight
            ("jump", [(1.02, 0), (apex + 0.04 if BONES else apex, 1), (1.46 if BONES else 1.4, 1), (1.76 if BONES else 1.74, 0)]),  # push off, tuck (hold); reach down
            ("squat", [(1.76 if BONES else 1.74, 0), (2.3, 1), (2.4, 1), (3.0 if BONES else 2.84, 0), (T, 0)])]           # land, absorb, recover
    air = lambda t: smooth(t, 0.8, 1.22) * (1 - smooth(t, 1.56, 1.94))
    height, _ = br.leg_track(an, T, segs, lift=lambda t: jump(t) - 0.06 * H * near(t), air=air)
    an["bones"]["root"] = {"scale": [{"time": round(t, 4), "x": round(1 + 0.08 * near(t), 4), "y": round(1 + 0.08 * near(t), 4)} for t in frames(T)]}
    an["bones"]["prop_hurdle"] = {"scale": [{"time": round(t, 4), "x": round(1 / (1 + 0.08 * near(t)), 4), "y": round(1 / (1 + 0.08 * near(t)), 4)} for t in frames(T)]}
    # arms: down beside the knees in the crouch, flung up at the apex, out at shoulder height on landing
    ua = [(0, None), (0.36, -58.0), (0.72, -57.0), (apex + 0.16, 45.0), (1.76, 35.0), (2.16, 12.0), (2.8, None), (T, None)]
    fa = [(0, None), (0.36, -82.0), (0.72, -81.0), (apex + 0.16, 62.0), (1.76, 50.0), (2.16, 22.0), (2.8, None), (T, None)]
    arm_tracks(an, rest, "l", ua, fa)
    arm_tracks(an, rest, "r", [(t, mirror(a)) for t, a in ua], [(t, mirror(a)) for t, a in fa])
    an["slots"]["hand_l"] = {"attachment": [{"time": 0, "name": "beaver_hand_l"}, {"time": 0.88, "name": "beaver_hand_l_open"}, {"time": 2.35, "name": "beaver_hand_l"}]}
    an["slots"]["hand_r"] = {"attachment": [{"time": 0, "name": "beaver_hand_r"}, {"time": 0.88, "name": "beaver_hand_r_open"}, {"time": 2.35, "name": "beaver_hand_r"}]}
    an["bones"]["head_base"] = {"rotate": track(keyed([(0, 0), (0.55, 3.0), (apex, -2.0), (1.7, 2.0), (2.2, 0), (T, 0)]), T)}
    # the tail out flat in the crouches, trailing low on the way up, flicking up at the apex (keyed, not from the legs)
    an["bones"]["tail"] = {"rotate": track(keyed([(0, 0), (0.55, TAIL_OUT), (0.9, -8), (apex, 14), (1.55, 0), (1.85, TAIL_OUT),
                                                  (2.05, 0.6 * TAIL_OUT), (2.45, 0), (T, 0)]), T)}
    faces(an, [(0, "neutral"), (0.3, "surprised"), (0.95, "laugh"), (2.4, "happy")], T)
    an["slots"]["prop_hurdle"] = {"attachment": [{"time": 0, "name": "beaver_prop_hurdle"}]}
    order = [s_["name"] for s_ in br.rig["slots"]]
    an["drawOrder"] = [{"time": 0}, {"time": apex, "offsets": [{"slot": "prop_hurdle", "offset": -order.index("prop_hurdle")}]}]
    return an


def wave_flag(br: Bridge, rest: dict):
    """wave_flag (3.6 s, flag_out / flag_in, mirrored): the left fist (picture right) holds the flag up, the arm
    raised high above the shoulder; it sweeps the stick from leaning out to leaning over the head and back, twice;
    the cloth trails the swing and flutters; the other paw on the hip, the head tipped up to the flag."""
    T = 3.6
    an = {"bones": {}}
    up = lambda t: smooth(t, 0.0, 0.8) * (1 - smooth(t, 2.8, 3.6))
    sw = lambda t: smooth(t, 0.55, 1.15) * (1 - smooth(t, 2.3, 3.0)) * math.sin(2 * math.pi * 0.9 * (t - 0.75))
    # raised arm: upper arm ~72 deg, forearm ~95 (near vertical), swinging +-14 at the elbow and +-12 at the wrist
    # (the wrist a little behind: drag)
    ua_t, fa_t = 55.0, 80.0                          # the fist above the shoulder, beside the head (not over the ear)
    d_ua = wrap(ua_t - rest["upperarm_l"])
    d_fa = wrap(fa_t - rest["forearm_l"])
    an["bones"]["upperarm_l"] = {"rotate": track(lambda t: d_ua * up(t) + 5 * sw(t), T)}
    an["bones"]["forearm_l"] = {"rotate": track(lambda t: (d_fa - d_ua) * up(t) + 12 * sw(t), T)}
    hand_hold = 88.0
    d_hd = wrap(hand_hold - rest["hand_l"])
    an["bones"]["hand_l"] = {"rotate": track(lambda t: (d_hd - d_fa) * up(t) + 12 * sw(max(0.0, t - 0.08)), T)}
    # the stick: at rest upright beside the fist (as the old wave_flag), in the raised fist leaning a little out
    flag_b = br.bones["prop_flag"]
    c_rest = 90.0 - rest["hand_l"] - flag_b.get("rotation", 0)
    c_hold = 86.0 - hand_hold - flag_b.get("rotation", 0)
    an["bones"]["prop_flag"] = {"rotate": track(lambda t: wrap(c_rest + wrap(c_hold - c_rest) * up(t)), T)}
    # stick world angle velocity drives the cloth's lag (it trails the swing), plus flutter
    stick = lambda t: 5 * sw(t) + 12 * sw(t) + 12 * sw(max(0.0, t - 0.08))
    vel = lambda t: (stick(t + 0.02) - stick(t - 0.02)) / 0.04
    an["bones"]["prop_cloth"] = {
        "rotate": track(lambda t: -0.03 * vel(t - 0.06) + 1.5 * math.sin(2 * math.pi * 2.2 * t) * up(t), T),   # small: it hinges on the stick
        "scale": [{"time": round(t, 4), "x": 1.0, "y": round(1 - 0.12 * (0.5 - 0.5 * math.cos(2 * math.pi * 2.2 * t)) - 0.25 * min(1.0, abs(vel(t - 0.06)) / 150) * up(t), 4)} for t in frames(T)]}
    # other arm: paw on the hip, elbow out (mirrored flag refs: upper arm -145, forearm -30)
    arm_tracks(an, rest, "r", [(0, None), (0.25, None), (0.85, -128.0), (2.75, -128.0), (3.4, None), (T, None)],
               [(0, None), (0.25, None), (0.85, -62.0), (2.75, -62.0), (3.4, None), (T, None)])
    an["bones"]["head_base"] = {"rotate": track(lambda t: 5 * up(t) + 2 * sw(t - 0.15), T)}
    an["bones"]["torso"] = {"rotate": track(lambda t: 2 * up(t) + 1.2 * sw(t - 0.1), T)}
    an["slots"] = {"prop_flag": {"attachment": [{"time": 0, "name": "beaver_prop_flag"}]},
                   "prop_cloth": {"attachment": [{"time": 0, "name": "beaver_prop_cloth"}]},
                   "hand_l": {"attachment": [{"time": 0, "name": "beaver_hand_l_fist"}, {"time": T, "name": "beaver_hand_l_fist"}]},
                   "hand_r": {"attachment": [{"time": 0, "name": "beaver_hand_r"}, {"time": 0.5, "name": "beaver_hand_r_fist"}, {"time": 3.1, "name": "beaver_hand_r"}]}}
    faces(an, [(0, "neutral"), (0.35, "happy"), (1.2, "laugh"), (2.6, "happy"), (3.2, "neutral")], T)
    return an


def main(base: Path, out: Path):
    br = Bridge(base, out)
    br.legs()
    br.flag()
    rest = rest_angles(br)
    new = {"squat": squat, "plant_seed": plant_seed, "jump_hurdle": jump_hurdle, "wave_flag": wave_flag}
    br.remap_draw_order(set(new))
    for name, fn in new.items():
        br.rig["animations"][name] = fn(br, rest)
    br.save()
    print("wrote", br.path)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
