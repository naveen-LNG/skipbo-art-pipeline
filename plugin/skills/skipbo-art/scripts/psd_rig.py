#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow", "psd-tools"]
# ///
"""psd_rig.py - a Spine 4.2 rig straight from a layered PSD (parts already cut and placed by an artist).

  uv run psd_rig.py bear.psdrig.json --out rig/
  (or: pip install numpy pillow psd-tools; python psd_rig.py ...)

Use this instead of spine_rig.py when the character arrives as a layered PSD: every layer is already a part in its
place and draw order, so nothing is generated or matched. The config maps PSD layers to parts and bones:

  {"character": "bear", "psd": "Bear.psd",
   "layers": {"11": {"part": "torso", "bone": "torso"}, "24": {"part": "lid_r", "bone": "head", "hidden": true},
              "27": {"part": "shovel", "bone": "tool", "tool": true}, ...},
   "extra_tools": {"hammer": {"image": "hammer.png", "length": 300}},
   "joints": {"shoulder_l": [690, 410]}}                     # optional overrides, PSD px

Layer keys are 1-based indices over the PSD's leaf layers, bottom first (psd_rig.py --list prints them). Part names
follow the pipeline: torso, hips, head, upperarm/forearm/hand/leg/foot + _l/_r (_l = the character's left = the
picture's right), plus jaw (mouth), muzzle, mustache, hat, brows, lid_l/lid_r (closed eyes, hidden at rest),
pupil_l/pupil_r, shadow. Tools ("tool": true, or extra_tools: images with a white or transparent background) hang
on a "tool" bone in hand_l's grip, hidden at rest and shown by their animation. Long two-handed tools (the shovel)
take both paws: Kin.reach (two-bone IK) puts each paw on the handle and the dig is keyed by where the top paw is.
Optional "props" ({"dirt_mound": {"image", "width"}, "dirt_clod": {...}}) give the dig a pile and a thrown clod.

Joints come from where layers overlap (elbow = centre of forearm over upperarm, and so on; shoulders sit on the
upper arm's long axis, a third in from its hidden end); override any of them under "joints".

Writes rig/<name>.json (bones, slots, skin, animations idle, cheer, talk and one <tool> animation per tool, baked
at 30 fps so spine_qa.py renders what the player plays), rig/<name>.atlas, rig/images/*.png, rig/preview.html,
rig/joints.png (debug: every joint on the master), rig/master.png and rig/report.json (master_frame for spine_qa).
Then: uv run spine_qa.py rig/<name>.json --master rig/master.png
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import rig_output

FPS = 30
ALPHA = 128


# ------------------------------------------------------------------ PSD

def leaf_layers(psd):
    return [l for l in psd.descendants() if not l.is_group()]


def load_parts(cfg: dict, base: Path):
    """{part: {"img", "bbox", "bone", "hidden", "tool", "order"}} in PSD order, plus the full-canvas composite."""
    from psd_tools import PSDImage
    psd = PSDImage.open(resolve(cfg["psd"], base))
    leaves = leaf_layers(psd)
    parts = {}
    for key, spec in cfg["layers"].items():
        layer = leaves[int(key) - 1]
        img = layer.composite()
        if img is None:
            raise SystemExit(f"layer {key} {layer.name!r} is empty")
        parts[spec["part"]] = {"img": img.convert("RGBA"), "bbox": tuple(layer.bbox), "bone": spec["bone"],
                               "hidden": spec.get("hidden", False), "tool": spec.get("tool", False),
                               "order": int(key), "layer": layer.name}
    master = psd.composite().convert("RGBA")
    return dict(sorted(parts.items(), key=lambda kv: kv[1]["order"])), master


def resolve(p: str, base: Path) -> Path:
    q = Path(p)
    return q if q.is_absolute() else base / q


def key_white(img: Image.Image) -> Image.Image:
    """Transparent background for a tool painted on white: border-connected near-white pixels go, edges soften."""
    a = np.asarray(img.convert("RGBA")).copy()
    if a[..., 3].min() < 250:                                   # already cut out
        return img.convert("RGBA")
    light = a[..., :3].min(2) > 232
    bg = np.zeros(light.shape, bool)
    stack = [(y, x) for y in (0, light.shape[0] - 1) for x in range(light.shape[1])]
    stack += [(y, x) for x in (0, light.shape[1] - 1) for y in range(light.shape[0])]
    while stack:
        y, x = stack.pop()
        if bg[y, x] or not light[y, x]:
            continue
        bg[y, x] = True
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < bg.shape[0] and 0 <= xx < bg.shape[1] and not bg[yy, xx] and light[yy, xx]:
                stack.append((yy, xx))
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    # one-pixel feather against the removed background
    m = Image.fromarray(alpha).filter(ImageFilter.MinFilter(3))
    a[..., 3] = (np.asarray(m).astype(np.uint16) + alpha) // 2
    out = Image.fromarray(a)
    return out.crop(out.getbbox())


def mask(part: dict, size) -> np.ndarray:
    """Part alpha on the full PSD canvas (bool)."""
    full = np.zeros((size[1], size[0]), bool)
    x0, y0, x1, y1 = part["bbox"]
    a = np.asarray(part["img"])[..., 3] > ALPHA
    full[y0:y0 + a.shape[0], x0:x0 + a.shape[1]] = a[: size[1] - y0, : size[0] - x0]
    return full


def centroid(m: np.ndarray):
    ys, xs = np.nonzero(m)
    return (float(xs.mean()), float(ys.mean())) if len(xs) else None


def axis(m: np.ndarray):
    """Principal axis of a mask: (centre, unit direction, (min, max) projections)."""
    ys, xs = np.nonzero(m)
    p = np.stack([xs, ys], 1).astype(float)
    c = p.mean(0)
    w, v = np.linalg.eigh(np.cov((p - c).T))
    d = v[:, np.argmax(w)]
    s = (p - c) @ d
    return c, d, (float(s.min()), float(s.max()))


# ------------------------------------------------------------------ skeleton

def joints(parts: dict, size, over: dict) -> dict:
    """PSD-px pivots for every bone that has parts, from layer overlaps (see the module doc)."""
    M = {n: mask(p, size) for n, p in parts.items() if not p["tool"]}
    def ov(a, b):
        c = centroid(M[a] & M[b]) if a in M and b in M else None
        return c or (centroid(M[a]) if a in M else None)
    J = {}
    feet = (M.get("foot_l", 0) | M.get("foot_r", 0)) if "foot_l" in M else M["torso"]
    ys, xs = np.nonzero(feet)
    J["root"] = (float(np.nonzero(M["torso"])[1].mean()), float(ys.max()))
    J["hips"] = centroid(M["hips"]) if "hips" in M else J["root"]
    J["torso"] = ov("torso", "hips") if "hips" in M else centroid(M["torso"])
    J["head"] = ov("head", "torso")
    for s in "lr":
        if f"upperarm_{s}" in M:
            elbow = ov(f"forearm_{s}", f"upperarm_{s}")
            c, d, (lo, hi) = axis(M[f"upperarm_{s}"])
            ends = [c + d * lo, c + d * hi]
            inner = max(ends, key=lambda e: math.dist(e, elbow))   # the end hidden behind the body
            J[f"upperarm_{s}"] = tuple(inner + (np.array(elbow) - inner) / 3)
            J[f"forearm_{s}"] = elbow
            J[f"hand_{s}"] = ov(f"hand_{s}", f"forearm_{s}")
        if f"leg_{s}" in M:
            J[f"leg_{s}"] = ov(f"leg_{s}", "hips")
            J[f"foot_{s}"] = ov(f"foot_{s}", f"leg_{s}")
        if f"sidefur_{s}" in M:
            J[f"sidefur_{s}"] = ov(f"sidefur_{s}", "head")
    for n in ("muzzle", "mustache", "brows"):
        if n in M:
            J[n] = centroid(M[n])
    if "mouth" in M:                                               # the jaw opens downward from the mouth's top
        ys, xs = np.nonzero(M["mouth"])
        J["jaw"] = (float(xs.mean()), float(ys.min() + 0.15 * (ys.max() - ys.min())))
    if "hat" in M:
        ys, xs = np.nonzero(M["hat"])
        J["hat"] = (float(xs.mean()), float(ys.max()))
    if "eye_whites" in M:
        J["pupils"] = centroid(M["eye_whites"])
    if "hand_l" in M:
        J["tool"] = centroid(M["hand_l"])
    # every pivot inside its own part (a hat's bottom edge, the gap between two pupils), and inside the parent's
    # part too where they overlap: spine_qa's "pivot on the joint"
    own = {}
    for n, p in parts.items():
        if not p["tool"] and n in M:
            own[p["bone"]] = own.get(p["bone"], 0) | M[n]
    for b, p in list(J.items()):
        if b in ("root", "tool") or b not in own:
            continue
        par = PARENT.get(b)
        both = own[b] & own[par] if par in own else None
        J[b] = nearest(own[b] if both is None or not both.any() else both, p)
    J.update({k: tuple(v) for k, v in over.items()})
    return J


def nearest(m: np.ndarray, p) -> tuple:
    """p itself if it lies in mask m, else the nearest pixel of m."""
    x, y = int(round(p[0])), int(round(p[1]))
    if 0 <= y < m.shape[0] and 0 <= x < m.shape[1] and m[y, x]:
        return tuple(p)
    ys, xs = np.nonzero(m)
    i = int(np.argmin((xs - p[0]) ** 2 + (ys - p[1]) ** 2))
    return float(xs[i]), float(ys[i])


PARENT = {"hips": "root", "torso": "hips", "head": "torso", "upperarm_l": "torso", "upperarm_r": "torso",
          "forearm_l": "upperarm_l", "forearm_r": "upperarm_r", "hand_l": "forearm_l", "hand_r": "forearm_r",
          "leg_l": "hips", "leg_r": "hips", "foot_l": "leg_l", "foot_r": "leg_r", "muzzle": "head", "jaw": "muzzle",
          "mustache": "muzzle", "hat": "head", "brows": "head", "pupils": "head", "sidefur_l": "head",
          "sidefur_r": "head", "tool": "hand_l"}
POINTS_TO = {"upperarm_l": "forearm_l", "upperarm_r": "forearm_r", "forearm_l": "hand_l", "forearm_r": "hand_r",
             "leg_l": "foot_l", "leg_r": "foot_r", "torso": "head"}
# bones with no children that only translate in the animations: they may point anywhere, so into their part
LEAVES = ("hand_l", "hand_r", "foot_l", "foot_r", "hat", "brows", "pupils", "sidefur_l", "sidefur_r")


def bone_angles(J: dict, parts: dict, size) -> dict:
    """World angle (degrees, y up) per bone: limbs point at their child joint, hands and feet at their part's
    centre, the rest 0 (the tool bone too, so tool holds are written in world angles)."""
    A = {}
    owned = {}
    for n, p in parts.items():
        if not p["tool"]:
            owned[p["bone"]] = owned.get(p["bone"], 0) | mask(p, size)
    for b in J:
        tgt = J.get(POINTS_TO.get(b, ""))
        if tgt is None and b in LEAVES and b in owned:            # leaf bones point into their own part
            tgt = centroid(owned[b])
            if math.dist(tgt, J[b]) < 3:
                tgt = None
        if tgt is None:
            A[b] = 0.0
        else:
            dx, dy = tgt[0] - J[b][0], -(tgt[1] - J[b][1])
            A[b] = math.degrees(math.atan2(dy, dx))
    return A


def to_sk(p, J):
    """PSD px (y down) -> skeleton units (y up, origin on the ground under the body)."""
    return p[0] - J["root"][0], J["root"][1] - p[1]


def rot(v, deg):
    r = math.radians(deg)
    return v[0] * math.cos(r) - v[1] * math.sin(r), v[0] * math.sin(r) + v[1] * math.cos(r)


def build_bones(J: dict, A: dict) -> list:
    order = ["root"] + [b for b in PARENT if b in J]
    bones = []
    for b in order:
        if b == "root":
            bones.append({"name": "root"})
            continue
        par = PARENT[b]
        while par not in J:
            par = PARENT.get(par, "root")
        w, pw = to_sk(J[b], J), to_sk(J[par], J) if par != "root" else (0.0, 0.0)
        pa = A.get(par, 0.0) if par != "root" else 0.0
        lx, ly = rot((w[0] - pw[0], w[1] - pw[1]), -pa)
        bone = {"name": b, "parent": par, "x": round(lx, 2), "y": round(ly, 2)}
        if abs(A[b] - pa) > 1e-6:
            bone["rotation"] = round(A[b] - pa, 2)
        if b in POINTS_TO and POINTS_TO[b] in J:
            bone["length"] = round(math.dist(J[b], J[POINTS_TO[b]]), 1)
        bones.append(bone)
    return bones


def region(img_size, centre_sk, bone_sk, bone_angle, extra_rot=0.0) -> dict:
    """A region attachment whose image centre sits at centre_sk (skeleton units) on a bone at bone_sk/bone_angle."""
    lx, ly = rot((centre_sk[0] - bone_sk[0], centre_sk[1] - bone_sk[1]), -bone_angle)
    att = {"x": round(lx, 2), "y": round(ly, 2), "width": img_size[0], "height": img_size[1]}
    r = extra_rot - bone_angle
    if abs(r) > 1e-6:
        att["rotation"] = round(r, 2)
    return att


def tool_hold(img: Image.Image, grip_from_handle: float, head_angle: float, J, A):
    """Region on the tool bone so the handle point grip_from_handle (0 = handle end, 1 = head end, along the long
    axis) sits on the bone and the head points at head_angle (world degrees at rest). The head end is the wider one."""
    a = np.asarray(img)[..., 3] > ALPHA
    c, d, (lo, hi) = axis(a)
    ys, xs = np.nonzero(a)
    s = (np.stack([xs, ys], 1) - c) @ d
    span = hi - lo
    near_lo = (s < lo + 0.2 * span).sum()
    near_hi = (s > hi - 0.2 * span).sum()
    if near_lo > near_hi:                                         # make +d point from handle to head
        d, lo, hi = -d, -hi, -lo
    g = c + d * (lo + grip_from_handle * (hi - lo))              # image px, y down
    head_img = math.degrees(math.atan2(-d[1], d[0]))              # head direction in image, y up
    R = head_angle - head_img                                     # rotate image so the head points at head_angle
    off = (img.width / 2 - g[0], -(img.height / 2 - g[1]))        # image centre relative to grip, y up
    cx, cy = rot(off, R)
    tool_sk = to_sk(J["tool"], J)
    reg = region(img.size, (tool_sk[0] + cx, tool_sk[1] + cy), tool_sk, A["tool"], R)
    return reg, {"length": float(hi - lo), "grip": grip_from_handle, "head_angle": head_angle}


class Kin:
    """Forward and two-bone inverse kinematics on the setup skeleton (rotation and translation; no scale), so a pose
    can be written as "paws here, tool along there" and turned into bone rotations."""

    def __init__(self, bones: list, palms: dict):
        self.bones = {b["name"]: b for b in bones}
        self.order = [b["name"] for b in bones]
        self.palms = palms                                        # hand bone -> palm point in its local frame

    def world(self, pose: dict) -> dict:
        """{bone: (angle, x, y)} in skeleton units for a pose {bone: {"r", "x", "y"}} of deltas from the setup."""
        W = {}
        for n in self.order:
            b, d = self.bones[n], pose.get(n, {})
            lx, ly = b.get("x", 0.0) + d.get("x", 0.0), b.get("y", 0.0) + d.get("y", 0.0)
            r = b.get("rotation", 0.0) + d.get("r", 0.0)
            if "parent" in b:
                pa, px, py = W[b["parent"]]
                ox, oy = rot((lx, ly), pa)
                W[n] = (pa + r, px + ox, py + oy)
            else:
                W[n] = (r, lx, ly)
        return W

    def point(self, W: dict, bone: str, local) -> tuple:
        a, x, y = W[bone]
        ox, oy = rot(local, a)
        return x + ox, y + oy

    def reach(self, side: str, target, pose: dict) -> tuple:
        """Upper-arm and forearm deltas that put hand_<side>'s palm on target (skeleton units) with the hand held
        straight on the forearm and the elbow hanging below, plus the distance still missing (0 = reached)."""
        ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
        W = self.world(pose)
        par = W[self.bones[ua]["parent"]][0]
        _, sx, sy = W[ua]
        L1 = math.hypot(self.bones[fa]["x"], self.bones[fa]["y"])
        v = self.bones[hd]["x"], self.bones[hd]["y"]                 # elbow -> palm in the forearm frame
        pv = rot(self.palms[hd], self.bones[hd].get("rotation", 0.0))
        v = v[0] + pv[0], v[1] + pv[1]
        L2, beta = math.hypot(*v), math.degrees(math.atan2(v[1], v[0]))
        dx, dy = target[0] - sx, target[1] - sy
        d = math.hypot(dx, dy)
        dc = min(max(d, abs(L1 - L2) + 1e-3), L1 + L2 - 1e-3)
        alpha = math.degrees(math.acos((L1 * L1 + dc * dc - L2 * L2) / (2 * L1 * dc)))
        base = math.degrees(math.atan2(dy, dx))
        best = None
        for th1 in (base + alpha, base - alpha):                 # elbows hang: the lower elbow wins
            ex, ey = sx + L1 * math.cos(math.radians(th1)), sy + L1 * math.sin(math.radians(th1))
            if best is None or ey < best[2]:
                best = (th1, ex, ey)
        th1, ex, ey = best
        thp = math.degrees(math.atan2(target[1] - ey, target[0] - ex))
        th2 = thp - beta
        d_ua = wrap(th1 - par - self.bones[ua].get("rotation", 0.0))
        d_fa = wrap(th2 - th1 - self.bones[fa].get("rotation", 0.0))
        return d_ua, d_fa, max(0.0, d - (L1 + L2))


def wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def unit(deg: float) -> tuple:
    return math.cos(math.radians(deg)), math.sin(math.radians(deg))


def draw_order_key(names: list, moves: dict, time: float = 0.0) -> dict:
    """A drawOrder key that puts each slot in moves right after its anchor slot ({slot: anchor})."""
    new = [n for n in names if n not in moves]
    for slot, anchor in moves.items():
        new.insert(new.index(anchor) + 1, slot)
    offs = [{"slot": s, "offset": new.index(s) - names.index(s)} for s in names if s in moves]
    return {"time": time, "offsets": offs} if time else {"offsets": offs}


# ------------------------------------------------------------------ animation

def spline(ts: list, vs: list, t: float, loop: bool) -> float:
    """Cubic Hermite through the keys with Catmull-Rom tangents, so motion flows through a pose instead of stopping
    on it. The ends are at rest, or, for a loop (last key = first), share the tangent across the seam."""
    n = len(ts)
    def tangent(i):
        if 0 < i < n - 1:
            return (vs[i + 1] - vs[i - 1]) / (ts[i + 1] - ts[i - 1])
        if loop and n > 2:                                       # wrap: neighbours are keys 1 and n-2
            return (vs[1] - vs[n - 2]) / ((ts[1] - ts[0]) + (ts[n - 1] - ts[n - 2]))
        return 0.0
    k = 0
    while k + 1 < n and ts[k + 1] <= t + 1e-9:
        k += 1
    if k + 1 >= n:
        return vs[-1]
    h = ts[k + 1] - ts[k]
    u = (t - ts[k]) / h
    h00, h10, h01, h11 = 2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u, -2 * u**3 + 3 * u**2, u**3 - u**2
    return h00 * vs[k] + h10 * h * tangent(k) + h01 * vs[k + 1] + h11 * h * tangent(k + 1)


DEFAULTS = {"r": 0.0, "x": 0.0, "y": 0.0, "sx": 1.0, "sy": 1.0}


def sampler(poses: list):
    """poses: [(time, {bone: {"r", "x", "y", "sx", "sy"}})] -> f(t) = {bone: channels} along the splines. Channels a
    pose leaves out hold their previous value (0 / 1 at the start); an empty pose ({}) is the rest pose."""
    track = {}
    for b in sorted({b for _, p in poses for b in p}):
        cur, keys = dict(DEFAULTS), []
        for t, p in poses:
            cur = {**cur, **p.get(b, {})} if p else dict(DEFAULTS)
            keys.append((t, dict(cur)))
        track[b] = ([k[0] for k in keys], keys, keys[0][1] == keys[-1][1])
    return lambda t: {b: {c: spline(ts, [k[1][c] for k in keys], t, loop) for c in DEFAULTS}
                      for b, (ts, keys, loop) in track.items()}


def bake(poses, duration: float) -> dict:
    """Spine bone timelines baked at FPS (spine_qa and the player then agree exactly) from a pose list (see sampler)
    or from any f(t) -> {bone: channels}."""
    f = poses if callable(poses) else sampler(poses)
    n = int(round(duration * FPS))
    per_t = [(round(i / FPS, 4), f(i / FPS)) for i in range(n + 1)]
    out = {}
    for b in sorted({b for _, s in per_t for b in s}):
        frames = [(t, {**DEFAULTS, **s.get(b, {})}) for t, s in per_t]
        tl = {}
        for chan, fields, base in (("rotate", ("r",), (0,)), ("translate", ("x", "y"), (0, 0)),
                                   ("scale", ("sx", "sy"), (1, 1))):
            vals = [tuple(round(v[f], 3) for f in fields) for _, v in frames]
            if all(x == base for x in vals):
                continue
            ks = []
            for i, ((t, _), val) in enumerate(zip(frames, vals)):
                if 0 < i < len(vals) - 1 and vals[i - 1] == val == vals[i + 1]:
                    continue                                      # a held value needs no key in between
                k = {"time": t} if t else {}
                if chan == "rotate":
                    k["value"] = val[0]
                else:
                    k.update(dict(zip(("x", "y"), val)))
                ks.append(k)
            tl[chan] = ks
        if tl:
            out[b] = tl
    return out


def blink(at: float, dur: float = 0.12) -> dict:
    return {s: {"attachment": [{"time": at, "name": s}, {"time": round(at + dur, 3), "name": None}]}
            for s in ("lid_l", "lid_r")}


def lids(on: float, off: float) -> dict:
    return {s: {"attachment": [{"time": on, "name": s}, {"time": off, "name": None}]} for s in ("lid_l", "lid_r")}


def show(slot: str, end: float) -> dict:
    return {slot: {"attachment": [{"name": slot}, {"time": end, "name": slot}]}}


# the dig, in fractions of the skeleton's height (front view). A shovel is far longer than a cartoon arm, so it
# is held low and flat (about 40 degrees, as the PSD paints it) with both paws at mid-chest and the blade on the
# ground well out to the picture's left; held steep, the top paw ends up at the mouth and the arms cross the face.
# (time, top paw x, top paw y, shovel angle handle->blade in degrees, torso turn, body dip, head turn)
DIG = [
    (0.0, 0.04, 0.45, -140, 0, 0.0, 3),          # ready, blade just off the ground
    (0.45, 0.03, 0.42, -141, 4, -0.006, 6),      # stab into the ground, body dips into it
    (0.9, 0.06, 0.39, -147, 2, -0.004, 4),       # pry: the handle pushed down, the blade levers up
    (1.3, 0.05, 0.47, -151, -2, 0.0, 2),         # scoop lifts out with the clod
    (1.7, 0.01, 0.50, -163, 5, 0.002, 7),        # toss to the left onto the pile
    (2.4, 0.04, 0.45, -140, 0, 0.0, 3),          # ready again (loops)
]
DIG_SCOOP, DIG_RELEASE = 1.0, 1.62                 # the clod rides the blade between these, then flies
MOUND_X = -0.64                                    # the pile, centre x, on the ground


def shovel_dig(kin: Kin, hold: dict, H: float, names: list) -> dict:
    """Both paws on the shovel: the top paw (hand_l) on the handle's grip, the other paw (hand_r, drawn in front of
    the body for this animation) at the nearest point of the shaft it can reach. Arms come from Kin.reach, so the
    paws stay on the handle; the tool bone turns the shovel to the wanted angle. A clod rides the blade from the
    scoop to the toss and flies onto the pile."""
    L, g1, H0 = hold["length"], hold["grip"], hold["head_angle"]
    tool_rot = kin.bones["tool"].get("rotation", 0.0)
    misses = []

    def pose(g, phi, torso, dip, head):
        u = unit(phi)
        handle = (g[0] - g1 * L * u[0], g[1] - g1 * L * u[1])
        p = {"torso": {"r": torso}, "root": {"y": dip}, "head": {"r": head}, "pupils": {"x": -4, "y": -3}}
        dua, dfa, m1 = kin.reach("l", g, p)
        p["upperarm_l"], p["forearm_l"] = {"r": dua}, {"r": dfa}
        _, sx, sy = kin.world(p)["upperarm_r"]
        s = ((sx - handle[0]) * u[0] + (sy - handle[1]) * u[1]) / L
        s = min(max(s, g1 + 0.12), 0.55)
        g2 = (handle[0] + s * L * u[0], handle[1] + s * L * u[1])
        dua, dfa, m2 = kin.reach("r", g2, p)
        p["upperarm_r"], p["forearm_r"] = {"r": dua}, {"r": dfa}
        hand_w = kin.world(p)["hand_l"][0]
        p["tool"] = {"r": wrap((phi - H0) - hand_w - tool_rot)}
        misses.append(round(max(m1, m2), 1))
        return p

    poses = [(t, pose((x * H, y * H), phi, torso, dip * H, head)) for t, x, y, phi, torso, dip, head in DIG]
    for i in range(1, len(poses)):                               # each turn within 180 degrees of the pose before,
        for b, ch in poses[i][1].items():                        # so the splines never spin the long way round
            if "r" in ch and "r" in poses[i - 1][1].get(b, {}):
                prev = poses[i - 1][1][b]["r"]
                ch["r"] = prev + wrap(ch["r"] - prev)
    body = sampler(poses)
    end = DIG[-1][0]

    def blade(t):
        """Where a clod sits on the blade at time t (skeleton units)."""
        p = body(t)
        W = kin.world(p)
        a, x, y = W["tool"]
        d = unit(a + H0)                                          # grip -> blade
        k = (1 - g1) * L * 0.88
        n = unit(a + H0 + 90)
        if n[1] < 0:                                              # the blade's upper side
            n = (-n[0], -n[1])
        return x + d[0] * k + n[0] * 14, y + d[1] * k + n[1] * 14

    # the clod: on the blade from scoop to release, then a throw under gravity onto the pile
    # (a flick: launched upward, not at the blade's own slow speed, or it seems to hover beside the blade)
    rel = blade(DIG_RELEASE)
    vy = 0.9 * H                                                  # launch speed up, units / s
    pile = (MOUND_X * H, 0.035 * H)
    g_ = 2.4 * H                                                  # gravity, units / s^2
    # time to fall onto the pile top given vy, and the sideways speed that lands it there
    disc = vy * vy + 2 * g_ * (rel[1] - pile[1])
    t_fly = (vy + math.sqrt(max(disc, 0))) / g_
    vx = (pile[0] - rel[0]) / max(t_fly, 1e-3)
    land = DIG_RELEASE + t_fly

    def clod(t):
        if t < DIG_SCOOP or t > land:
            return blade(DIG_SCOOP)
        if t <= DIG_RELEASE:
            return blade(t)
        s = t - DIG_RELEASE
        return rel[0] + vx * s, rel[1] + vy * s - 0.5 * g_ * s * s

    def full(t):
        p = body(t)
        cx, cy = clod(t)
        p["clod"] = {"x": cx, "y": cy}
        return p

    if any(misses):
        print(f"  ? doubt: shovel dig: a paw misses the handle by {max(misses)} units at some key pose")
    t_land = round(min(land, end - 0.05), 3)
    slots = {**show("tool_shovel", end), **blink(2.1)}
    # the top paw reaches across the chest, which swings the upper sleeve's hidden end out past the shoulder;
    # the cuff already covers the elbow at the body's edge, so that sleeve is off for this animation
    slots["upperarm_l"] = {"attachment": [{"name": None}, {"time": end, "name": None}]}
    if "dirt_mound" in names:
        slots["dirt_mound"] = {"attachment": [{"name": "dirt_mound"}, {"time": end, "name": "dirt_mound"}]}
    if "dirt_clod" in names:
        slots["dirt_clod"] = {"attachment": [{"name": None}, {"time": DIG_SCOOP, "name": "dirt_clod"},
                                             {"time": t_land, "name": None}]}
    order = {"forearm_r": "tool_shovel", "hand_r": "forearm_r"} # the lower paw grips in front of the body
    return {"bones": bake(full, end), "slots": slots, "drawOrder": [draw_order_key(names, order)]}


def animations(tools: list, kin: Kin | None = None, holds: dict | None = None, height: float = 0.0,
               slot_names: list | None = None) -> dict:
    """Starter set for a front-facing standing character with the tool hand on the picture's right (hand_l)."""
    A = {}
    base = {}
    # idle: breathe, sway, one blink
    A["idle"] = {"bones": bake([
        (0.0, base),
        (1.2, {"torso": {"sy": 1.02, "sx": 1.005}, "head": {"y": 3, "r": 1.5}, "upperarm_l": {"r": 3},
               "upperarm_r": {"r": -3}, "mustache": {"r": 2}, "hat": {"r": -1}, "pupils": {"x": 2}}),
        (2.4, {"torso": {"sy": 1, "sx": 1}, "head": {"y": 0, "r": 0}, "upperarm_l": {"r": 0},
               "upperarm_r": {"r": 0}, "mustache": {"r": 0}, "hat": {"r": 0}, "pupils": {"x": 0}}),
    ], 2.4), "slots": blink(1.6)}
    # cheer: crouch, jump with both arms up and a big open mouth, land, settle
    up = {"upperarm_l": {"r": 125}, "forearm_l": {"r": 25}, "upperarm_r": {"r": -125}, "forearm_r": {"r": -25},
          "hand_l": {"r": 10}, "hand_r": {"r": -10}}
    A["cheer"] = {"bones": bake([
        (0.0, base),
        (0.25, {"root": {"y": -10}, "torso": {"sy": 0.94, "sx": 1.03}, "head": {"y": -6},
                "upperarm_l": {"r": 35}, "upperarm_r": {"r": -35}, "forearm_l": {"r": 10}, "forearm_r": {"r": -10}}),
        (0.5, {"root": {"y": 48}, "torso": {"sy": 1.05, "sx": 0.98}, "head": {"y": 4, "r": 0},
               **up, "jaw": {"sy": 1.7}, "brows": {"y": 8}, "hat": {"y": 8, "r": 6},
               "leg_l": {"r": 8}, "leg_r": {"r": -8}, "mustache": {"y": 3}}),
        (0.75, {"root": {"y": 38}, "upperarm_l": {"r": 140}, "upperarm_r": {"r": -140}, "head": {"r": 3}}),
        (0.95, {"root": {"y": -8}, "torso": {"sy": 0.94, "sx": 1.03}, "head": {"y": -5, "r": 0},
                "hat": {"y": 0, "r": 0}, "leg_l": {"r": 0}, "leg_r": {"r": 0}}),
        (1.15, {"root": {"y": 0}, "torso": {"sy": 1.0, "sx": 1.0}, "head": {"y": 0}}),
        (1.5, {"upperarm_l": {"r": 0}, "forearm_l": {"r": 0}, "upperarm_r": {"r": 0}, "forearm_r": {"r": 0},
               "hand_l": {"r": 0}, "hand_r": {"r": 0}, "jaw": {"sy": 1}, "brows": {"y": 0},
               "mustache": {"y": 0}}),
        (1.8, base),
    ], 1.8), "slots": lids(0.3, 1.3)}
    # talk: jaw chatter with a hand gesture, raised brows, a nod and a blink
    chat = [1.55, 1.1, 1.65, 1.0, 1.45, 1.05, 1.6, 1.15, 1.5, 1.0]
    poses = [(0.0, base)]
    for i, v in enumerate(chat):
        t = round(0.14 * (i + 1), 3)
        poses.append((t, {"jaw": {"sy": v}, "mustache": {"y": 2.5 * (v - 1)}, "muzzle": {"y": 1.2 * (v - 1)}}))
    talk = bake(poses + [(1.6, {"jaw": {"sy": 1}, "mustache": {"y": 0}, "muzzle": {"y": 0}}), (2.4, {})], 2.4)
    gest = bake([
        (0.0, base),
        (0.45, {"upperarm_l": {"r": 28}, "forearm_l": {"r": 45}, "hand_l": {"r": 15}, "brows": {"y": 5},
                "head": {"r": -3}}),
        (0.9, {"upperarm_l": {"r": 32}, "forearm_l": {"r": 52}, "head": {"r": 2}}),
        (1.35, {"upperarm_l": {"r": 26}, "forearm_l": {"r": 40}, "head": {"r": -2}, "brows": {"y": 2}}),
        (1.9, {"upperarm_l": {"r": 0}, "forearm_l": {"r": 0}, "hand_l": {"r": 0}, "brows": {"y": 0},
               "head": {"r": 0}}),
        (2.4, base),
    ], 2.4)
    A["talk"] = {"bones": {**gest, **talk}, "slots": blink(1.95)}
    # tools
    if "wrench" in tools:
        # a ratchet: the hand cranks the wrench through a wide arc and back, the body leans into each pull
        hold = {"upperarm_l": {"r": 55}, "forearm_l": {"r": 35}, "hand_l": {"r": 0}, "tool": {"r": 0},
                "torso": {"r": 0}, "head": {"r": -4}, "pupils": {"x": 5, "y": -1}}
        turn = {"upperarm_l": {"r": 40}, "forearm_l": {"r": -5}, "hand_l": {"r": -20}, "tool": {"r": -30},
                "torso": {"r": -4}, "head": {"r": -7}, "pupils": {"x": 6, "y": -3}}
        A["wrench"] = {"bones": bake([
            (0.0, hold), (0.5, turn), (1.0, hold), (1.5, turn), (2.0, hold),
        ], 2.0), "slots": {**show("tool_wrench", 2.0), **blink(1.0)}}
    if "shovel" in tools and kin is not None:
        A["shovel"] = shovel_dig(kin, holds["shovel"], height, slot_names)
    if "hammer" in tools:
        rest = {"upperarm_l": {"r": 40}, "forearm_l": {"r": 30}, "tool": {"r": 0}, "torso": {"r": 0},
                "head": {"r": -2}, "pupils": {"x": 4, "y": -2}}
        A["hammer"] = {"bones": bake([
            (0.0, rest),
            # wind up out to the side (head up and back, clear of the face), strike down and out, small rebound
            (0.45, {"upperarm_l": {"r": 95}, "forearm_l": {"r": 40}, "tool": {"r": -80}, "torso": {"r": 4},
                    "head": {"r": 3}, "root": {"y": 3}, "pupils": {"y": 2}}),
            (0.65, {"upperarm_l": {"r": 10}, "forearm_l": {"r": -5}, "tool": {"r": -50}, "torso": {"r": -6, "sy": 0.97},
                    "head": {"r": -5}, "root": {"y": -3}, "hat": {"y": 3}, "pupils": {"y": -3}}),
            (0.8, {"upperarm_l": {"r": 18}, "tool": {"r": -44}, "torso": {"sy": 1}, "hat": {"y": 0}}),
            (1.4, rest),
        ], 1.4), "slots": {**show("tool_hammer", 1.4), **lids(0.63, 0.78)}}
    return A


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path, nargs="?")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--list", type=Path, metavar="PSD", help="print the PSD's leaf layers with their indices and stop")
    ap.add_argument("--spine", default="4.2.00")
    a = ap.parse_args()
    if a.list:
        from psd_tools import PSDImage
        for i, l in enumerate(leaf_layers(PSDImage.open(a.list)), 1):
            print(i, repr(l.name), tuple(l.bbox), "" if l.visible else "hidden")
        return 0
    if not a.config or not a.out:
        ap.error("config and --out are required")
    base = a.config.resolve().parent
    cfg = json.loads(a.config.read_text(encoding="utf-8"))
    name = cfg["character"]
    out = a.out
    if (out / "images").exists():
        shutil.rmtree(out / "images")
    (out / "images").mkdir(parents=True, exist_ok=True)

    parts, master = load_parts(cfg, base)
    size = master.size
    J = joints(parts, size, cfg.get("joints", {}))
    A = bone_angles(J, parts, size)
    bones = build_bones(J, A)
    # the master spine_qa compares the setup pose with: what the setup shows (no tools, no closed lids), on white
    setup = Image.new("RGBA", size, (255, 255, 255, 255))
    for d in parts.values():
        if not d["hidden"] and not d["tool"]:
            setup.alpha_composite(d["img"], d["bbox"][:2])
    setup.convert("RGB").save(out / "master.png")

    # tools: PSD tool layers keep their painted place (a shovel already in hand) unless the config gives a hold;
    # extra tools get a hold from their shape
    holds = {"wrench": (0.5, -70.0), "hammer": (0.12, 20.0), "shovel": (0.06, -146.0),
             **{k: tuple(v) for k, v in cfg.get("holds", {}).items()}}
    hold_info = {}
    tools = {}
    for p, d in parts.items():
        if d["tool"]:
            tools[p] = {"img": d["img"], "bbox": d["bbox"]}
    for t, spec in cfg.get("extra_tools", {}).items():
        img = key_white(Image.open(resolve(spec["image"], base)))
        length = spec.get("length", 300)
        k = length / max(img.size)
        tools[t] = {"img": img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)}

    slots, skin, images = [], {}, []
    tool_slots = []
    for t, d in tools.items():
        att = f"tool_{t}"
        d["img"].save(out / "images" / f"{name}_{att}.png")
        images.append(f"{name}_{att}")
        if t in holds:                                            # a grip from the tool's shape; else its PSD place
            reg, hold_info[t] = tool_hold(d["img"], *holds[t], J, A)
        else:
            x0, y0, *_ = d["bbox"]
            c = to_sk((x0 + d["img"].width / 2, y0 + d["img"].height / 2), J)
            reg = region(d["img"].size, c, to_sk(J["tool"], J), A["tool"])
        tool_slots.append({"name": att, "bone": "tool"})
        skin[att] = {f"{name}_{att}": reg}
    # props that a tool animation shows (the shovel's dirt): "props": {"dirt_mound": {"image", "width"}, ...}.
    # The mound sits on the ground on a bone of its own; the clod has a root bone the dig moves.
    props = {}
    H_est = J["root"][1] - min(p["bbox"][1] for p in parts.values() if not p["tool"])
    for pn, spec in cfg.get("props", {}).items():
        img = key_white(Image.open(resolve(spec["image"], base)))
        k = spec.get("width", 100) / img.width
        img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
        img.save(out / "images" / f"{name}_{pn}.png")
        images.append(f"{name}_{pn}")
        if pn == "dirt_mound":
            bones.append({"name": pn, "parent": "root", "x": round(MOUND_X * H_est, 2), "y": 0.0})
            skin[pn] = {f"{name}_{pn}": {"x": 0.0, "y": round(img.height / 2 - 4, 2), "width": img.width, "height": img.height}}
        else:
            bones.append({"name": "clod", "parent": "root"})
            skin[pn] = {f"{name}_{pn}": {"x": 0.0, "y": 0.0, "width": img.width, "height": img.height}}
        props[pn] = {"name": pn, "bone": pn if pn == "dirt_mound" else "clod"}
    for p, d in parts.items():
        if d["tool"]:
            continue
        if p == "hand_l":                                         # tools are drawn just behind the gripping paw
            slots += tool_slots
            if "dirt_clod" in props:                              # the clod rides on the blade
                slots.append(props["dirt_clod"])
        att = f"{name}_{p}"
        d["img"].save(out / "images" / f"{att}.png")
        images.append(att)
        x0, y0, *_ = d["bbox"]
        c = to_sk((x0 + d["img"].width / 2, y0 + d["img"].height / 2), J)
        bone = d["bone"] if d["bone"] in J or d["bone"] == "root" else "root"
        bsk = to_sk(J[bone], J) if bone != "root" else (0.0, 0.0)
        reg = region(d["img"].size, c, bsk, A.get(bone, 0.0) if bone != "root" else 0.0)
        slot = {"name": p, "bone": bone}
        if not d["hidden"]:
            slot["attachment"] = att
        slots.append(slot)
        skin[p] = {att: reg}                                      # attachments are named after their images
        if p == "shadow" and "dirt_mound" in props:               # the pile lies on the ground, behind the body
            slots.append(props["dirt_mound"])

    tb = next(b for b in bones if b["name"] == "tool")
    palms = {"hand_l": (tb["x"], tb["y"])}
    if "hand_r" in parts:
        c = centroid(mask(parts["hand_r"], size))
        w, j = to_sk(c, J), to_sk(J["hand_r"], J)
        palms["hand_r"] = rot((w[0] - j[0], w[1] - j[1]), -A["hand_r"])
    kin = Kin(bones, palms)
    anims = animations(list(tools), kin, hold_info, H_est, [s["name"] for s in slots])
    for an in anims.values():                                     # drop keys for slots/bones this character lacks;
        an["slots"] = {k: v for k, v in an.get("slots", {}).items() if k in skin}   # slot keys name the slot's image
        for slot, tl in an["slots"].items():
            for k in tl["attachment"]:
                if k["name"] is not None:
                    k["name"] = next(iter(skin[slot]))
        an["bones"] = {k: v for k, v in an["bones"].items() if k in kin.bones}
    boxes = [d["bbox"] for d in parts.values() if not d["tool"]]  # setup bounds, skeleton units (y up)
    x0, y0 = to_sk((min(b[0] for b in boxes), max(b[3] for b in boxes)), J)
    x1, y1 = to_sk((max(b[2] for b in boxes), min(b[1] for b in boxes)), J)
    data = {"skeleton": {"hash": "", "spine": a.spine, "x": round(x0, 1), "y": round(y0, 1),
                         "width": round(x1 - x0, 1), "height": round(y1 - y0, 1), "images": "./images/", "audio": ""},
            "bones": bones, "slots": slots,
            "skins": [{"name": "default", "attachments": skin}], "animations": anims}
    (out / f"{name}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    rig_output.write_atlas(out, name, images)
    rig_output.write_preview(out, name, anims)
    (out / "report.json").write_text(json.dumps({
        "source": str(cfg["psd"]), "builder": "psd_rig.py",
        "master_frame": {"width": size[0], "height": size[1], "mid_x": round(J["root"][0], 2),
                         "ground_y": round(J["root"][1], 2), "units_per_px": 1.0},
        "joints_psd_px": {k: [round(v[0], 1), round(v[1], 1)] for k, v in J.items()},
        "animations": {k: round(max([kk.get("time", 0) for tl in v["bones"].values() for ch in tl.values()
                                        for kk in ch] or [0]), 3) for k, v in anims.items()},
    }, indent=1), encoding="utf-8")

    dbg = master.convert("RGB")
    d = ImageDraw.Draw(dbg)
    for b, p in J.items():
        par = PARENT.get(b)
        if par in J and par != "root":
            d.line([J[par], p], fill=(255, 0, 255), width=2)
        d.ellipse([p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6], outline=(255, 0, 0), width=3)
        d.text((p[0] + 8, p[1] - 6), b, fill=(200, 0, 0))
    dbg.save(out / "joints.png")
    print(f"{name}: {len(bones)} bones, {len(slots)} slots, animations {', '.join(anims)} -> {out / (name + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
