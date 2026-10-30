#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""spine_qa.py - render a generated Spine rig frame by frame and measure it. No Spine install needed.

  uv run spine_qa.py rig/moose.json [--master moose_master.png] [--fps 30]
  uv run spine_qa.py --contract master_a.png master_b.png      (is a master rig-ready?)
    flat background, no faint shadow, centred, leg gap, arm gaps, and keyable: under KEY_HOLES of the silhouette
    keys out as holes (pale fur near the background's grey, the rabbit's first masters)

For every animation it renders all frames and checks:
  structure  each bone's pivot lies inside BOTH its part and its parent's part (a real joint), parts
             overlap their parent by >= 3% of the smaller part, each bone points into its own part, and
             no part carries thin slivers (stray edge pixels from a neighbouring part)
  attached   every part touches its parent part in every frame (no detached / floating pieces)
  stitched   near the joint (a disk about one limb-width across), the overlap between a part and its parent
             never drops below 0.5x its setup-pose value with the same attachments (a gap opening) and never
             grows by more than 8% of the smaller part (sliding into the parent)
  joints     the joint point between a part and its parent is covered in every frame (no holes)
  occluded   a part clearly visible at rest (>70%) is never mostly hidden (<40% visible) behind another, and a
             part partly tucked at rest (a hand under its cuff) never loses more than 65% of what showed
             (props, slots with no attachment at rest, are neither judged nor counted as hiding anything: a
             hurdle in front of the legs, then behind the jumper, is their purpose; nor is a jerk on a bone that
             draws nothing in that animation)
  fragments  (structure) no part or pose variant carries a detached solid island
  order      (structure) tails are drawn behind the legs, feet and hips
  variants   (structure) every swappable variant, swapped into the setup pose, still covers its joint and
             overlaps its parent about as much as the rest attachment does (0.4x-2.5x), and is drawn within
             VARIANT_SIZE (1.6x either way, sqrt of the drawn area) of the rest attachment's size: a mis-scaled
             variant that still closes its joint (the bear's 3.2x tiptoe clog) fails "variant_size"
  smooth     per-bone angular and positional motion between consecutive frames: velocity jumps
             (sudden starts, stops or reversals) and acceleration spikes
  seams      (setup + the middle frame of each animation) hairlines along a piece's edge where it lies over another
             piece: edge pixels lighter or darker than both sides, confined to the edge and greyer than both sides
             (background-removal leftovers); at most SEAM_MAX of each pair's shared edge
  setup      the setup pose against the master (silhouette IoU), if --master is given; uses the master frame
             spine_rig.py records in report.json, so a longer tail can't shift the comparison
Rigs built with --annotations (rig/annotations.resolved.json exists) also get:
  thumbs     at each gesture's hold, the thumb (rig_hands.thumb_vector, carried through the hand's attachment) is
             within THUMB_TOL of its target; a thumb on the hand's axis is reported unchecked. The target is the
             hold's own "thumb_target" when spine_rig recorded one: up for point / thumbs_up / hold_card (at the pose
             they chose), and for wave / cheer_jump wherever anatomy puts the thumb of the painted side (they have no
             pose to choose, so judging them against a fixed direction would fail by design); else thumb_targets
  sockets    (setup + every 3rd frame) a leg's hem stays within half its boot's opening width of the opening, its hip
             likewise in the hips, and at most SOCKET_SPILL of the leg near the opening shows past the rim beside it
             (a forearm trimmed under a glove's cuff, "rim_inset" in the resolved file, has its rim that far inside)
  landmarks  (setup) each placed joint lies within LANDMARK_DRIFT x body height (plus its push-in) of its master point
  layer_order (setup + every frame) each hand is drawn on the side of its forearm's (or sleeve mesh's) slot that
             master.layers.hand says (below: tucked under the cuff; above: over_forearm), drawOrder keys included
