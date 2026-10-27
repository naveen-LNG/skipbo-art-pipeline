#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""rig_place.py - place the rest parts on the master from confirmed annotations (spine_rig.py --annotations).

Instead of guessing where each painted part sits by colour, the annotated joints are lined up:
  - two-point parts (torso, hips, upper arm, forearm, leg) put their proximal joint on the master's and turn so
    their distal joint lies along the master's; width keeps the sheet's scale, length stretches by up to +-15%;
  - a child's end is pushed into its parent's opening by a third of the opening's depth and narrowed to the
    opening's width by up to 15% (leg into the boot and the hips); a hand's wrist is pushed into the forearm's
    wrist the same way (not narrowed). The upper arm hangs from the MASTER's shoulder, neither pushed in nor
    narrowed to an opening (only to its forearm, below); a torso shoulder point (optional) only cross-checks the torso ("shoulder_mismatch" beyond
    SHOULDER_DISAGREE). A master shoulder outside the placed torso (annotated on the shoulder's outline, as on the
    moose) moves only the bone's origin - the art stays on the master's shoulder - to the nearest pixel of the
    torso/upper-arm overlap (eroded 2 px), so the joint lies on both parts: a "shoulder_outside_torso" doubt
    {"part", "moved_px"}, with info[upperarm]["push"]["shoulder"] = the distance moved (landmark tolerance);
  - the hips bone runs from the top of the hips through the waist toward the leg openings;
  - feet stand their ankle opening on the master's ankle, scaled so their ankle-to-ground height matches the
    master's (within 0.85-1.15 x the sheet's scale; hitting that limit is a "ground_miss" doubt carrying the raw
    ratio; leg-less with feet over_hips, moved across under the placed hips' leg opening on its side,
    info[foot]["ankle_shift"] = {"dx"}, the ankle's push; leg-less with feet under the hips, a hidden shaft rising
    under the cuff, rig_shaft, info[foot]["shaft"] = {"rows", "master_px", "width_px", "kept_px"}), neckwear its
    neck on the master's neck (then snapped by colour within NECKWEAR_SNAP), hands turned along the master's wrist-to-fingertip (the hand bone runs along the rest hand image's own image-down, so
    a variant turned that way continues the forearm at the holds);
  - width fits (annotations only, at most WIDTH_FIT_MAX, a doubt beyond, info[part]["width_fit"] = {factor, raw}):
    leg-less hips with feet over_hips are narrowed across until each leg opening is <= HIPS_FOOT_FIT x its boot's
    ankle opening ("hips_too_wide"); the rest upper arm (not its variants) is narrowed until its elbow round end
    is no wider than its forearm's ("upperarm_too_wide"; never widened);
  - the forearm loses its hand-coloured pixels past its wrist rim, whatever the hand's layer (wrist_trim;
    info[forearm]["wrist_trim"]);
  - a side with a whole sleeve (role arm) places it instead of its upper arm and forearm (sleeve_mesh): one drawing
    over both bones, at its own scale, narrowed across each half's axis to the master's sleeve (never widened; a
    "sleeve_too_wide" doubt past 35%), which spine_rig writes as a weighted mesh (rig_mesh); it is wrist-trimmed like
    a forearm (info[forearm]["wrist_trim"]), the hand goes into the sleeve's wrist opening, and its socket in
    resolved() is the sleeve's;
  - heads, hats, tails and props are still placed by the colour matcher; ears, antlers and horns too, but held to
    their annotated side and root (match_headgear). Their annotated root/neck point only sets the pivot, and a
    pivot off its own part moves onto the part's nearest opaque pixel.
Positions are full-resolution master pixels; `unit` is Spine units per image pixel, as in spine_rig.main.

place_from_annotations also returns `info`, per placed part:
  {"method": "two_point" | "matcher" | "socket" | "hand",
   "stretch": raw length ratio |PD| / (g |JpJd|) (two-point parts, else None),
   "narrow":  raw width ratio opening / child end, the smallest over its openings (fitted parts, else None),
   "push":    {joint name: push-in distance applied, master px}, e.g. leg {"hip": 7.0, "hem": 6.5}}
The applied stretch and narrowing are these ratios clipped to STRETCH_MAX / NARROW_MAX (narrowing never widens).

Also used by spine_rig.py in annotation mode:
  - check_required: a clean SystemExit naming the master/piece that lacks a required point (--allow-proposed drafts);
  - scale_estimates / global_scale: the global scale from the torso's neck-to-waist, cross-checked against the torso's
    and the head's widths (a "scale_disagree" doubt; outvoted only when both others agree against it);
  - cross_check: the colour matcher's second opinion; > MATCHER_DISAGREE x body height away is a doubt;
  - variant_fit: pose variants (hand gestures, raised sleeve, tiptoe foot, tail up) placed by their annotated joint;
  - resolved: the content of rig/annotations.resolved.json (annotated points per attachment, sockets, gesture
    holds, thumb targets, master points and push-in distances in Spine units) for spine_qa.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

import rig_annotations as ra
import rig_hands
import rig_image
import rig_match
import rig_mesh
import rig_roles
import rig_shaft

STRETCH_MAX = 0.15        # a two-point part may stretch its length by this much to hit both joints
NARROW_MAX = 0.15         # a child's end may be narrowed by this much to fit its parent's opening
MATCHER_DISAGREE = 0.04   # of body height: the matcher's placement this far from the annotation's is a doubt
SHOULDER_DISAGREE = 0.04  # of body height: a torso's placed shoulder point this far from the master's is a doubt
FOOT_SCALE = (0.85, 1.15)  # a foot's scale against the sheet's, to match the master's ankle-to-ground height; hitting it is a doubt
HAND_SCALE = (0.8, 1.6)   # a hand's scale against the sheet's, to match the master's wrist-to-fingertip
MATCHED_ROLES = ("head", "hat", "tail", "ear", "antler", "horn", "prop")
# Tails, ears, antlers and horns come out of normalise joint end up, whatever angle the master holds them at:
# search all the way round to the side, then refine around the best.
BACK_ANGLES = list(range(-90, 91, 10))
REFINE_ANGLES = range(-5, 6, 1)
REFINE_SCALES = (0.97, 1.0, 1.03)
PIVOTS = ("root", "neck")
HEADGEAR_ROLES = ("ear", "antler", "horn")   # hung from the head: matched by match_headgear
MATCH_SCALES = (0.9, 0.95, 1.0, 1.05, 1.1)   # around the annotated scale, as match_parts searches
RESIDUAL_WEIGHT = 0.1     # match_headgear's reward per unit fraction of a piece over master foreground nothing explains
NECKWEAR_SNAP = 0.04      # of body height: how far the colour matcher may move neckwear from its annotated place
NECKWEAR_SCALES = (0.95, 1.0, 1.05)
NECKWEAR_ANGLES = (-6, -3, 0, 3, 6)
WIDTH_FIT_MAX = 0.35      # the hips (to the boots) and an upper arm (to its forearm) may be narrowed this much
HIPS_FOOT_FIT = 0.8       # leg-less, feet over the hips: each hips leg opening at most this x its boot's ankle opening
WRIST_TRIM_INSET = 0.15   # hand over_forearm: the forearm is trimmed this x the wrist's depth inside its wrist rim
TRIM_FEATHER = 2.0        # px over which the trimmed edge fades


# ------------------------------------------------------------------ geometry

def _vis(v) -> float:
    """World angle (degrees, y up) of an image-space vector (y down)."""
    return math.degrees(math.atan2(-v[1], v[0]))


def _rot(v, ang: float) -> np.ndarray:
    """Rotate an image-space vector counterclockwise on screen by ang degrees (PIL's and Spine's sense)."""
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return np.array([c * v[0] + s * v[1], -s * v[0] + c * v[1]])


def _unitv(v) -> np.ndarray:
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else np.zeros(2)


@dataclass
class Placement:
    """An image drawn at (cx, cy) in master px, scaled fx across and fy along its own axes, then turned by angle."""
    size: tuple
    cx: float
    cy: float
    fx: float
    fy: float
    angle: float

    def world(self, p) -> np.ndarray:
        w, h = self.size
        return np.array([self.cx, self.cy]) + _rot(((p[0] - w / 2) * self.fx, (p[1] - h / 2) * self.fy), self.angle)


def _centre_for(size, J, P, fx: float, fy: float, ang: float) -> np.ndarray:
    """Image centre in master px that puts image point J on P."""
    w, h = size
    return np.asarray(P, float) - _rot(((J[0] - w / 2) * fx, (J[1] - h / 2) * fy), ang)


def two_point(img_size, Jp, Jd, P, D, g: float, narrow: float = 1.0) -> dict:
    """Place an image so its joint Jp lands on P and the direction Jp->Jd runs along P->D.
    Width keeps scale g (times `narrow`); the length stretches to put Jd on D, by at most +-STRETCH_MAX.
    Returns {"cx", "cy", "angle", "unit", "unit_y", "stretch"}: unit/unit_y are master px per image px across/along
    the image's axes, stretch the raw length ratio |PD| / (g |JpJd|)."""
    Jp, Jd, P, D = (np.asarray(x, float) for x in (Jp, Jd, P, D))
    v = Jd - Jp
    L, T = float(np.linalg.norm(v)), float(np.linalg.norm(D - P))
    raw = T / (g * L) if L > 1e-9 else 1.0
    s = float(np.clip(raw, 1 - STRETCH_MAX, 1 + STRETCH_MAX))
    fx = g * narrow
    target, ax = g * L * s, v[0] * fx
    if abs(v[1]) > 0.2 * L and target > abs(ax):      # solve the length along a slanted axis exactly
        fy = math.sqrt(target * target - ax * ax) / abs(v[1])
    else:
        fy = g * s
    ang = _vis(D - P) - _vis((v[0] * fx, v[1] * fy))
    ang = (ang + 180.0) % 360.0 - 180.0
    C = _centre_for(img_size, Jp, P, fx, fy, ang)
    return {"cx": float(C[0]), "cy": float(C[1]), "angle": ang, "unit": fx, "unit_y": fy, "stretch": raw}


def push_in(C, axis, depth: float) -> tuple:
    """A child's end, pushed into its parent's opening at C along `axis` by a third of the opening's depth."""
    p = np.asarray(C, float) + _unitv(axis) * depth / 3
    return (float(p[0]), float(p[1]))


def narrow(width_child: float, width_opening: float) -> tuple:
    """(width factor, raw ratio): narrow a child's end to its parent's opening, by at most NARROW_MAX; never widen."""
    raw = width_opening / width_child
    return float(np.clip(raw, 1 - NARROW_MAX, 1.0)), float(raw)


