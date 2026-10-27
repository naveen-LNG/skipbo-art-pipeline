#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""synth_character.py - a synthetic, fully annotated test character drawn with PIL.

make_character(root) writes, under root/:
  master.png                              600 x 900 front view on flat (214, 214, 214), one flat colour per part
  runs/synth-body-parts/synth_NN.png      raw split pieces, joint end up, painted at 0.8 x the master's scale
  runs/synth-hands-parts/synth_NN.png     hand variants: open, fist, point, thumbsup, grip
  runs/synth-heads-parts/synth_NN.png     expression heads: neutral, happy
  runs/synth-poses-parts/synth_NN.png     (pose_variants=True) raised sleeves, tiptoe feet, tail up, painted at
                                          POSE_SCALE (their own sheet's scale) so variant scaling is exercised
  runs/synth-legs-parts/synth_NN.png      (legs=True) whole legs, belt to soles (role legs): two in-between sheets,
                                          squat_1..5 and jump_1..5 (LEGS_SHEETS: each drawing's height over the
                                          rest's) and their in-betweens (LEGS_MIDS), painted at POSE_SCALE
  (sleeves=True) one more body piece: a whole sleeve (role arm, side either, painted as the left), and the master's
  arms drawn as that sleeve, straight (shoulder, elbow and wrist on one line); the two-piece arm pieces stay on the
  sheet (a real character has both) but no longer match the master
  (hat=True) one more body piece: a hat (role hat) on top of the head, in the master too
  (names={role: name}) free-form names for the non-structural roles foot, neckwear, hat and tail (default: the foot's
  kind, "scarf", "hat", "tail"); the output files follow the name
  body/, variants/, face-heads/           the normalised outputs (synth_<name>.png), as normalise would write them
  annotations.json                        valid under rig_annotations, everything "confirmed", outputs filled in
  truth.json                              exact joints: master points in master px, piece points in raw piece px

Every part is described once in a local frame at master scale (proximal joint at the origin, distal joint
along +y, i.e. joint end up), then rendered three ways: into its raw piece (x0.8), into its outputs (the raw
piece, mirrored where its side needs it) and into the master (rotated and moved onto the master's joints).
Deterministic: no randomness. `_l` is the character's left = the picture's right.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

import rig_annotations as ra
import rig_hands as rh

CHAR = "synth"
W, H = 600, 900
BG = (214, 214, 214)
SCALE = 0.8              # raw pieces are painted at this fraction of the master's scale
SS = 4                   # supersampling factor for anti-aliased edges
PAD = 10                 # transparent margin around each raw piece, px
DEPTH_RATIO = 0.35       # an opening's depth as a fraction of its width
POSE_SCALE = 0.7         # the pose-variant sheet paints at its own scale
BODY_RUN, HANDS_RUN, HEADS_RUN = "synth-body-parts", "synth-hands-parts", "synth-heads-parts"
POSES_RUN = "synth-poses-parts"
LEGS_RUN = "synth-legs-parts"
LEGS_SHEETS = {"squat": (1.0, 0.98, 0.9, 0.8, 0.7),          # buckle to soles over drawing 1's: stand -> crouch;
               "jump": (1.0, 1.06, 0.85, 0.7, 0.6)}            # stand -> push-off -> tuck (deeper than the beaver's)
LEGS_MIDS = {"squat": [(4, 5)], "jump": [(2, 3)]}              # in-betweens <sheet>_<a>-<b>, painted MID_SHORT x the
MID_SHORT = 0.96                                               # halfway height (the rig squashes them to halfway)
HAND_VARIANTS = ("open", "fist", "point", "thumbsup", "grip")
EXPRESSIONS = ("neutral", "happy")
MASTER_HANDS = {"l": {"thumb_side": "lateral", "facing": "palm"}, "r": {"thumb_side": "lateral", "facing": "palm"}}

# Flat colours, one per part (plus darker openings/features), all far from the background.
C = {
    "torso": (60, 110, 190), "armhole": (30, 60, 115),
    "hips": (70, 140, 90), "leghole": (35, 80, 50),
    "upperarm": (200, 60, 60), "forearm": (235, 185, 140), "hand": (250, 250, 250),
    "leg": (110, 70, 150),
    "boot": (125, 75, 35), "boot_rim": (85, 48, 20), "boot_hole": (35, 20, 10),
    "hoof_fur": (150, 120, 95), "hoof": (60, 50, 45), "hoof_split": (25, 20, 18),
    "head": (240, 200, 90), "eye": (30, 30, 30), "mouth": (130, 40, 40),
    "tail": (215, 125, 40), "tail_tip": (250, 235, 215),
    "scarf": (40, 190, 190),
    "hat": (225, 110, 200), "hat_brim": (150, 50, 130),
    "sleeve": (170, 50, 120),
}

# Master layout, master px. Arms hang at about -70 deg (world angles, y up, for the character's left side).
NECK = (300.0, 232.0)
LEN = {"upperarm": 120.0, "forearm": 110.0, "hand": 64.0}
ARM_DEG = {"upperarm": -70.0, "forearm": -76.0, "hand": -80.0}
HIP_X, ANKLE = 38.0, {"l": (346.0, 792.0), "r": (254.0, 792.0)}
TAIL_ROOT, TAIL_DEG = (352.0, 540.0), -35.0

# The most recent make_character() truth, also written to root/truth.json.
TRUTH: dict = {}


# ------------------------------------------------------------------ geometry

@dataclass
class Part:
    shapes: list                                  # [(rgb, [(x, y), ...])] polygons, back to front, local coords
    points: dict                                  # joint name -> (x, y), local coords
    widths: dict = field(default_factory=dict)    # joint name -> width (round ends and openings), local units

    def mirrored(self) -> "Part":
        return Part([(c, [(-x, y) for x, y in poly]) for c, poly in self.shapes],
                    {n: (-x, y) for n, (x, y) in self.points.items()}, dict(self.widths))


def ellipse(cx, cy, rx, ry, n=64):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def capsule(colour, p0, r0, p1, r1):
    """Round-ended tube from p0 (radius r0) to p1 (radius r1)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy)
    nx, ny = -dy / ln, dx / ln
    quad = [(p0[0] + nx * r0, p0[1] + ny * r0), (p1[0] + nx * r1, p1[1] + ny * r1),
            (p1[0] - nx * r1, p1[1] - ny * r1), (p0[0] - nx * r0, p0[1] - ny * r0)]
    return [(colour, ellipse(*p0, r0, r0)), (colour, ellipse(*p1, r1, r1)), (colour, quad)]


def tip(p0, p1, r):
    """The far end of a capsule p0 -> p1 with end radius r."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy)
    return (p1[0] + r * dx / ln, p1[1] + r * dy / ln)


def world_dir(deg_left: float, side: str):
    """Image direction (y down) of a world angle given for the character's left side."""
    a = math.radians(rh.side_deg(deg_left, side))
    return (math.cos(a), -math.sin(a))


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def unit(a, b):
    d = dist(a, b)
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def placer(origin, d):
    """Local -> master: local +y runs along image direction d, the origin lands on `origin` (a rotation)."""
    dx, dy = d

    def f(p):
        x, y = p
        return (origin[0] + x * dy + y * dx, origin[1] - x * dx + y * dy)
    return f


# ------------------------------------------------------------------ parts (local frame, master scale)

def torso() -> Part:
    body = [(-60, -8), (60, -8), (80, 12), (84, 40), (78, 225), (-78, 225), (-84, 40), (-80, 12)]
    shapes = [(C["torso"], body), (C["armhole"], ellipse(68, 30, 12, 24)), (C["armhole"], ellipse(-68, 30, 12, 24))]
    return Part(shapes, {"neck": (0, 0), "waist": (0, 218), "shoulder_l": (68, 30), "shoulder_r": (-68, 30)},
                {"shoulder_l": 48, "shoulder_r": 48})


def hips() -> Part:
    body = [(-74, -14), (74, -14), (78, 60), (70, 70), (-70, 70), (-78, 60)]
    shapes = [(C["hips"], body), (C["leghole"], ellipse(HIP_X, 70, 30, 9)), (C["leghole"], ellipse(-HIP_X, 70, 30, 9))]
    return Part(shapes, {"waist": (0, 0), "hip_l": (HIP_X, 70), "hip_r": (-HIP_X, 70)}, {"hip_l": 60, "hip_r": 60})


def upperarm(length) -> Part:
    return Part(capsule(C["upperarm"], (0, 0), 22, (0, length), 20),
                {"shoulder": (0, 0), "elbow": (0, length)}, {"shoulder": 44, "elbow": 40})


def forearm(length) -> Part:
    """A sleeve whose cuff is 3 px wider than the hand's wrist on each side (as the boot is around the leg's hem):
    the hand is pushed a third of the cuff's depth in, and its corners must not poke out when it turns a little."""
    shapes = [(C["forearm"], ellipse(0, 0, 19, 19)), (C["forearm"], [(-19, 0), (19, 0), (18, length), (-18, length)])]
    return Part(shapes, {"elbow": (0, 0), "wrist": (0, length)}, {"elbow": 38, "wrist": 36})


def leg(length) -> Part:
    shapes = [(C["leg"], ellipse(0, 0, 29, 29)), (C["leg"], [(-29, 0), (29, 0), (25, length), (-25, length)])]
    return Part(shapes, {"hip": (0, 0), "hem": (0, length)}, {"hip": 58, "hem": 50})


def foot(kind: str, side: str) -> Part:
    """A boot (toe out to the lateral side) or a hoof; an elliptical darker opening rim at the top."""
    s = 1 if side == "l" else -1
    if kind == "boot":
        shapes = [(C["boot"], [(-28, 0), (28, 0), (28, 56), (-28, 56)]),
                  (C["boot"], ellipse(12 * s, 64, 44, 16))]
        ground = (12 * s, 80)
    else:
        shapes = [(C["hoof_fur"], [(-28, 0), (28, 0), (30, 46), (-30, 46)]),
                  (C["hoof"], [(-32, 46), (32, 46), (38, 80), (-38, 80)]),
                  (C["hoof_split"], [(-3, 80), (3, 80), (0, 58)])]
        ground = (0, 80)
    shapes += [(C["boot_rim"], ellipse(0, 0, 28, 8)), (C["boot_hole"], ellipse(0, 1, 22, 5))]
    return Part(shapes, {"ankle": (0, 0), "ground": ground}, {"ankle": 56})


def sleeve(lu, lf) -> Part:
    """A whole sleeve (role arm), shoulder to cuff, straight, joint end up: a round shoulder end, tapering a little
    to a flat cuff (the wrist opening, about as wide as the forearm's cuff)."""
    c = C["sleeve"]
    shapes = [(c, ellipse(0, 0, 22, 22)),
              (c, [(-22, 0), (22, 0), (20, lu), (18.5, lu + lf), (-18.5, lu + lf), (-20, lu)])]
    return Part(shapes, {"shoulder": (0, 0), "elbow": (0, lu), "wrist": (0, lu + lf)}, {"shoulder": 44, "wrist": 37})


def raised_sleeve() -> Part:
    """The raised upper-arm variant: a shorter sleeve with a turned-back cuff, joint end up."""
    shapes = capsule(C["upperarm"], (0, 0), 22, (0, 100), 20) + [(C["armhole"], [(-21, 86), (21, 86), (21, 94), (-21, 94)])]
    return Part(shapes, {"shoulder": (0, 0), "elbow": (0, 100)}, {"shoulder": 44, "elbow": 40})


def tiptoe(kind: str, side: str) -> Part:
    """A foot on tiptoe: the rest foot narrowed and drawn out downwards below the rim."""
    base = foot(kind, side)

    def f(p):
        x, y = p
        return (x, y) if y <= 10 else (x * 0.75, 10 + (y - 10) * 1.3)
    return Part([(c, [f(q) for q in poly]) for c, poly in base.shapes], {n: f(q) for n, q in base.points.items()},
                dict(base.widths))


def tail_up() -> Part:
    shapes = capsule(C["tail"], (0, 0), 14, (0, 120), 9) + [(C["tail_tip"], ellipse(0, 122, 9, 9))]
    return Part(shapes, {"root": (0, 0)})


def legs_part(frac: float, rest_h: float) -> Part:
    """Whole legs, belt to soles (role legs), joint end up: the belt band (as wide as the hips at the waist) with the
    waist point in its middle, two trouser legs bending out at the knee as the drawing gets shorter (frac of the rest
    height), a boot under each; ground: the soles' line, midway."""
    h = rest_h * frac
    bend = max(0.0, 1 - frac)                            # 0 standing (or stretched) .. 0.4 tucked
    knee_y, knee_x = 0.48 * h, 38 + 150 * bend
    shapes = [(C["hips"], [(-75, -14), (75, -14), (77, 22), (-77, 22)])]
    for s in (1, -1):
        hip, ankle = (s * 38, 16), (s * (38 + 40 * bend), h - 74)
        knee = (s * knee_x, knee_y)
        shapes += capsule(C["leg"], hip, 30, knee, 28) + capsule(C["leg"], knee, 28, ankle, 26)
        shapes += [(C["boot"], [(ankle[0] - 28, ankle[1]), (ankle[0] + 28, ankle[1]), (ankle[0] + 28, h - 20),
                                (ankle[0] - 28, h - 20)]),
                   (C["boot"], ellipse(ankle[0] + 12 * s, h - 14, 44, 14))]
    return Part(shapes, {"waist": (0, 0), "ground": (0, h)})


def head(expr: str) -> Part:
    shapes = [(C["head"], ellipse(0, -74, 74, 74)),
              (C["eye"], ellipse(-24, -92, 7, 9)), (C["eye"], ellipse(24, -92, 7, 9))]
    if expr == "happy":
        outer = [(22 * math.cos(math.radians(a)), -54 + 14 * math.sin(math.radians(a))) for a in range(15, 166, 10)]
        inner = [(18 * math.cos(math.radians(a)), -54 + 7 * math.sin(math.radians(a))) for a in range(165, 14, -10)]
        shapes.append((C["mouth"], outer + inner))
    else:
        shapes.append((C["mouth"], [(-16, -48), (16, -48), (16, -43), (-16, -43)]))
    return Part(shapes, {"neck": (0, 0)})


def scarf() -> Part:
    """Neckwear (neckwear=True): a band round the neck with a small knot, on the upper chest just where the
    highest across-the-chest point would put its paw."""
    sc = C["scarf"]
    shapes = [(sc, [(-46, -6), (46, -6), (50, 22), (-50, 22)]), (sc, ellipse(0, 26, 12, 8))]
    return Part(shapes, {"neck": (0, 0)})


def hat_part() -> Part:
    """A hat (hat=True): a dome with a brim, sitting on the top of the head; local frame as the head's (neck at the
    origin), its root where it meets the head."""
    dome = [(56 * math.cos(math.radians(a)), -132 + 36 * math.sin(math.radians(a))) for a in range(180, 361, 10)]
    shapes = [(C["hat"], dome), (C["hat_brim"], [(-66, -136), (66, -136), (66, -124), (-66, -124)])]
    return Part(shapes, {"root": (0, -128)})


def tail_part() -> Part:
    shapes = capsule(C["tail"], (0, 0), 14, (0, 150), 9) + [(C["tail_tip"], ellipse(0, 152, 9, 9))]
    return Part(shapes, {"root": (0, 0)})


def hand(variant) -> Part:
    """Wrist (flat cuff edge) at the origin, fingers down, the thumb on the -x side."""
    hc = C["hand"]
    shapes = [(hc, [(-15, 0), (15, 0), (18, 14), (-18, 14)])]
    pts = {"wrist": (0, 0)}

    def thumb(p0, p1):
        shapes.extend(capsule(hc, p0, 6, p1, 6))
        pts["thumb_tip"] = tip(p0, p1, 6)

    def fist_body():
        shapes.append((hc, ellipse(0, 26, 22, 19)))
        for x, y in ((-11, 42), (0, 44), (11, 42)):
            shapes.append((hc, ellipse(x, y, 7, 6)))

    if variant in (None, "open"):
        shapes.append((hc, ellipse(0, 28, 22 if variant else 21, 21 if variant else 20)))
        spread = 6 if variant == "open" else 0
        side_x, side_r = (12, 36), 5
        for sx in (-1, 1):
            shapes.extend(capsule(hc, (sx * side_x[0], side_x[1]), side_r, (sx * (side_x[0] + spread), 54 + spread / 2), side_r))
        mid_end = (0, 63) if variant == "open" else (0, 59)
        shapes.extend(capsule(hc, (0, 38), 5, mid_end, 5))
        pts["fingertip"] = tip((0, 38), mid_end, 5)
        thumb((-14, 14), (-32, 15))
    elif variant == "fist":
        fist_body()
        thumb((-14, 12), (-28, 8))
    elif variant == "point":
        fist_body()
        shapes.extend(capsule(hc, (-6, 36), 5, (-6, 64), 5))
        pts["fingertip"] = tip((-6, 36), (-6, 64), 5)
        thumb((-14, 14), (-30, 14))
    elif variant == "thumbsup":
        fist_body()
        thumb((-14, 12), (-40, 8))
    elif variant == "grip":
        shapes.append((hc, ellipse(0, 26, 20, 19)))
        shapes.extend(capsule(hc, (14, 40), 7, (-8, 52), 7))
        pts["fingertip"] = tip((14, 40), (-8, 52), 7)
        thumb((-14, 14), (-32, 15))
    else:
        raise ValueError(f"unknown hand variant {variant!r}")
    return Part(shapes, pts, {"wrist": 30})


# ------------------------------------------------------------------ rendering

def draw(img: Image.Image, shapes, to_px) -> None:
    """Draw local-coordinate polygons onto a supersampled image through to_px (local -> final px)."""
    d = ImageDraw.Draw(img)
    for colour, poly in shapes:
        fill = tuple(colour) + ((255,) if img.mode == "RGBA" else ())
        d.polygon([(x * SS, y * SS) for x, y in map(to_px, poly)], fill=fill)


def render_raw(part: Part, scale: float = SCALE):
    """Paint a part at `scale` into its own padded RGBA image. Returns (image, local -> px function)."""
    xs = [x for _, poly in part.shapes for x, _ in poly]
    ys = [y for _, poly in part.shapes for _, y in poly]
    w = int(math.ceil((max(xs) - min(xs)) * scale + 2 * PAD))
    h = int(math.ceil((max(ys) - min(ys)) * scale + 2 * PAD))
    ox, oy = PAD - min(xs) * scale, PAD - min(ys) * scale

    def to_px(p):
        return (p[0] * scale + ox, p[1] * scale + oy)
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    draw(big, part.shapes, to_px)
    return big.resize((w, h), Image.BOX), to_px


# ------------------------------------------------------------------ building

class _Builder:
    def __init__(self, root: Path):
        self.root = root
        self.pieces: dict = {}
        self.truth_pieces: dict = {}
        self.counters: dict = {}

    def piece(self, run, *, role, name, variant, side, part: Part, outputs, facing=None, scale=SCALE,
              painted_as=None):
        """Write the raw piece and its outputs; outputs = [(out_name, folder, file_prefix, mirrored)]."""
        idx = self.counters.get(run, 0)
        self.counters[run] = idx + 1
        key = f"{run}/{idx:02d}"
        img, to_px = render_raw(part, scale)
        w, h = img.size
        rawdir = self.root / "runs" / run
        rawdir.mkdir(parents=True, exist_ok=True)
        img.save(rawdir / f"{CHAR}_{idx:02d}.png")

        raw_px = {n: to_px(p) for n, p in part.points.items()}
        points = {}
        for n, (x, y) in raw_px.items():
            kind = ra.default_kind(role, n)
            at = (x / w, y / h)
            pt = ra.Point(n, at, kind)
            if kind in ("round_end", "opening"):
                pt.snapped, pt.snap = at, "ok"
            if kind == "opening":
                pt.width = part.widths[n] * scale
                pt.depth = DEPTH_RATIO * pt.width
            points[n] = pt

        recs = []
        for out_name, folder, prefix, mirrored in outputs:
            out_img = ImageOps.mirror(img) if mirrored else img
            rel = f"{folder}/{CHAR}_{prefix}{out_name}.png"
            (self.root / folder).mkdir(parents=True, exist_ok=True)
            out_img.save(self.root / rel)
            opts = {n: ((w - x) if mirrored else x, y) for n, (x, y) in raw_px.items()}
            widths, depths = {}, {}
            for n in raw_px:
                kind = ra.default_kind(role, n)
                if kind in ("round_end", "opening"):
                    widths[n] = part.widths[n] * scale
                if kind == "opening":
                    depths[n] = DEPTH_RATIO * widths[n]
            recs.append(ra.Output(name=out_name, file=rel, mirrored=bool(mirrored), rotated=0.0,
                                  points=opts, widths=widths, depths=depths))

        self.pieces[key] = ra.Piece(key=key, role=role, name=name, variant=variant, side=side, points=points,
                                    facing=facing, status="confirmed", confidence=1.0, outputs=recs,
                                    painted_as=painted_as)
        self.truth_pieces[key] = {n: [x, y] for n, (x, y) in raw_px.items()}
        return key


# Which side of the hand each synthetic hand shows. The grip is painted thumb on the same image side as the others
# but is held across the belly with its thumb up, which only a hand showing its BACK can do (rig_hands.hold_pose).
HAND_FACING = {None: "palm", "open": "palm", "fist": "palm", "point": "palm", "thumbsup": "palm", "grip": "back"}


def _hand_mirror(part: Part, variant, side) -> bool:
    thumb = rh.thumb_vector(part.points["wrist"], part.points["thumb_tip"], part.points.get("fingertip"))
    return rh.anatomical_mirror(thumb, HAND_FACING[variant], side)[0]


def make_character(root: Path, *, tail: bool = True, feet: str = "boot", hand_thumb_wrong: bool = False,
                   pose_variants: bool = False, neckwear: bool = False, sleeves: bool = False, hat: bool = False,
                   names: dict | None = None, legs: bool = False) -> Path:
    """Draw the synthetic character under root and return root/annotations.json (see the module doc)."""
    if feet not in ("boot", "hoof"):
        raise ValueError(f"feet must be 'boot' or 'hoof', got {feet!r}")
    nm = {"foot": feet, "neckwear": "scarf", "hat": "hat", "tail": "tail"} | dict(names or {})
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    b = _Builder(root)
    body = ("body", "")
    layers = {k: [] for k in ("back", "leg", "foot", "hips", "torso", "hand", "forearm", "arm", "neckwear", "head",
                              "hat")}
    placed = {}                                   # rest output name -> joint name -> master px

    def to_master(layer, out_name, part, origin, d):
        f = placer(origin, d)
        layers[layer].append((part.shapes, f))
        placed[out_name] = {n: f(p) for n, p in part.points.items()}
        return placed[out_name]

    # torso and hips: upright, moved onto the neck and waist
    t = torso()
    b.piece(BODY_RUN, role="torso", name="torso", variant=None, side="", part=t, outputs=[("torso", *body, False)])
    tm = to_master("torso", "torso", t, NECK, (0.0, 1.0))
    hp = hips()
    b.piece(BODY_RUN, role="hips", name="hips", variant=None, side="", part=hp, outputs=[("hips", *body, False)])
    hm = to_master("hips", "hips", hp, tm["waist"], (0.0, 1.0))
    M = {"neck": tm["neck"], "waist": tm["waist"]}

    # arms: upper arm, forearm, rest hand, each rotated onto the previous joint
    rest_hand = hand(None)
    mirror_rest = {s: _hand_mirror(rest_hand, None, s) for s in "lr"}
    for s in "lr":
        M[f"shoulder_{s}"] = tm[f"shoulder_{s}"]
    for seg, prox, dist_ in (("upperarm", "shoulder", "elbow"), ("forearm", "elbow", "wrist")):
        for s in "lr":
            part = upperarm(LEN[seg]) if seg == "upperarm" else forearm(LEN[seg])
            b.piece(BODY_RUN, role=seg, name=seg, variant=None, side=s, part=part,
                    outputs=[(f"{seg}_{s}", *body, False)])
            if sleeves:                       # on the sheet only: the master wears the whole sleeve (below)
                continue
            pm = to_master("arm" if seg == "upperarm" else "forearm", f"{seg}_{s}", part,
                           M[f"{prox}_{s}"], world_dir(ARM_DEG[seg], s))
            M[f"{dist_}_{s}"] = pm[dist_]
    if sleeves:
        sl = sleeve(LEN["upperarm"], LEN["forearm"])
        b.piece(BODY_RUN, role="arm", name="arm", variant=None, side="either", part=sl, painted_as="l",
                outputs=[(f"arm_{s}", *body, s != "l") for s in "lr"])
        for s in "lr":
            pm = to_master("arm", f"arm_{s}", sl.mirrored() if s != "l" else sl, M[f"shoulder_{s}"],
                           world_dir(ARM_DEG["upperarm"], s))
            M[f"elbow_{s}"], M[f"wrist_{s}"] = pm["elbow"], pm["wrist"]
    b.piece(BODY_RUN, role="hand", name="hand", variant=None, side="either", part=rest_hand, facing="palm",
            outputs=[(f"hand_{s}", *body, mirror_rest[s]) for s in "lr"])
    for s in "lr":
        worn = rest_hand.mirrored() if mirror_rest[s] else rest_hand
        hm_ = to_master("hand", f"hand_{s}", worn, M[f"wrist_{s}"], world_dir(ARM_DEG["hand"], s))
        M[f"fingertip_{s}"] = hm_["fingertip"]

    # legs and feet
    for s in "lr":
        M[f"hip_{s}"], M[f"ankle_{s}"] = hm[f"hip_{s}"], ANKLE[s]
        lg = leg(dist(M[f"hip_{s}"], M[f"ankle_{s}"]))
        b.piece(BODY_RUN, role="leg", name="leg", variant=None, side=s, part=lg, outputs=[(f"leg_{s}", *body, False)])
        to_master("leg", f"leg_{s}", lg, M[f"hip_{s}"], unit(M[f"hip_{s}"], M[f"ankle_{s}"]))
    for s in "lr":
        ft = foot(feet, s)
        b.piece(BODY_RUN, role="foot", name=nm["foot"], variant=None, side=s, part=ft,
                outputs=[(f"{nm['foot']}_{s}", *body, False)])
        fm = to_master("foot", f"{nm['foot']}_{s}", ft, M[f"ankle_{s}"], (0.0, 1.0))
        M["ground"] = (NECK[0], fm["ground"][1])

    # head (base in body/, expressions in face-heads/) and tail
    b.piece(BODY_RUN, role="head", name="head", variant=None, side="", part=head("neutral"),
            outputs=[("head_base", *body, False)])
    to_master("head", "head_base", head("neutral"), M["neck"], (0.0, 1.0))
    if neckwear:
        b.piece(BODY_RUN, role="neckwear", name=nm["neckwear"], variant=None, side="", part=scarf(),
                outputs=[(nm["neckwear"], *body, False)])
        to_master("neckwear", nm["neckwear"], scarf(), M["neck"], (0.0, 1.0))
    if tail:
        tl = tail_part()
        b.piece(BODY_RUN, role="tail", name=nm["tail"], variant=None, side="", part=tl,
                outputs=[(nm["tail"], *body, False)])
        to_master("back", nm["tail"], tl, TAIL_ROOT, world_dir(TAIL_DEG, "l"))
    if hat:
        b.piece(BODY_RUN, role="hat", name=nm["hat"], variant=None, side="", part=hat_part(),
                outputs=[(nm["hat"], *body, False)])
        to_master("hat", nm["hat"], hat_part(), M["neck"], (0.0, 1.0))
    for expr in EXPRESSIONS:
        b.piece(HEADS_RUN, role="head", name="head", variant=expr, side="", part=head(expr),
                outputs=[(f"head_{expr}", "face-heads", "", False)])

    # hand variants: each output mirrored so its thumb meets its hold target (point: wrong on purpose if asked)
    for v in HAND_VARIANTS:
        part = hand(v)
        mirror = {s: _hand_mirror(part, v, s) for s in "lr"}
        if hand_thumb_wrong and v == "point":
            part = part.mirrored()            # thumb painted on the other side, mirrors left as they were
        b.piece(HANDS_RUN, role="hand", name="hand", variant=v, side="either", part=part, facing=HAND_FACING[v],
                outputs=[(f"hand_{s}_{v}", "variants", "", mirror[s]) for s in "lr"])

    # pose variants (their own sheet, at POSE_SCALE): raised sleeves, tiptoe feet, tail up
    if pose_variants:
        for s in "lr":
            b.piece(POSES_RUN, role="upperarm", name="upperarm", variant="raised", side=s, part=raised_sleeve(),
                    outputs=[(f"upperarm_{s}_raised", "variants", "", False)], scale=POSE_SCALE)
        for s in "lr":
            b.piece(POSES_RUN, role="foot", name=nm["foot"], variant="tiptoe", side=s, part=tiptoe(feet, s),
                    outputs=[(f"{nm['foot']}_{s}_tiptoe", "variants", "", False)], scale=POSE_SCALE)
        if tail:
            b.piece(POSES_RUN, role="tail", name=nm["tail"], variant="up", side="", part=tail_up(),
                    outputs=[(f"{nm['tail']}_up", "variants", "", False)], scale=POSE_SCALE)

    # whole legs (two in-between sheets, at POSE_SCALE): squat_1..5, jump_1..5
    if legs:
        for sheet, fracs in LEGS_SHEETS.items():
            for i, f in enumerate(fracs, 1):
                b.piece(LEGS_RUN, role="legs", name="legs", variant=f"{sheet}_{i}", side="",
                        part=legs_part(f, M["ground"][1] - M["waist"][1]),
                        outputs=[(f"legs_{sheet}_{i}", "variants", "", False)], scale=POSE_SCALE)
            for a_, b_ in LEGS_MIDS[sheet]:
                f = MID_SHORT * 0.5 * (fracs[a_ - 1] + fracs[b_ - 1])
                b.piece(LEGS_RUN, role="legs", name="legs", variant=f"{sheet}_{a_}-{b_}", side="",
                        part=legs_part(f, M["ground"][1] - M["waist"][1]),
                        outputs=[(f"legs_{sheet}_{a_}-{b_}", "variants", "", False)], scale=POSE_SCALE)

    # master
    big = Image.new("RGB", (W * SS, H * SS), BG)
    for layer in layers.values():
        for shapes, f in layer:
            draw(big, shapes, f)
    big.resize((W, H), Image.BOX).save(root / "master.png")

    master = ra.Master(image="master.png", points={n: (M[n][0] / W, M[n][1] / H) for n in ra.MASTER_POINTS},
                       hands=json.loads(json.dumps(MASTER_HANDS)), layers={}, status="confirmed")
    ann = ra.Annotations(version=ra.VERSION, character=CHAR, master=master, pieces=b.pieces,
                         path=root / "annotations.json")
    ra.save(ann)

    extra = {"head_neck": list(placed["head_base"]["neck"])}
    if tail:
        extra["tail_root"] = list(placed["tail"]["root"])
    truth = {
        "master_size": [W, H], "scale": SCALE,
        "options": {"tail": tail, "feet": feet, "hand_thumb_wrong": hand_thumb_wrong, "pose_variants": pose_variants,
                    "neckwear": neckwear, "sleeves": sleeves, "legs": legs},
        "master": {n: [M[n][0], M[n][1]] for n in ra.MASTER_POINTS},
        "master_extra": extra,
        "placed": {o: {n: [x, y] for n, (x, y) in pts.items()} for o, pts in placed.items()},
        "pieces": b.truth_pieces,
    }
    (root / "truth.json").write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n")
    TRUTH.clear()
    TRUTH.update(truth)
    return ann.path


if __name__ == "__main__":
    out = make_character(Path(sys.argv[1] if len(sys.argv) > 1 else "synth-character"))
    print(out)