Mesh attachments (spine_rig's weighted sleeves) also get:
  mesh_fold  (setup + every frame) every triangle keeps the sign of its area: in the setup pose its uv triangle's
             orientation, in each frame the setup pose's (a flip = the elbow bent further than the mesh can follow)
  A weighted mesh's triangles count as part of the bone with the highest mean weight on them (a sleeve gives the forearm
  bone its part, so the hand's joint checks run), and annotated points on a mesh map through their deformed triangle.
Worn items: a back slot <slot>_back on its shell's bone (rig_worn.py) counts as part of that bone; going out of sight
behind the leg is its purpose (not occluded), its shell's cut edge over it is not a seam, a variant swapped in for the
check takes its back with it, and a socket's parent includes its back part (the leg showing inside the opening).
Writes rig/qa/<anim>.gif, rig/qa/<anim>_strip.png (every 5th frame), rig/qa/report.json.
Exit code 1 if any check fails.

Supports the subset spine_rig.py emits: region attachments; mesh attachments, weighted (vertex = sum of weight x bone
world matrix x bind position) or unweighted (x, y in the slot bone's space), drawn as per-triangle affine warps of their
uv triangles (no deform timelines); rotate/translate/scale bone timelines with linear (or stepped) keys; slot
attachment timelines; drawOrder timelines (stepped; render, the occlusion and seam checks use the keyed order).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import qa_constraints   # spine_pro's constructs (inherit modes, constraints, slot colours); legacy rigs never reach it

# thresholds (per frame at the given fps)
CHECK_H = 760          # checks render at this height so pixel quantisation can't flip a result
GIF_H = 480            # GIFs and strips are written at this height
MAX_ANG_JUMP = 4.0     # deg/frame change in angular velocity between consecutive frames
MAX_POS_JUMP = 0.012   # change in velocity, as a fraction of skeleton height, between consecutive frames
FADED_OUT = 0.02       # slot alpha at or under this: the slot draws nothing (a fade below it is judged as hidden)
JOINT_COVER = 0.9      # fraction of the joint disk that parent+child must cover
STITCH_MIN = 0.5           # overlap(t) / overlap(setup) below this = a gap is opening at the joint
STITCH_GROW = 0.08         # overlap growth beyond this fraction of the smaller part = it slides into its parent
VARIANT_FIT = (0.4, 2.5)   # variant overlap with its parent / rest attachment's overlap, in the setup pose
VARIANT_SIZE = 1.6         # a variant's drawn size (sqrt of its area, setup pose) within this factor of its rest's
MIN_JOINT_OVERLAP = 0.03   # setup overlap between a part and its parent, as a fraction of the smaller part
MAX_STRAY_PX = 40          # stray pixels (faint or thin, >4px from the part's solid body), native resolution
FRAGMENT_PX = 60           # a second solid island this big (native px) in one part = a detached fragment
OCCLUDED_FRAC = 0.4        # a part >70% visible at rest that drops below this visible fraction = hidden behind another
SETUP_IOU = 0.85       # setup-pose silhouette vs master
SEAM_MAX = 0.10        # fraction of a piece's edge (over another piece) that may read as a hairline. Calibrated on the
                       # part-variants fox/moose: unfixed rigs 0.135-0.42 on the seams seen by eye, fixed rigs <= 0.07
SEAM_DELTA = 0.04      # luminance (0..1) beyond the inside/outside range that makes an edge pixel a line pixel
SEAM_CHROMA = 0.02     # a line pixel is greyer (max-min RGB, 0..1) than both sides by more than this
SEAM_STEP = 3          # px: inside/outside sample distance, and the erosion of the lower piece
SEAM_MIN_PX = 30       # a pair needs this many sampled edge pixels in a frame to be scored
SOCKET_SPILL = 0.03    # fraction of a child's pixels near its parent's opening that may show past the rim beside the parent
LANDMARK_DRIFT = 0.01  # setup-pose joint vs its master point, as a fraction of body height (plus the joint's push-in)
KEY_HOLES = 0.015      # contract: share of the silhouette keyed as background holes. Calibrated: the rejected rabbit
                       # masters (pale fur, white muzzle on light grey) 4.5-7.6%, every rigged master <= 0.25%
KEY_CLOSE = 0.0025     # the key is closed by this x the image height (6 px at 2400) before its holes are filled
KEY_BG_NOISE = 0.015   # a hole pixel this close to the border colour is flat background, not figure keyed out
SOCKET_EVERY = 3       # sockets are checked on every 3rd frame of every animation (plus the setup pose)


def apply_offsets(names: list, offsets: list) -> list:
    """A drawOrder key applied to the setup order, as Spine does: each keyed slot goes to its setup index + offset,
    the other slots fill the remaining places in their setup order."""
    out = [None] * len(names)
    moved = set()
    for o in offsets:
        i = names.index(o["slot"])
        out[i + int(o["offset"])] = o["slot"]
        moved.add(o["slot"])
    rest = iter(n for n in names if n not in moved)
    return [n if n is not None else next(rest) for n in out]


def bezier(t0, v0, cx1, cy1, cx2, cy2, t1, v1, t: float) -> float:
    """A Spine Bezier segment from (t0, v0) to (t1, v1) with handles (cx1, cy1), (cx2, cy2): the curve's parameter
    is solved for time t, then its value read off."""
    lo, hi = 0.0, 1.0
    for _ in range(40):                                           # x(s) is monotone for valid Spine handles
        s = (lo + hi) / 2
        x = (1 - s) ** 3 * t0 + 3 * (1 - s) ** 2 * s * cx1 + 3 * (1 - s) * s * s * cx2 + s ** 3 * t1
        lo, hi = (s, hi) if x < t else (lo, s)
    s = (lo + hi) / 2
    return (1 - s) ** 3 * v0 + 3 * (1 - s) ** 2 * s * cy1 + 3 * (1 - s) * s * s * cy2 + s ** 3 * v1


def interp(keys: list, t: float, fields: tuple, defaults: tuple):
    if not keys:
        return None
    times = [k.get("time", 0.0) for k in keys]
    if t <= times[0]:
        return tuple(keys[0].get(f, d) for f, d in zip(fields, defaults))
    for i in range(len(keys) - 1):
        t0, t1 = times[i], times[i + 1]
        if t0 <= t < t1:
            a, b = keys[i], keys[i + 1]
            if a.get("curve") == "stepped":
                return tuple(a.get(f, d) for f, d in zip(fields, defaults))
            if isinstance(a.get("curve"), list):                  # Spine 4 Bezier: 4 numbers per value
                c = a["curve"]
                return tuple(bezier(t0, a.get(f, d), *c[4 * i:4 * i + 4], t1, b.get(f, d), t)
                             for i, (f, d) in enumerate(zip(fields, defaults)))
            u = (t - t0) / (t1 - t0) if t1 > t0 else 0
            return tuple(a.get(f, d) + (b.get(f, d) - a.get(f, d)) * u for f, d in zip(fields, defaults))
    return tuple(keys[-1].get(f, d) for f, d in zip(fields, defaults))


class Rig:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.bones = self.data["bones"]
        self.index = {b["name"]: i for i, b in enumerate(self.bones)}
        self.slots = self.data["slots"]
        self.skin = self.data["skins"][0]["attachments"]
        qa_constraints.resolve_linked(self.skin)
        self.extended = qa_constraints.extended(self.data)
        images = path.parent / self.data["skeleton"].get("images", "./images/")
        self.images = {}
        for slot in self.skin.values():
            for name in slot:
                self.images[name] = Image.open(images / f"{name}.png").convert("RGBA")

    def duration(self, anim: str) -> float:
        a = self.data["animations"][anim]
        times = [k.get("time", 0) for tl in a.get("bones", {}).values() for keys in tl.values() for k in keys]
        times += [k.get("time", 0) for tl in a.get("slots", {}).values() for keys in tl.values() for k in keys]
        times += [k.get("time", 0) for k in a.get("drawOrder", [])]
        return max(times or [0])

    def draw_order(self, anim: str | None, t: float) -> list[str]:
        """Slot names back to front at time t: the setup order, or the last drawOrder key at or before t (stepped;
        a key without offsets is the setup order)."""
        names = [s["name"] for s in self.slots]
        keys = self.data["animations"].get(anim, {}).get("drawOrder", []) if anim else []
        key = None
        for k in keys:
            if k.get("time", 0) <= t + 1e-6:
                key = k
        return apply_offsets(names, key.get("offsets", [])) if key else names

    def pose(self, anim: str | None, t: float, override: dict | None = None):
        """World matrices per bone (a, b, c, d, x, y) and the active attachment per slot (override: slot -> attachment)."""
        a = self.data["animations"].get(anim, {}) if anim else {}
        world = qa_constraints.pose_world(self.data, anim, t, interp) if getattr(self, "extended", False) else {}
        for b in (self.bones if not world else []):
            name = b["name"]
            x, y, rot = b.get("x", 0.0), b.get("y", 0.0), b.get("rotation", 0.0)
            sx, sy = b.get("scaleX", 1.0), b.get("scaleY", 1.0)
            tl = a.get("bones", {}).get(name, {})
            r = interp(tl.get("rotate", []), t, ("value",), (0.0,))
            if r:
                rot += r[0]
            tr = interp(tl.get("translate", []), t, ("x", "y"), (0.0, 0.0))
            if tr:
                x, y = x + tr[0], y + tr[1]
            sc = interp(tl.get("scale", []), t, ("x", "y"), (1.0, 1.0))
            if sc:
                sx, sy = sx * sc[0], sy * sc[1]
            rr = math.radians(rot)
            la, lb, lc, ld = math.cos(rr) * sx, -math.sin(rr) * sy, math.sin(rr) * sx, math.cos(rr) * sy
            if "parent" in b and b.get("inherit") == "noRotationOrReflection":   # rig_props: a stream stays upright
                pa, pb, pc, pd, px, py = world[b["parent"]]
                ksx, ksy = math.hypot(pa, pc), math.hypot(pb, pd)
                world[name] = (ksx * la, ksx * lb, ksy * lc, ksy * ld, pa * x + pb * y + px, pc * x + pd * y + py)
            elif "parent" in b:
                pa, pb, pc, pd, px, py = world[b["parent"]]
                world[name] = (pa * la + pb * lc, pa * lb + pb * ld, pc * la + pd * lc, pc * lb + pd * ld,
                               pa * x + pb * y + px, pc * x + pd * y + py)
            else:
                world[name] = (la, lb, lc, ld, x, y)
        active = {}
        for s in self.slots:
            name = s.get("attachment")
            keys = a.get("slots", {}).get(s["name"], {}).get("attachment", [])
            for k in keys:
                if k.get("time", 0) <= t + 1e-6:
                    name = k.get("name")
            active[s["name"]] = name
        active.update(override or {})
        return world, active

    def is_mesh(self, slot: str, att: str) -> bool:
        return self.skin[slot][att].get("type") == "mesh"

    def mesh_uv_px(self, slot: str, att: str) -> np.ndarray:
        """(n, 2) mesh vertices in attachment-image px (uvs are 0..1 over the image, v down)."""
        im = self.images[att]
        return np.array(self.skin[slot][att]["uvs"], dtype=float).reshape(-1, 2) * (im.width, im.height)

    def mesh_world(self, slot: str, att: str, world: dict) -> np.ndarray:
        """(n, 2) deformed mesh vertices in skeleton space (y up). Weighted form (more numbers than 2 per uv): per
        vertex boneCount, then boneCount x (boneIndex, bindX, bindY, weight), vertex = sum weight x bone world
        matrix . (bindX, bindY). Unweighted form: plain x, y in the slot bone's space."""
        A = self.skin[slot][att]
        v, n = A["vertices"], len(A["uvs"]) // 2
        if len(v) == 2 * n:
            a_, b_, c_, d_, x_, y_ = world[next(s["bone"] for s in self.slots if s["name"] == slot)]
            p = np.array(v, dtype=float).reshape(-1, 2)
            return np.stack([a_ * p[:, 0] + b_ * p[:, 1] + x_, c_ * p[:, 0] + d_ * p[:, 1] + y_], 1)
        out, k = np.zeros((n, 2)), 0
        for i in range(n):
            cnt = int(v[k])
            k += 1
            for _ in range(cnt):
                bi, bx, by, w = int(v[k]), v[k + 1], v[k + 2], v[k + 3]
                k += 4
                a_, b_, c_, d_, x_, y_ = world[self.bones[bi]["name"]]
                out[i] += w * np.array([a_ * bx + b_ * by + x_, c_ * bx + d_ * by + y_])
        return out

    def mesh_triangles(self, slot: str, att: str) -> np.ndarray:
        return np.array(self.skin[slot][att]["triangles"], dtype=int).reshape(-1, 3)

    def mesh_areas(self, slot: str, att: str, world: dict) -> np.ndarray:
        """Signed area (skeleton units^2, counter-clockwise > 0) of each deformed triangle."""
        p = self.mesh_world(slot, att, world)[self.mesh_triangles(slot, att)]
        e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
        return 0.5 * (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])

    def mesh_weighted(self, slot: str, att: str) -> bool:
        A = self.skin[slot][att]
        return len(A["vertices"]) != len(A["uvs"])

    def mesh_tri_bones(self, slot: str, att: str) -> list[str]:
        """Per triangle of a weighted mesh, the bone with the highest mean weight over its three vertices (the bone
        whose part that triangle draws: a sleeve's lower triangles belong to the forearm)."""
        v, n = self.skin[slot][att]["vertices"], len(self.skin[slot][att]["uvs"]) // 2
        W, k = np.zeros((n, len(self.bones))), 0
        for i in range(n):
            cnt = int(v[k])
            k += 1
            for _ in range(cnt):
                W[i, int(v[k])] += v[k + 3]
                k += 4
        return [self.bones[int(np.argmax(W[tri].mean(0)))]["name"] for tri in self.mesh_triangles(slot, att)]

    def att_affine_at(self, slot: str, att: str, world: dict, p) -> np.ndarray:
        """3x3 matrix taking attachment-image px to skeleton space, exact at image px p: a region's att_matrix; for a
        mesh, the affine map of the deformed triangle containing p (the nearest one, extrapolated, if p is outside)."""
        if not self.is_mesh(slot, att):
            return self.att_matrix(slot, att, world)
        tris = self.mesh_triangles(slot, att)
        uv, xy = self.mesh_uv_px(slot, att)[tris], self.mesh_world(slot, att, world)[tris]
        a, e1, e2 = uv[:, 0], uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
        det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        ok = np.abs(det) > 1e-12
        q = np.asarray(p, dtype=float) - a
        s = np.where(ok, (q[:, 0] * e2[:, 1] - q[:, 1] * e2[:, 0]) / np.where(ok, det, 1), 0)
        t = np.where(ok, (e1[:, 0] * q[:, 1] - e1[:, 1] * q[:, 0]) / np.where(ok, det, 1), 0)
        inside = np.where(ok, np.minimum(np.minimum(s, t), 1 - s - t), -np.inf)   # >= 0: p is in the triangle
        i = int(np.argmax(inside))
        S = np.vstack([uv[i].T, np.ones(3)])                                    # columns: (u, v, 1) per vertex
        D = np.vstack([xy[i].T, np.ones(3)])
        return D @ np.linalg.inv(S)

    def att_matrix(self, slot: str, att: str, world: dict):
        """3x3 matrix: attachment image pixel (u, v) -> skeleton space (x, y up). A mesh has no single matrix: this is
        the least-squares affine fit of its deformed vertices (exact while the mesh is not bent); map points with
        att_point / att_affine_at instead."""
        if self.is_mesh(slot, att):
            src, dst = self.mesh_uv_px(slot, att), self.mesh_world(slot, att, world)
            X = np.hstack([src, np.ones((len(src), 1))])
            sol, *_ = np.linalg.lstsq(X, dst, rcond=None)
            return np.vstack([sol.T, [0, 0, 1]])
        s = next(s for s in self.slots if s["name"] == slot)
        A = self.skin[slot][att]
        im = self.images[att]
        w, h = A.get("width", im.width), A.get("height", im.height)
        kx, ky = w / im.width * A.get("scaleX", 1), h / im.height * A.get("scaleY", 1)
        r = math.radians(A.get("rotation", 0))
        # pixel -> attachment local (centered, y up, scaled) -> rotated + offset -> bone world
        P = np.array([[kx, 0, -im.width / 2 * kx], [0, -ky, im.height / 2 * ky], [0, 0, 1]])
        R = np.array([[math.cos(r), -math.sin(r), A.get("x", 0)], [math.sin(r), math.cos(r), A.get("y", 0)], [0, 0, 1]])
        a_, b_, c_, d_, x_, y_ = world[s["bone"]]
        B = np.array([[a_, b_, x_], [c_, d_, y_], [0, 0, 1]])
        return B @ R @ P


class Canvas:
    def __init__(self, rig: Rig, height_px: int = 520, pad: float = 0.12, headroom: float = 0.25):
        sk = rig.data["skeleton"]
        self.h_units = sk["height"] * (1 + pad + headroom)      # extra room above for jumps and raised arms
        self.S = height_px / self.h_units
        self.ox = sk["x"] - sk["width"] * pad - sk["height"] * 0.35
        self.oy = sk["y"] + sk["height"] * (1 + headroom)
        self.W = int((sk["width"] * (1 + 2 * pad) + sk["height"] * 0.7) * self.S)
        self.H = height_px
        self.cache = {}

    def to_px(self):
        return np.array([[self.S, 0, -self.ox * self.S], [0, -self.S, self.oy * self.S], [0, 0, 1]])

    def layer(self, rig: Rig, slot: str, att: str, world: dict) -> Image.Image:
        if rig.is_mesh(slot, att):
            return self.mesh_layer(rig, slot, att, world)
        M = self.to_px() @ rig.att_matrix(slot, att, world)
        inv = np.linalg.inv(M)
        src = rig.images[att]
        return src.transform((self.W, self.H), Image.AFFINE, tuple(inv[:2].flatten()), resample=Image.BILINEAR)

    def mesh_layer(self, rig: Rig, slot: str, att: str, world: dict, owner: np.ndarray | None = None) -> Image.Image:
        """A mesh drawn triangle by triangle: each triangle's canvas px are an affine image of its uv triangle (bilinear,
        sampled like the region layer), clipped to the triangle (its outline included, so neighbours leave no gap).
        Pixels a triangle reaches first are copied; later triangles over them (a neighbour's shared edge, or a fold)
        are alpha-composited on top, in triangle order as Spine draws them. owner (H x W ints), if given, receives the
        index of the last triangle drawn at each pixel (-1: none)."""
        src_img = rig.images[att]
        P = rig.mesh_world(slot, att, world)
        dst = np.stack([(P[:, 0] - self.ox) * self.S, (self.oy - P[:, 1]) * self.S], 1)
        src = rig.mesh_uv_px(slot, att)
        out = np.zeros((self.H, self.W, 4), np.float32)
        drawn = np.zeros((self.H, self.W), bool)
        for ti, tri in enumerate(rig.mesh_triangles(slot, att)):
            d, s = dst[tri], src[tri]
            D = np.hstack([d, np.ones((3, 1))])
            if abs(np.linalg.det(D)) < 1e-9:                 # collapsed to a line: nothing to draw
                continue
            x0, y0 = max(0, int(math.floor(d[:, 0].min())) - 1), max(0, int(math.floor(d[:, 1].min())) - 1)
            x1, y1 = min(self.W, int(math.ceil(d[:, 0].max())) + 2), min(self.H, int(math.ceil(d[:, 1].max())) + 2)
            if x0 >= x1 or y0 >= y1:
                continue
            M = np.linalg.solve(D, s)                         # [X, Y, 1] (canvas px) @ M = image px
            data = (M[0, 0], M[1, 0], M[2, 0] + M[0, 0] * x0 + M[1, 0] * y0,
                    M[0, 1], M[1, 1], M[2, 1] + M[0, 1] * x0 + M[1, 1] * y0)
            t = np.asarray(src_img.transform((x1 - x0, y1 - y0), Image.AFFINE, data, resample=Image.BILINEAR),
                           dtype=np.float32)
            mk = Image.new("1", (x1 - x0, y1 - y0), 0)
            poly = [(float(x - x0 - 0.5), float(y - y0 - 0.5)) for x, y in d]   # px centres sit at +0.5
            ImageDraw.Draw(mk).polygon(poly, fill=1, outline=1)
            m = np.asarray(mk, dtype=bool)
            sub, dr = out[y0:y1, x0:x1], drawn[y0:y1, x0:x1]
            new, over = m & ~dr, m & dr
            sub[new] = t[new]
            if over.any():
                ts, ds = t[over], sub[over]
                a_s, a_d = ts[:, 3:] / 255, ds[:, 3:] / 255
                a_o = a_s + a_d * (1 - a_s)
                rgb = (ts[:, :3] * a_s + ds[:, :3] * a_d * (1 - a_s)) / np.maximum(a_o, 1e-6)
                sub[over] = np.hstack([rgb, a_o * 255])
            dr |= m
            if owner is not None:
                owner[y0:y1, x0:x1][m] = ti
        return Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), "RGBA")

    def point(self, x: float, y: float):
        return ((x - self.ox) * self.S, (self.oy - y) * self.S)