def apply_layers(layers: dict, base: list, has_legs: bool = True, has_neckwear: bool = False) -> list:
    """Draw order with master.layers applied. upperarm: under_torso puts the upper arm ("arm") just below the torso,
    so a vest or strap covers the sleeve top; forearm and hand stay in front of the torso (a forearm crossing the
    belly must not vanish behind the vest), which also draws the forearm over the upper arm at the elbow. foot: over_hips draws the feet in front of the hips (default
    under_hips) - only for a character without leg pieces, whose legs are part of the hips; with legs the feet
    stay over the legs and under the hips. hand: over_forearm draws the hand just above the forearm (a glove's fur cuff
    over the sleeve's end; default under_forearm, tucked under its cuff). has_neckwear (annotations, a character with
    neckwear): forearm and hand are drawn above the neckwear, still under the head; the upper arm stays under it."""
    out = list(base)
    if layers.get("foot") == "over_hips" and not has_legs and "hips" in out and "foot" in out:
        out.remove("foot")
        out.insert(out.index("hips") + 1, "foot")
    if layers.get("upperarm") == "under_torso" and "torso" in out and "arm" in out:
        out.remove("arm")
        out.insert(out.index("torso"), "arm")
    if layers.get("hand") == "over_forearm" and "hand" in out and "forearm" in out:
        out.remove("hand")
        out.insert(out.index("forearm") + 1, "hand")
    if has_neckwear and "neckwear" in out:
        # an arm crossing the chest (point, thumbs up across, hold_card) passes in front of a hanging scarf: forearm and
        # hand go just above the neckwear, in their order so far, still under the head; the upper arm stays under the
        # neckwear, which wraps over the shoulders
        fore = [x for x in out if x in ("forearm", "hand")]
        for x in fore:
            out.remove(x)
        at = out.index("neckwear") + 1
        out[at:at] = fore
    return out


def has_neckwear(ann) -> bool:
    """Whether the rest outputs include neckwear (a scarf, collar, ...)."""
    return any(p.role == "neckwear" for p, _ in _rest_outputs(ann).values())


AXIS_TOP_INSET = 0.05     # axis_top stops this fraction of the axis' length inside the part's edge


def axis_top(mask: np.ndarray, P, d) -> np.ndarray:
    """From P back along -d (image px) to the part's far edge, then AXIS_TOP_INSET x |d| back inside: where a bone
    that runs along d through the whole part starts. P itself when P is not on the part."""
    P, d = np.asarray(P, float), np.asarray(d, float)
    L = float(np.linalg.norm(d))
    if L < 1e-9:
        return P
    u = d / L
    inside = lambda q: 0 <= int(round(q[1])) < mask.shape[0] and 0 <= int(round(q[0])) < mask.shape[1] and \
        bool(mask[int(round(q[1])), int(round(q[0]))])
    if not inside(P):
        return P
    t = 0.0
    while inside(P - u * (t + 1)) and t < 4 * L:
        t += 1
    return P - u * max(0.0, t - AXIS_TOP_INSET * L)


def _on(mask: np.ndarray, P) -> bool:
    x, y = int(round(P[0])), int(round(P[1]))
    return 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and bool(mask[y, x])


def _erode(mask: np.ndarray, r: int) -> np.ndarray:
    """Binary erosion by r px (4-neighbour steps)."""
    out = mask.copy()
    for _ in range(r):
        out = out & np.roll(out, 1, 0) & np.roll(out, -1, 0) & np.roll(out, 1, 1) & np.roll(out, -1, 1)
    return out


def onto_part(mask: np.ndarray, P) -> tuple:
    """P, or the nearest opaque pixel of mask when P falls outside it (a pivot belongs on its own part).
    An empty mask leaves P as it is."""
    x, y = int(round(P[0])), int(round(P[1]))
    if 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y, x]:
        return (float(P[0]), float(P[1]))
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return (float(P[0]), float(P[1]))
    i = int(np.argmin((xs - P[0]) ** 2 + (ys - P[1]) ** 2))
    return (float(xs[i]), float(ys[i]))


def dominant_colours(rgb: np.ndarray, k: int) -> np.ndarray:
    """k dominant colours (k x 3 float) of an N x 3 pixel sample: a few k-means rounds seeded at luminance quantiles
    (deterministic). Fewer when the sample is small or empty."""
    rgb = np.asarray(rgb, np.float64).reshape(-1, 3)
    if not len(rgb):
        return np.zeros((0, 3))
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    order = np.argsort(lum)
    c = rgb[order[np.linspace(0, len(rgb) - 1, k + 2)[1:-1].round().astype(int)]]
    for _ in range(8):
        lab = np.argmin(((rgb[:, None, :] - c[None]) ** 2).sum(2), 1)
        c = np.array([rgb[lab == i].mean(0) if (lab == i).any() else c[i] for i in range(len(c))])
    return c


def _nearest(rgb: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Distance of each pixel (H x W x 3) to the nearest of cols (k x 3)."""
    return np.sqrt(((rgb[..., None, :] - cols[None, None]) ** 2).sum(-1)).min(-1)


def _box(m: np.ndarray, r: int, outside: bool = False) -> np.ndarray:
    """Square (2r+1) binary dilation; pixels beyond the edge count as `outside`."""
    h, w = m.shape
    p = np.pad(m, r, constant_values=outside)
    out = np.zeros_like(m)
    for dy in range(2 * r + 1):
        for dx in range(2 * r + 1):
            out |= p[dy: dy + h, dx: dx + w]
    return out


def _bleed(a: np.ndarray, known: np.ndarray, todo: np.ndarray) -> None:
    """In place: the `todo` pixels of a (RGBA uint8) take the mean colour of their known 4-neighbours, step by step
    outward from `known` until every reachable one is filled (solidify's bleed: straight-alpha bilinear sampling shows
    the RGB of faint and transparent pixels next to the part)."""
    rgb = a[..., :3].astype(np.float32)
    known, todo = known.copy(), todo & ~known
    while todo.any():
        acc, cnt = np.zeros_like(rgb), np.zeros(known.shape, np.float32)
        for ax, k in ((0, 1), (0, -1), (1, 1), (1, -1)):
            kn = np.roll(known, k, ax)
            acc += np.roll(rgb, k, ax) * kn[..., None]
            cnt += kn
        new = todo & (cnt > 0)
        if not new.any():
            break
        rgb[new] = acc[new] / cnt[new][:, None]
        known |= new
        todo &= ~new
    a[..., :3] = np.round(rgb).astype(np.uint8)


def trim_beyond(img: Image.Image, P, u, inset: float, feather: float = TRIM_FEATHER, hand_cols=None,
                sleeve_cols=None) -> tuple:
    """Make the pixels of img on the far side (along unit vector u, image px) of the line through P - u * inset,
    perpendicular to u, transparent; alpha fades over `feather` px centred on the line (pixel centres at i + 0.5).
    With hand_cols and sleeve_cols (k x 3 colours), only the far-side pixels whose colour is nearer the hand's than
    the sleeve's go: sleeve-coloured pixels past the line (a cuff's rounded bottom) stay, and the cut between the two
    is feathered over ~2 px too. The trimmed and faded pixels then take the colour of the kept ones (_bleed), so no
    fur colour is left in transparent pixels.
    Returns (image, {"trimmed_px": opaque pixels made fully transparent, "feathered_px": pixels only faded,
    "kept_px": far-side pixels kept as sleeve})."""
    a = np.asarray(img.convert("RGBA")).copy()
    h, w = a.shape[:2]
    u = _unitv(u)
    C = np.asarray(P, float) - u * inset
    yy, xx = np.mgrid[:h, :w].astype(np.float64) + 0.5
    s = (xx - C[0]) * u[0] + (yy - C[1]) * u[1]
    r = 1.0 - np.clip(0.5 - s / feather, 0.0, 1.0)          # removal: 0 before the line, 1 past it
    had = a[..., 3] > 0
    kept = np.zeros((h, w), bool)
    if hand_cols is not None and sleeve_cols is not None and len(hand_cols) and len(sleeve_cols):
        rgb = a[..., :3].astype(np.float64)
        handlike = _nearest(rgb, np.asarray(hand_cols, float)) < _nearest(rgb, np.asarray(sleeve_cols, float))
        body = had & (r <= 0)                               # the sleeve before the line
        cand = had & ~handlike & (r > 0)
        # Kept only where it joins the sleeve's body and is not a thin bit: a light highlight on a fur tuft is
        # sleeve-coloured too, but it would stay behind as a speck or a sliver (spine_qa's opening: 3 px).
        kept = cand & _box(body, 1)
        while True:
            grown = cand & _box(kept, 1) & ~kept
            if not grown.any():
                break
            kept |= grown
        core = _box(~_box(~(body | kept), 3, outside=True), 3)
        kept &= _box(core, 1)
        r = r * (had & ~kept)
        p = np.pad(r, 1, mode="edge")                       # feather the colour cut: grow the removal ~1 px, softly
        soft = sum(p[1 + dy: h + 1 + dy, 1 + dx: w + 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9
        r = np.maximum(r, np.where(s > -feather / 2, soft, 0.0))
    k = 1.0 - r
    new = np.round(a[..., 3] * k).astype(np.uint8)
    info = {"trimmed_px": int((had & (new == 0)).sum()), "feathered_px": int((had & (new > 0) & (k < 1)).sum()),
            "kept_px": int((kept & (new > 0)).sum())}
    a[..., 3] = new
    if (k < 1).any():
        _bleed(a, (new >= 250) & (k >= 1), k < 1)
    return Image.fromarray(a, "RGBA"), info


WRIST_SAMPLE = 0.6        # the hand's colours near its wrist: opaque pixels within this x its wrist width


def wrist_colours(ann, name: str, img: Image.Image, rim) -> tuple:
    """(hand colours, sleeve colours) for wrist_trim of forearm output `name`: the dominant colours (3) of the rest
    hand on its side, opaque pixels within WRIST_SAMPLE x its wrist width of its wrist (cuff, fur, glove), and of
    the forearm's opaque pixels before the rim line (2). (None, None) when there is no such hand."""
    m = re.match(r"[a-z]+_(l|r)(_|$)", name)            # forearm_l, forearm_l_<variant>
    side = m.group(1) if m else ""
    hand = next((o for p in ann.pieces.values() if p.role == "hand" and p.variant in (None, "rest")
                 for o in p.outputs if side and _side(o.name) == side), None)
    if hand is None or "wrist" not in hand.points:
        return None, None
    him = np.asarray(rig_image.solidify(Image.open(ann.path.parent / hand.file), rig_image.TRUST_ALPHA_ANNOTATED)).astype(np.float64)
    hy, hx = np.mgrid[:him.shape[0], :him.shape[1]] + 0.5
    R = WRIST_SAMPLE * float(hand.widths.get("wrist") or 0.5 * him.shape[1])
    near = (him[..., 3] >= 250) & ((hx - hand.points["wrist"][0]) ** 2 + (hy - hand.points["wrist"][1]) ** 2 <= R * R)
    P, inward, inset = rim
    fa = np.asarray(img.convert("RGBA")).astype(np.float64)
    fy, fx = np.mgrid[:fa.shape[0], :fa.shape[1]] + 0.5
    Cx, Cy = P[0] + inward[0] * inset, P[1] + inward[1] * inset
    before = (fa[..., 3] >= 250) & (((fx - Cx) * -inward[0] + (fy - Cy) * -inward[1]) < -TRIM_FEATHER)
    return dominant_colours(him[near][:, :3], 3), dominant_colours(fa[before][:, :3], 2)


