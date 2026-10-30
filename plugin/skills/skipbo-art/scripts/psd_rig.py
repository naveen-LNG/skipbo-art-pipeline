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
Optional "props" ({"dirt_mound": {"image", "width"}, "dirt_clod": {...}}) give the dig a pile and a thrown clod;
chore props (see PROPS: sapling + plant_soil, ladder + frame + cloth, wall + paint_a/b with a "brush" extra tool,
watering_can + flowers + drop, pumpkin) add the plant, polish, paint, water and carry animations.

Joints come from where layers overlap (elbow = centre of forearm over upperarm, and so on; shoulders sit on the
upper arm's long axis, a third in from its hidden end); override any of them under "joints".

Writes rig/<name>.json (bones, slots, skin, animations idle, cheer, talk and one <tool> animation per tool, keyed
only at the poses with Spine Bezier curves between them, so an animator can edit them; see bake), rig/<name>.atlas,
rig/images/*.png, rig/preview.html,
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


def key_white(img: Image.Image, holes: int = 1500) -> Image.Image:
    """Transparent background for a tool painted on white: border-connected near-white pixels go, and so do enclosed
    white areas larger than holes px (between a ladder's steps, inside a can's handle); edges soften."""
    a = np.asarray(img.convert("RGBA")).copy()
    if a[..., 3].min() < 250:                                   # already cut out
        return img.convert("RGBA")
    light = a[..., :3].min(2) > 232
    bg = np.zeros(light.shape, bool)

    def fill(seeds, into):
        """Flood the light pixels connected to seeds into mask into; returns them."""
        stack, got = list(seeds), []
        while stack:
            y, x = stack.pop()
            if into[y, x] or not light[y, x]:
                continue
            into[y, x] = True
            got.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < into.shape[0] and 0 <= xx < into.shape[1] and not into[yy, xx] and light[yy, xx]:
                    stack.append((yy, xx))
        return got
    fill([(y, x) for y in (0, light.shape[0] - 1) for x in range(light.shape[1])]
         + [(y, x) for x in (0, light.shape[1] - 1) for y in range(light.shape[0])], bg)
    seen = bg.copy()
    for y, x in zip(*np.nonzero(light & ~bg)):                  # enclosed white: big areas are background too
        comp = fill([(y, x)], seen)
        if len(comp) > holes:
            ys_, xs_ = zip(*comp)
            bg[list(ys_), list(xs_)] = True
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
    if "hand_l" in M:                                              # tool grips: one at each palm
        J["tool"] = centroid(M["hand_l"])
    if "hand_r" in M:
        J["tool_r"] = centroid(M["hand_r"])
    # every pivot inside its own part (a hat's bottom edge, the gap between two pupils), and inside the parent's
    # part too where they overlap: spine_qa's "pivot on the joint"
    own = {}
    for n, p in parts.items():
        if not p["tool"] and n in M:
            own[p["bone"]] = own.get(p["bone"], 0) | M[n]
    for b, p in list(J.items()):
        if b in ("root", "tool", "tool_r") or b not in own:
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
          "sidefur_r": "head", "tool": "hand_l", "tool_r": "hand_r"}
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


def tool_hold(img: Image.Image, grip_from_handle: float, head_angle: float, J, A, bone: str = "tool"):
    """Region on a grip bone ("tool" in hand_l, "tool_r" in hand_r) so the handle point grip_from_handle (0 = handle
    end, 1 = head end, along the long axis) sits on the bone and the head points at head_angle (world degrees at
    rest). The head end is the wider one."""
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
    tool_sk = to_sk(J[bone], J)
    reg = region(img.size, (tool_sk[0] + cx, tool_sk[1] + cy), tool_sk, A[bone], R)
    return reg, {"length": float(hi - lo), "grip": grip_from_handle, "head_angle": head_angle, "bone": bone}


class Kin:
    """Forward and two-bone inverse kinematics on the setup skeleton (rotation and translation; no scale), so a pose
    can be written as "paws here, tool along there" and turned into bone rotations."""

    def __init__(self, bones: list, palms: dict):
        self.bones = {b["name"]: b for b in bones}
        self.order = [b["name"] for b in bones]
        self.palms = palms                                        # hand bone -> palm point in its local frame

    def world(self, pose: dict) -> dict:
        """{bone: (angle, x, y)} in skeleton units for a pose {bone: {"r", "x", "y", "sx", "sy"}} of deltas from the
        setup. Scale is inherited the way Spine does it (a squashed torso pulls the shoulders down), so W["__M"]
        holds each bone's world matrix."""
        W, M = {}, {}
        for n in self.order:
            b, d = self.bones[n], pose.get(n, {})
            lx, ly = b.get("x", 0.0) + d.get("x", 0.0), b.get("y", 0.0) + d.get("y", 0.0)
            r = math.radians(b.get("rotation", 0.0) + d.get("r", 0.0))
            sx, sy = d.get("sx", 1.0), d.get("sy", 1.0)
            L = ((math.cos(r) * sx, -math.sin(r) * sy), (math.sin(r) * sx, math.cos(r) * sy))
            if "parent" in b:
                P = M[b["parent"]]
                _, px, py = W[b["parent"]]
                x, y = px + P[0][0] * lx + P[0][1] * ly, py + P[1][0] * lx + P[1][1] * ly
                L = ((P[0][0] * L[0][0] + P[0][1] * L[1][0], P[0][0] * L[0][1] + P[0][1] * L[1][1]),
                     (P[1][0] * L[0][0] + P[1][1] * L[1][0], P[1][0] * L[0][1] + P[1][1] * L[1][1]))
            else:
                x, y = lx, ly
            M[n] = L
            W[n] = (math.degrees(math.atan2(L[1][0], L[0][0])), x, y)
        W["__M"] = M
        return W

    def point(self, W: dict, bone: str, local) -> tuple:
        _, x, y = W[bone]
        m = W["__M"][bone]
        return x + m[0][0] * local[0] + m[0][1] * local[1], y + m[1][0] * local[0] + m[1][1] * local[1]

    def reach(self, side: str, target, pose: dict) -> tuple:
        """Upper-arm and forearm deltas that put hand_<side>'s palm on target (skeleton units) with the hand held
        straight on the forearm and the elbow hanging below, plus the distance still missing (0 = reached). The
        two-bone solve is exact without scale; a squashed body is closed in on by re-aiming a few times."""
        ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
        aim, err = target, 0.0
        for _ in range(6):
            d_ua, d_fa, miss = self._reach(side, aim, pose)
            q = {**pose, ua: {**pose.get(ua, {}), "r": d_ua}, fa: {**pose.get(fa, {}), "r": d_fa}}
            px, py = self.point(self.world(q), hd, self.palms[hd])
            ex, ey = target[0] - px, target[1] - py
            err = math.hypot(ex, ey)
            if err < 0.3 or miss > 0:
                break
            aim = aim[0] + ex, aim[1] + ey
        return d_ua, d_fa, max(miss, err if err >= 0.3 else 0.0)

    def _reach(self, side: str, target, pose: dict) -> tuple:
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
    """Cubic Hermite through the keys, so motion flows through a passing pose instead of stopping on it, and eases in
    and out of an extreme (a key where the value turns back, or holds): its tangent is flat there, and elsewhere the
    Catmull-Rom tangent is limited so the curve never overshoots a key (as Spine's auto curves do). The ends are at
    rest, or, for a loop (last key = first), share the tangent across the seam."""
    n = len(ts)
    def tangent(i):
        if 0 < i < n - 1:
            a, b, c, ta, tb, tc = vs[i - 1], vs[i], vs[i + 1], ts[i - 1], ts[i], ts[i + 1]
        elif loop and n > 2:                                     # wrap: neighbours are keys 1 and n-2
            a, b, c = vs[n - 2], vs[0], vs[1]
            ta, tb, tc = ts[0] - (ts[n - 1] - ts[n - 2]), ts[0], ts[1]
        else:
            return 0.0
        d0, d1 = (b - a) / (tb - ta), (c - b) / (tc - tb)
        if d0 * d1 <= 0:                                         # an extreme or a hold: ease in and out
            return 0.0
        m = (c - a) / (tc - ta)
        lim = 3 * min(abs(d0), abs(d1))
        return max(-lim, min(lim, m))
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


# how far a keyed curve may drift from the motion it stands for before another key is added
TOLERANCE = {"r": 0.25, "x": 0.4, "y": 0.4, "sx": 0.002, "sy": 0.002}


def bake(poses, duration: float, key_times: list | None = None) -> dict:
    """Spine bone timelines with keys only where an animator would put them: at the poses (key_times, or the pose
    list's own times), each segment a Spine Bezier whose handles follow the motion's slope there, so the curve is
    the spline itself (a cubic Hermite is exactly one Bezier). Motion that isn't a spline through the poses (a
    clod's throw) gets a key added at its worst frame until no frame drifts past TOLERANCE. A channel that never
    moves gets no timeline. poses: a pose list (see sampler) or any f(t) -> {bone: channels}."""
    f = poses if callable(poses) else sampler(poses)
    if key_times is None:
        key_times = [] if callable(poses) else [t for t, _ in poses]
    n = int(round(duration * FPS))
    frames = [i / FPS for i in range(n + 1)]
    cache = {}

    def at(t):
        k = round(t, 6)
        if k not in cache:
            cache[k] = f(t)
        return cache[k]

    h = 1e-3
    out = {}
    for b in sorted({b for t in frames for b in at(t)}):
        def val(t, fields):
            s = {**DEFAULTS, **at(t).get(b, {})}
            return [s[c] for c in fields]
        tl = {}
        for chan, fields, base in (("rotate", ("r",), (0.0,)), ("translate", ("x", "y"), (0.0, 0.0)),
                                   ("scale", ("sx", "sy"), (1.0, 1.0))):
            dense = [val(t, fields) for t in frames]
            if all(all(abs(v - b0) < 1e-6 for v, b0 in zip(d, base)) for d in dense):
                continue
            keys = sorted({0.0, duration, *[t for t in key_times if 0 < t < duration]})

            def slopes(t):                                       # (incoming, outgoing) slope per field
                v = val(t, fields)
                lo = [(a - c) / h for a, c in zip(v, val(max(t - h, 0.0), fields))] if t > 0 else None
                hi = [(c - a) / h for a, c in zip(v, val(min(t + h, duration), fields))] if t < duration else None
                return lo or hi, hi or lo

            S, V = {}, {}

            def error(keys):
                """Worst drift (in tolerances) of the keyed curve from the motion, and the frame where it is."""
                for t in keys:
                    if t not in S:
                        S[t], V[t] = slopes(t), val(t, fields)
                worst, worst_t = 0.0, None
                for i, t in enumerate(frames):
                    j = max(k for k in range(len(keys) - 1) if keys[k] <= t + 1e-9) if t < duration else len(keys) - 2
                    t0, t1 = keys[j], keys[j + 1]
                    u, dt = (t - t0) / (t1 - t0), t1 - t0
                    h00, h10, h01, h11 = 2*u**3 - 3*u**2 + 1, u**3 - 2*u**2 + u, -2*u**3 + 3*u**2, u**3 - u**2
                    for fi, fld in enumerate(fields):
                        y = (h00 * V[t0][fi] + h10 * dt * S[t0][1][fi] + h01 * V[t1][fi] + h11 * dt * S[t1][0][fi])
                        e = abs(y - dense[i][fi]) / TOLERANCE[fld]
                        if e > worst:
                            worst, worst_t = e, t
                return worst, worst_t

            for _ in range(60):                                   # add keys where the curve drifts
                worst, worst_t = error(keys)
                if worst <= 1 or worst_t in keys:
                    break
                keys = sorted(keys + [round(worst_t, 4)])
            for t in list(keys[1:-1]):                            # drop keys the curve doesn't need (a bone that
                trial = [k for k in keys if k != t]               # holds still through a pose)
                if error(trial)[0] <= 1:
                    keys = trial
            ks = []
            for i, t in enumerate(keys):
                v = V[t]
                k = {"time": round(t, 4)} if t else {}
                if chan == "rotate":
                    k["value"] = round(v[0], 3)
                else:
                    k.update({c: round(x, 3) for c, x in zip(("x", "y"), v)})
                if i + 1 < len(keys):                             # Bezier handles at a third of the segment
                    t1, dt = keys[i + 1], keys[i + 1] - t
                    curve = []
                    for fi in range(len(fields)):
                        curve += [round(t + dt / 3, 4), round(v[fi] + S[t][1][fi] * dt / 3, 3),
                                  round(t1 - dt / 3, 4), round(V[t1][fi] - S[t1][0][fi] * dt / 3, 3)]
                    k["curve"] = curve
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


def hide(slot: str, end: float) -> dict:
    return {slot: {"attachment": [{"name": None}, {"time": end, "name": None}]}}


# follow-through and overlapping action: loose parts hang on the body by a damped spring, so they trail a move,
# swing past where it stops and settle a beat later. (part, channel, source bones summed, source channel, gain,
# spring frequency Hz, damping ratio)
FOLLOW = [
    ("hat", "r", ("torso", "head"), "r", 1.0, 2.6, 0.35),
    ("sidefur_l", "r", ("torso", "head"), "r", 0.4, 3.0, 0.4),
    ("sidefur_r", "r", ("torso", "head"), "r", 0.4, 3.0, 0.4),
    ("mustache", "r", ("torso", "head"), "r", 0.6, 3.0, 0.35),
    ("hat", "y", ("root", "torso", "head"), "y", 0.6, 3.0, 0.3),
    ("mustache", "y", ("root", "torso", "head"), "y", 0.3, 3.5, 0.35),
]


def follow_through(f, end: float, loop: bool | None = None):
    """f(t) -> pose, plus FOLLOW's springs on top. A loop runs the springs round twice so the seam matches."""
    dt = 1 / 240
    n = int(round(end / dt))
    F = [f(i * dt) for i in range(n + 1)]
    if loop is None:
        a, b = F[0], F[-1]
        loop = all(abs(a.get(k, {}).get(c, DEFAULTS[c]) - b.get(k, {}).get(c, DEFAULTS[c])) < 1e-3
                   for k in set(a) | set(b) for c in DEFAULTS)
    off = {}
    for part, ch, bones, sch, gain, hz, zeta in FOLLOW:
        s = [sum(p.get(b, {}).get(sch, 0.0) for b in bones) for p in F]
        if max(s) - min(s) < 1e-6:
            continue
        w = 2 * math.pi * hz
        x, v, rec = s[0], 0.0, []
        for _ in range(2 if loop else 1):
            rec = []
            for i in range(n + 1):
                rec.append(gain * (x - s[i]))
                v += (w * w * (s[i] - x) - 2 * zeta * w * v) * dt
                x += v * dt
        if max(abs(r) for r in rec) > 0.05:
            off[(part, ch)] = rec

    def g(t):
        p = {b: dict(c) for b, c in f(t).items()}
        u = min(max(t / dt, 0.0), n)
        i = min(int(u), n - 1)
        for (part, ch), rec in off.items():
            d = rec[i] + (rec[i + 1] - rec[i]) * (u - i)
            c = p.setdefault(part, {})
            c[ch] = c.get(ch, DEFAULTS[ch]) + d
        return p
    return g


def bake_ft(poses, duration: float, key_times: list | None = None) -> dict:
    """bake with follow-through on the loose parts (see FOLLOW)."""
    f = poses if callable(poses) else sampler(poses)
    if key_times is None and not callable(poses):
        key_times = [t for t, _ in poses]
    return bake(follow_through(f, duration), duration, key_times)


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
    # (a flick: launched upward, not at the blade's own slow speed, or it seems to hover beside the blade). The
    # flight time is fixed so it lands on the pile well before the loop ends; the launch speeds follow from it.
    rel = blade(DIG_RELEASE)
    pile = (MOUND_X * H, 0.035 * H)
    g_ = 2.4 * H                                                  # gravity, units / s^2
    t_fly = min(0.5, end - DIG_RELEASE - 0.15)
    vy = (pile[1] - rel[1] + 0.5 * g_ * t_fly * t_fly) / t_fly
    vx = (pile[0] - rel[0]) / t_fly
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
    keys = [t for t, *_ in DIG] + [DIG_SCOOP, DIG_RELEASE, t_land]  # the poses, the scoop, the throw, the landing
    return {"bones": bake_ft(full, end, keys), "slots": slots, "drawOrder": [draw_order_key(names, order)]}


# the wrench turn, front view, in the character's right paw (picture left), as the artist posed it: the arm reaches
# out to the side, the fist grips the wrench by its middle (a jaw either side, the paw over it) and the wrench lies
# nearly level. It pivots on a bolt at its outer jaw, the paw rides it (IK), the body bends into the pull and the
# face strains. (time, wrench angle bolt->handle, torso turn, torso drop (fraction of height), torso squash,
# head turn, head drop, brows, jaw open, other arm's upper / fore turn)
WRENCH = [
    (0.0, -16, 9, 0.016, 1.0, 7, 4, -3, 0.85, 6, 10),      # set: arm out, wrench on the bolt
    (0.4, -6, 4, 0.004, 1.025, 3, -2, 3, 1.15, 12, 16),    # anticipation: rises, wrench eased back, a breath in
    (0.75, -26, 15, 0.034, 0.95, 12, 10, -7, 0.6, 2, 6),   # pull: bends hard into it, eyes squeezed, jaw clenched
    (1.0, -28, 16, 0.036, 0.945, 13, 11, -8, 0.55, 0, 4),  # strain
    (1.35, -17, 9, 0.017, 1.0, 7, 4, -3, 0.85, 6, 10),     # ratchets back
    (1.7, -16, 9, 0.016, 1.0, 7, 4, -3, 0.85, 6, 10),      # set again (loops)
]
WRENCH_BOLT = (-0.62, 0.44)                                 # bolt (the outer jaw), fractions of the height
WRENCH_SQUEEZE = (0.72, 1.05)                               # eyes shut through the pull


def wrench_turn(kin: Kin, hold: dict, H: float, names: list) -> dict:
    """The wrench in the gripping paw (hold["bone"]'s hand), turning a bolt with anticipation, a body bend and an
    effort face; the paw and wrench are drawn in front of the body. The wrench's grip point sits half way along it,
    its head end on the bolt."""
    L, g, H0, grip = hold["length"], hold["grip"], hold["head_angle"], hold["bone"]
    hand = PARENT[grip]
    side = hand[-1]
    other = "l" if side == "r" else "r"
    s_other = 1 if other == "l" else -1                          # the free arm swings out to its own side
    grip_rot = kin.bones[grip].get("rotation", 0.0)
    bolt = (WRENCH_BOLT[0] * H, WRENCH_BOLT[1] * H)
    misses = []

    def pose(theta, tr, ty, tsy, hr, hy, brows, jaw, oua, ofa):
        u = unit(theta)
        G = (bolt[0] + (1 - g) * L * u[0], bolt[1] + (1 - g) * L * u[1])   # head (bolt) end -> grip
        p = {"torso": {"r": tr, "y": -ty * H, "sy": tsy}, "head": {"r": hr, "y": -hy},
             "brows": {"y": brows}, "jaw": {"sy": jaw}, "mustache": {"y": -3 * (1 - jaw)},
             "pupils": {"x": -6, "y": -4}, f"upperarm_{other}": {"r": s_other * oua},
             f"forearm_{other}": {"r": s_other * ofa}}
        q = {b: {k: v for k, v in c.items() if k != "sy"} for b, c in p.items()}   # Kin has no scale
        dua, dfa, m = kin.reach(side, G, q)
        p[f"upperarm_{side}"], p[f"forearm_{side}"] = {"r": dua}, {"r": dfa}
        q[f"upperarm_{side}"], q[f"forearm_{side}"] = {"r": dua}, {"r": dfa}
        hand_w = kin.world(q)[hand][0]
        p[grip] = {"r": wrap((theta + 180 - H0) - hand_w - grip_rot)}
        misses.append(round(m, 1))
        return p

    poses = [(t, pose(*rest)) for t, *rest in WRENCH]
    for i in range(1, len(poses)):                               # turns stay within 180 degrees key to key
        for b, ch in poses[i][1].items():
            if "r" in ch and "r" in poses[i - 1][1].get(b, {}):
                ch["r"] = poses[i - 1][1][b]["r"] + wrap(ch["r"] - poses[i - 1][1][b]["r"])
    if any(misses):
        print(f"  ? doubt: wrench: the paw misses the handle by {max(misses)} units at some key pose")
    end = WRENCH[-1][0]
    slots = {**show("tool_wrench", end), **lids(*WRENCH_SQUEEZE)}
    order = {f"forearm_{side}": "tool_wrench", hand: f"forearm_{side}"}   # paw over the wrench, in front of the body
    return {"bones": bake_ft(poses, end), "slots": slots, "drawOrder": [draw_order_key(names, order)]}


# ------------------------------------------------------------------ chores: props the character works with

# where each prop sits: (parent bone, layer, anchor = the image point (fractions from its top left) on the bone,
# the bone's place (fractions of the height, y up from the ground) or None to ride the right paw's grip, tool_r).
# Layer "back" is drawn behind the body (just after the shadow), "held" in front of it, just behind the left paw.
# "stage" props stand on the ground while the character is lifted onto the ladder.
PLANT_AT = (-0.05, 0.07)            # the sapling's root ball, planted in front of the feet
FRAME_AT = (-0.44, 1.12)             # the picture frame on the wall, up beside the ladder, clear of the head
LADDER_STEP = 0.41                   # the feet rest on the ladder's second step: this fraction of its height
WALL_X, PAINT_Y0, PAINT_X = -0.72, 0.42, (-0.56, -0.63)   # arm out, the paw clear of the face
FLOWERS_X = -0.60
PUMPKIN_X = 0.01                     # where the pumpkin is set down, in front of the feet
PROPS = {
    "sapling": ("root", "held", (0.58, 0.82), PLANT_AT),
    "plant_soil": ("root", "held", (0.5, 0.93), (PLANT_AT[0], 0.0)),
    "ladder": ("stage", "back", (0.5, 1.0), (0.0, 0.0)),
    "frame": ("stage", "back", (0.5, 0.5), FRAME_AT),
    "cloth": ("tool_r", "held", (0.45, 0.72), None),  # bunched over the fist
    "wall": ("root", "back", (0.5, 1.0), (WALL_X, 0.0)),
    "paint_a": ("root", "back", (0.5, 0.985), (PAINT_X[0], PAINT_Y0)),
    "paint_b": ("root", "back", (0.5, 0.985), (PAINT_X[1], PAINT_Y0)),
    "watering_can": ("tool_r", "held", (0.63, 0.05), None),   # hung from the top of its carry handle
    "flowers": ("root", "back", (0.5, 0.95), (FLOWERS_X, 0.0)),
    "drop": ("root", "held", (0.5, 0.6), (0.0, 0.0)),
    "pumpkin": ("root", "held", (0.5, 0.98), (PUMPKIN_X, 0.0)),   # bone on the ground under it
}
PROP_POINTS = {"watering_can": {"rose": (0.035, 0.35)}}   # named image points the animations aim with


def ik_pose(kin: Kin, body: dict, paws: dict | None = None, grips: dict | None = None) -> tuple:
    """A pose from body deltas, paw targets ({side: palm point}) solved with Kin.reach, and grip bones turned to a
    world angle ({grip bone: degrees}); plus the worst miss."""
    p = {b: dict(c) for b, c in body.items()}
    miss = 0.0
    for side, tgt in (paws or {}).items():
        dua, dfa, m = kin.reach(side, tgt, p)
        p.setdefault(f"upperarm_{side}", {})["r"] = dua
        p.setdefault(f"forearm_{side}", {})["r"] = dfa
        miss = max(miss, m)
    for g, ang in (grips or {}).items():
        hand_w = kin.world(p)[PARENT[g]][0]
        p.setdefault(g, {})["r"] = wrap(ang - hand_w - kin.bones[g].get("rotation", 0.0))
    return p, miss


def unwrap(poses: list):
    """Each turn within 180 degrees of the pose before, so the splines never spin the long way round."""
    for i in range(1, len(poses)):
        for b, ch in poses[i][1].items():
            if "r" in ch and "r" in poses[i - 1][1].get(b, {}):
                prev = poses[i - 1][1][b]["r"]
                ch["r"] = prev + wrap(ch["r"] - prev)


def face(hr=0.0, hy=0.0, brows=0.0, jaw=1.0, px=0.0, py=0.0) -> dict:
    """Head turn and drop, brows up, jaw open (1 = rest), eyes looking (pupils x, y)."""
    return {"head": {"r": hr, "y": hy}, "brows": {"y": brows}, "jaw": {"sy": jaw}, "pupils": {"x": px, "y": py}}


def chore(kin: Kin, keys: list, what: str) -> list:
    """keys: [(time, body, paws, grips)] -> unwrapped poses, with a doubt printed if a paw can't reach."""
    poses, misses = [], []
    for t, body, paws, grips in keys:
        p, m = ik_pose(kin, body, paws, grips)
        poses.append((t, p))
        misses.append(m)
    unwrap(poses)
    if max(misses) > 1:
        print(f"  ? doubt: {what}: a paw misses its target by {max(misses):.1f} units at some key pose")
    return poses


def plant_sapling(kin: Kin, H: float, info: dict, names: list) -> dict:
    """Both paws hold the sapling by its root ball; anticipation (rise, lift, breathe in), a deep squat that settles
    a little further, the sapling let go into the soil (it drops in and wobbles), two pats of the soil, then up with
    an overshoot and a proud, happy look."""
    bw = 0.29 * info["sapling"]["w"] + 0.03 * H                  # ball centre -> each palm
    def hold(x, y):
        return {"r": (x * H - bw, y * H), "l": (x * H + bw, y * H)}
    sq = {"leg_l": {"r": 8}, "leg_r": {"r": -8}}
    up = {"leg_l": {"r": 0}, "leg_r": {"r": 0}}
    rest_arms = {"upperarm_l": {"r": 0}, "forearm_l": {"r": 0}, "upperarm_r": {"r": 0}, "forearm_r": {"r": 0}}
    pat_x = (PLANT_AT[0] * H - 0.14 * H, PLANT_AT[0] * H + 0.14 * H)
    def pats(y):
        return {"r": (pat_x[0], y * H), "l": (pat_x[1], y * H)}
    T = lambda r, y, sy: {"torso": {"r": r, "y": y * H, "sy": sy}}
    keys = [
        (0.0, {**T(0, 0, 1.0), **up, **face(-4, -3, 0, 1.1, -1, -6)}, hold(-0.03, 0.30), None),     # holds it, smiles
        (0.5, {**T(-3, 0.008, 1.03), **up, **face(2, 0, 4, 1.15, 0, -3)}, hold(-0.02, 0.34), None),  # rise, breathe in
        (1.2, {**T(5, -0.20, 0.92), **sq, **face(-6, -6, -5, 0.85, -1, -6)}, hold(-0.05, 0.165), None),  # squat down
        (1.5, {**T(5, -0.21, 0.91), **sq, **face(-7, -7, -6, 0.8, -1, -6)}, hold(-0.05, 0.155), None),   # settles in
        (1.95, {**T(4, -0.20, 0.93), **sq, **face(-5, -5, 2, 1.0, -1, -6)}, pats(0.18), None),       # lets go
        (2.2, {**T(4, -0.215, 0.91), **sq, **face(-6, -7, -2, 0.9, -1, -6)}, pats(0.085), None),   # pat
        (2.4, {**T(4, -0.205, 0.92), **sq, **face(-5, -5, 0, 1.0, -1, -6)}, pats(0.16), None),
        (2.6, {**T(4, -0.215, 0.91), **sq, **face(-6, -7, -2, 0.9, -1, -6)}, pats(0.085), None),   # pat
        (2.85, {**T(3, -0.20, 0.93), **sq, **face(-5, -5, 1, 1.0, -1, -6)}, pats(0.17), None),
        (3.25, {**T(-2, 0.012, 1.03), **up, **rest_arms, **face(3, 1, 6, 1.3, -1, -6)}, None, None),  # up, overshoot
        (3.6, {**T(0, 0, 1.0), **up, **rest_arms, **face(-3, -2, 4, 1.25, -1, -6)}, None, None),      # settles, proud
        (4.2, {**T(0, 0, 1.0), **up, **rest_arms, **face(-3, -2, 4, 1.25, -1, -6)}, None, None),
    ]
    poses = chore(kin, keys, "plant")
    end = keys[-1][0]
    # the sapling: carried in the paws, then let go into the soil, where it drops in and wobbles to a stop
    S = []
    for t, _, paws, _ in keys[:4]:
        (xr, y), (xl, _) = paws["r"], paws["l"]
        S.append((t, {"sapling": {"x": (xr + xl) / 2 - PLANT_AT[0] * H, "y": y - PLANT_AT[1] * H, "r": 0}}))
    S += [(1.95, {"sapling": {**S[-1][1]["sapling"], "r": 0}}), (2.08, {"sapling": {"x": 0, "y": -0.008 * H, "r": -7}}),
          (2.25, {"sapling": {"x": 0, "y": 0.004 * H, "r": 5}}), (2.45, {"sapling": {"x": 0, "y": 0, "r": -2}}),
          (2.6, {"sapling": {"x": 0, "y": 0, "r": 0}}), (end, {"sapling": {"x": 0, "y": 0, "r": 0}})]
    slots = {**show("sapling", end), **show("plant_soil", end), **lids(1.35, 1.7)}
    slots["lid_l"]["attachment"] += [{"time": 3.35, "name": "lid_l"}, {"time": 3.8, "name": None}]   # happy eyes
    slots["lid_r"]["attachment"] += [{"time": 3.35, "name": "lid_r"}, {"time": 3.8, "name": None}]
    order = {"forearm_r": "plant_soil", "hand_r": "forearm_r"}     # both paws in front of the plant
    return {"bones": {**bake_ft(poses, end), **bake(S, end)}, "slots": slots,
            "drawOrder": [draw_order_key(names, order)]}


def polish_frame(kin: Kin, H: float, info: dict, names: list) -> dict:
    """On the ladder's second step, the right paw polishes a picture frame up above with a cloth: a huff on the
    glass first (anticipation), two big circles with the body swaying into them and the free arm out for balance,
    then the paw pulls away (follow-through) and he leans back to check it."""
    lift = LADDER_STEP * info["ladder"]["h"]
    F = (FRAME_AT[0] * H, FRAME_AT[1] * H)
    R = 0.045 * H
    stand = {"root": {"y": lift}, "stage": {"y": -lift}}
    def k(t, paw, cloth, tr, sy, fc, free):
        body = {**stand, "torso": {"r": tr, "sy": sy}, **fc,
                "upperarm_l": {"r": free[0]}, "forearm_l": {"r": free[1]}}
        return (t, body, {"r": (F[0] + paw[0] * H, F[1] + paw[1] * H)}, {"tool_r": cloth})
    keys = [k(0.0, (0.06, -0.08), 0, 3, 1.0, face(4, 0, 2, 1.05, -5, 4), (25, 20)),
            k(0.5, (0.08, -0.13), -8, 1, 0.97, face(9, -3, 5, 1.55, -6, 3), (20, 15)),     # huff on the glass
            k(0.8, (0.0, 0.045), 5, 7, 1.04, face(7, 2, 3, 1.0, -6, 5), (35, 25))]         # reach up
    for i in range(1, 9):                                         # two circles
        a = math.radians(90 + 90 * i)
        c = math.cos(a)
        keys.append(k(round(0.8 + 0.28 * i, 3), (R / H * c, R / H * math.sin(a)), 6 * math.sin(a), 7 - 2.5 * c,
                      1.04, face(7 - 1.5 * c, 2, 3, 1.0, -6, 5), (30 - 8 * c, 22)))
    keys += [k(3.35, (0.09, -0.08), -6, 0, 0.99, face(1, 0, 6, 1.3, -4, 4), (22, 18)),     # pulls away, checks it
             k(3.75, (0.07, -0.08), 0, 2.5, 1.0, face(3.5, 0, 2.5, 1.08, -5, 4), (25, 20))]
    keys.append((4.1, *keys[0][1:]))
    poses = chore(kin, keys, "polish")
    end = 4.1
    slots = {**show("ladder", end), **show("frame", end), **show("cloth", end), **hide("shadow", end), **blink(3.55)}
    order = {"forearm_r": "cloth", "hand_r": "forearm_r"}          # the paw over the cloth
    return {"bones": bake_ft(poses, end), "slots": slots, "drawOrder": [draw_order_key(names, order)]}


def paint_wall(kin: Kin, hold: dict, H: float, info: dict, names: list) -> dict:
    """A small flat brush in the right paw paints two upward strokes on a wall beside him: the brush pulls back and
    down first (anticipation), each stroke drags the bristles behind it, the second ends in a flick (follow-through),
    then he steps back to admire it. Each paint stripe grows behind the brush tip."""
    L, g, H0 = hold["length"], hold["grip"], hold["head_angle"]
    reach = (1 - g) * L
    A_, B_ = PAINT_X
    def k(t, tip, phi, tr, ty, sy, fc):
        u = unit(phi)
        paw = (tip[0] * H - reach * u[0], tip[1] * H - reach * u[1])
        body = {"torso": {"r": tr, "y": ty * H, "sy": sy}, **fc, "upperarm_l": {"r": 4}, "forearm_l": {"r": 6}}
        return (t, body, {"r": paw}, {"tool_r": phi - H0})
    keys = [k(0.0, (-0.40, 0.58), 150, 4, 0, 1.0, face(4, 0, 1, 1.05, -6, 0)),
            k(0.45, (-0.38, 0.40), 140, 2, -0.012, 0.97, face(1, -2, 4, 1.15, -6, -3)),    # pulls back, loads up
            k(0.7, (A_, 0.42), 172, 8, -0.005, 1.0, face(5, 0, 0, 0.95, -6, -3)),          # brush on the wall
            k(1.2, (A_, 0.70), 188, 10, 0.01, 1.04, face(9, 2, -2, 0.9, -6, 4)),          # stroke up
            k(1.6, (A_, 0.49), 168, 8, 0, 1.0, face(5, 0, 0, 0.95, -6, -2)),              # back down
            k(1.95, (B_, 0.42), 172, 11, -0.005, 0.99, face(6, 0, 0, 0.95, -7, -3)),       # next stripe
            k(2.45, (B_, 0.70), 190, 13, 0.01, 1.04, face(10, 2, -2, 0.9, -7, 4)),          # stroke up
            k(2.75, (B_ + 0.015, 0.74), 195, 12, 0.012, 1.05, face(11, 2, 0, 1.0, -7, 5)),  # flick off the top
            k(3.2, (-0.36, 0.52), 140, -3, 0, 1.0, face(-4, 0, 6, 1.3, -6, 0))]           # steps back, admires
    keys.append((3.9, *keys[0][1:]))
    poses = chore(kin, keys, "paint")
    end = 3.9
    body = sampler(poses)
    ph = info["paint_a"]["h"]

    def tip_y(t):
        W = kin.world(body(t))
        a, x, y = W["tool_r"]
        return y + reach * unit(a + H0)[1]
    frames = [i / FPS for i in range(int(round(end * FPS)) + 1)]
    ty = {round(t, 6): tip_y(t) for t in frames}

    def grown(t, t0, t1):
        """How far a stripe has been painted by time t: the highest the tip got while stroking it."""
        hi = max([ty[round(s, 6)] for s in frames if t0 <= s <= min(t, t1)] or [PAINT_Y0 * H])
        return min(max((hi - PAINT_Y0 * H) / ph, 0.0), 1.0)
    strokes = {"paint_a": (0.7, 1.25), "paint_b": (1.95, 2.75)}

    def paint(t):
        return {s: {"sy": max(grown(t, *w), 0.01) if t >= w[0] else 0.01} for s, w in strokes.items()}
    stripe_keys = sorted({0.0, end, *[w for ws in strokes.values() for w in ws]})
    slots = {**show("tool_brush", end), **show("wall", end), **lids(3.3, 3.6)}
    for s, (t0, _) in strokes.items():
        slots[s] = {"attachment": [{"name": None}, {"time": t0, "name": s}, {"time": end, "name": s}]}
    order = {"forearm_r": "tool_brush", "hand_r": "forearm_r"}     # the paw over the brush handle
    return {"bones": {**bake_ft(poses, end), **bake(paint, end, stripe_keys)}, "slots": slots,
            "drawOrder": [draw_order_key(names, order)]}


def carry_pumpkin(kin: Kin, H: float, info: dict, names: list) -> dict:
    """Both paws carry a heavy pumpkin at the belly: a waddle in place (feet lift in turn, the body sways and bobs,
    an effort face), a stop where the pumpkin swings on (follow-through), a lift and a breath in (anticipation), a
    little bend that lowers it, a short drop to the ground that squashes it and bounces (follow-through), then he
    straightens with an overshoot and a pleased look."""
    w, h = info["pumpkin"]["w"], info["pumpkin"]["h"]
    mid = 0.38 * h                                                # the pumpkin's middle above its bottom
    side = w / 2 - 0.03 * H                                       # palm centres just inside its sides
    x0 = PUMPKIN_X * H

    def hold(x, y, out=0.0):
        """Paws on the pumpkin's sides with its bottom at (x, y) fractions of the height; out opens them."""
        return {"r": (x0 + x * H - side - out * H, y * H + mid), "l": (x0 + x * H + side + out * H, y * H + mid)}
    rest_arms = {"upperarm_l": {"r": 0}, "forearm_l": {"r": 0}, "upperarm_r": {"r": 0}, "forearm_r": {"r": 0}}
    feet = lambda l, r: {"foot_l": {"x": -l * H}, "foot_r": {"x": -r * H}}   # foot lift (the leg points down)
    def B(tr, ty, sy, fc, fl=0.0, fr=0.0, root=0.0):
        return {"root": {"y": root * H}, "torso": {"r": tr, "y": ty * H, "sy": sy}, **face(*fc), **feet(fl, fr)}
    effort = lambda hr: (hr, -2, -3, 0.85, 0, -4)
    # (time, body, pumpkin bottom x, y)
    plan = [
        (0.0, B(0, 0, 0.98, effort(0)), 0.0, 0.22),
        (0.35, B(-2, 0, 0.985, effort(-1.5), fl=0.03, root=0.006), -0.004, 0.226),   # step: left foot up
        (0.7, B(0, -0.005, 0.975, effort(0), root=-0.003), 0.0, 0.218),             # weight down
        (1.05, B(2, 0, 0.985, effort(1.5), fr=0.03, root=0.006), 0.004, 0.226),       # step: right foot up
        (1.4, B(0, -0.005, 0.975, effort(0), root=-0.003), 0.0, 0.218),
        (1.75, B(-2, 0, 0.985, effort(-1.5), fl=0.03, root=0.006), -0.004, 0.226),
        (2.1, B(1, -0.004, 0.975, effort(1)), 0.006, 0.21),                         # stops, the load swings on
        (2.5, B(-1, 0.008, 1.02, (-2, 1, 3, 1.1, 0, -4)), 0.0, 0.25),                # lifts it, breathes in
        (3.0, B(2, -0.11, 0.95, (4, -5, -4, 0.85, 0, -6)), 0.0, 0.11),             # a little bend, lowers it
    ]
    keys = [(t, body, hold(px, py), None) for t, body, px, py in plan]
    up = B(0, 0, 1.0, (0, 0, 0, 1.0, 0, -5))
    keys += [(3.2, B(2, -0.115, 0.945, (4, -5, -2, 0.95, 0, -6)), hold(0.0, 0.11, 0.045), None),   # lets go
             (3.65, {**B(-1, 0.01, 1.025, (-2, 1, 6, 1.3, 0, -5)), **rest_arms}, None, None),     # up, overshoot
             (4.0, {**B(0, 0, 1.0, (1, 0, 4, 1.25, 0, -5)), **rest_arms}, None, None),
             (4.6, {**B(0, 0, 1.0, (1, 0, 4, 1.25, 0, -5)), **rest_arms}, None, None)]
    poses = chore(kin, keys, "carry")
    end = keys[-1][0]
    # the pumpkin: in the paws until 3.2, then it drops to the ground, squashes, bounces and settles
    P = [(t, {"pumpkin": {"x": px * H, "y": py * H, "sx": 1, "sy": 1}}) for t, _, px, py in plan]
    P += [(3.2, {"pumpkin": {"x": 0, "y": 0.11 * H, "sx": 1, "sy": 1}}),
          (3.36, {"pumpkin": {"x": 0, "y": 0, "sx": 1.08, "sy": 0.9}}),               # thud
          (3.5, {"pumpkin": {"x": 0, "y": 0.012 * H, "sx": 0.97, "sy": 1.04}}),      # bounce
          (3.65, {"pumpkin": {"x": 0, "y": 0, "sx": 1.01, "sy": 0.99}}),
          (3.85, {"pumpkin": {"x": 0, "y": 0, "sx": 1, "sy": 1}}),
          (end, {"pumpkin": {"x": 0, "y": 0, "sx": 1, "sy": 1}})]
    slots = {**show("pumpkin", end), **lids(3.75, 4.2)}            # pleased, eyes closed
    # the left paw reaches in across the belly, which swings the upper sleeve's hidden end out past the shoulder;
    # the cuff covers the elbow at the body's edge, so that sleeve is off while he holds the pumpkin
    slots["upperarm_l"] = {"attachment": [{"name": None}, {"time": 3.45, "name": "upperarm_l"}]}
    order = {"forearm_r": "pumpkin", "hand_r": "forearm_r"}         # both paws in front of the pumpkin
    return {"bones": {**bake_ft(poses, end), **bake(P, end)}, "slots": slots,
            "drawOrder": [draw_order_key(names, order)]}


def water_plants(kin: Kin, H: float, info: dict, names: list) -> dict:
    """The watering can hangs from the right paw by its carry handle (the artist's pose: arm relaxed at the side).
    He swings it back (anticipation), out over the flowers and tips it, overshooting the tilt and settling; water
    drops fall from the rose in a stream while he sways it along the bed; then the can swings back level, past it and
    settles (follow-through), and the flowers perk up."""
    W0 = kin.world({})
    rest_palm = W0["tool_r"][1:]
    def k(t, paw, tilt, tr, ty, sy, fc, free=(0, 0)):
        body = {"torso": {"r": tr, "y": ty * H, "sy": sy}, **fc,
                "upperarm_l": {"r": free[0]}, "forearm_l": {"r": free[1]}}
        if paw is None:
            return (t, {**body, "upperarm_r": {"r": 0}, "forearm_r": {"r": 0}, "tool_r": {"r": 0}}, None, None)
        return (t, body, {"r": (paw[0] * H, paw[1] * H)}, {"tool_r": tilt})
    keys = [k(0.0, None, 0, 0, 0, 1.0, face(3, 0, 0, 1.05, -6, -5)),
            k(0.45, (rest_palm[0] / H + 0.03, rest_palm[1] / H + 0.04), -10, -3, 0.006, 1.02,
              face(0, 1, 3, 1.15, -5, -3), (4, 4)),                                        # swings it back
            k(0.9, (-0.45, 0.49), 58, 9, -0.004, 0.99, face(7, -2, 1, 1.1, -6, -6), (-4, -2)),  # out and tip, past it
            k(1.1, (-0.455, 0.485), 50, 9.5, -0.004, 0.99, face(7.5, -2, 1, 1.1, -6, -6), (-4, -2)),
            k(1.5, (-0.47, 0.47), 53, 10, -0.005, 0.99, face(8, -2, 2, 1.15, -7, -6), (-5, -2)),   # sways along
            k(1.9, (-0.43, 0.49), 49, 8, -0.004, 0.99, face(6.5, -2, 2, 1.15, -6, -6), (-3, -2)),
            k(2.2, (-0.42, 0.48), 45, 8, -0.004, 0.99, face(6, -2, 2, 1.1, -6, -6), (-3, -2)),
            k(2.45, (-0.36, 0.42), -8, 2, 0.004, 1.01, face(2, 0, 5, 1.25, -5, -4), (2, 2)),  # level, swings past
            k(2.8, (rest_palm[0] / H - 0.01, rest_palm[1] / H + 0.01), 4, 0.5, 0, 1.0,
              face(3, 0, 2, 1.1, -6, -5))]
    keys.append((3.2, *keys[0][1:]))
    poses = chore(kin, keys, "water")
    end = 3.2
    body = sampler(poses)
    can = info["watering_can"]
    rose = can["points"]["rose"]
    fl_top = FLOWERS_X * H, 0.13 * H
    g_ = 2.4 * H

    def spout(t):
        W = kin.world(body(t))
        return kin.point(W, "tool_r", rose), W["tool_r"][0]
    drops = [n for n in names if n.startswith("drop")]
    fly = {}
    for i, d in enumerate(drops):                                 # each drop leaves the rose, falls on the bed,
        fl, t0 = [], 0.95 + i * 0.09                              # and goes again
        while t0 < 2.25:
            (x0, y0), a = spout(t0)
            v = unit(a + 165)
            vx, vy = 0.25 * H * v[0], 0.25 * H * v[1]
            tf = (vy + math.sqrt(vy * vy + 2 * g_ * max(y0 - fl_top[1], 1.0))) / g_
            fl.append((round(t0, 3), round(t0 + tf, 3), (x0, y0), (vx, vy)))
            t0 += 0.09 * len(drops)
        fly[d] = fl

    def drop_pose(t):
        out = {}
        for d, fl in fly.items():
            pos = None
            for j, (t0, t1, (x0, y0), (vx, vy)) in enumerate(fl):
                if t0 <= t <= t1:
                    s = t - t0
                    pos = (x0 + vx * s, y0 + vy * s - 0.5 * g_ * s * s)
                    break
                nxt = fl[j + 1] if j + 1 < len(fl) else None
                if t1 < t and (nxt is None or t < nxt[0]):       # hidden between flights: glide to the next start
                    s = t1 - t0
                    land = (x0 + vx * s, y0 + vy * s - 0.5 * g_ * s * s)
                    to = nxt[2] if nxt else land
                    u = (t - t1) / ((nxt[0] if nxt else end) - t1)
                    pos = (land[0] + (to[0] - land[0]) * u, land[1] + (to[1] - land[1]) * u)
                    break
            if pos is None:
                pos = fl[0][2]
            out[d] = {"x": pos[0], "y": pos[1]}
        return out
    drop_keys = sorted({0.0, end, *[t for fl in fly.values() for f in fl for t in f[:2]]})
    perk = [(0.0, {"flowers": {"sx": 1, "sy": 1}}), (2.0, {"flowers": {"sx": 1, "sy": 1}}),
            (2.15, {"flowers": {"sx": 1.03, "sy": 0.95}}), (2.4, {"flowers": {"sx": 0.97, "sy": 1.07}}),
            (2.65, {"flowers": {"sx": 1.01, "sy": 0.99}}), (2.9, {"flowers": {"sx": 1, "sy": 1}}),
            (end, {"flowers": {"sx": 1, "sy": 1}})]
    slots = {**show("watering_can", end), **show("flowers", end), **blink(2.95)}
    for d, fl in fly.items():
        ks = [{"name": None}]
        for t0, t1, *_ in fl:
            ks += [{"time": t0, "name": d}, {"time": t1, "name": None}]
        slots[d] = {"attachment": ks}
    order = {"forearm_r": "watering_can", "hand_r": "forearm_r"}   # the fist round the handle, in front
    return {"bones": {**bake_ft(poses, end), **bake(drop_pose, end, drop_keys), **bake(perk, end)},
            "slots": slots, "drawOrder": [draw_order_key(names, order)]}


def animations(tools: list, kin: Kin | None = None, holds: dict | None = None, height: float = 0.0,
               slot_names: list | None = None, props: dict | None = None) -> dict:
    """Starter set for a front-facing standing character with the tool hand on the picture's right (hand_l), plus
    a chore per set of props: plant (sapling), polish (ladder, frame, cloth), paint (brush, wall, paint stripes),
    water (watering can, flowers, drops)."""
    props, names = props or {}, slot_names or []
    A = {}
    base = {}
    # idle: breathe, sway, one blink
    A["idle"] = {"bones": bake_ft([
        (0.0, base),
        (1.2, {"torso": {"sy": 1.02, "sx": 1.005}, "head": {"y": 3, "r": 1.5}, "upperarm_l": {"r": 3},
               "upperarm_r": {"r": -3}, "mustache": {"r": 2}, "hat": {"r": -1}, "pupils": {"x": 2}}),
        (2.4, {"torso": {"sy": 1, "sx": 1}, "head": {"y": 0, "r": 0}, "upperarm_l": {"r": 0},
               "upperarm_r": {"r": 0}, "mustache": {"r": 0}, "hat": {"r": 0}, "pupils": {"x": 0}}),
    ], 2.4), "slots": blink(1.6)}
    if kin is not None:
        A["cheer"] = cheer_wave(kin, height, "hand_open" in props)
    # talk: jaw chatter with a hand gesture, raised brows, a nod and a blink
    chat = [1.55, 1.1, 1.65, 1.0, 1.45, 1.05, 1.6, 1.15, 1.5, 1.0]
    poses = [(0.0, base)]
    for i, v in enumerate(chat):
        t = round(0.14 * (i + 1), 3)
        poses.append((t, {"jaw": {"sy": v}, "mustache": {"y": 2.5 * (v - 1)}, "muzzle": {"y": 1.2 * (v - 1)}}))
    talk = bake(poses + [(1.6, {"jaw": {"sy": 1}, "mustache": {"y": 0}, "muzzle": {"y": 0}}), (2.4, {})], 2.4)
    gest = bake_ft([
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
    if "wrench" in tools and kin is not None:
        A["wrench"] = wrench_turn(kin, holds["wrench"], height, slot_names)
    if "shovel" in tools and kin is not None:
        A["shovel"] = shovel_dig(kin, holds["shovel"], height, slot_names)
    if kin is not None and {"sapling", "plant_soil"} <= props.keys():
        A["plant"] = plant_sapling(kin, height, props, names)
    if kin is not None and {"ladder", "frame", "cloth"} <= props.keys():
        A["polish"] = polish_frame(kin, height, props, names)
    if kin is not None and "brush" in tools and {"wall", "paint_a", "paint_b"} <= props.keys():
        A["paint"] = paint_wall(kin, holds["brush"], height, props, names)
    if kin is not None and {"watering_can", "flowers"} <= props.keys():
        A["water"] = water_plants(kin, height, props, names)
    if kin is not None and "pumpkin" in props:
        A["carry"] = carry_pumpkin(kin, height, props, names)
    if "hammer" in tools and kin is not None:
        A["hammer"] = hammer_strike(kin, holds["hammer"], height, names)
    return A


# cheer: no jump. Both arms are up in a V from the first frame (no raise from the sides) and wave, open paws (the
# "open" hand variant) palm out; paws as fractions of the height, wave as paw sway and paw tilt. The two arms wave
# in opposite phase, each paw's tilt trailing its arm's sway (follow-through), the body bobs on the beat.
CHEER_PAWS = {"r": (-0.38, 0.83), "l": (0.40, 0.82)}
CHEER_WAVE = 1.0                                                # seconds per wave
CHEER_SWAY, CHEER_TILT, CHEER_LAG = 0.035, 18.0, 0.09           # paw sway (fraction of height), paw tilt, its lag


def cheer_wave(kin: Kin, H: float, open_hands: bool) -> dict:
    end = 2 * CHEER_WAVE
    keys = []
    for i in range(9):
        t = round(end * i / 8, 4)
        w = 2 * math.pi * t / CHEER_WAVE
        body = {"torso": {"r": 1.5 * math.sin(w), "sy": 1.0 + 0.012 * math.cos(2 * w)},
                **face(-2.5 * math.sin(w), 2 + 1.5 * math.cos(2 * w), 7, 1.55 + 0.1 * math.cos(2 * w), 0, 3)}
        paws, grips = {}, {}
        for side, (x, y) in CHEER_PAWS.items():
            ph = w if side == "r" else w + math.pi
            paws[side] = ((x + CHEER_SWAY * math.sin(ph)) * H, y * H)
            grips[f"hand_{side}"] = 90 - CHEER_TILT * math.sin(ph - 2 * math.pi * CHEER_LAG / CHEER_WAVE)
        keys.append((t, body, paws, grips))
    poses = chore(kin, keys, "cheer")
    slots = {}
    for s in "lr" if open_hands else "":
        slots[f"hand_{s}"] = {"attachment": [{"name": f"hand_{s}_open"}, {"time": end, "name": f"hand_{s}_open"}]}
    return {"bones": bake_ft(poses, end), "slots": slots}


# the hammer in the gripping paw (the character's right by default, picture left): (time, paw x, y (fractions of the
# height), hammer angle handle->head in world degrees, torso turn, torso drop, torso squash, face, other arm's
# upper / fore turn). He winds up high beside his head (rises, leans back, breathes in), strikes down and out with a
# little bend of the body into the blow (eyes squeezed, jaw clenched), rebounds, and eases back to the ready hold.
HAMMER = [
    (0.0, (-0.33, 0.36), 150, 0, 0.0, 1.0, (0, 0, 0, 1.05, -6, -3), (4, 6)),        # ready
    (0.45, (-0.34, 0.60), 100, -4, -0.008, 1.03, (-3, 1, 5, 1.15, -6, 2), (10, 12)),  # anticipation: wind up
    (0.68, (-0.42, 0.33), 185, 7, 0.03, 0.95, (6, -5, -6, 0.75, -6, -5), (0, 2)),    # strike, bent into it
    (0.82, (-0.40, 0.37), 172, 6, 0.025, 0.96, (5, -4, -4, 0.8, -6, -5), (2, 4)),    # rebound
    (1.2, (-0.35, 0.40), 160, 2, 0.008, 0.99, (2, -1, 0, 1.0, -6, -4), (3, 5)),      # eases back
    (1.6, (-0.33, 0.36), 150, 0, 0.0, 1.0, (0, 0, 0, 1.05, -6, -3), (4, 6)),        # ready (loops)
]
HAMMER_SQUEEZE = (0.64, 0.86)                                   # eyes shut through the blow


def hammer_strike(kin: Kin, hold: dict, H: float, names: list) -> dict:
    """A hammer blow keyed by where the gripping paw is (IK) and where the hammer points, with anticipation, a
    little bend into the strike and an effort face; the paw is drawn over the handle, in front of the body."""
    grip, H0 = hold["bone"], hold["head_angle"]
    hand = PARENT[grip]
    side, other = hand[-1], "l" if hand[-1] == "r" else "r"
    s_other = 1 if other == "l" else -1
    keys = []
    for t, paw, phi, tr, ty, tsy, fc, (oua, ofa) in HAMMER:
        body = {"torso": {"r": tr if side == "r" else -tr, "y": -ty * H, "sy": tsy}, **face(*fc),
                f"upperarm_{other}": {"r": s_other * oua}, f"forearm_{other}": {"r": s_other * ofa}}
        x = paw[0] if side == "r" else -paw[0]
        keys.append((t, body, {side: (x * H, paw[1] * H)}, {grip: (phi if side == "r" else 180 - phi) - H0}))
    poses = chore(kin, keys, "hammer")
    end = HAMMER[-1][0]
    slots = {**show("tool_hammer", end), **lids(*HAMMER_SQUEEZE)}
    order = {f"forearm_{side}": "tool_hammer", hand: f"forearm_{side}"}   # the fist round the handle, in front
    return {"bones": bake_ft(poses, end), "slots": slots, "drawOrder": [draw_order_key(names, order)]}


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
    parts, master = load_parts(cfg, base)                         # read the PSD before clearing the last build
    if (out / "images").exists():
        shutil.rmtree(out / "images")
    (out / "images").mkdir(parents=True, exist_ok=True)
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
    holds = {"wrench": (0.5, -70.0), "hammer": (0.12, 20.0), "shovel": (0.06, -146.0), "brush": (0.15, 160.0),
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
    # which paw holds each tool: "l" (picture right, the default) or "r" (the character's right, picture left)
    hands = {"wrench": "r", "brush": "r", "hammer": "r", **cfg.get("tool_hands", {})}
    for t, d in tools.items():
        att = f"tool_{t}"
        bone = "tool_r" if hands.get(t) == "r" and "tool_r" in J else "tool"
        d["img"].save(out / "images" / f"{name}_{att}.png")
        images.append(f"{name}_{att}")
        if t in holds:                                            # a grip from the tool's shape; else its PSD place
            reg, hold_info[t] = tool_hold(d["img"], *holds[t], J, A, bone)
        else:
            x0, y0, *_ = d["bbox"]
            c = to_sk((x0 + d["img"].width / 2, y0 + d["img"].height / 2), J)
            reg = region(d["img"].size, c, to_sk(J[bone], J), A[bone])
        tool_slots.append({"name": att, "bone": bone})
        skin[att] = {f"{name}_{att}": reg}
    # props that a tool animation shows (the shovel's dirt): "props": {"dirt_mound": {"image", "width"}, ...}.
    # The mound sits on the ground on a bone of its own; the clod has a root bone the dig moves.
    # Chore props (PROPS: sapling, ladder, frame, cloth, wall, paint stripes, watering can, flowers, drops) take
    # "width" or "height" in skeleton units, and "copies" for several of one (drop -> drop1, drop2, ...).
    props, back, held, prop_info = {}, [], [], {}
    H_est = J["root"][1] - min(p["bbox"][1] for p in parts.values() if not p["tool"])
    for pn, spec in cfg.get("props", {}).items():
        img = key_white(Image.open(resolve(spec["image"], base)))
        k = spec["height"] / img.height if "height" in spec else spec.get("width", 100) / img.width
        size_ = (spec.get("width", img.width * k), spec.get("height", img.height * k))   # both: stretched
        img = img.resize((max(1, round(size_[0])), max(1, round(size_[1]))), Image.LANCZOS)
        img.save(out / "images" / f"{name}_{pn}.png")
        images.append(f"{name}_{pn}")
        w, h = img.size
        if pn == "dirt_mound":
            bones.append({"name": pn, "parent": "root", "x": round(MOUND_X * H_est, 2), "y": 0.0})
            skin[pn] = {f"{name}_{pn}": {"x": 0.0, "y": round(img.height / 2 - 4, 2), "width": img.width, "height": img.height}}
        elif pn == "dirt_clod":
            bones.append({"name": "clod", "parent": "root"})
            skin[pn] = {f"{name}_{pn}": {"x": 0.0, "y": 0.0, "width": img.width, "height": img.height}}
        if pn in ("dirt_mound", "dirt_clod"):
            props[pn] = {"name": pn, "bone": pn if pn == "dirt_mound" else "clod"}
            continue
        if pn not in PROPS:
            raise SystemExit(f"prop {pn!r}: no place for it (known: {', '.join(PROPS)})")
        parent, layer, (fx, fy), place = PROPS[pn]
        local = ((0.5 - fx) * w, (fy - 0.5) * h)                  # image centre from the anchor, y up
        prop_info[pn] = {"w": w, "h": h, "points": {n: ((px - fx) * w, (fy - py) * h)
                                                    for n, (px, py) in PROP_POINTS.get(pn, {}).items()}}
        copies = [pn] if spec.get("copies", 1) == 1 else [f"{pn}{i + 1}" for i in range(spec["copies"])]
        for cn in copies:
            if place is None:                                     # rides the right paw's grip
                bone = "tool_r"
                bsk = to_sk(J[bone], J)
                skin[cn] = {f"{name}_{pn}": region(img.size, (bsk[0] + local[0], bsk[1] + local[1]), bsk, A[bone])}
            else:
                if parent == "stage" and not any(b["name"] == "stage" for b in bones):
                    bones.append({"name": "stage", "parent": "root"})
                bone = cn
                bones.append({"name": cn, "parent": parent, "x": round(place[0] * H_est, 2),
                              "y": round(place[1] * H_est, 2)})
                skin[cn] = {f"{name}_{pn}": {"x": round(local[0], 2), "y": round(local[1], 2), "width": w, "height": h}}
            (back if layer == "back" else held).append({"name": cn, "bone": bone})
    for p, d in parts.items():
        if d["tool"]:
            continue
        if p == "hand_l":                                         # tools are drawn just behind the gripping paw
            slots += tool_slots
            if "dirt_clod" in props:                              # the clod rides on the blade
                slots.append(props["dirt_clod"])
            slots += held                                         # held props too
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
        if p == "shadow":                                         # the pile lies on the ground, behind the body,
            if "dirt_mound" in props:                             # and so do the back props (ladder, wall, flowers)
                slots.append(props["dirt_mound"])
            slots += back

    # hand variants swapped in by an animation: "hand_variants": {"open": {"image", "height"}} paints the character's
    # right paw (picture left, thumb toward the body, fingers up); the left one is its mirror. Fingers run along the
    # hand bone, the wrist a little inside the cuff.
    for vn, spec in cfg.get("hand_variants", {}).items():
        img = key_white(Image.open(resolve(spec["image"], base)))
        k = spec.get("height", 160) / img.height
        img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
        for s, im in (("r", img), ("l", img.transpose(Image.FLIP_LEFT_RIGHT))):
            if f"hand_{s}" not in skin:
                continue
            att = f"{name}_hand_{s}_{vn}"
            im.save(out / "images" / f"{att}.png")
            images.append(att)
            skin[f"hand_{s}"][att] = {"x": round(im.height * (0.5 - spec.get("tuck", 0.12)), 2), "y": 0.0,
                                      "rotation": -90.0, "width": im.width, "height": im.height}
            prop_info[f"hand_{vn}"] = True
    grips = {b["name"]: b for b in bones if b["name"] in ("tool", "tool_r")}   # palm = the grip bone's place
    palms = {PARENT[g]: (b["x"], b["y"]) for g, b in grips.items()}
    kin = Kin(bones, palms)
    anims = animations(list(tools), kin, hold_info, H_est, [s["name"] for s in slots], prop_info)
    for an in anims.values():                                     # drop keys for slots/bones this character lacks;
        an["slots"] = {k: v for k, v in an.get("slots", {}).items() if k in skin}   # slot keys name the slot's image
        for slot, tl in an["slots"].items():
            for k in tl["attachment"]:
                if k["name"] is not None and k["name"] not in skin[slot]:   # a variant (hand_r_open) or the slot's own
                    k["name"] = f"{name}_{k['name']}" if f"{name}_{k['name']}" in skin[slot] else next(iter(skin[slot]))
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