class SlotAlphas(dict):
    """Slot -> alpha mask (as render returns it), plus bone_split: for a slot showing a weighted mesh, bone -> the
    pixels of the triangles that bone owns (Rig.mesh_tri_bones), which bone_masks uses in place of the slot's bone."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.bone_split = {}


def render(rig: Rig, canvas: Canvas, anim: str | None, t: float, bg=(214, 214, 214, 255), override: dict | None = None):
    world, active = rig.pose(anim, t, override)
    frame = Image.new("RGBA", (canvas.W, canvas.H), bg)
    alphas = SlotAlphas()                                  # in draw order (a drawOrder key may change it)
    by_name = {s["name"]: s for s in rig.slots}
    decor = qa_constraints.decor_slots(rig)
    for s in (by_name[n] for n in rig.draw_order(anim, t)):
        att = active.get(s["name"])
        if not att:
            continue
        if rig.is_mesh(s["name"], att) and rig.mesh_weighted(s["name"], att):
            owner = np.full((canvas.H, canvas.W), -1, np.int32)
            lay = canvas.mesh_layer(rig, s["name"], att, world, owner)
            a_ = np.asarray(lay)[..., 3] > 127
            split = {}
            for ti, bn in enumerate(rig.mesh_tri_bones(s["name"], att)):
                split.setdefault(bn, []).append(ti)
            alphas.bone_split[s["name"]] = {bn: a_ & np.isin(owner, tis) for bn, tis in split.items()}
        else:
            lay = canvas.layer(rig, s["name"], att, world)
        color = qa_constraints.slot_color(rig.data, s, anim, t)
        if color is not None and color[3] <= FADED_OUT:   # faded out entirely: draws nothing
            alphas.bone_split.pop(s["name"], None)
            continue
        # a slot part-way through a fade (rig_anim.cross_fade: the legs drawings) is judged by its whole drawing, as
        # at full alpha (the stricter case: both drawings of a cross-fade count); only the picture fades
        shape = np.asarray(lay)[..., 3] > 127
        lay = qa_constraints.tint(lay, color)
        if s["name"] in decor:                             # shadow / underfill: drawn, never judged as a part
            alphas.bone_split.pop(s["name"], None)
            frame.alpha_composite(lay)
            continue
        alphas[s["name"]] = shape
        frame.alpha_composite(lay)
    return frame, world, active, alphas


def mesh_joined(alphas: dict, bone: str, other: str) -> bool:
    """Do both bones draw parts of one weighted mesh (one continuous drawing: their joint needs no overlap)?"""
    return any(bone in sp and other in sp for sp in getattr(alphas, "bone_split", {}).values())


def worn_backs(rig: Rig) -> dict:
    """Back slots of worn items (spine_rig.py --annotations cuts a boot into its shell and <slot>_back, the inside and
    back rim drawn behind the leg, on the same bone): back slot -> shell slot."""
    bone = {s["name"]: s["bone"] for s in rig.slots}
    return {n: n[: -len("_back")] for n in bone if n.endswith("_back") and bone.get(n[: -len("_back")]) == bone[n]}


def with_back(rig: Rig, slot: str, att: str | None) -> dict:
    """Attachment override for a shell slot and, if it has one, its back slot (the back of that attachment or none)."""
    out = {slot: att}
    back = f"{slot}_back"
    if back in rig.skin and worn_backs(rig).get(back) == slot:
        out[back] = f"{att}_back" if att and f"{att}_back" in rig.skin[back] else None
    return out


def bone_masks(rig: Rig, alphas: dict) -> dict:
    """Union silhouette of every slot on each bone (a bone may carry a part plus patches). A weighted mesh gives each
    triangle's pixels to the bone with the highest mean weight on it (render's bone_split), so a sleeve on the upper
    arm's slot gives the forearm bone its part too."""
    out = {}
    split = getattr(alphas, "bone_split", {})
    for s in rig.slots:
        if s["name"] in alphas:
            for bone, m in (split[s["name"]].items() if s["name"] in split else [(s["bone"], alphas[s["name"]])]):
                out[bone] = out[bone] | m if bone in out else m.copy()
    return out