def wrist_trim(ann, name: str, img: Image.Image) -> tuple:
    """The forearm output `name` (rest or variant) loses what lies past its wrist rim and is coloured like its hand
    (whatever master.layers says about the hand: a glove's fur cuff over the sleeve's end, or a sleeve cuff over the
    glove's fur band - either way the forearm's own fur tufts must go): trim_beyond at the wrist opening, across the
    forearm's axis (rig_annotations.opening_inward), WRIST_TRIM_INSET x the opening's depth toward the elbow.
    Colour-aware only (wrist_colours): past the line only pixels nearer the hand's colours than the sleeve's go, so a
    sleeve-coloured cuff stays whole (a no-op for the fox). Returns (image, info) or (img, None) when it doesn't
    apply (not a forearm, no annotated wrist). Skipped, the image unchanged, with info {"skipped": "no_rest_hand"}
    when there is no rest hand on its side to take the colours from, {"skipped": "ambiguous_colours"} when the hand
    shares the sleeve's colours (trim_wrist_colours; the caller raises a wrist_trim_ambiguous doubt)."""
    rim = wrist_rim(ann, name)
    if rim is None:
        return img, None
    P, inward, inset = rim
    hand_cols, sleeve_cols = wrist_colours(ann, name, img, rim)
    if hand_cols is None:
        return img, {"skipped": "no_rest_hand"}
    return trim_wrist_colours(img, P, (-inward[0], -inward[1]), inset, hand_cols, sleeve_cols)


WRIST_SHARED_RGB = 40     # a hand colour this close (RGB distance) to a sleeve colour can't tell glove from sleeve


def distinct_hand_colours(hand_cols, sleeve_cols) -> np.ndarray:
    """The hand colours further than WRIST_SHARED_RGB from every sleeve colour (k x 3)."""
    h = np.asarray(hand_cols, float).reshape(-1, 3)
    s = np.asarray(sleeve_cols, float).reshape(-1, 3)
    if not len(h) or not len(s):
        return h
    return h[np.sqrt(((h[:, None] - s[None]) ** 2).sum(-1)).min(1) > WRIST_SHARED_RGB]


def trim_wrist_colours(img: Image.Image, P, u, inset: float, hand_cols, sleeve_cols) -> tuple:
    """trim_beyond, colour-aware, with only the hand colours that differ from the sleeve's (distinct_hand_colours):
    a glove sharing the sleeve's colours would otherwise take the sleeve's own cuff with it. None left (or no sleeve
    colours): nothing can be told apart, the image is returned unchanged with {"skipped": "ambiguous_colours"}."""
    hand = distinct_hand_colours(hand_cols, sleeve_cols)
    if not len(hand) or not len(np.asarray(sleeve_cols).reshape(-1, 3)):
        return img, {"skipped": "ambiguous_colours"}
    return trim_beyond(img, P, u, inset, hand_cols=hand, sleeve_cols=sleeve_cols)


def trimmed(trim) -> bool:
    """Whether a wrist_trim info removed or faded anything (its rim then moved in: resolved's rim_inset)."""
    return bool(trim) and (trim.get("trimmed_px", 0) + trim.get("feathered_px", 0)) > 0


def wrist_rim(ann, name: str):
    """(wrist point, unit inward axis, inset) image px of forearm (or whole-sleeve arm) output `name` (wrist_trim's
    line), else None. Where the trim removed something, its wrist rim lies `inset` along the inward axis from the point."""
    rec = next(((p, o) for p in ann.pieces.values() for o in p.outputs if o.name == name), None)
    if rec is None or rec[0].role not in ("forearm", "arm") or "wrist" not in rec[1].points \
            or "elbow" not in rec[1].points:
        return None
    o = rec[1]
    inward = ra.opening_inward(rec[0].role, "wrist", tuple(o.points["wrist"]), {n: tuple(q) for n, q in o.points.items()})
    if inward is None:
        return None
    return tuple(o.points["wrist"]), inward, WRIST_TRIM_INSET * float(o.depths.get("wrist", 0.0))


# ------------------------------------------------------------------ headgear (ears, antlers, horns)

def _work_mask(m: dict, shape: tuple) -> np.ndarray:
    """A matcher placement's opaque area (its template alpha at x, y) as a work-px mask of `shape`."""
    out = np.zeros(shape, bool)
    a = m["tpl"][..., 3] > 0.5
    x0, y0 = int(m["x"]), int(m["y"])
    ys, xs = slice(max(0, y0), min(shape[0], y0 + a.shape[0])), slice(max(0, x0), min(shape[1], x0 + a.shape[1]))
    if ys.start < ys.stop and xs.start < xs.stop:
        out[ys, xs] = a[ys.start - y0: ys.stop - y0, xs.start - x0: xs.stop - x0]
    return out


def _allowed(tpl_shape, img_shape, box, root_off, anchor) -> np.ndarray:
    """Allowed top-left offsets of a template in rig_match.masked_ssd's valid map: its centre inside box (x0, x1, y0, y1)
    and, given root_off (root - centre, work px) and an anchor mask, its root on the anchor."""
    th, tw = tpl_shape
    H, W = img_shape
    cx, cy = np.arange(W - tw + 1) + tw / 2, np.arange(H - th + 1) + th / 2
    x0, x1, y0, y1 = box
    ok = ((cy >= y0) & (cy <= y1))[:, None] & ((cx >= x0) & (cx <= x1))[None, :]
    if anchor is not None and root_off is not None:
        rx, ry = np.round(cx + root_off[0]).astype(int), np.round(cy + root_off[1]).astype(int)
        inx, iny = (rx >= 0) & (rx < W), (ry >= 0) & (ry < H)
        on = np.zeros(ok.shape, bool)
        on[np.ix_(iny, inx)] = anchor[np.ix_(ry[iny], rx[inx])]
        ok &= on
    return ok


def _search(matcher, img: np.ndarray, root, scales, angles, box, anchor, pens) -> dict | None:
    """matcher.best with an allowed-offset mask (_allowed) and extra penalties; None when nothing is allowed."""
    h0, w0 = img.shape[:2]
    best = None
    for s in scales:
        for a in angles:
            tpl = rig_match.transform(img, s, a)
            th, tw = tpl.shape[:2]
            if th >= matcher.img.shape[0] or tw >= matcher.img.shape[1]:
                continue
            off = None if root is None else _rot(((root[0] - w0 / 2) * s, (root[1] - h0 / 2) * s), a)
            ok = _allowed((th, tw), matcher.img.shape[:2], box, off, anchor)
            if not ok.any():
                continue
            r = rig_match.masked_ssd(matcher.img, matcher.img_sq, tpl, ok, [(matcher.f_bg, rig_match.BG_WEIGHT)] + pens)
            if r and np.isfinite(r[0]) and (best is None or r[0] < best["err"]):
                best = {"err": r[0], "x": r[1], "y": r[2], "w": tw, "h": th, "scale": s, "angle": a,
                        "cx": r[1] + tw / 2, "cy": r[2] + th / 2, "tpl": tpl}
    return best


def match_headgear(frame, items: dict, g: float, anchor, claimed: np.ndarray) -> dict:
    """Ears, antlers and horns by the colour matcher, held to what the annotations say (work px throughout):
      - a sided piece stays on its annotated side: no left/right swap (the lighting painted on a mirrored ear is the
        other side's, and colour alone would swap the pair and turn each root outwards);
      - its annotated root lands on the anchor (the placed head and hat), so the pivot sits in its parent;
      - the piece is drawn behind the head, so colour alone would rather lay it over the head's fur: it is rewarded
        (RESIDUAL_WEIGHT per unit fraction of its area) for covering master foreground that no placed part (head,
        hat, torso, hips, earlier headgear: `claimed`) explains. Largest piece first; each claims its pixels.
    BACK_ANGLES x MATCH_SCALES, then REFINE_ANGLES x REFINE_SCALES around the best. A piece whose root can't land on
    the anchor anywhere is matched without that constraint.
    items: name -> (rgba float array, root (x, y) image px or None). Returns name -> match dict (as match_parts')."""
    matcher = rig_match.Matcher(frame.work, frame.fg)
    band = rig_match.make_band(frame)
    claimed = claimed.copy()
    out = {}
    for n in sorted(items, key=lambda n_: (-int((items[n_][0][..., 3] > 0.5).sum()), n_)):
        img, root = items[n]
        pens = [(np.fft.rfft2(((frame.fg > 0) & ~claimed).astype(np.float32)), -RESIDUAL_WEIGHT)]
        box = band("back", _side(n))
        scales = [g * s for s in MATCH_SCALES]
        best = None
        for anc in ((anchor, None) if anchor is not None and root is not None else (None,)):
            best = _search(matcher, img, root, scales, BACK_ANGLES, box, anc, pens)
            if best is not None:
                pad = 0.08 * frame.half_w
                fine_box = (max(box[0], best["cx"] - pad), min(box[1], best["cx"] + pad),
                            max(box[2], best["cy"] - pad), min(box[3], best["cy"] + pad))
                fine = _search(matcher, img, root, [best["scale"] * k for k in REFINE_SCALES],
                               [best["angle"] + a for a in REFINE_ANGLES], fine_box, anc, pens)
                if fine is not None and fine["err"] <= best["err"]:
                    best = fine
                break
        if best is None:
            continue
        out[n] = best
        claimed |= _work_mask(best, claimed.shape)
    return out


# ------------------------------------------------------------------ annotations

def _master_size(ann) -> tuple:
    with Image.open(ann.path.parent / ann.master.image) as im:
        return im.size


def _rest_outputs(ann) -> dict:
    """Rest outputs by name: name -> (piece, output). Whole legs (role legs) are placed by rig_variants.add_legs."""
    return {o.name: (p, o) for p in ann.pieces.values() if p.variant in (None, "rest") and p.role != "legs"
            for o in p.outputs}