def components(mask: np.ndarray) -> list[int]:
    """Areas of the connected components of a boolean mask, largest first (flood fill via PIL)."""
    from PIL import ImageDraw as _D
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return []
    sub = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    im = Image.fromarray(np.where(sub, 255, 0).astype(np.uint8)).copy()   # writable (fromarray shares a read-only buffer)
    areas = []
    for k in range(250):
        arr = np.asarray(im)
        left_ = np.argwhere(arr == 255)
        if not len(left_):
            break
        y, x = left_[0]
        _D.floodfill(im, (int(x), int(y)), 1 + (k % 200))
        arr2 = np.asarray(im)
        areas.append(int(((arr2 == 1 + (k % 200)) & (arr == 255)).sum()))
    return sorted(areas, reverse=True)


def dilate(m: np.ndarray, r: int = 1) -> np.ndarray:
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def mesh_attachments(rig: Rig) -> list[tuple[str, str]]:
    return [(slot, att) for slot, atts in rig.skin.items() for att in atts if rig.is_mesh(slot, att)]


def mesh_fold_setup(rig: Rig) -> dict:
    """mesh_fold on the setup pose: every triangle of every mesh keeps the orientation of its uv triangle as the slot
    bone carries it (image v runs down, the skeleton's y up; a mirrored bone mirrors it). A triangle against it (or
    collapsed) is a fold baked into the bind. Returns {attachment: {"flipped": [triangle index], "triangles": n}}."""
    world, _ = rig.pose(None, 0)
    bone = {s["name"]: s["bone"] for s in rig.slots}
    out = {}
    for slot, att in mesh_attachments(rig):
        a_, b_, c_, d_, _, _ = world[bone[slot]]
        uv = rig.mesh_uv_px(slot, att)[rig.mesh_triangles(slot, att)]
        e1, e2 = uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
        ref = -np.sign(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) * np.sign(a_ * d_ - b_ * c_)
        bad = np.flatnonzero((rig.mesh_areas(slot, att, world) * ref <= 0) & (ref != 0))
        if len(bad):
            out[att] = {"flipped": bad.tolist(), "triangles": len(ref)}
    return out


def mesh_flips(rig: Rig, world: dict, active: dict, setup_signs: dict) -> dict:
    """Number of triangles of each active mesh whose signed area has the opposite sign (or none) to the setup pose's
    (setup_signs: (slot, attachment) -> sign per triangle). Returns {attachment: (flipped, triangles)}, folds only."""
    out = {}
    for slot, att in mesh_attachments(rig):
        if active.get(slot) != att:
            continue
        ref = setup_signs[(slot, att)]
        n = int(((rig.mesh_areas(slot, att, world) * ref <= 0) & (ref != 0)).sum())
        if n:
            out[att] = (n, len(ref))
    return out


def check_anim(rig: Rig, canvas: Canvas, anim: str, fps: int, outdir: Path) -> dict:
    dur = max(rig.duration(anim), 1 / fps)
    n = int(round(dur * fps)) + 1
    parent = {b["name"]: b.get("parent") for b in rig.bones}
    frames, traj = [], {b["name"]: [] for b in rig.bones}
    shown = set()                       # bones that draw something in some frame (a prop's bone is hidden at rest)
    drawn = {b["name"]: [] for b in rig.bones}                             # per frame: does the bone draw anything
    hanging = {b["name"] for b in rig.bones if b.get("inherit") == "noRotationOrReflection"}   # rig_props: a stream
    # pouring from a spout hangs free by design; it touches its prop but is no joint to stitch
    props_ = {s_["name"] for s_ in rig.slots if not s_.get("attachment")}   # props (rig_props): no attachment at rest;
                                                                           # going behind the character is their job
    slotted = {s_["bone"] for s_ in rig.slots}
    detached, holes, unstitched, ov0, occluded = {}, {}, {}, {}, {}
    vis0 = {}
    bone_slots = {}
    for s_ in rig.slots:
        bone_slots.setdefault(s_["bone"], []).append(s_["name"])
    setup_world, setup_active = rig.pose(None, 0)
    setup_signs = {k: np.sign(rig.mesh_areas(*k, setup_world)) for k in mesh_attachments(rig)}
    folds = {}                                             # mesh_fold: attachment -> [(t, flipped triangles)]
    backs = worn_backs(rig)                                # hidden behind the leg on purpose: not occlusion

    def local_overlap(alph: dict, world: dict, bone: str, pbone: str) -> tuple[int, int]:
        """Overlap of part and parent inside a disk around the pivot about one limb-width across, and the disk area."""
        jx, jy = canvas.point(world[bone][4], world[bone][5])
        R = max(4, int(0.5 * math.sqrt(alph[bone].sum())))
        y0, y1, x0, x1 = max(0, int(jy) - R), min(canvas.H, int(jy) + R + 1), max(0, int(jx) - R), min(canvas.W, int(jx) + R + 1)
        yy_, xx_ = np.mgrid[y0:y1, x0:x1]
        d_ = (xx_ - jx) ** 2 + (yy_ - jy) ** 2 <= R * R
        return int((alph[bone][y0:y1, x0:x1] & alph[pbone][y0:y1, x0:x1] & d_).sum()), int(d_.sum())
    baseline = {}

    def base_overlap(bone: str, pbone: str, active: dict) -> int:
        """Joint overlap in the setup pose with the attachments currently active on both bones."""
        key = (bone, pbone) + tuple(active.get(n_) for n_ in bone_slots.get(bone, []) + bone_slots.get(pbone, []))
        if key not in baseline:
            ov_ = {n_: active.get(n_) for n_ in bone_slots.get(bone, []) + bone_slots.get(pbone, [])}
            _, w0, _, al0 = render(rig, canvas, None, 0, override=ov_)
            baseline[key] = local_overlap(bone_masks(rig, al0), w0, bone, pbone)[0]
        return baseline[key]
    for i in range(n):
        t = i / fps
        frame, world, active, alphas = render(rig, canvas, anim, t)
        frames.append(frame.convert("RGB").resize((round(canvas.W * GIF_H / canvas.H), GIF_H), Image.LANCZOS))
        for b in rig.bones:
            a_, b_, c_, d_, x_, y_ = world[b["name"]]
            traj[b["name"]].append((x_, y_, math.degrees(math.atan2(c_, a_))))
        now = {s_["bone"] for s_ in rig.slots if active.get(s_["name"])}
        shown.update(now)
        for b in rig.bones:
            drawn[b["name"]].append(b["name"] in now or b["name"] not in slotted)
        for att_, (nf, nt) in mesh_flips(rig, world, active, setup_signs).items():
            folds.setdefault(att_, []).append((round(t, 3), nf, nt))
        order_ = list(alphas)                                # render's order: the frame's draw order
        later = np.zeros((canvas.H, canvas.W), bool)
        vis = {}
        for name_ in reversed(order_):                       # front-most first
            a_ = alphas[name_]
            vis[name_] = float((a_ & ~later).sum() / max(1, a_.sum()))
            if name_ not in props_:                          # a prop in front (a hurdle) may hide the body
                later |= a_
        if i == 0:
            vis0 = vis
        else:
            for name_, v in vis.items():
                v0 = vis0.get(name_, 0)                         # clearly visible at rest and mostly hidden now, or a
                if not name_.endswith("_patch") and name_ not in backs and name_ not in props_ and ((v0 > 0.7 and v < OCCLUDED_FRAC) or (v0 > 0.3 and v < 0.35 * v0)):   # part tucked at rest losing most of what showed
                    occluded.setdefault(name_, []).append((round(t, 2), round(v, 2)))
        alphas = bone_masks(rig, alphas)
        for bone in list(alphas):
            slot, pslot = bone, parent.get(bone)
            if not pslot or pslot not in alphas:
                continue
            # attached: child and parent silhouettes touch
            if not (dilate(alphas[slot], 2) & alphas[pslot]).any():
                detached.setdefault(slot, []).append(round(t, 3))
            ov, disk_area = local_overlap(alphas, world, slot, pslot)
            ref = base_overlap(slot, pslot, active) if slot not in hanging else 0
            if ref:
                ratio = ov / ref
                grow_frac = (ov - ref) / max(1, disk_area)
                if ratio < STITCH_MIN or grow_frac > STITCH_GROW * 3:   # growth judged against the joint disk (~1/3 of a limb)
                    unstitched.setdefault(slot, []).append((round(t, 2), round(ratio, 2)))
            # joint: the child's pivot is covered by parent or child
            jx, jy = canvas.point(world[bone][4], world[bone][5])
            r = max(3, round(0.007 * rig.data["skeleton"]["height"] * canvas.S))   # ~0.7% of body height
            yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
            disk = (xx ** 2 + yy ** 2) <= r * r
            X, Y = (np.clip(int(jx) + xx[disk], 0, canvas.W - 1), np.clip(int(jy) + yy[disk], 0, canvas.H - 1))
            cover = (alphas[slot][Y, X] | alphas[pslot][Y, X]).mean()
            if cover < JOINT_COVER:
                holes.setdefault(slot, []).append(round(t, 3))
    # smoothness on world trajectories
    h_units = rig.data["skeleton"]["height"]
    jerks = {}
    for name, tr in traj.items():
        arr = np.array(tr)
        if len(arr) < 3 or (name in slotted and name not in shown):     # nothing of it is drawn in this animation
            continue
        ang = np.unwrap(np.radians(arr[:, 2])) * 180 / math.pi
        va = np.diff(ang)
        vp = np.diff(arr[:, :2], axis=0) / h_units
        on = np.array(drawn[name], bool)
        on3 = on[:-2] & on[1:-1] & on[2:]                                  # only while it is drawn (a prop shown late)
        ja = np.abs(np.diff(va)) * on3
        jp = np.linalg.norm(np.diff(vp, axis=0), axis=1) * on3
        worst_a, worst_p = float(ja.max(initial=0)), float(jp.max(initial=0))
        if worst_a > MAX_ANG_JUMP or worst_p > MAX_POS_JUMP:
            jerks[name] = {"max_ang_vel_change_deg": round(worst_a, 2), "at_frame": int(np.argmax(ja)) + 1,
                           "max_pos_vel_change": round(worst_p, 4)}
    outdir.mkdir(parents=True, exist_ok=True)
    frames[0].save(outdir / f"{anim}.gif", save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0)
    picks = frames[::5] or frames
    fw, fh = frames[0].size
    tw, th = fw // 2, fh // 2
    strip = Image.new("RGB", (tw * len(picks), th), (255, 255, 255))
    for k, f in enumerate(picks):
        strip.paste(f.resize((tw, th)), (k * tw, 0))
        ImageDraw.Draw(strip).text((k * tw + 4, 4), f"{k * 5 / fps:.2f}s", fill=(200, 0, 0))
    strip.save(outdir / f"{anim}_strip.png")
    unstitched = {k: {"frames": len(v), "worst": min(v, key=lambda x: min(x[1], 1 / max(x[1], 1e-6)))} for k, v in unstitched.items()}
    occluded = {k: {"frames": len(v), "worst": min(v, key=lambda x: x[1])} for k, v in occluded.items()}
    mesh_fold = {}
    for att_, v in folds.items():                          # worst frame: the most triangles flipped (latest on a tie)
        t_, nf, nt = max(v, key=lambda x: (x[1], x[0]))
        mesh_fold[att_] = {"frames": len(v), "worst": {"t": t_, "flipped": nf, "triangles": nt}}
    ok = not detached and not holes and not jerks and not unstitched and not occluded and not mesh_fold
    return {"pass": ok, "frames": n, "duration": round(dur, 3), "detached": detached, "joint_holes": holes,
            "unstitched": unstitched, "jerky_bones": jerks, "occluded": occluded, "mesh_fold": mesh_fold}


def check_structure(rig: Rig, canvas: Canvas) -> dict:
    """Setup pose: every child pivot inside child AND parent silhouettes; bone points into its part."""
    frame, world, active, slot_alphas = render(rig, canvas, None, 0)
    alphas = bone_masks(rig, slot_alphas)
    parent = {b["name"]: b.get("parent") for b in rig.bones}
    off_joint, reversed_, weak = {}, {}, {}
    for bone in list(alphas):
        slot = bone
        jx, jy = canvas.point(world[bone][4], world[bone][5])
        X, Y = int(np.clip(jx, 0, canvas.W - 1)), int(np.clip(jy, 0, canvas.H - 1))
        pslot = parent.get(bone)
        inside_child = bool(dilate(alphas[slot], 2)[Y, X])
        inside_parent = bool(dilate(alphas[pslot], 2)[Y, X]) if pslot in alphas else True
        if not (inside_child and inside_parent):
            off_joint[slot] = {"in_part": inside_child, "in_parent": inside_parent}
        if pslot in alphas and not mesh_joined(slot_alphas, bone, pslot):   # one mesh's two bones meet edge to edge
            ov = int((alphas[slot] & alphas[pslot]).sum())
            need = MIN_JOINT_OVERLAP * min(alphas[slot].sum(), alphas[pslot].sum())
            if ov < need:
                weak[slot] = {"overlap_px": ov, "needed_px": int(need)}
        ys, xs = np.nonzero(alphas[slot])
        if len(xs) and pslot:
            v = np.array([xs.mean() - jx, -(ys.mean() - jy)])
            a_, _, c_, _, _, _ = world[bone]
            d = np.array([a_, c_])
            if np.linalg.norm(v) > 3 and np.dot(v, d) / (np.linalg.norm(v) * np.linalg.norm(d) + 1e-9) < -0.2:
                reversed_[slot] = "bone points away from its own part"
    slivers, fragments = {}, {}
    every = [(slot, att) for slot, atts in rig.skin.items() for att in atts if not slot.endswith("_patch")]
    for slot, att in every:
        comps = components(np.asarray(rig.images[att])[..., 3] > 127)
        extra = [c for c in comps[1:] if c >= max(FRAGMENT_PX, 0.003 * comps[0])]
        if extra:
            fragments[att] = extra[:5]
    for slot, att in every:
        al = np.asarray(rig.images[att])[..., 3] > 30   # native resolution, faint pixels included
        if al.sum() < 4000:                              # too small to judge
            continue
        a8 = np.asarray(rig.images[att])[..., 3]
        solid = a8 > 127
        core = dilate(~dilate(~solid, 3), 3)             # the part's solid body (opening removes thin bits)
        stray = (a8 > 8) & ~dilate(core, 4)              # faint or thin pixels away from the body
        if stray.sum() > MAX_STRAY_PX:
            slivers[att] = int(stray.sum())
    # draw order: a tail drawn after a leg, foot or the hips shows in front of them
    decor_ = qa_constraints.decor_slots(rig)               # shadow / underfills sit behind everything by design
    names = [s_["name"] for s_ in rig.slots if s_["name"] not in decor_]
    lower = [i for i, n_ in enumerate(names) if any(w in n_ for w in ("leg", "foot", "boot", "hoof", "shoe", "hips"))]
    order = {n_: "drawn in front of the legs/hips" for i, n_ in enumerate(names) if "tail" in n_ and lower and i > min(lower)}
    # variants: swapped into the setup pose they still close their joint, overlap their parent like the rest part,
    # and are drawn about the rest part's size
    misfit, oversize = {}, {}
    backs = worn_backs(rig)
    for slot, atts in rig.skin.items():
        rest = active.get(slot)
        if slot in backs:                                # checked together with its shell
            continue
        if len(atts) < 2 or not rest or slot not in slot_alphas:
            continue
        bone = next(s_["bone"] for s_ in rig.slots if s_["name"] == slot)
        pbone = parent.get(bone)
        joint_check = pbone in alphas and slot != "head"
        base = int((alphas[bone] & alphas[pbone]).sum()) if joint_check else 0
        rest_px = int(slot_alphas[slot].sum())
        for att in atts:
            if att == rest:
                continue
            _, w_, _, sal_ = render(rig, canvas, None, 0, override=with_back(rig, slot, att))
            size = math.sqrt(int(sal_[slot].sum()) / max(1, rest_px)) if slot in sal_ else 0.0
            if not (1 / VARIANT_SIZE <= size <= VARIANT_SIZE):
                oversize[att] = {"size_vs_rest": round(size, 2)}
            if not joint_check:
                continue
            al_ = bone_masks(rig, sal_)
            ratio = int((al_[bone] & al_[pbone]).sum()) / max(1, base)
            jx, jy = canvas.point(w_[bone][4], w_[bone][5])
            X, Y = int(np.clip(jx, 0, canvas.W - 1)), int(np.clip(jy, 0, canvas.H - 1))
            if not (VARIANT_FIT[0] <= ratio <= VARIANT_FIT[1]) or not dilate(al_[bone], 2)[Y, X]:
                misfit[att] = {"overlap_vs_rest": round(ratio, 2), "covers_joint": bool(dilate(al_[bone], 2)[Y, X])}
    mesh_fold = mesh_fold_setup(rig)
    ok = not off_joint and not reversed_ and not weak and not slivers and not fragments and not order and not misfit \
        and not oversize and not mesh_fold
    return {"pass": ok, "pivot_off_joint": off_joint, "reversed_bones": reversed_, "weak_joints": weak, "slivers": slivers,
            "fragments": fragments, "draw_order": order, "variant_misfit": misfit, "variant_size": oversize,
            "mesh_fold": mesh_fold}