def output_roles(ann) -> dict:
    """Annotated role by part name: every output name (hand_l, sneaker_r_tiptoe, head_base) and every piece name
    (sneaker, hand), for rig_roles.role. Names are one role each (rig_annotations validates it)."""
    roles = {}
    for p in ann.pieces.values():
        if p.status == "ignored" or p.role not in ra.ROLES:
            continue
        roles[p.name] = p.role
        for o in p.outputs:
            roles[o.name] = p.role
    return roles


def named(outs: dict, role: str, side: str = "") -> str:
    """The output in `outs` (name -> (piece, output)) of annotated `role` on `side`, looked up by role, not by name;
    "<role>[_<side>]" when there is none (so `in outs` is False). The structural roles' names are their role
    (rig_annotations.STRUCTURAL_ROLES), so this is also the part's bone name."""
    return next((n for n, (p, _) in outs.items() if p.role == role and _side(n) == side),
                f"{role}_{side}" if side else role)


def has_legs(ann) -> bool:
    """Whether the rest outputs include leg pieces."""
    return any(p.role == "leg" for p, _ in _rest_outputs(ann).values())


def _side(name: str) -> str:
    m = re.search(r"_(l|r)$", name)
    return m.group(1) if m else ""


def check_required(ann) -> None:
    """SystemExit naming the master or the piece (and its output) that lacks a required point. Confirmed annotations
    always pass (validation demands the points); this catches drafts built with --allow-proposed."""
    miss = [n for n in ra.MASTER_POINTS if n not in ann.master.points]
    if miss:
        raise SystemExit(f"annotations: the master ({ann.master.status}) is missing required point(s) "
                         f"{', '.join(miss)}; annotate them before building")
    for key, p in ann.pieces.items():
        if p.role not in ra.ROLES:
            continue
        need = ra._required_points(p)
        for o in p.outputs:
            miss = [n for n in need if n not in o.points]
            if miss:
                raise SystemExit(f"annotations: piece {key} ({p.role}, {p.status}) output {o.name} is missing required "
                                 f"point(s) {', '.join(miss)}; annotate them before building")


SCALE_DOUBT = 0.15        # a scale estimate this far off the scale used is a "scale_disagree" doubt
SCALE_AGREE = 0.12        # two other estimates this close to each other, and both over SCALE_DOUBT off the torso's
                          # neck-to-waist, replace it (their median): the torso's points are the odd one out
TORSO_WIDTH_AT = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)   # the torso's width is compared at these fractions of neck -> waist
HEAD_WIDTH_AT = (0.3, 0.4)  # ... the head's (cheeks, below ears and antlers) this far up from the neck, as a fraction
                            # of the head piece's neck-to-top height
RUN_GAP = 2.0             # px: a run across a part bridges transparent gaps up to this wide (antialiasing, a seam)


def global_scale(ann, frame, size=None) -> float:
    """g in work px per part px (scale_estimates' choice)."""
    return scale_estimates(ann, frame, size)["g"]


def scale_estimates(ann, frame, size=None) -> dict:
    """The global scale g (work px per part px) from three estimates, each master px per part px:
      torso_length  the master's neck-to-waist against the rest torso's (the annotated points);
      torso_width   the master's width across the torso against the piece's, at TORSO_WIDTH_AT of neck -> waist
                    (median of the ratios; the run across through the axis point, so a hanging arm that doesn't
                    touch the body is not counted);
      head_width    the master's width across the head against the head_base piece's, HEAD_WIDTH_AT of the
                    piece's neck-to-top above the neck (measured at the scale found so far, then once more).
    torso_length is used (as before) unless the two others agree with each other within SCALE_AGREE and both lie
    over SCALE_DOUBT from it: then their median ("used": "others"). Any estimate over SCALE_DOUBT off the scale used
    gives "doubt" {"part": "global_scale", "reason": "scale_disagree", "used", "estimates", "off_by" (estimate / g)}.
    A torso painted wider for its height than the master (the bear) or a torso waist point below the master's waist
    (the rabbit, silently at IoU 0.64) shows up here. torso_width is often missing: most masters' arms touch the body
    at those rows (a run across the torso that crosses an annotated shoulder-elbow-wrist line is dropped).
    Returns {"g", "estimates" (master px per part px), "used": "torso_length" | "others", "doubt": dict | None}."""
    check_required(ann)
    W, H = size or _master_size(ann)
    outs = _rest_outputs(ann)
    T = named(outs, "torso")
    if T not in outs:
        raise SystemExit("annotations: no rest torso output; it sets the global scale")
    t = outs[T][1].points
    mp = ann.master.points
    nm, wm = np.array([mp["neck"][0] * W, mp["neck"][1] * H]), np.array([mp["waist"][0] * W, mp["waist"][1] * H])
    nt, wt = np.asarray(t["neck"], float), np.asarray(t["waist"], float)
    g_len = float(np.linalg.norm(nm - wm)) / max(1e-9, float(np.linalg.norm(nt - wt)))
    est = {"torso_length": g_len}
    with Image.open(ann.path.parent / ann.master.image) as im:   # the figure as the pipeline keys it
        master_fg = rig_match.master_mask(np.asarray(im.convert("RGB"), np.float32) / 255) > 0.5
    root = ann.path.parent
    timg = _alpha_of(root / outs[T][1].file)
    if timg is not None:
        um, ut = _unitv(wm - nm), _unitv(wt - nt)
        arms = [[np.array([mp[f"{j}_{s_}"][0] * W, mp[f"{j}_{s_}"][1] * H]) for j in ("shoulder", "elbow", "wrist")]
                for s_ in "lr"]
        r = [_ratio(_run_width(master_fg, nm + f * (wm - nm), um, arms), _run_width(timg, nt + f * (wt - nt), ut))
             for f in TORSO_WIDTH_AT]
        r = [x for x in r if x]
        if r:
            est["torso_width"] = float(np.median(r))
    Hd = named(outs, "head")
    himg = _alpha_of(root / outs[Hd][1].file) if Hd in outs and "neck" in outs[Hd][1].points else None
    if himg is not None:
        nh = np.asarray(outs[Hd][1].points["neck"], float)
        hh = nh[1] - float(np.nonzero(himg.any(1))[0].min())
        g_ = float(np.median(list(est.values())))
        for _ in range(2):                                  # the master's cheek row depends on the scale
            r = [_ratio(_run_width(master_fg, nm - np.array([0.0, f * hh * g_]), np.array([0.0, 1.0])),
                        _run_width(himg, nh - np.array([0.0, f * hh]), np.array([0.0, 1.0]))) for f in HEAD_WIDTH_AT]
            r = [x for x in r if x]
            if not r or hh < 4:
                break
            est["head_width"] = float(np.median(r))
            g_ = float(np.median(list(est.values())))
    others = [v for k, v in est.items() if k != "torso_length"]
    g, used = g_len, "torso_length"
    if len(others) >= 2 and max(others) / min(others) - 1 <= SCALE_AGREE:
        alt = float(np.median(others))
        if abs(g_len / alt - 1) > SCALE_DOUBT:            # the torso's points are the odd one out
            g, used = alt, "others"
    off = {k: round(v / g, 3) for k, v in est.items() if abs(v / g - 1) > SCALE_DOUBT}
    rounded = {k: round(v, 4) for k, v in est.items()}
    doubt = {"part": "global_scale", "reason": "scale_disagree", "used": used, "estimates": rounded,
             "off_by": off} if off else None
    return {"g": g * frame.k, "estimates": rounded, "used": used, "doubt": doubt}


def _alpha_of(path) -> np.ndarray | None:
    try:
        with Image.open(path) as im:
            return np.asarray(im.convert("RGBA"))[..., 3] > 127
    except FileNotFoundError:
        return None


def _ratio(a, b):
    return a / b if a and b else None


def _run_width(mask: np.ndarray, P, along, arms=None) -> float | None:
    """Width (px) of the opaque run through P across `along` (unit), bridging gaps up to RUN_GAP; None when P is not
    on the mask. arms: polylines (shoulder, elbow, wrist) either side; a run reaching past one of them runs into an
    arm touching the body and is not the body's width (None)."""
    H, W = mask.shape
    across = np.array([-along[1], along[0]], float)

    def on(q) -> bool:
        x, y = int(round(q[0])), int(round(q[1]))
        return 0 <= x < W and 0 <= y < H and bool(mask[y, x])
    P = np.asarray(P, float)
    if not on(P):
        return None
    ends = []
    for sgn in (1.0, -1.0):
        d, last = 0.0, 0.0
        while d - last <= RUN_GAP and d < W + H:
            d += 0.5
            if on(P + sgn * d * across):
                last = d
        ends.append(last)
    for arm in arms or ():
        for E in (P + ends[0] * across, P - ends[1] * across):
            if _beyond(arm, P, E):
                return None
    return ends[0] + ends[1] + 1.0


def _beyond(line, P, E) -> bool:
    """Does the segment P -> E cross the polyline `line`?"""
    def cross(a, b, c, d) -> bool:
        def o(p, q, r):
            return np.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]))
        return o(a, b, c) != o(a, b, d) and o(c, d, a) != o(c, d, b)
    return any(cross(P, E, line[i], line[i + 1]) for i in range(len(line) - 1))


def default_dirs(ann) -> tuple:
    """(expression heads folder or None, variant folders) from the outputs of the variant pieces."""
    root = ann.path.parent
    heads, variants = set(), set()
    for p in ann.pieces.values():
        if p.variant in (None, "rest"):
            continue
        for o in p.outputs:
            (heads if p.role == "head" else variants).add((root / o.file).parent)
    return (sorted(heads)[0] if heads else None), sorted(variants)


def _mask(img: Image.Image, x: Placement, W: int, H: int) -> np.ndarray:
    im = img.resize((max(1, round(img.width * x.fx)), max(1, round(img.height * x.fy))), Image.LANCZOS)
    im = im.rotate(x.angle, Image.BICUBIC, expand=True)
    a = np.asarray(im)[..., 3] > 127
    mm = np.zeros((H, W), bool)
    x0, y0 = int(round(x.cx - im.width / 2)), int(round(x.cy - im.height / 2))
    xs, ys = slice(max(0, x0), min(W, x0 + im.width)), slice(max(0, y0), min(H, y0 + im.height))
    if xs.start < xs.stop and ys.start < ys.stop:
        mm[ys, xs] = a[ys.start - y0: ys.stop - y0, xs.start - x0: xs.stop - x0]
    return mm


def _pull_back(mask: np.ndarray, x: Placement) -> np.ndarray:
    """A master-px mask sampled at the centres of an image's pixels as Placement x draws it: (h, w) bool."""
    w, h = x.size
    yy, xx = np.mgrid[:h, :w].astype(np.float64) + 0.5
    c, s = math.cos(math.radians(x.angle)), math.sin(math.radians(x.angle))
    u, v = (xx - w / 2) * x.fx, (yy - h / 2) * x.fy
    X, Y = np.floor(x.cx + c * u + s * v).astype(int), np.floor(x.cy - s * u + c * v).astype(int)
    ok = (X >= 0) & (X < mask.shape[1]) & (Y >= 0) & (Y < mask.shape[0])
    out = np.zeros((h, w), bool)
    out[ok] = mask[Y[ok], X[ok]]
    return out


def _far_point(mask: np.ndarray, P) -> np.ndarray:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return np.asarray(P, float) + np.array([0.0, -1.0])
    i = np.argmax((xs - P[0]) ** 2 + (ys - P[1]) ** 2)
    return np.array([xs[i], ys[i]], float)


def place_from_annotations(ann, frame, g: float, size=None):
    """Place every rest part from the annotations. g: work px per part px (global_scale).
    Returns (pieces, joints, bone_dir, doubts, info): pieces as in spine_rig.main plus "unit_y"; joints (the proximal
    point) and bone_dir (distal - proximal) in full-resolution master px; doubts [{"part", "reason", ...}];
    info per part as in the module doc (method, stretch, narrow, push). A rest output nothing places (e.g. a limb
    output without a side) is a doubt {"part", "reason": "not_placed"}."""
    check_required(ann)
    W, H = size or _master_size(ann)
    G = g / frame.k                                    # master px per part px
    root = ann.path.parent
    M = {n: np.array([x * W, y * H]) for n, (x, y) in ann.master.points.items()}
    body_h = (frame.ground_y - frame.top) / frame.k
    outs = _rest_outputs(ann)
    roles = output_roles(ann)                          # rig_roles.role: layers and parents by annotated role
    pieces, joints, bone_dir, doubts, xf, info = {}, {}, {}, [], {}, {}

    def record(n, method, stretch=None, narrow_raw=None, push=None):
        info[n] = {"method": method, "stretch": None if stretch is None else float(stretch),
                   "narrow": None if narrow_raw is None else float(narrow_raw), "push": dict(push or {})}

    def img_of(n):
        return rig_image.solidify(Image.open(root / outs[n][1].file), rig_image.TRUST_ALPHA_ANNOTATED)

    def pt(n, p):
        q = outs[n][1].points.get(p)
        return None if q is None else np.asarray(q, float)

    def width(n, p):
        return outs[n][1].widths.get(p)

    def depth(n, p):
        return outs[n][1].depths.get(p, 0.0)

    def put(n, img, x: Placement):
        pieces[n] = {"img": img, "cx": float(x.cx), "cy": float(x.cy), "unit": x.fx / G, "unit_y": x.fy / G,
                     "angle": float(x.angle), "mask": _mask(img, x, W, H)}
        xf[n] = x

    def at(n, p):
        return xf[n].world(pt(n, p))

    def uniform(n, J, P, f, ang=0.0):
        img = img_of(n)
        C = _centre_for(img.size, J, P, f, f, ang)
        put(n, img, Placement(img.size, C[0], C[1], f, f, ang))

    def limb(n, Jp, Jd, P, D, fitted=(1.0, None), push=None, img=None):
        img = img_of(n) if img is None else img
        tp = two_point(img.size, Jp, Jd, P, D, G, fitted[0])
        if abs(tp["stretch"] - 1) > STRETCH_MAX:
            doubts.append({"part": n, "reason": "stretch", "stretch": round(tp["stretch"], 3), "limit": STRETCH_MAX})
        put(n, img, Placement(img.size, tp["cx"], tp["cy"], tp["unit"], tp["unit_y"], tp["angle"]))
        record(n, "two_point", tp["stretch"], fitted[1], push)
        return xf[n].world(Jp), xf[n].world(Jd)

    def fit(n, pairs):
        """(width factor, raw ratio or None) for child n against its parents' openings:
        pairs of (child width in image px, opening width in master px)."""
        got = [narrow(wc * G, wo) for wc, wo in pairs if wc and wo]
        if not got:
            return 1.0, None
        f, raw = min(x[0] for x in got), min(x[1] for x in got)
        if raw < 1 - NARROW_MAX:
            doubts.append({"part": n, "reason": "narrow", "ratio": round(raw, 3), "limit": NARROW_MAX})
        return f, raw

    def width_fit(n, raw, reason):
        """(factor, raw): narrow part n by raw, at most WIDTH_FIT_MAX (a doubt `reason` beyond); never widen."""
        if raw < 1 - WIDTH_FIT_MAX:
            doubts.append({"part": n, "reason": reason, "ratio": round(raw, 3), "limit": WIDTH_FIT_MAX})
        return float(np.clip(raw, 1 - WIDTH_FIT_MAX, 1.0)), float(raw)

    def socket(parent, joint, axis, push, key):
        """A child's end pushed into the parent's opening `joint` along axis; records the distance (master px)."""
        d = depth(parent, joint) * xf[parent].fx
        P = push_in(at(parent, joint), axis, d)
        push[key] = d / 3
        return P

    # feet's scale: ankle-to-ground height (vertical) matches the master's, within FOOT_SCALE of the sheet's scale
    feet_f = {}
    for n, (p, _) in outs.items():
        s = _side(n)
        if p.role != "foot" or not s or pt(n, "ankle") is None:
            continue
        f = G
        if pt(n, "ground") is not None:
            h, hm = float(pt(n, "ground")[1] - pt(n, "ankle")[1]), float(M["ground"][1] - M[f"ankle_{s}"][1])
            if h > 1e-6 and hm > 1e-6:
                raw = hm / (h * G)
                f = G * float(np.clip(raw, *FOOT_SCALE))
                if not FOOT_SCALE[0] <= raw <= FOOT_SCALE[1]:
                    doubts.append({"part": n, "reason": "ground_miss", "ratio": round(float(raw), 3),
                                   "limit": list(FOOT_SCALE)})
        feet_f[n] = f

    # 1-2. torso (neck -> waist) and hips (waist -> between the leg openings), found by their annotated role
    T, HP = named(outs, "torso"), named(outs, "hips")
    if T not in outs:
        raise SystemExit("annotations: no rest torso output")
    Tn, Tw = limb(T, pt(T, "neck"), pt(T, "waist"), M["neck"], M["waist"])
    joints[T], bone_dir[T] = Tw, Tn - Tw
    if HP in outs:
        mid = (pt(HP, "hip_l") + pt(HP, "hip_r")) / 2
        # Leg-less, feet drawn over the hips: the hips' trouser legs run into the boots, so the hips are narrowed
        # (across, about the centre line) until each leg opening is at most HIPS_FOOT_FIT x its boot's ankle opening.
        hfit = None
        if ann.master.layers.get("foot") == "over_hips" and not has_legs(ann):
            ratios = [HIPS_FOOT_FIT * width(fn, "ankle") * f_ / (width(HP, f"hip_{_side(fn)}") * G)
                      for fn, f_ in feet_f.items() if width(fn, "ankle") and width(HP, f"hip_{_side(fn)}")]
            if ratios:
                hfit = width_fit(HP, min(ratios), "hips_too_wide")
        Hw, Hm = limb(HP, pt(HP, "waist"), mid, M["waist"], (M["hip_l"] + M["hip_r"]) / 2,
                      fitted=(hfit[0] if hfit else 1.0, None))
        if hfit:
            info[HP]["width_fit"] = {"factor": hfit[0], "raw": hfit[1]}
        # The hips bone runs into the hips, toward the leg openings. Its origin is the top of the piece on that line,
        # not the waist: a piece painted with its waistband well above the annotated waist (the fox's dungarees)
        # would otherwise have most of itself behind the bone's origin.
        Ht = axis_top(pieces[HP]["mask"], Hw, Hm - Hw)
        joints[HP], bone_dir[HP] = Ht, Hm - Ht

    # 3. head, hat, tail, ears, antlers, props: the colour matcher; the annotated root/neck is the pivot.
    #    Ears, antlers and horns come after the head and hat, held to their annotated side and root (match_headgear).
    matched = [n for n, (p, _) in outs.items() if p.role in MATCHED_ROLES]
    if matched:
        files = {n: root / outs[n][1].file for n in matched}
        parts = {n: (f, rig_image.load_rgba(f)) for n, f in files.items()}
        gear = [n for n in matched if outs[n][0].role in HEADGEAR_ROLES]
        placed, _, _ = rig_match.match_parts(frame, {n: v for n, v in parts.items() if n not in gear}, False, g,
                                      {"back": BACK_ANGLES}, roles)   # at the annotated scale
        if gear:
            Hk, Wk = frame.fg.shape
            anchor, claimed = np.zeros((Hk, Wk), bool), np.zeros((Hk, Wk), bool)
            for n, m in placed.items():
                mk = _work_mask(m, (Hk, Wk))
                claimed |= mk
                if outs[n][0].role in ("head", "hat"):
                    anchor |= mk
            for n in pieces:                                      # torso and hips, placed above
                claimed |= np.asarray(Image.fromarray(pieces[n]["mask"]).resize((Wk, Hk), Image.NEAREST))
            items = {n: (parts[n][1], pt(n, "root")) for n in gear}
            for n, m in match_headgear(frame, items, g, anchor if anchor.any() else None, claimed).items():
                placed[n] = m | {"src": files[n]}
                print(f"  {n:14s} err {m['err']:.4f}  scale {m['scale'] / g:.2f}  angle {m['angle']}  (side and root held)")
        by_src = {str(f): n for n, f in files.items()}
        matcher = None
        for n, m in placed.items():
            src = by_src[str(m["src"])]                           # a pair may have been swapped left/right
            if rig_roles.role(n, roles)[1] == "back" and n not in gear:         # refine the 10-degree search around the best
                matcher = matcher or rig_match.Matcher(frame.work, frame.fg)
                pad = 0.08 * frame.half_w
                fine = matcher.best(parts[src][1], [m["scale"] * k_ for k_ in REFINE_SCALES],
                                    [m["angle"] + a_ for a_ in REFINE_ANGLES],
                                    (m["cx"] - pad, m["cx"] + pad, m["cy"] - pad, m["cy"] + pad))
                if fine is not None and fine["err"] <= m["err"]:
                    m = fine | {"src": m["src"]}
            img = rig_image.solidify(Image.open(m["src"]), rig_image.TRUST_ALPHA_ANNOTATED)
            f = m["scale"] / frame.k
            put(n, img, Placement(img.size, m["cx"] / frame.k, m["cy"] / frame.k, f, f, float(m["angle"])))
            piv = next((p for p in PIVOTS if pt(src, p) is not None), None)
            if piv:
                J = xf[n].world(pt(src, piv))
            else:
                ys, xs = np.nonzero(pieces[n]["mask"])
                J = np.array([xs.mean(), ys.mean()])
            J = np.array(onto_part(pieces[n]["mask"], J))          # a pivot belongs on its own part
            joints[n] = J
            bone_dir[n] = np.array([0.0, -1.0]) if outs[src][0].role == "head" else _far_point(pieces[n]["mask"], J) - J
            record(n, "matcher")

    # 4. neckwear: its neck on the master's neck, then snapped by colour
    matcher_ = None
    for n, (p, _) in outs.items():
        if p.role == "neckwear" and pt(n, "neck") is not None:
            uniform(n, pt(n, "neck"), M["neck"], G)
            # The master's neck is where the neck meets the body; a scarf's annotated neck is the middle of its ring.
            # They need not coincide (the moose's scarf landed 35 px low, opening a gap under the chin that showed the
            # sleeve top), so the colour matcher snaps the piece within NECKWEAR_SNAP x body height of there.
            matcher_ = matcher_ or rig_match.Matcher(frame.work, frame.fg)
            c0, R = np.array([xf[n].cx, xf[n].cy]) * frame.k, NECKWEAR_SNAP * body_h * frame.k
            m = matcher_.best(rig_image.load_rgba(root / outs[n][1].file), [g * s for s in NECKWEAR_SCALES], NECKWEAR_ANGLES,
                              (c0[0] - R, c0[0] + R, c0[1] - R, c0[1] + R))
            if m is not None:
                f = m["scale"] / frame.k
                put(n, pieces[n]["img"], Placement(pieces[n]["img"].size, m["cx"] / frame.k, m["cy"] / frame.k, f, f,
                                                   float(m["angle"])))
            J = np.array(onto_part(pieces[n]["mask"], at(n, "neck")))   # a scarf's neck is its hollow: pin it on the cloth
            joints[n] = J
            bone_dir[n] = _far_point(pieces[n]["mask"], J) - J
            record(n, "socket")

    # 5. feet: the ankle opening centre on the master's ankle. Leg-less, feet over the hips: the trouser legs are the
    #    hips' (narrowed above), so each foot moves across to stand under its hips leg opening (x of the placed hips'
    #    hip_<side>), still at the master's ankle height; the shift is the ankle's push (landmark tolerance)
    #    Leg-less, feet under the hips: each foot gets a hidden shaft rising under the trouser cuff (rig_shaft), so
    #    walk / run can bob the hips without the boot coming out from under the trousers
    feet = {}
    under_hips = ann.master.layers.get("foot") == "over_hips" and not has_legs(ann) and HP in xf
    shafted = rig_shaft.wanted(ann, has_legs(ann), HP in xf)
    hips_in = _erode(pieces[HP]["mask"], rig_shaft.HIDE_ERODE) if shafted else None

    def shaft(n, A):
        """Foot n (placed with its ankle on A) on a canvas grown upward by a shaft, kept where the hips hide it;
        its annotated points move down by the rows added (the output's points: variant_fit and resolved use them)."""
        o, plain, f, x0 = outs[n][1], pieces[n]["img"], feet_f[n], xf[n]
        rows = int(round(rig_shaft.SHAFT_UP * body_h / f))
        J = pt(n, "ankle")
        w = width(n, "ankle") or rig_shaft.opening_width(plain, J)
        layer = rig_shaft.layer(plain, J, w, depth(n, "ankle"), rows)
        o.points = {k: (float(x), float(y) + rows) for k, (x, y) in o.points.items()}
        size2 = (plain.width, plain.height + rows)
        C = _centre_for(size2, pt(n, "ankle"), A, f, f, 0.0)
        x2 = Placement(size2, C[0], C[1], f, f, 0.0)
        hidden = rig_shaft.band(_pull_back(hips_in, x2), J[0], w, int(round(rows + J[1])))
        put(n, rig_shaft.compose(plain, layer, rows, hidden), x2)
        pieces[n]["shaft"] = {"rows": rows, "plain": plain, "width": float(w), "depth": depth(n, "ankle"),
                              "hidden": hidden, "centre": (float(x0.cx), float(x0.cy))}
        return {"rows": rows, "master_px": round(rows * f, 1), "width_px": round(float(w), 1),
                "kept_px": int((layer[..., 3] > 0)[hidden].sum())}

    for n, (p, _) in outs.items():
        s = _side(n)
        if p.role != "foot" or not s or pt(n, "ankle") is None:
            continue
        A = M[f"ankle_{s}"].copy()
        push = {}
        if under_hips and pt(HP, f"hip_{s}") is not None:
            dx = float(at(HP, f"hip_{s}")[0] - A[0])
            A[0] += dx
            push["ankle"] = abs(dx)
        uniform(n, pt(n, "ankle"), A, feet_f[n])   # scaled above (feet_f)
        sh = shaft(n, A) if shafted else None
        feet[s] = n
        gp = at(n, "ground") if pt(n, "ground") is not None else None
        joints[n] = A
        bone_dir[n] = (gp if gp is not None else _far_point(pieces[n]["mask"], A)) - A
        record(n, "socket", push=push)
        if push:
            info[n]["ankle_shift"] = {"dx": dx}
        if sh:
            info[n]["shaft"] = sh

    # 6. legs: from inside the hips' leg opening to inside the foot's ankle opening
    for n, (p, _) in outs.items():
        s = _side(n)
        if p.role != "leg" or not s:
            continue
        pairs, push = [], {}
        if HP in xf and pt(HP, f"hip_{s}") is not None:
            up = at(HP, "waist") - (at(HP, "hip_l") + at(HP, "hip_r")) / 2
            P = socket(HP, f"hip_{s}", up, push, "hip")
            pairs.append((width(n, "hip"), (width(HP, f"hip_{s}") or 0) * xf[HP].fx))
        else:
            P = M[f"hip_{s}"]
        foot = feet.get(s)
        if foot:
            down = _rot((0.0, 1.0), xf[foot].angle)
            D = socket(foot, "ankle", down, push, "hem")
            pairs.append((width(n, "hem"), (width(foot, "ankle") or 0) * xf[foot].fx))
        else:
            D = M[f"ankle_{s}"]
        Lp, Ld = limb(n, pt(n, "hip"), pt(n, "hem"), P, D, fit(n, pairs), push)
        joints[n], bone_dir[n] = Lp, Ld - Lp

    def shoulder_check(s):
        """The master's shoulder is the single source of truth (a plain point: not pushed in, not narrowed).
        A torso shoulder, when annotated, only cross-checks where the torso landed."""
        if pt(T, f"shoulder_{s}") is not None:
            off = float(np.linalg.norm(at(T, f"shoulder_{s}") - M[f"shoulder_{s}"])) / body_h
            if off > SHOULDER_DISAGREE:
                doubts.append({"part": T, "reason": "shoulder_mismatch", "point": f"shoulder_{s}",
                               "distance_frac": round(off, 4), "limit": SHOULDER_DISAGREE})

    def onto_torso(ua, Up):
        """A master shoulder annotated on the shoulder's outline can sit above the torso piece's own (lower) shoulder
        line: the joint must lie on both parts, so the bone's origin (not the art) moves to the nearest point the
        torso and the upper arm share. The move is the shoulder's push-in, and a doubt."""
        if T in pieces and not _on(pieces[T]["mask"], Up):
            both = _erode(pieces[T]["mask"] & pieces[ua]["mask"], 2)
            if both.any():
                Q = np.array(onto_part(both, Up))
                moved = float(np.linalg.norm(Q - Up))
                info[ua]["push"]["shoulder"] = moved
                doubts.append({"part": ua, "reason": "shoulder_outside_torso", "moved_px": round(moved, 1)})
                return Q
        return Up

    master_cache = {}

    def master_rgb():
        """(rgb 0..1, silhouette) of the master at full resolution (rig_frame.full_frame's background rule)."""
        if not master_cache:
            rgb = rig_image.load_rgba(root / ann.master.image)[..., :3]
            border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
            dist = np.linalg.norm(rgb - np.median(border, axis=0), axis=2)
            master_cache["v"] = (rgb, np.clip((dist - 0.03) / 0.05, 0, 1) > 0.5)
        return master_cache["v"]

    def above_sleeve():
        """The placed parts drawn over a sleeve's upper arm at rest (apply_layers): the head, hats and neckwear, and
        the torso when master.layers has upperarm under_torso - a sleeve edge against them may be hidden under them."""
        m = np.zeros((H, W), bool)
        for pn, pc in pieces.items():
            r = outs[pn][0].role if pn in outs else rig_roles.role(pn)[1]
            if r in ("head", "hat", "neckwear") or (r == "torso" and ann.master.layers.get("upperarm") == "under_torso"):
                m |= pc["mask"]
        return m

    def sleeve_mesh(n, s):
        """Whole sleeve output n (role arm) on side s, one drawing over both arm bones: its shoulder -> elbow lined up
        with the master's (the upper-arm placement), its elbow -> wrist on to the master's wrist (the forearm
        placement), two_point each at the sleeve's own scale (its shoulder -> elbow -> wrist against the master's;
        info[upperarm_<s>]["sleeve_scale"] = that / the sheet's), stretch doubts as for limbs. Pieces upperarm_<s> and
        forearm_<s> carry the drawing with those placements, their masks split at the elbow row; upperarm_<s> holds a
        "mesh" record for spine_rig (rig_mesh), forearm_<s> "mesh_of". The sleeve loses its hand-coloured
        pixels past its wrist rim like a forearm (wrist_trim; recorded on forearm_<s>). Width fit (rig_mesh.width_fit):
        each half narrowed across its axis onto the master's sleeve by the mesh's bind geometry ("fit" in the mesh
        record; info[upperarm_<s>]["width_fit"]; sleeve_too_wide doubts past rig_mesh.WIDTH_FIT_MIN, sleeve_too_thin past
        rig_mesh.SLEEVE_THIN), the masks too.
        Returns n: the cuff the hand goes into (xf[n] is the forearm placement)."""
        ua, fa, hd = named(outs, "upperarm", s), named(outs, "forearm", s), named(outs, "hand", s)
        shoulder_check(s)
        img, trim = img_of(n), None
        if hd in outs:
            timg, trim = wrist_trim(ann, n, img)
            img = timg if trim else img
        S_i, E_i, W_i = pt(n, "shoulder"), pt(n, "elbow"), pt(n, "wrist")
        # A sleeve sheet is generated on its own and paints at its own scale (the fox's: ~1.8x the body sheet's), so
        # its scale is its shoulder -> elbow -> wrist length against the master's; each half then stretches to its
        # joints as a limb does.
        Ms, Me, Mw = M[f"shoulder_{s}"], M[f"elbow_{s}"], M[f"wrist_{s}"]
        Gs = float((np.linalg.norm(Me - Ms) + np.linalg.norm(Mw - Me))
                   / max(np.linalg.norm(E_i - S_i) + np.linalg.norm(W_i - E_i), 1e-6))
        tu = two_point(img.size, S_i, E_i, Ms, Me, Gs)
        Tu = Placement(img.size, tu["cx"], tu["cy"], tu["unit"], tu["unit_y"], tu["angle"])
        Eu = Tu.world(E_i)
        tf = two_point(img.size, E_i, W_i, Eu, Mw, Gs)
        Tf = Placement(img.size, tf["cx"], tf["cy"], tf["unit"], tf["unit_y"], tf["angle"])
        for bone, tp in ((ua, tu), (fa, tf)):
            if abs(tp["stretch"] - 1) > STRETCH_MAX:
                doubts.append({"part": n, "bone": bone, "reason": "stretch", "stretch": round(tp["stretch"], 3),
                               "limit": STRETCH_MAX})
        # Width fit (rig_mesh.width_fit): each half's thickness across its axis against the master's sleeve, the
        # sleeve narrowed (never widened) onto the master's tube by the mesh's bind geometry; the masks follow.
        rgb, fg = master_rgb()
        fit = rig_mesh.width_fit(rgb, fg, (Ms, Me, Mw), np.asarray(img.convert("RGBA"))[..., 3] > 127,
                                 (S_i, E_i, W_i), Gs, above_sleeve())
        for half in ("upper", "lower"):
            raw = fit[half]["raw"]
            if raw is not None and raw < rig_mesh.WIDTH_FIT_MIN:
                doubts.append({"part": n, "reason": "sleeve_too_wide", "half": half, "ratio": round(raw, 3),
                               "limit": rig_mesh.WIDTH_FIT_MIN})
            if raw is not None and raw > rig_mesh.SLEEVE_THIN:      # never widened: a thin cuff makes the hand look big
                doubts.append({"part": n, "reason": "sleeve_too_thin", "half": half, "ratio": round(raw, 3),
                               "limit": rig_mesh.SLEEVE_THIN})
        upper, lower = rig_mesh.split_at_elbow(rig_mesh.fit_image(img, fit), S_i, E_i, W_i)
        put(ua, img, Tu)
        put(fa, img, Tf)
        pieces[ua]["mask"], pieces[fa]["mask"] = _mask(upper, Tu, W, H), _mask(lower, Tf, W, H)
        pieces[ua]["mesh"] = {"arm": n, "fore": fa, "upper": Tu, "lower": Tf, "fit": fit,
                              "points": {"shoulder": S_i, "elbow": E_i, "wrist": W_i}}
        pieces[fa]["mesh_of"] = ua
        xf[n] = Tf
        record(ua, "mesh", tu["stretch"], None, {"shoulder": 0.0})
        record(fa, "mesh", tf["stretch"])
        info[ua]["mesh"] = n
        info[ua]["sleeve_scale"] = Gs / G
        info[ua]["width_fit"] = {h: {"factor": round(fit[h]["factor"], 4), "offset_px": round(fit[h]["offset_px"], 2),
                                     "raw": None if fit[h]["raw"] is None else round(fit[h]["raw"], 4),
                                     "samples": fit[h]["samples"]} for h in ("upper", "lower")}
        if trim:
            info[fa]["wrist_trim"] = trim
            if trim.get("skipped") == "ambiguous_colours":
                doubts.append({"part": n, "reason": "wrist_trim_ambiguous"})
        Up = onto_torso(ua, Tu.world(S_i))
        joints[ua], bone_dir[ua] = Up, Eu - Up
        joints[fa], bone_dir[fa] = Eu, Tf.world(W_i) - Eu
        return n

    # 7-8. arms: upper arm from the master's shoulder to its elbow, forearm on to the wrist, then the hand. A side with
    #      a whole sleeve (role arm) places it instead, as one drawing over both bones (sleeve_mesh)
    sleeves = {_side(n): n for n, (p, _) in outs.items() if p.role == "arm" and _side(n)}
    for s in ("l", "r"):
        ua, fa, hd = named(outs, "upperarm", s), named(outs, "forearm", s), named(outs, "hand", s)
        E = M[f"elbow_{s}"]
        cuff = fa                                               # what the hand goes into
        if s in sleeves:
            cuff = sleeve_mesh(sleeves[s], s)
            E = joints[fa]
        elif ua in outs:
            shoulder_check(s)
            # The master's sleeve is one tube: the upper arm is narrowed (across) so its elbow round end is no wider
            # than the forearm's (placed at the sheet's scale), else the forearm's top shows as a step at the elbow.
            ufit = None
            if fa in outs and width(ua, "elbow") and width(fa, "elbow"):
                ufit = width_fit(ua, width(fa, "elbow") / width(ua, "elbow"), "upperarm_too_wide")
            Up, E = limb(ua, pt(ua, "shoulder"), pt(ua, "elbow"), M[f"shoulder_{s}"], M[f"elbow_{s}"],
                         fitted=(ufit[0] if ufit else 1.0, None), push={"shoulder": 0.0})
            if ufit:
                info[ua]["width_fit"] = {"factor": ufit[0], "raw": ufit[1]}
            Up = onto_torso(ua, Up)
            joints[ua], bone_dir[ua] = Up, E - Up
        Wr = M[f"wrist_{s}"]
        if fa in outs and s not in sleeves:
            fimg, trim = wrist_trim(ann, fa, img_of(fa)) if hd in outs else (None, None)
            Fp, Wr = limb(fa, pt(fa, "elbow"), pt(fa, "wrist"), E, M[f"wrist_{s}"], img=fimg if trim else None)
            joints[fa], bone_dir[fa] = Fp, Wr - Fp
            if trim:
                info[fa]["wrist_trim"] = trim
                if trim.get("skipped") == "ambiguous_colours":
                    doubts.append({"part": fa, "reason": "wrist_trim_ambiguous"})
        if hd in outs and pt(hd, "wrist") is not None:
            push = {}
            if cuff in xf and pt(cuff, "wrist") is not None:      # into the cuff, along the forearm towards the elbow
                Wr = socket(cuff, "wrist", at(cuff, "elbow") - at(cuff, "wrist"), push, "wrist")
            hw, hf = pt(hd, "wrist"), pt(hd, "fingertip")
            f = G
            if hf is None:                                      # a fist: wrist to the painted centroid
                al = np.asarray(img_of(hd))[..., 3] > 127
                ys, xs = np.nonzero(al)
                hf = np.array([xs.mean(), ys.mean()])
            else:
                f = float(np.clip(np.linalg.norm(M[f"fingertip_{s}"] - M[f"wrist_{s}"]) / max(np.linalg.norm(hf - hw), 1e-6),
                                  HAND_SCALE[0] * G, HAND_SCALE[1] * G))
            ang = _vis(M[f"fingertip_{s}"] - M[f"wrist_{s}"]) - _vis(hf - hw)
            uniform(hd, hw, Wr, f, (ang + 180.0) % 360.0 - 180.0)
            Wr = np.asarray(Wr, float)
            # The bone runs along the hand image's own axis, image-down (hands are painted joint end up), not along
            # the master's wrist -> fingertip: the art still matches the master, and every hand variant, turned so its
            # image-down lies along the bone (rig_variants), continues the forearm wherever the bone does.
            L = float(np.linalg.norm(hf - hw))
            joints[hd], bone_dir[hd] = Wr, xf[hd].world(hw + np.array([0.0, L])) - Wr
            record(hd, "hand", push=push)
    for n in outs:
        if n not in pieces and n not in sleeves.values():          # a sleeve lives in its side's arm pieces
            doubts.append({"part": n, "reason": "not_placed"})
    joints = {n: np.asarray(v, float) for n, v in joints.items()}
    return pieces, joints, bone_dir, doubts, info