def check_seams(rig: Rig, canvas: Canvas, frames: list) -> dict:
    """Hairlines where one piece's edge lies over another piece. For each pair of slots (upper drawn after lower),
    sample the boundary pixels of upper's silhouette that lie inside lower's silhouette eroded by 3 px (and are not
    covered by anything drawn later). A boundary pixel is a line pixel when its luminance on the composite lies
    more than SEAM_DELTA outside the range spanned by the pixels 3 px inside and 3 px outside the edge (along the
    alpha-gradient normal), the pixel 1 px inside does not (the line is confined to the boundary), and its chroma is
    more than SEAM_CHROMA below both of those samples' (greyer than either side: background-removal leftovers are
    the sheet's neutral grey). Painted folds inside a piece are never sampled, only piece boundaries; a painted rim
    runs inward or keeps its colour and is not counted.
    Score per pair = fraction of line pixels, worst over `frames` ((anim or None, seconds) each)."""
    worst = {}
    own = {frozenset(p) for p in worn_backs(rig).items()}   # a shell's cut edge over its own back part is not a seam
    for anim, t in frames:
        frame, _, _, alphas = render(rig, canvas, anim, t)
        rgb = np.asarray(frame.convert("RGB"), dtype=np.float32) / 255
        lum = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        chroma = rgb.max(2) - rgb.min(2)
        order = list(alphas)                            # render's order: the frame's draw order
        eroded = {n: ~dilate(~alphas[n], SEAM_STEP) for n in order}
        later = np.zeros((canvas.H, canvas.W), bool)
        cover_after = {}
        for n in reversed(order):                       # what is drawn after each slot
            cover_after[n] = dilate(later, SEAM_STEP + 1)
            later = later | alphas[n]
        for i, up in enumerate(order):
            m = alphas[up]
            edge = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1)) & ~cover_after[up]
            if not edge.any():
                continue
            blur = m.astype(np.float32)
            for ax in (0, 1):                           # 5-px box blur, so the gradient gives a stable normal
                blur = sum(np.roll(blur, k, ax) for k in range(-2, 3)) / 5
            gy, gx = np.gradient(blur)
            for lo in order[:i]:
                if frozenset((up, lo)) in own:
                    continue
                sel = edge & eroded[lo]
                if sel.sum() < SEAM_MIN_PX:
                    continue
                ys, xs = np.nonzero(sel)
                nx, ny = gx[ys, xs], gy[ys, xs]
                nn = np.hypot(nx, ny) + 1e-9
                nx, ny = nx / nn, ny / nn                  # unit normal pointing into upper
                def at(img, k):
                    X = np.clip(np.round(xs + k * nx).astype(int), 0, canvas.W - 1)
                    Y = np.clip(np.round(ys + k * ny).astype(int), 0, canvas.H - 1)
                    return img[Y, X]
                le, lin, lout, l1 = lum[ys, xs], at(lum, SEAM_STEP), at(lum, -SEAM_STEP), at(lum, 1)
                lo_, hi_ = np.minimum(lin, lout) - SEAM_DELTA, np.maximum(lin, lout) + SEAM_DELTA
                # a hairline is confined to the boundary (a rim the piece carries 1 px further in is painted: a boot's
                # lip, a bell's rim, chin fur) and greyer than both sides (what leaks in is the neutral sheet colour)
                confined = ((le < lo_) & (l1 >= lo_)) | ((le > hi_) & (l1 <= hi_))
                greyer = chroma[ys, xs] < np.minimum(at(chroma, SEAM_STEP), at(chroma, -SEAM_STEP)) - SEAM_CHROMA
                line = confined & greyer
                key = f"{up}/{lo}"
                worst[key] = max(worst.get(key, 0.0), round(float(line.mean()), 3))
    return {"pass": all(v <= SEAM_MAX for v in worst.values()), "seams": worst}


def _xy(M: np.ndarray, p) -> np.ndarray:
    """Apply a 3x3 affine matrix to a 2-D point."""
    return (M @ np.array([float(p[0]), float(p[1]), 1.0]))[:2]


def mesh_point(rig: Rig, slot: str, att: str, world: dict, p) -> np.ndarray:
    """A mesh attachment's image px p -> skeleton space, through the deformed triangle containing it (barycentric)."""
    return _xy(rig.att_affine_at(slot, att, world, p), p)


def att_point(rig: Rig, slot: str, att: str, world: dict, p) -> np.ndarray:
    """Any attachment's image px p -> skeleton space (a mesh's exactly, a region's by its matrix)."""
    return mesh_point(rig, slot, att, world, p) if rig.is_mesh(slot, att) else _xy(rig.att_matrix(slot, att, world), p)


def check_thumbs(rig: Rig, resolved: dict, anims: list | None = None) -> dict:
    """At each gesture's hold, with the hold's hand variant active, the thumb points within THUMB_TOL of its target.
    The thumb is rig_hands.thumb_vector (the part of wrist -> thumb_tip across wrist -> fingertip, or across image-down
    without a fingertip), taken in attachment-image px and carried through the attachment's matrix to the world
    (y up). A thumb on the hand's axis has no side: that hold is reported as unchecked, not failed.
    Returns {"pass", "thumbs": {anim: error_deg}, "unchecked": {anim: reason}}."""
    import rig_hands
    thumbs, unchecked = {}, {}
    for anim, h in resolved.get("holds", {}).items():
        if anim not in rig.data["animations"] or (anims is not None and anim not in anims):
            continue
        att = h["attachment"]
        pts = resolved["attachments"].get(att, {}).get("points", {})
        target = h.get("thumb_target", resolved.get("thumb_targets", {}).get(att))   # the hold's own, when recorded
        if target is None or "wrist" not in pts or "thumb_tip" not in pts:
            unchecked[anim] = "no thumb target" if target is None else "no wrist/thumb_tip"
            continue
        tv = rig_hands.thumb_vector(pts["wrist"], pts["thumb_tip"], pts.get("fingertip"))
        if math.hypot(*tv) < 1e-9:
            unchecked[anim] = "thumb on the hand's axis"
            continue
        world, _ = rig.pose(anim, h["time"], {h["slot"]: att})
        M = rig.att_affine_at(h["slot"], att, world, pts["wrist"])   # a mesh's: the triangle at the wrist
        w0 = _xy(M, pts["wrist"])
        w1 = _xy(M, (pts["wrist"][0] + tv[0], pts["wrist"][1] + tv[1]))
        deg = math.degrees(math.atan2(w1[1] - w0[1], w1[0] - w0[0]))
        thumbs[anim] = round(rig_hands.ang_diff(deg, target), 1)
    return {"pass": all(e <= rig_hands.THUMB_TOL for e in thumbs.values()), "thumbs": thumbs, "unchecked": unchecked}


def _opening_inward(prec: dict, parent_point: str):
    """Unit inward axis (attachment-image px of the parent) of the parent's opening: rig_annotations.opening_inward
    for the role that owns the point (hips.hip_l, foot.ankle, ...). None when it has none; the caller then uses the
    child's own axis."""
    import rig_annotations as ra
    pts = set(prec["points"])                 # "wrist" is a forearm's and a hand's: the role that has all its points
    roles = [r for r in ra.ROLES if parent_point in ra.role_points(r) and pts <= set(ra.role_points(r))]
    if len(roles) > 1:                        # a forearm's points are also a whole sleeve's (arm): the closest fit
        fewest = min(len(ra.role_points(r)) for r in roles)
        roles = [r for r in roles if len(ra.role_points(r)) == fewest]
    if len(roles) != 1:
        return None
    return ra.opening_inward(roles[0], parent_point, tuple(prec["points"][parent_point]),
                             {n: tuple(p) for n, p in prec["points"].items()})