# ------------------------------------------------------------------ cross-check against the colour matcher

CROSS_BOX = 0.15                  # of body height: how far around the annotated centre the matcher may look
CROSS_ANGLES = range(-30, 31, 10)  # degrees around the annotated angle (the matcher's limb range)


def cross_check(ann, frame, g: float, pieces: dict) -> list:
    """A second opinion from the colour matcher (rig_match.Matcher, masked colour SSD) on every annotation-placed
    rest part (not the ones it placed itself): at the part's annotated scale, within CROSS_ANGLES of its annotated
    angle and CROSS_BOX x body height of its annotated centre. A best fit more than MATCHER_DISAGREE x body height
    away is a doubt {"part", "reason": "matcher_disagreement", "distance_frac", "annotation": [x, y],
    "matcher": [x, y]} (centres in full-resolution master px).
    match_parts' own search is not reused: its scale range lets a torso shrink 10% into the master's silhouette
    (5% of body height off on an exact synthetic character), and its hand search box leans on master proportions."""
    outs = _rest_outputs(ann)
    root = ann.path.parent
    names = [n for n, (p, _) in outs.items() if p.role not in MATCHED_ROLES and n in pieces
             and "mesh" not in pieces[n] and "mesh_of" not in pieces[n]]    # a sleeve mesh is not its two-piece outputs
    matcher = rig_match.Matcher(frame.work, frame.fg)
    body_w = frame.ground_y - frame.top                       # work px
    r = CROSS_BOX * body_w
    doubts = []
    for n in sorted(names):
        pc = pieces[n]
        sh = pc.get("shaft")                                  # a foot with a hidden shaft: judge the painted foot
        ac = np.array(sh["centre"] if sh else (pc["cx"], pc["cy"]), float) * frame.k
        m = matcher.best(rig_image.load_rgba(root / outs[n][1].file), [pc["unit"] * g],
                         [pc["angle"] + a for a in CROSS_ANGLES], (ac[0] - r, ac[0] + r, ac[1] - r, ac[1] + r))
        if m is None:
            continue
        mc = np.array([m["cx"], m["cy"]], float)
        frac = float(np.linalg.norm(mc - ac)) / body_w
        if frac > MATCHER_DISAGREE:
            doubts.append({"part": n, "reason": "matcher_disagreement", "distance_frac": round(frac, 4),
                           "annotation": [round(float(v) / frame.k, 1) for v in ac],
                           "matcher": [round(float(v) / frame.k, 1) for v in mc]})
    return doubts


# ------------------------------------------------------------------ pose variants (spine_rig stage 4b, rig_variants)

TUBE_ROLES = ("upperarm", "forearm", "leg")
AREA_ROLES = ("tail", "ear", "antler", "horn")
VARIANT_STRETCH = (0.75, 1.33)     # a tube variant's own length may differ from its width's scale by this much
FOOT_SCALE_AGREE = 1.3    # a foot variant's ankle-width scale this far (either way) from its area scale is mis-measured


def variant_fit(ann, slot: str, name: str, rest_img: Image.Image, var_img: Image.Image, s_r: float, s_ry: float,
                narrow: float = 1.0):
    """Where a pose variant goes, from the annotated joints of its output `name` and of the rest output `slot`.
    The joint is the role's proximal point (hand wrist, upper arm shoulder, foot ankle, tail root...). Scale:
    hands and feet by the ratio of their joint widths; tubes by the proximal round end's width ratio across and the
    two-point length ratio along (scaleY, within VARIANT_STRETCH of the width's scale); tails and ears by area.
    Tubes turn so the annotated axes agree. s_r, s_ry: the rest attachment's scaleX, scaleY. narrow: the rest's
    width fit (an upper arm narrowed to its forearm). Only the rest is narrowed: a variant (a raised sleeve, whose
    bunched painted shape is intentional) is scaled against the rest's un-narrowed width scale s_r / narrow, across
    and along.
    A foot's ankle widths are cross-checked against the two images' area ratio (a tiptoe is the same foot, painted
    at its sheet's scale): beyond FOOT_SCALE_AGREE either way the widths were measured unlike for like (the bear's
    tilted clog: its snapped heel rim, 137 px, against the rest clog's unsnapped cross width, 362 px, gave scaleX
    3.17), so the area ratio is used and "scale_check" {"from": "area", "width_ratio", "area_ratio", "snaps"} says so.
    Returns {"Jr", "Jv" (image px), "sxy", "ratio", "turn" (radians)[, "scale_check"]}, or None when the annotations
    can't say."""
    by_name = {o.name: (p, o) for p in ann.pieces.values() for o in p.outputs}
    if slot not in by_name or name not in by_name:
        return None
    (p, ro), (_, vo) = by_name[slot], by_name[name]
    joint = ra.ROLES.get(p.role, (None,))[0]
    if joint is None or joint not in ro.points or joint not in vo.points:
        return None
    Jr, Jv = np.asarray(ro.points[joint], float), np.asarray(vo.points[joint], float)
    turn, check = 0.0, None
    if p.role in TUBE_ROLES:
        dist = ra.ROLES[p.role][1]
        wr, wv = ro.widths.get(joint), vo.widths.get(joint)
        if not (wr and wv and dist in ro.points and dist in vo.points):
            return None
        ratio = wr / wv
        ar, av = np.asarray(ro.points[dist], float) - Jr, np.asarray(vo.points[dist], float) - Jv
        Lr, Lv = float(np.linalg.norm(ar)), float(np.linalg.norm(av))
        if Lr < 1 or Lv < 1:
            return None
        s_w = s_r / narrow                                  # the rest's width scale before any width fit
        stretch = float(np.clip(Lr * (s_ry / s_w) / Lv / ratio, *VARIANT_STRETCH))
        sxy = (s_w * ratio, s_w * ratio * stretch)          # not narrowed: only the rest is fitted to its forearm
        turn = math.radians(_vis((ar[0] * s_r, ar[1] * s_ry)) - _vis((av[0] * sxy[0], av[1] * sxy[1])))
    elif p.role in ("hand", "foot"):
        wr, wv = ro.widths.get(joint), vo.widths.get(joint)
        if not (wr and wv):
            return None
        ratio = wr / wv
        if p.role == "foot":
            area = _area_ratio(rest_img, var_img)
            if area and abs(math.log(ratio / area)) > math.log(FOOT_SCALE_AGREE):
                snaps = [_snap_state(q, joint) for q in (p, by_name[name][0])]
                check = {"from": "area", "width_ratio": round(ratio, 3), "area_ratio": round(area, 3), "snaps": snaps}
                ratio = area
        sxy = (s_r * ratio, s_r * ratio)
    elif p.role in AREA_ROLES:
        ratio = _area_ratio(rest_img, var_img)
        if not ratio:
            return None
        sxy = (s_r * ratio, s_r * ratio)
    else:
        return None
    out = {"Jr": Jr, "Jv": Jv, "sxy": sxy, "ratio": float(ratio), "turn": turn}
    if check:
        out["scale_check"] = check
    return out