def check_sockets(rig: Rig, canvas: Canvas, resolved: dict, anims: list, fps: int = 30) -> dict:
    """Every socket in the resolved file (a leg's hem in its boot, a leg's hip in the hips), on the setup pose and
    every SOCKET_EVERY-th frame of each animation, with whatever attachments are active on both slots:
      off    the child's end point must lie within width/2 of the parent's opening centre (reported as
             distance / (width/2), so > 1 fails);
      spill  of the child's opaque pixels within a disk (radius = the opening's width) around the opening centre, the
             fraction that lies past the rim line (the line through the centre across the opening's inward axis,
             towards the parent's interior; moved rim_inset along that axis when the parent attachment
             records one, a forearm trimmed under its glove) and is not covered by the parent; > SOCKET_SPILL fails.
    Returns {"pass", "sockets": {"child/parent": {"spill", "spill_at", "off", "off_at"}}} (worst per socket)."""
    atts = resolved.get("attachments", {})
    socks = [s for s in resolved.get("sockets", []) if s["child"] in atts and s["parent"] in atts]
    frames = [(None, 0.0)]
    for anim in anims:
        n = int(round(max(rig.duration(anim), 1 / fps) * fps)) + 1
        frames += [(anim, i / fps) for i in range(0, n, SOCKET_EVERY)]
    to_px = canvas.to_px()
    worst = {}
    back_of = {v: k for k, v in worn_backs(rig).items()}   # a worn boot's back part (its inside) is part of the parent
    for anim, t in frames:
        world, active = rig.pose(anim, t)
        masks = {}

        def mask(slot, att):
            if slot not in masks:
                masks[slot] = np.asarray(canvas.layer(rig, slot, att, world))[..., 3] > 127
                back = back_of.get(slot)
                if back and active.get(back):
                    masks[slot] = masks[slot] | (np.asarray(canvas.layer(rig, back, active[back], world))[..., 3] > 127)
            return masks[slot]
        for s in socks:
            cslot, pslot = atts[s["child"]]["slot"], atts[s["parent"]]["slot"]
            ca, pa = active.get(cslot), active.get(pslot)
            crec, prec = atts.get(ca), atts.get(pa)
            cp, pp = s["child_point"], s["parent_point"]
            if not crec or not prec or cp not in crec["points"] or pp not in prec["points"]:
                continue
            width = prec["widths"].get(pp) or (s["width"] if pa == s["parent"] else None)
            if not width:
                continue
            Mp = to_px @ rig.att_affine_at(pslot, pa, world, prec["points"][pp])   # a mesh's: exact at the point
            Mc = to_px @ rig.att_affine_at(cslot, ca, world, crec["points"][cp])
            u = _opening_inward(prec, pp)
            L = Mp[:2, :2]
            if u is None:                       # the child's own axis: from its other point through the socket point
                other = next((q for n_, q in crec["points"].items() if n_ != cp), None)
                if other is None:
                    continue
                d = _xy(Mc, crec["points"][cp]) - _xy(to_px, att_point(rig, cslot, ca, world, other))
                width_px = width * math.sqrt(abs(float(np.linalg.det(L))))
            else:
                d = L @ np.array(u, dtype=float)
                width_px = width * float(np.linalg.norm(L @ np.array([-u[1], u[0]], dtype=float)))   # across the axis
            if np.linalg.norm(d) < 1e-9:
                continue
            d = d / np.linalg.norm(d)
            c = _xy(Mp, prec["points"][pp])
            off = float(np.linalg.norm(_xy(Mc, crec["points"][cp]) - c)) / max(1e-9, width_px / 2)
            rim = c                             # a parent trimmed under its child's cuff (rim_inset): its rim moved in
            inset = (prec.get("rim_inset") or {}).get(pp)
            if inset and u is not None:
                rim = _xy(to_px, att_point(rig, pslot, pa, world, (prec["points"][pp][0] + u[0] * inset,
                                                                  prec["points"][pp][1] + u[1] * inset)))
            R = max(2.0, width_px)
            y0, y1 = max(0, int(c[1] - R)), min(canvas.H, int(c[1] + R) + 2)
            x0, x1 = max(0, int(c[0] - R)), min(canvas.W, int(c[0] + R) + 2)
            spill = 0.0
            if y0 < y1 and x0 < x1:
                yy, xx = np.mgrid[y0:y1, x0:x1]
                disk = (xx - c[0]) ** 2 + (yy - c[1]) ** 2 <= R * R
                child = mask(cslot, ca)[y0:y1, x0:x1] & disk
                past = (xx - rim[0]) * d[0] + (yy - rim[1]) * d[1] > 0
                spill = float((child & past & ~mask(pslot, pa)[y0:y1, x0:x1]).sum() / max(1, child.sum()))
            key = f"{s['child']}/{s['parent']}"
            at = f"{anim or 'setup'}@{t:.2f}"
            w = worst.setdefault(key, {"spill": 0.0, "spill_at": at, "off": 0.0, "off_at": at})
            if spill > w["spill"]:
                w["spill"], w["spill_at"] = round(spill, 3), at
            if off > w["off"]:
                w["off"], w["off_at"] = round(off, 2), at
    ok = all(w["spill"] <= SOCKET_SPILL and w["off"] <= 1.0 for w in worst.values())
    return {"pass": ok, "sockets": worst}


def check_landmarks(rig: Rig, resolved: dict) -> dict:
    """In the setup pose each placed joint's bone origin lies on its master point: within LANDMARK_DRIFT x body height,
    plus that joint's push-in (a hip pushed into its socket sits that much off the master's hip on purpose).
    Returns {"pass", "landmarks": {joint: drift_units}, "failed": {joint: tolerance_units}}."""
    world, _ = rig.pose(None, 0.0)
    mp, push = resolved.get("master_points_units", {}), resolved.get("push_in", {})
    base = LANDMARK_DRIFT * resolved.get("body_height_units", rig.data["skeleton"]["height"])
    drift, failed = {}, {}
    for joint, bone in resolved.get("point_bones", {}).items():
        if joint not in mp or bone not in world:
            continue
        d = math.hypot(world[bone][4] - mp[joint][0], world[bone][5] - mp[joint][1])
        tol = base + push.get(joint, 0.0)
        drift[joint] = round(d, 2)
        if d > tol:
            failed[joint] = round(tol, 2)
    return {"pass": not failed, "landmarks": drift, "failed": failed}


def check_layer_order(rig: Rig, resolved: dict, anims: list | None = None, fps: int = 30) -> dict:
    """Each hand on its side of its forearm's (or sleeve mesh's) slot as master.layers.hand says (resolved
    "layer_order": {slot, over, relation above | below}), in the setup pose and every frame of every animation
    (drawOrder keys included). Returns {"pass", "wrong": {"slot/over": {"frames", "first"}}}."""
    pairs = [x for x in resolved.get("layer_order", []) if x["slot"] in rig.skin and x["over"] in rig.skin]
    wrong = {}
    for anim in [None] + [a for a in (anims if anims is not None else list(rig.data["animations"]))
                          if a in rig.data["animations"]]:
        n = 1 if anim is None else int(round(max(rig.duration(anim), 1 / fps) * fps)) + 1
        for i in range(n):
            t = i / fps
            o = rig.draw_order(anim, t)
            for x in pairs:
                above = o.index(x["slot"]) > o.index(x["over"])
                if above != (x["relation"] == "above"):
                    w = wrong.setdefault(f"{x['slot']}/{x['over']}", {"frames": 0, "first": f"{anim or 'setup'}@{t:.2f}"})
                    w["frames"] += 1
    return {"pass": not wrong, "wrong": wrong}


def annotation_checks(rig: Rig, canvas: Canvas, anims: list, fps: int = 30) -> dict:
    """thumbs, sockets, landmarks and layer_order, when the rig has an annotations.resolved.json next to it; else {}."""
    path = rig.path.parent / "annotations.resolved.json"
    if not path.exists():
        return {}
    resolved = json.loads(path.read_text(encoding="utf-8"))
    return {"thumbs": check_thumbs(rig, resolved, anims), "sockets": check_sockets(rig, canvas, resolved, anims, fps),
            "landmarks": check_landmarks(rig, resolved), "layer_order": check_layer_order(rig, resolved, anims, fps)}