def _area_ratio(rest_img, var_img) -> float | None:
    """sqrt(opaque area of the rest image / the variant's): their size ratio in their own pixels (None: no images)."""
    if rest_img is None or var_img is None:
        return None
    ar_, av_ = ((np.asarray(im)[..., 3] > 127).sum() for im in (rest_img, var_img))
    return math.sqrt(ar_ / av_) if av_ and ar_ else None


def _snap_state(piece, joint: str) -> str:
    """How the piece's joint point was measured (rig_annotations.Point.snap: ok | failed | none)."""
    pt = getattr(piece, "points", {}).get(joint)
    return getattr(pt, "snap", "none") if pt is not None else "none"


# ------------------------------------------------------------------ rig/annotations.resolved.json

# Each gesture's hold: (hand variant, time in seconds) - the frame QA judges the thumb at.
HOLDS = {"point": ("point", 1.2), "thumbs_up": ("thumbsup", 1.2), "hold_card": ("grip", 1.2),
         "wave": ("open", 0.75), "cheer_jump": ("fist", 0.95)}
PUSHED_ORIGINS = ("hip", "shoulder", "wrist", "ankle")   # moved joints that are bone origins (the leg's hem is not)


def resolved(ann, prefix: str, skin: dict, anims: dict, bones, info: dict, units, unit: float,
             body_height_units: float, size: tuple, variant_trims: dict | None = None) -> dict:
    """Every annotated point per attachment (attachment-image px), for spine_qa's annotation checks.
    skin: slot -> attachment -> region; bones: the bone names; info: place_from_annotations' info;
    units: full-res master px -> Spine units; unit: units per master px; size: (W, H) of the master;
    variant_trims: variant attachment -> its wrist_trim info (the rest forearms' are in info). A forearm the trim
    changed gets "rim_inset" {"wrist": inset px}: spine_qa judges its socket at the moved rim."""
    by_name = {o.name: (p, o) for p in ann.pieces.values() for o in p.outputs}
    atts, targets = {}, {}
    for slot, entries in skin.items():
        side = _side(slot)
        for att in entries:
            rec = by_name.get(att[len(prefix):]) if att.startswith(prefix) else None
            if rec is None:
                continue
            p, o = rec
            v = None if p.variant in (None, "rest") else p.variant
            atts[att] = {"slot": slot, "variant": v, "side": side,
                         "points": {n: [round(float(x), 2), round(float(y), 2)] for n, (x, y) in o.points.items()},
                         "widths": {n: round(float(w), 2) for n, w in o.widths.items()}}
            rim = wrist_rim(ann, o.name) if p.role in ("forearm", "arm") else None
            own = f"forearm_{side}" if p.role == "arm" else o.name      # a sleeve's trim is recorded on its forearm
            trim = (info.get(own) or {}).get("wrist_trim") if v is None else (variant_trims or {}).get(att)
            if rim is not None and rim[2] > 0 and trimmed(trim):   # trimmed at the wrist: its rim sits this far inside
                atts[att]["rim_inset"] = {"wrist": round(float(rim[2]), 2)}
            if p.role == "hand" and side:
                tgt = rig_hands.THUMB_TARGET.get(v) if v else ann.master.hands.get(side, {}).get("thumb_side")
                if tgt:
                    targets[att] = rig_hands.target_deg(tgt, side)

    def rest(n):
        a = f"{prefix}{n}"
        return a if a in atts and atts[a]["variant"] is None else None

    outs = _rest_outputs(ann)                       # by annotated role, not by name
    feet = {_side(n): n for n, (p, _) in outs.items() if p.role == "foot" and _side(n)}
    sleeves = {_side(n): n for n, (p, _) in outs.items() if p.role == "arm" and _side(n)}
    sockets, layer_order = [], []

    def socket(child, cp, parent, pp):
        c, pa = rest(child), (rest(parent) if parent else None)
        if c and pa and cp in atts[c]["points"] and pp in atts[pa]["points"] and pp in atts[pa]["widths"]:
            sockets.append({"child": c, "child_point": cp, "parent": pa, "parent_point": pp,
                            "width": atts[pa]["widths"][pp]})
    for s in ("l", "r"):
        leg, hand = named(outs, "leg", s), named(outs, "hand", s)
        socket(leg, "hem", feet.get(s), "ankle")
        socket(leg, "hip", named(outs, "hips"), f"hip_{s}")
        sleeve = sleeves.get(s)                     # a sleeve mesh: the hand sits in the sleeve's wrist opening
        cuff = sleeve if sleeve and rest(sleeve) else named(outs, "forearm", s)
        socket(hand, "wrist", cuff, "wrist")
        if rest(hand) and rest(cuff):               # the hand's side of its cuff's slot, as master.layers.hand says
            layer_order.append({"slot": atts[rest(hand)]["slot"], "over": atts[rest(cuff)]["slot"],
                                "relation": "above" if ann.master.layers.get("hand") == "over_forearm" else "below"})

    holds = {}
    for anim, (v, t) in HOLDS.items():
        keyed = anims.get(anim, {}).get("slots", {})
        for slot in ("hand_l", "hand_r"):
            att = f"{prefix}{slot}_{v}"
            if any(k.get("name") == att for k in keyed.get(slot, {}).get("attachment", [])):
                holds[anim] = {"time": t, "slot": slot, "variant": v, "side": slot[-1], "attachment": att}
                break

    bones = set(bones)
    point_bones = {}
    for s in ("l", "r"):
        for joint, bone in (("shoulder", "upperarm"), ("elbow", "forearm"), ("wrist", "hand"), ("hip", "leg")):
            if f"{bone}_{s}" in bones:
                point_bones[f"{joint}_{s}"] = f"{bone}_{s}"
        if feet.get(s) in bones:
            point_bones[f"ankle_{s}"] = feet[s]
    # no "neck": the head is placed by the colour matcher, with its own annotated neck as the pivot

    W, H = size
    push = {}
    for n, i in info.items():
        for j, d in (i.get("push") or {}).items():
            if j in PUSHED_ORIGINS and _side(n):
                push[f"{j}_{_side(n)}"] = round(float(d) * unit, 3)
    return {"attachments": atts, "sockets": sockets, "layer_order": layer_order, "holds": holds,
            "thumb_targets": targets,
            "master_points_units": {n: [round(float(c), 3) for c in units((x * W, y * H))]
                                    for n, (x, y) in ann.master.points.items()},
            "point_bones": point_bones, "body_height_units": round(float(body_height_units), 3), "push_in": push}