def check_setup(rig: Rig, canvas: Canvas, master: Path, outdir: Path) -> dict:
    frame, *_ = render(rig, canvas, None, 0, bg=(0, 0, 0, 0))
    a = np.asarray(frame)[..., 3] > 127
    ys, xs = np.nonzero(a)
    m = np.asarray(Image.open(master).convert("RGB"), dtype=np.float32) / 255
    border = np.concatenate([m[0], m[-1], m[:, 0], m[:, -1]])
    fg = np.linalg.norm(m - np.median(border, 0), axis=2) > 0.06
    report = rig.path.parent / "report.json"
    frame_ = json.loads(report.read_text(encoding="utf-8")).get("master_frame") if report.exists() else None
    mm = np.zeros_like(a)
    if frame_ and frame_["width"] == m.shape[1]:          # exact: master px -> skeleton units -> canvas px
        k = frame_["units_per_px"]
        x0, y0 = canvas.point(-frame_["mid_x"] * k, frame_["ground_y"] * k)
        im = Image.fromarray(fg).resize((max(1, round(m.shape[1] * k * canvas.S)), max(1, round(m.shape[0] * k * canvas.S))), Image.NEAREST)
        t_ = np.asarray(im)
        X0, Y0 = int(round(x0)), int(round(y0))
        xs_, ys_ = slice(max(0, X0), min(canvas.W, X0 + t_.shape[1])), slice(max(0, Y0), min(canvas.H, Y0 + t_.shape[0]))
        mm[ys_, xs_] = t_[ys_.start - Y0: ys_.stop - Y0, xs_.start - X0: xs_.stop - X0]
    else:                                                 # no frame recorded: fit the bounding boxes
        my, mx = np.nonzero(fg)
        crop = Image.fromarray(fg[my.min():my.max() + 1, mx.min():mx.max() + 1])
        target = crop.resize((xs.max() - xs.min() + 1, ys.max() - ys.min() + 1))
        mm[ys.min():ys.max() + 1, xs.min():xs.max() + 1] = np.asarray(target) > 0
    iou = float((a & mm).sum() / max(1, (a | mm).sum()))
    over = Image.new("RGB", (canvas.W, canvas.H), (255, 255, 255))
    ov = np.asarray(over).copy()
    ov[mm & ~a] = (255, 0, 0)    # master only: missing in the rig
    ov[a & ~mm] = (0, 120, 255)  # rig only: sticks out
    ov[a & mm] = (200, 200, 200)
    Image.fromarray(ov).save(outdir / "setup_vs_master.png")
    return {"pass": iou >= SETUP_IOU, "silhouette_iou": round(iou, 3)}


def check_contract(path: Path) -> dict:
    """Does a master image meet spine_rig's input contract? Measured, not eyeballed."""
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255
    H, W = rgb.shape[:2]
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, 0)
    dist = np.linalg.norm(rgb - bg, axis=2)
    fg = dist > 0.06
    ys, xs = np.nonzero(fg)
    top, bottom, left, right = ys.min(), ys.max(), xs.min(), xs.max()
    h = bottom - top
    res = {}
    # flat background: the border is one colour
    res["flat_background"] = bool(np.linalg.norm(border - bg, axis=1).mean() < 0.02)
    # cast shadow: a band of slightly-darker-than-background pixels right under the feet
    # (a) faint: slightly-darker-than-background pixels right under the feet
    band = dist[max(0, bottom - int(0.03 * h)): min(H, bottom + int(0.06 * h)), left:right + 1]
    faint = ((band > 0.02) & (band <= 0.06)).mean()
    res["no_faint_shadow"] = bool(faint < 0.08)
    # centred: silhouette centre of mass near the bounding-box centre
    uy = ys < top + 0.55 * h
    res["centred"] = bool(abs(np.median(xs[uy]) - (left + right) / 2) < 0.12 * (right - left))
    # leg gap: the tallest background run up from the ground, on columns near the body's centre line.
    # The centre line comes from the head and torso (top 55%) so a tail can't drag it sideways.
    upper = ys < top + 0.55 * h
    cx = int(round(np.median(xs[upper])))
    half_w = right - left
    best_run = 0
    for c in range(max(0, cx - int(0.12 * half_w)), min(W, cx + int(0.12 * half_w) + 1)):
        col = fg[top:bottom + 1, c]
        run = 0
        for v in col[::-1]:
            if v:
                break
            run += 1
        if run < h * 0.98:          # ignore columns that miss the body entirely
            best_run = max(best_run, run)
    run = best_run
    res["leg_gap_pct_of_height"] = round(100 * run / h, 1)
    res["leg_gap"] = bool(run / h >= 0.12)
    # arm gaps: rows in the arm band where, going outwards from the body, foreground-background-foreground occurs
    gaps = {"picture_left": 0, "picture_right": 0}
    rows = range(top + int(0.35 * h), top + int(0.65 * h))
    for y in rows:
        for side, xr in (("picture_left", range(cx, left - 1, -1)), ("picture_right", range(cx, right + 1))):
            seq = fg[y, list(xr)]
            change = np.flatnonzero(np.diff(seq.astype(int)) != 0)
            if len(change) >= 2:          # body ends, gap, arm starts
                gaps[side] += 1
    n = max(1, len(rows))
    res["arm_gap_rows_pct"] = {k: round(100 * v / n) for k, v in gaps.items()}
    res["arm_gaps"] = bool(min(gaps.values()) / n >= 0.15)   # calibrated: rejected moose 4-8%, rigged moose 20-31%
    # keyable: the pipeline keys the figure as > 0.06 from the border colour (rig_match.master_mask, the setup IoU).
    # Pale fur or a white muzzle near the background's grey drops out as holes inside the silhouette (the arm gaps
    # above even passed because the paws read as background). Holes = inside the closed, filled key but not keyed,
    # and not flat background (an arm loop enclosing real background is fine)
    holes = key_holes(fg, dist)
    res["key_holes_pct_of_silhouette"] = round(100 * holes, 2)
    res["keyable"] = bool(holes < KEY_HOLES)
    passed = all(v for k, v in res.items() if isinstance(v, bool))
    return {"pass": passed, **res,
            "manual": "not measured, check by eye: colour contrast at shoulder/wrist/ankle; a solid ground shadow under the feet"}


def _box_count(m: np.ndarray, r: int) -> np.ndarray:
    """Number of True pixels in the (2r+1)^2 box around each pixel (zero padding)."""
    P = np.pad(m.astype(np.int32), r)
    c = np.zeros((P.shape[0] + 1, P.shape[1] + 1), np.int32)
    c[1:, 1:] = P.cumsum(0).cumsum(1)
    k = 2 * r + 1
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def fill_holes(m: np.ndarray) -> np.ndarray:
    """The mask with every region not connected to the image border filled (flood fill via PIL)."""
    from PIL import ImageDraw as _D
    im = Image.fromarray(np.pad(m, 1).astype(np.uint8) * 255).copy()   # writable (fromarray shares a read-only buffer)
    _D.floodfill(im, (0, 0), 128)
    return np.asarray(im)[1:-1, 1:-1] != 128


def key_holes(fg: np.ndarray, dist: np.ndarray) -> float:
    """Share of the silhouette (the key closed by KEY_CLOSE, holes filled) that the key misses although it is not
    the flat background (dist > KEY_BG_NOISE): figure that would key out as background."""
    r = max(2, round(KEY_CLOSE * fg.shape[0]))
    closed = _box_count(_box_count(fg, r) > 0, r) == (2 * r + 1) ** 2
    filled = fill_holes(closed | fg)
    return float((filled & ~fg & (dist > KEY_BG_NOISE)).sum() / max(1, filled.sum()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("skeleton", type=Path, nargs="?")
    ap.add_argument("--contract", type=Path, nargs="*", help="only check master image(s) against the rig input contract")
    ap.add_argument("--master", type=Path)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--anims", nargs="*")
    a = ap.parse_args()
    if a.contract:
        results = {str(p_): check_contract(p_) for p_ in a.contract}
        for k, v in results.items():
            print(f"{'PASS' if v['pass'] else 'FAIL'}  {Path(k).name}  {json.dumps({kk: vv for kk, vv in v.items() if kk not in ('pass', 'manual')})}")
        return 0 if all(v["pass"] for v in results.values()) else 1
    rig = Rig(a.skeleton)
    canvas = Canvas(rig, CHECK_H)
    outdir = a.skeleton.parent / "qa"
    outdir.mkdir(exist_ok=True)
    report = {"structure": check_structure(rig, canvas)}
    if a.master:
        report["setup"] = check_setup(rig, canvas, a.master, outdir)
    anims = a.anims or list(rig.data["animations"])
    report["seams"] = check_seams(rig, canvas, [(None, 0.0)] + [(n, rig.duration(n) / 2) for n in anims])
    report.update(annotation_checks(rig, canvas, anims, a.fps))      # thumbs, sockets, landmarks (annotated rigs only)
    for anim in anims:
        report[anim] = check_anim(rig, canvas, anim, a.fps, outdir)
    (outdir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for k, v in report.items():
        details = {kk: vv for kk, vv in v.items() if kk != "pass" and vv}
        print(f"{'PASS' if v['pass'] else 'FAIL'}  {k:10s} {json.dumps(details)[:300]}")
    return 0 if all(v["pass"] for v in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
