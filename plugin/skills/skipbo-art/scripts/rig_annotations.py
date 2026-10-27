#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""rig_annotations.py - the annotation file that tells the rig where every part's joints are.

One <char>/annotations.json per character. An agent writes rough joint points on the raw split
pieces (keyed "<split-run-dir>/<NN>"); code snaps them, derives mirror/rotation/file names and
builds the Spine rig from them. This module holds the schema (dataclasses, load/save, validation) and
normalise (snap the rough points, write each piece joint end up and mirrored per side, list the doubts).

Coordinates in the file run 0..1 across the source image (origin top-left, y down). Coordinates in
`outputs` records are pixels of the output image. `_l` is the character's left = the picture's right.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw

import rig_hands
import rig_snap

VERSION = 1

# A piece below this confidence gets its own doubt question at its checkpoint.
CONFIDENCE_DOUBT = 0.7

# --- vocabulary -------------------------------------------------------------------------------

ROLES = {
    "torso": ("neck", "waist"),
    "hips": ("waist", "hip_l", "hip_r"),
    "upperarm": ("shoulder", "elbow"),
    "forearm": ("elbow", "wrist"),
    # A whole sleeve, shoulder to cuff, drawn straight: spine_rig exports it as one weighted mesh over the upper-arm
    # and forearm bones (rig_mesh.py), replacing that side's two-piece arm. The elbow is where it bends.
    "arm": ("shoulder", "elbow", "wrist"),
    "hand": ("wrist", "thumb_tip"),          # plus "fingertip" unless the variant is a fist/thumbsup
    "leg": ("hip", "hem"),
    "foot": ("ankle", "ground"),
    # Whole legs, belt to soles (trousers and boots in one drawing): the in-between drawings of one movement, painted
    # together on one sheet (prompts/spine/legs-inbetweens.txt), variant <sheet>_<n> (squat_1 .. squat_5, jump_1 ..),
    # drawing 1 the rest legs. spine_rig shows them in a `legs` slot at the master's waist instead of the trousers and
    # feet (rig_variants.add_legs). waist: the middle of the belt, where the master's waist point sits on the master's
    # belt; ground: the soles' line, midway between the feet.
    "legs": ("waist", "ground"),
    "tail": ("root",), "ear": ("root",), "antler": ("root",), "horn": ("root",),
    "hat": ("root",), "prop": ("root",),
    "head": ("neck",), "neckwear": ("neck",),
}
# Points a role may carry but does not need. The torso's shoulders: the upper arm hangs from the MASTER's shoulder
# (the single source of truth); a torso shoulder, when annotated, only cross-checks the torso's placement.
OPTIONAL_POINTS = {"torso": ("shoulder_l", "shoulder_r")}
# Names allowed on hand pieces in addition to the hand's required points.
HAND_ONLY_POINTS = ("fingertip",)
# The legs sheets rig_anim knows: squat (stand -> deep crouch: squat, plant_seed, the jump's crouches) and jump
# (stand -> push-off -> tuck). A legs piece's variant is <sheet>_<n>, n from 1 (the rest legs, which sets the sheet's
# scale) left to right, or <sheet>_<a>-<b> (b = a + 1) for an in-between painted from drawings a and b
# (prompts/spine/legs-midpoint.txt); a spare drawing is `ignored`.
LEGS_SHEETS = ("squat", "jump")
LEGS_VARIANT_RE = re.compile(r"^(%s)_([1-9])(?:-([1-9]))?$" % "|".join(LEGS_SHEETS))


def legs_variant(v) -> tuple | None:
    """(sheet, a, b or None) of a legs variant, or None when it isn't one (an in-between needs b = a + 1)."""
    m = LEGS_VARIANT_RE.match(v or "")
    if not m or (m.group(3) and int(m.group(3)) != int(m.group(2)) + 1):
        return None
    return m.group(1), int(m.group(2)), (int(m.group(3)) if m.group(3) else None)
# Hand variants that have no separate fingertip.
NO_FINGERTIP_VARIANTS = ("fist", "thumbsup")

_SIDED = ("shoulder", "elbow", "wrist", "fingertip", "hip", "ankle")
MASTER_POINTS = ("neck", "waist", "ground") + tuple(f"{n}_{s}" for n in _SIDED for s in ("l", "r"))

KINDS = ("round_end", "opening", "point")
SNAP_STATES = ("none", "ok", "failed")
SIDES = ("l", "r", "either", "")
FACINGS = ("palm", "back")
STATUSES = ("proposed", "confirmed", "fixed", "ignored")
# "ignored": a spare piece on the sheet that the rig does not use. Any role (or none), points optional; it is
# never snapped, normalised, doubted or listed as unconfirmed, and `confirm` leaves it as it is.
LAYER_VALUES = {"upperarm": ("under_torso", "over_torso"), "foot": ("over_hips", "under_hips"),
                "hand": ("over_forearm", "under_forearm"),
                # in_hips: one-piece trousers, the cuffed legs composited under the belt-to-crotch hips into one hips
                # piece (rig_trousers.py); the rig is then leg-less, so the master's hip_l / hip_r mark the cuffs
                "leg": ("separate", "in_hips")}
LAYER_ROLES = tuple(LAYER_VALUES)
THUMB_SIDES = ("lateral", "medial")
# A piece's `name` goes into its output files (<character>_<name>[_<side>][_<variant>].png) and is free-form, except
# for these roles: spine_rig keys the skeleton's bones, its animations and the expression heads by them (torso, hips,
# upperarm_l, hand_r, head_base, ...), so their name must be the role, and no other role may use one of these names.
# Every other role (foot, tail, ear, antler, horn, hat, neckwear, prop) takes any name: the rig reads its role from
# the annotations, not from the name.
STRUCTURAL_ROLES = ("torso", "hips", "upperarm", "forearm", "arm", "hand", "leg", "legs", "head")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*(_[A-Za-z0-9-]+)*$")


def role_points(role: str) -> tuple:
    """Every point name a role may carry: required, optional, and the hand's fingertip."""
    return (tuple(ROLES[role]) + tuple(OPTIONAL_POINTS.get(role, ()))
            + (HAND_ONLY_POINTS if role == "hand" else ()))


def _default_kinds() -> dict:
    """Keys are "<role>.<point>". Round ends: limb joints; openings: sockets on hips/foot and cuffs.
    The torso's shoulder sockets are plain points: a torso's side is one contiguous outline (the armhole is
    bounded by colour, not alpha), so nothing there can be snapped or measured; the agent's point is used."""
    # a whole sleeve's round top is a round end; its elbow is a plain point (where it bends)
    round_end = {"upperarm.shoulder", "upperarm.elbow", "forearm.elbow", "leg.hip", "arm.shoulder"}
    # Wrists and the leg hem are painted flat or cuffed, so they snap as openings (edge centre + width).
    opening = {"hips.hip_l", "hips.hip_r", "foot.ankle", "hand.wrist", "forearm.wrist", "leg.hem", "arm.wrist"}
    kinds = {}
    for role in ROLES:
        for name in role_points(role):
            key = f"{role}.{name}"
            kinds[key] = "round_end" if key in round_end else "opening" if key in opening else "point"
    return kinds


DEFAULT_KIND = _default_kinds()


def default_kind(role: str, point: str) -> str:
    return DEFAULT_KIND.get(f"{role}.{point}", "point")


# An opening's inward axis: where its hollow runs, and across which its width is measured.
# Pieces painted upright have a fixed one (hips and feet are never turned): the leg holes open downward, so
# their hollow runs image-up; a boot's or hoof's top opens upward, so its hollow runs image-down (toward a
# toe-side ground point it would lean and miss the rim).
FIXED_INWARD = {"hips.hip_l": (0.0, -1.0), "hips.hip_r": (0.0, -1.0), "foot.ankle": (0.0, 1.0)}
# Other openings point from the opening toward this partner point on the same piece. Without the partner
# (e.g. a fist without a fingertip) the axis points toward the alpha centroid (rig_snap.inward_axis), as it
# does for any opening listed in neither table.
OPENING_PARTNER = {"leg.hem": "hip", "forearm.wrist": "elbow", "hand.wrist": "fingertip", "arm.wrist": "elbow"}


def opening_inward(role: str, name: str, p: tuple, pts: dict):
    """Unit inward axis of opening `name` at p (pixels): FIXED_INWARD, else toward its OPENING_PARTNER point;
    None when neither applies or the partner is missing (or sits on p). pts: point name -> (x, y) pixels."""
    key = f"{role}.{name}"
    if key in FIXED_INWARD:
        return FIXED_INWARD[key]
    partner = OPENING_PARTNER.get(key)
    q = pts.get(partner) if partner else None
    if q is None:
        return None
    dx, dy = q[0] - p[0], q[1] - p[1]
    n = math.hypot(dx, dy)
    return None if n < 1e-9 else (dx / n, dy / n)


# --- data -------------------------------------------------------------------------------------

@dataclass
class Point:
    name: str
    at: tuple                      # (x, y) in 0..1, as annotated; never overwritten by code
    kind: str
    snapped: Optional[tuple] = None  # (x, y) in 0..1, set by snapping
    width: Optional[float] = None    # pixels of the source image (round ends: 2r, or the piece's width across
                                     # its axis at `at` when the snap failed; openings: rim width, or the
                                     # width across the inward axis at `at` when the snap failed)
    depth: Optional[float] = None    # pixels of the source image (openings; 0.35 x width when the snap failed)
    snap: str = "none"               # none | ok | failed


@dataclass
class Output:
    name: str
    file: str
    mirrored: bool
    rotated: float                 # degrees turned to make the piece joint-end-up, as PIL Image.rotate takes them:
                                   # anticlockwise-positive on screen (a 90 turns the top to the left), in [-180, 180]
    points: dict                   # name -> (x, y) pixels of the output image
    widths: dict                   # name -> pixels
    depths: dict                   # name -> pixels


@dataclass
class Piece:
    key: str
    role: str
    name: str                      # base part name used in file names; defaults to the role
    variant: Optional[str]
    side: str                      # l | r | either | ""
    points: dict                   # name -> Point
    facing: Optional[str]          # palm | back | None
    status: str                    # proposed | confirmed | fixed
    confidence: float
    note: str = ""
    mirror: bool = False
    painted_as: Optional[str] = None
    outputs: list = field(default_factory=list)


@dataclass
class Master:
    image: str
    points: dict                   # name -> (x, y) in 0..1
    hands: dict                    # "l"/"r" -> {"thumb_side": ..., "facing": ...}
    layers: dict                   # upperarm -> under_torso | over_torso; foot -> over_hips | under_hips;
                                   # hand -> over_forearm | under_forearm; leg -> separate | in_hips
    status: str
    snapped: dict = field(default_factory=dict)  # name -> (x, y) 0..1 or None (failed); recorded only


@dataclass
class Annotations:
    version: int
    character: str
    master: Master
    pieces: dict                   # key -> Piece
    path: Path


class AnnotationError(ValueError):
    """Raised with every problem found, one per line."""

    def __init__(self, problems):
        if isinstance(problems, str):
            problems = [problems]
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


# --- validation -------------------------------------------------------------------------------
#
# A piece or master with status "proposed" is a draft: it may lack required points (and a draft
# piece may have no role yet). Everything else - unknown names, ranges, kinds, sides, statuses - is
# checked at every status. "confirmed"/"fixed" must satisfy every rule.

def _required_points(piece: Piece) -> tuple:
    req = ROLES[piece.role]
    if piece.role == "hand" and piece.variant not in NO_FINGERTIP_VARIANTS:
        req = req + ("fingertip",)
    return req


def _allowed_points(role: str) -> set:
    return set(role_points(role))


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_xy(xy) -> bool:
    return isinstance(xy, (list, tuple)) and len(xy) == 2 and all(_is_num(v) for v in xy)


def _in_unit(xy) -> bool:
    return _is_xy(xy) and all(0.0 <= v <= 1.0 for v in xy)


MASTER_STATUSES = tuple(s for s in STATUSES if s != "ignored")     # the rig cannot do without its master
# Anatomy: with the arm hanging, a hand showing its palm has the thumb away from the body, one showing its back has
# it toward the body (rig_hands.anatomical_thumb_sign).
THUMB_SIDE_OF_FACING = {"palm": "lateral", "back": "medial"}


def master_hand_conflict(side, hand) -> Optional[str]:
    """The problem when a master hand's thumb_side and facing disagree (lateral <=> palm, medial <=> back), else
    None. A validation error on a confirmed master, a checkpoint doubt on a draft one."""
    ts, fc = hand.get("thumb_side"), hand.get("facing")
    if ts in THUMB_SIDES and fc in FACINGS and THUMB_SIDE_OF_FACING[fc] != ts:
        return (f"hands[{side!r}].thumb_side {ts} disagrees with its facing {fc}: anatomy puts the thumb "
                f"{THUMB_SIDE_OF_FACING[fc]} when the {fc} faces the viewer (lateral = palm, medial = back)")
    return None


def _validate_master(m: Master, errs: list) -> None:
    if m.status not in MASTER_STATUSES:
        errs.append(f"master: status {m.status!r} is not one of {', '.join(MASTER_STATUSES)}")
    if not isinstance(m.points, dict):
        errs.append("master: points must be an object")
    else:
        for name, xy in m.points.items():
            if name not in MASTER_POINTS:
                errs.append(f"master: unknown point {name!r}")
            if not _in_unit(xy):
                errs.append(f"master: point {name!r} {xy!r} must be [x, y] within 0..1")
        if m.status in ("confirmed", "fixed"):
            for name in MASTER_POINTS:
                if name not in m.points:
                    errs.append(f"master: missing required point {name!r}")
    if not isinstance(m.layers, dict):
        errs.append("master: layers must be an object")
    else:
        for role, value in m.layers.items():
            if role not in LAYER_ROLES:
                errs.append(f"master: layers key {role!r} is not one of {', '.join(LAYER_ROLES)}")
            elif value not in LAYER_VALUES[role]:
                errs.append(f"master: layers[{role!r}] = {value!r} is not one of {', '.join(LAYER_VALUES[role])}")
    if not isinstance(m.hands, dict):
        errs.append("master: hands must be an object")
    else:
        for side, hand in m.hands.items():
            if side not in ("l", "r"):
                errs.append(f"master: hands key {side!r} must be l or r")
            if not isinstance(hand, dict):
                errs.append(f"master: hands[{side!r}] must be an object, got {hand!r}")
                continue
            ts = hand.get("thumb_side")
            if ts is not None and ts not in THUMB_SIDES:
                errs.append(f"master: hands[{side!r}].thumb_side {ts!r} is not lateral or medial")
            fc = hand.get("facing")
            if fc is not None and fc not in FACINGS:
                errs.append(f"master: hands[{side!r}].facing {fc!r} is not palm or back")
            if m.status in ("confirmed", "fixed") and master_hand_conflict(side, hand):
                errs.append(f"master: {master_hand_conflict(side, hand)}")
    for name, xy in (m.snapped.items() if isinstance(m.snapped, dict) else ()):
        if name not in MASTER_POINTS or not (xy is None or _in_unit(xy)):
            errs.append(f"master: snapped {name!r} = {xy!r} must be a master point with [x, y] within 0..1 or null")


def _validate_piece(key: str, p: Piece, errs: list) -> None:
    where = f"{key} ({p.role})"
    draft = p.status == "proposed"
    spare = p.status == "ignored"
    known = p.role in ROLES
    if not known and not (draft and p.role == "") and not spare:
        errs.append(f"{where}: unknown role {p.role!r}")
    if p.status not in STATUSES:
        errs.append(f"{where}: status {p.status!r} is not one of {', '.join(STATUSES)}")
    if p.side not in SIDES:
        errs.append(f"{where}: side {p.side!r} is not one of l, r, either, ''")
    if p.facing is not None and p.facing not in FACINGS:
        errs.append(f"{where}: facing {p.facing!r} is not palm or back")
    if p.side == "either" and p.role != "hand" and not p.painted_as and (known or not draft) and not spare:
        errs.append(f"{where}: side 'either' needs role hand or painted_as set")
    if not _is_num(p.confidence) or not 0.0 <= p.confidence <= 1.0:
        errs.append(f"{where}: confidence {p.confidence!r} must be a number within 0..1")
    if known and not spare:
        _validate_name(where, p, errs)
    if p.role == "legs" and not spare and legs_variant(p.variant) is None:
        errs.append(f"{where}: variant {p.variant!r} must be <sheet>_<n> or <sheet>_<n>-<n+1>, sheet one of "
                    f"{', '.join(LEGS_SHEETS)}, n 1-9 (a drawing of a legs sheet, 1 = the rest legs; n-<n+1>: an "
                    "in-between of n and n+1)")
    if not isinstance(p.points, dict):
        errs.append(f"{where}: points must be an object")
        return
    if known and not draft and not spare:
        for name in _required_points(p):
            if name not in p.points:
                errs.append(f"{where}: missing required point {name!r}")
    allowed = _allowed_points(p.role) if known and not spare else None
    for name, pt in p.points.items():
        if allowed is not None and name not in allowed:
            errs.append(f"{where}: unknown point {name!r} (allowed: {', '.join(sorted(allowed))})")
        if not _in_unit(pt.at):
            errs.append(f"{where}: point {name!r} at {pt.at!r} must be [x, y] within 0..1")
        if pt.snapped is not None and not _in_unit(pt.snapped):
            errs.append(f"{where}: point {name!r} snapped {pt.snapped!r} must be [x, y] within 0..1")
        if pt.kind not in KINDS:
            errs.append(f"{where}: point {name!r} kind {pt.kind!r} is not one of {', '.join(KINDS)}")
        if pt.snap not in SNAP_STATES:
            errs.append(f"{where}: point {name!r} snap {pt.snap!r} is not one of {', '.join(SNAP_STATES)}")


def _validate_name(where: str, p: Piece, errs: list) -> None:
    """The piece's name: a structural role's must be the role itself; any other a file-name token that does not end
    in a side (_l / _r: the rig reads the side from the output name) and is not a structural name."""
    name = p.name
    if not isinstance(name, str) or not NAME_RE.match(name) or re.search(r"_(l|r)$", name):
        errs.append(f"{where}: name {name!r} must be letters, digits, '-' and '_' (no path or glob characters), "
                    f"not ending in _l or _r (the side is added to the output names)")
    elif p.role in STRUCTURAL_ROLES and name != p.role:
        errs.append(f"{where}: name {name!r} must be {p.role!r}: {', '.join(STRUCTURAL_ROLES)} names are structural "
                    f"(the rig's bones, animations and expression heads are keyed by them); any name is fine for "
                    f"the other roles (a foot named 'sneaker', a hat named 'beanie')")
    elif name in STRUCTURAL_ROLES and p.role != name:
        errs.append(f"{where}: name {name!r} is reserved for role {name}; give this {p.role} another name")


def _validate_name_roles(ann: Annotations, errs: list) -> None:
    """One name, one role: the rig maps output names to annotated roles."""
    roles: dict = {}
    for p in ann.pieces.values():
        if p.status != "ignored" and p.role in ROLES and isinstance(p.name, str):
            roles.setdefault(p.name, set()).add(p.role)
    for name, rs in sorted(roles.items()):
        if len(rs) > 1:
            errs.append(f"name {name!r} is used by pieces of roles {', '.join(sorted(rs))}: one name, one role")


UNSAFE_NAME_CHARS = "/\\*?[]"      # the character name goes into output file names and a glob


def validate(ann: Annotations) -> list:
    """Every problem with the annotations, one string each. Empty means valid."""
    errs = []
    if ann.version != VERSION:
        errs.append(f"version must be {VERSION}, got {ann.version!r}")
    c = ann.character
    if not isinstance(c, str) or not c.strip() or c in (".", "..") or any(ch in c for ch in UNSAFE_NAME_CHARS):
        errs.append(f"character {c!r} must be a non-empty file-name stem without path separators "
                    f"or glob characters ({' '.join(UNSAFE_NAME_CHARS)})")
    _validate_master(ann.master, errs)
    for key, p in ann.pieces.items():
        _validate_piece(key, p, errs)
    _validate_name_roles(ann, errs)
    return errs


def unconfirmed(ann: Annotations) -> list:
    """Piece keys still `proposed` (sorted), then "master" if the master is."""
    out = sorted(k for k, p in ann.pieces.items() if p.status == "proposed")
    if ann.master.status == "proposed":
        out.append("master")
    return out


# --- json <-> dataclasses ---------------------------------------------------------------------

def _r4(v):
    return round(float(v), 4)


def _r2(v):
    return round(float(v), 2)


def _xy4(xy):
    return [_r4(xy[0]), _r4(xy[1])]


def _xy2(xy):
    return [_r2(xy[0]), _r2(xy[1])]


def _tup(xy):
    return (float(xy[0]), float(xy[1]))


def _point_to_json(pt: Point) -> dict:
    d = {"at": _xy4(pt.at), "kind": pt.kind}
    if pt.snapped is not None:
        d["snapped"] = _xy4(pt.snapped)
    if pt.width is not None:
        d["width"] = _r2(pt.width)
    if pt.depth is not None:
        d["depth"] = _r2(pt.depth)
    if pt.snap != "none":
        d["snap"] = pt.snap
    return d


def _output_to_json(o: Output) -> dict:
    return {"name": o.name, "file": o.file, "mirrored": bool(o.mirrored), "rotated": _r2(o.rotated),
            "points": {k: _xy2(v) for k, v in o.points.items()},
            "widths": {k: _r2(v) for k, v in o.widths.items()},
            "depths": {k: _r2(v) for k, v in o.depths.items()}}


def _piece_to_json(p: Piece) -> dict:
    d = {"role": p.role, "side": p.side,
         "points": {k: _point_to_json(v) for k, v in p.points.items()},
         "status": p.status, "confidence": _r4(p.confidence), "outputs": [_output_to_json(o) for o in p.outputs]}
    if p.name != p.role:
        d["name"] = p.name
    if p.variant is not None:
        d["variant"] = p.variant
    if p.facing is not None:
        d["facing"] = p.facing
    if p.note:
        d["note"] = p.note
    if p.mirror:
        d["mirror"] = True
    if p.painted_as is not None:
        d["painted_as"] = p.painted_as
    return d


def to_json(ann: Annotations) -> dict:
    m = ann.master
    master = {"image": m.image, "points": {k: _xy4(v) for k, v in m.points.items()},
              "hands": m.hands, "layers": m.layers, "status": m.status}
    if m.snapped:
        master["snapped"] = {k: None if v is None else _xy4(v) for k, v in m.snapped.items()}
    return {"version": ann.version, "character": ann.character, "master": master,
            "pieces": {k: _piece_to_json(p) for k, p in ann.pieces.items()}}


def _point_from_json(role: str, name: str, d: dict) -> Point:
    # A known role fixes its points' kinds (a stored "kind" is ignored: the file may predate a kind change,
    # e.g. the torso's shoulders, once openings, are plain points); only an unknown role keeps what is stored.
    kind = default_kind(role, name) if role in ROLES else d.get("kind") or default_kind(role, name)
    return Point(name=name, at=_tup(d["at"]), kind=kind,
                 snapped=_tup(d["snapped"]) if d.get("snapped") is not None else None,
                 width=d.get("width"), depth=d.get("depth"), snap=d.get("snap", "none"))


def _output_from_json(d: dict) -> Output:
    return Output(name=d["name"], file=d["file"], mirrored=bool(d["mirrored"]), rotated=float(d["rotated"]),
                  points={k: _tup(v) for k, v in d.get("points", {}).items()},
                  widths=dict(d.get("widths", {})), depths=dict(d.get("depths", {})))


def _piece_from_json(key: str, d: dict) -> Piece:
    role = d["role"]
    return Piece(key=key, role=role, name=d.get("name") or role, variant=d.get("variant"),
                 side=d.get("side", ""),
                 points={n: _point_from_json(role, n, pd) for n, pd in d.get("points", {}).items()},
                 facing=d.get("facing"), status=d.get("status", "proposed"),
                 confidence=float(d.get("confidence", 0.0)), note=d.get("note", ""),
                 mirror=bool(d.get("mirror", False)), painted_as=d.get("painted_as"),
                 outputs=[_output_from_json(o) for o in d.get("outputs", [])])


def from_json(raw: dict, path: Path) -> Annotations:
    m = raw["master"]
    master = Master(image=m["image"], points={k: _tup(v) for k, v in m.get("points", {}).items()},
                    hands=m.get("hands", {}), layers=m.get("layers", {}), status=m.get("status", "proposed"),
                    snapped={k: None if v is None else _tup(v) for k, v in m.get("snapped", {}).items()})
    pieces = {k: _piece_from_json(k, d) for k, d in raw.get("pieces", {}).items()}
    return Annotations(version=raw.get("version", 0), character=raw["character"], master=master,
                       pieces=pieces, path=path)


def load(path) -> Annotations:
    """Read and validate an annotations file. Raises AnnotationError listing every problem."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise AnnotationError(f"{path}: cannot read annotations ({e})")
    try:
        ann = from_json(raw, path)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
        raise AnnotationError(f"{path}: malformed annotations ({type(e).__name__}: {e})")
    try:
        errs = validate(ann)
    except Exception as e:  # unexpected structure that the type checks missed
        raise AnnotationError(f"{path}: malformed annotations ({type(e).__name__}: {e})")
    if errs:
        raise AnnotationError(errs)
    return ann


def save(ann: Annotations, path=None) -> None:
    """Write the file with sorted keys; normalised floats to 4 decimals, pixels to 2."""
    path = Path(path) if path is not None else ann.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_json(ann), indent=2, sort_keys=True) + "\n")


# --- piece files ------------------------------------------------------------------------------

def piece_image(ann: Annotations, key: str) -> Path:
    """Resolve "<split-run-dir>/<NN>" to <annotations dir>/runs/<split-run-dir>/*_<NN>.png."""
    run_dir, _, idx = key.rpartition("/")
    if not run_dir or not idx.isdigit():
        raise AnnotationError(f"{key}: piece key must look like '<split-run-dir>/<NN>'")
    pattern = str(Path(glob.escape(str(ann.path.parent / "runs" / run_dir))) / f"*_{int(idx):02d}.png")
    found = sorted(glob.glob(pattern))
    if not found:
        raise AnnotationError(f"{key}: no piece image matches {pattern}")
    if len(found) > 1:
        raise AnnotationError(f"{key}: {len(found)} piece images match {pattern}: "
                              + ", ".join(Path(f).name for f in found))
    return Path(found[0])


# --- snap, normalise, doubts ------------------------------------------------------------------
#
# snap_all fills each point's snapped/width/depth/snap from its piece image. normalise turns the
# arm, leg and hand pieces joint end up (feet are not turned), mirrors each piece per side (hands by anatomy: their painted side, rig_hands.anatomical_mirror), writes
# <dir>/<character>_<output>.png and records the result in Piece.outputs. doubts lists the questions
# for the checkpoint. Pixel coordinates here are continuous: pixel i spans [i, i + 1).

OUT_DIRS = ("body", "variants", "face-heads")
# Proximal and distal point of each piece normalise turns, so proximal -> distal points straight down.
# A hand without a fingertip (fist, thumbsup) uses its centroid, and turns by a multiple of 90 degrees.
ROTATE_AXIS = {"upperarm": ("shoulder", "elbow"), "forearm": ("elbow", "wrist"), "arm": ("shoulder", "wrist"),
               "leg": ("hip", "hem"),
               "hand": ("wrist", "fingertip")}
MASTER_SNAP = tuple(f"{n}_{s}" for n in ("shoulder", "elbow", "wrist", "hip", "ankle") for s in ("l", "r"))
ALPHA_MIN = 128          # alpha at or above this counts as opaque
MASTER_BG_TOL = 24       # a master without transparency: summed RGB distance from the corner colour
HAND_TILT_DOUBT = 30.0   # a hand without a fingertip left tilted more than this after its quarter turn is a doubt
ROTATE_MIN_DEG = 0.5     # smaller turns are skipped: resampling would only soften the piece
SNAP_MAX_MOVE = 0.10     # a snap landing further than this x the piece's own width from `at` is rejected
OPENING_DEPTH_FRAC = 0.35  # an opening that did not snap gets depth = this x its width (snap_opening's default)


def _alpha(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGBA"))[..., 3] >= ALPHA_MIN


def _master_alpha(img: Image.Image) -> np.ndarray:
    a = np.asarray(img.convert("RGBA")).astype(int)
    if (a[..., 3] < 255).any():
        return a[..., 3] >= ALPHA_MIN
    return np.abs(a[..., :3] - a[0, 0, :3]).sum(-1) > MASTER_BG_TOL


def _snap_px(alpha: np.ndarray, kind: str, p: tuple, inward=None):
    """Snap the continuous pixel point p; (at, width, depth) or None. rig_snap puts pixel centres on integers.
    An opening uses `inward` (opening_inward), else the direction toward the alpha centroid."""
    q = (p[0] - 0.5, p[1] - 0.5)
    radius = rig_snap.search_radius(alpha)
    if kind == "round_end":
        r = rig_snap.snap_round_end(alpha, q, radius)
    else:
        r = rig_snap.snap_opening(alpha, q, inward or rig_snap.inward_axis(alpha, q), radius)
    return None if r is None else ((r.at[0] + 0.5, r.at[1] + 0.5), r.width, r.depth)


def _unit_xy(xy, w, h) -> tuple:
    return (min(max(xy[0] / w, 0.0), 1.0), min(max(xy[1] / h, 0.0), 1.0))


def snap_all(ann: Annotations) -> None:
    """Snap every round_end/opening point of every piece; record the master's limb joints as round ends."""
    for key, p in ann.pieces.items():
        todo = [pt for pt in p.points.values() if pt.kind in ("round_end", "opening")]
        if not todo or p.status == "ignored":
            continue
        img = Image.open(piece_image(ann, key))
        alpha, (w, h) = _alpha(img), img.size
        max_move = SNAP_MAX_MOVE * rig_snap.piece_width(alpha)
        rough = {n: (q.at[0] * w, q.at[1] * h) for n, q in p.points.items()}    # partners by their `at`
        for pt in todo:
            p0 = (pt.at[0] * w, pt.at[1] * h)
            inward = opening_inward(p.role, pt.name, p0, rough) if pt.kind == "opening" else None
            res = _snap_px(alpha, pt.kind, p0, inward)
            # e.g. a socket painted inside the silhouette: the snap runs to the outline, keep the rough point
            if res is None or math.dist(res[0], p0) > max_move:
                pt.snapped, pt.width, pt.depth, pt.snap = None, None, None, "failed"
                # still give it a width (and an opening its depth), for variant scaling and narrowing
                q = (p0[0] - 0.5, p0[1] - 0.5)          # rig_snap puts pixel centres on integers
                if pt.kind == "round_end":
                    pt.width = rig_snap.cross_width(alpha, q)
                elif pt.kind == "opening":
                    pt.width = rig_snap.opening_cross_width(alpha, q, inward or rig_snap.inward_axis(alpha, q))
                    pt.depth = None if pt.width is None else OPENING_DEPTH_FRAC * pt.width
            else:
                pt.snapped, pt.width, pt.depth, pt.snap = _unit_xy(res[0], w, h), res[1], res[2], "ok"
    path = ann.path.parent / ann.master.image
    if not path.exists():
        raise AnnotationError(f"master: image {path} not found")
    img = Image.open(path)
    alpha, (w, h) = _master_alpha(img), img.size
    ann.master.snapped = {}
    for name in MASTER_SNAP:
        if name in ann.master.points:
            x, y = ann.master.points[name]
            res = _snap_px(alpha, "round_end", (x * w, y * h))
            ann.master.snapped[name] = None if res is None else _unit_xy(res[0], w, h)


def _px(pt: Point, w: int, h: int) -> tuple:
    xy = pt.snapped if pt.snap == "ok" and pt.snapped is not None else pt.at
    return (xy[0] * w, xy[1] * h)


def _turn(xy, deg, size, new_size) -> tuple:
    """Where xy lands after Image.rotate(deg, expand=True) (anticlockwise on screen, about the centre)."""
    t = math.radians(deg)
    dx, dy = xy[0] - size[0] / 2, xy[1] - size[1] / 2
    return (dx * math.cos(t) + dy * math.sin(t) + new_size[0] / 2,
            -dx * math.sin(t) + dy * math.cos(t) + new_size[1] / 2)


def _turn_deg(p: Piece, img: Image.Image, pts: dict):
    """(wanted, applied) degrees to put the piece joint-end-up, or None when the axis is missing.
    `wanted` follows proximal -> distal exactly. `applied` equals it, except for a hand without a fingertip:
    the thumb pulls the centroid off the hand's axis, so that hand turns by quarter turns only."""
    if p.role not in ROTATE_AXIS:
        return None
    prox, dist = ROTATE_AXIS[p.role]
    a, b = pts.get(prox), pts.get(dist)
    centroid = b is None and p.role == "hand"
    if centroid:
        ys, xs = np.nonzero(_alpha(img))
        b = (xs.mean() + 0.5, ys.mean() + 0.5) if len(xs) else None
    if a is None or b is None:
        return None
    deg = (math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) - 90.0 + 180.0) % 360.0 - 180.0
    applied = deg
    if centroid:
        applied = float(90 * round(deg / 90)) if abs(deg) < 135 else 180.0
    return deg, applied


def _upright(p: Piece, img: Image.Image, pts: dict):
    """Rotate a limb piece so proximal -> distal points straight down. Returns (image, degrees, points)."""
    turn = _turn_deg(p, img, pts)
    if turn is None or abs(turn[1]) < ROTATE_MIN_DEG:
        return img, 0.0, pts
    deg = turn[1]
    # premultiplied alpha, so the transparent surround does not bleed dark into the edges
    out = img.convert("RGBa").rotate(deg, resample=Image.BICUBIC, expand=True).convert("RGBA")
    return out, deg, {n: _turn(xy, deg, img.size, out.size) for n, xy in pts.items()}


def _sides(p: Piece) -> tuple:
    return ("l", "r") if p.side == "either" else (p.side,)


def _hand_rule(ann: Annotations, p: Piece, side: str, pts: dict):
    """(mirror, margin) for a joint-end-up hand, or None when no rule can apply. pts: joint-end-up points.

    A hand with a `facing` is mirrored by anatomy (rig_hands.anatomical_mirror; margin = the thumb's sideways share,
    unclear under THUMB_SIDE_MIN). Without one, the legacy thumb-target rule (rig_hands.choose_mirror; margin in
    degrees, unclear under MIRROR_AMBIGUOUS) - a doubt either way ("facing missing"). Judge margins with
    _mirror_unclear."""
    if side not in ("l", "r") or "wrist" not in pts or "thumb_tip" not in pts:
        return None
    if p.facing in FACINGS:
        thumb = rig_hands.thumb_vector(pts["wrist"], pts["thumb_tip"], pts.get("fingertip"))
        return rig_hands.anatomical_mirror(thumb, p.facing, side)
    rest = p.variant in (None, "rest")
    if not rest and p.variant not in rig_hands.THUMB_TARGET:
        return None
    target = ann.master.hands.get(side, {}).get("thumb_side") if rest else None
    if rest and target is None:
        return None
    thumb = rig_hands.thumb_vector(pts["wrist"], pts["thumb_tip"], pts.get("fingertip"))
    return rig_hands.choose_mirror(thumb, p.variant, side, rest_target=target)


def _mirror_unclear(p: Piece, margin: float) -> bool:
    """Is _hand_rule's margin too small to trust the mirror (each rule has its own unit)?"""
    if p.facing in FACINGS:
        # Mostly redundant: thumb_vector already returns (0, 0) - margin 0 - for a thumb tip within THUMB_SIDE_MIN of
        # the hand's axis, and what it returns lies square to that axis. It still catches a thumb that runs mostly
        # along the image's vertical when the fingertip axis is not image-down (a hand left tilted after normalise).
        return margin < rig_hands.THUMB_SIDE_MIN
    return margin < rig_hands.MIRROR_AMBIGUOUS


def _out_name(p: Piece, side: str) -> str:
    if p.role == "head":
        return f"{p.name}_{p.variant or 'base'}"
    return "_".join(x for x in (p.name, side, p.variant) if x)


def _out_dir(p: Piece) -> str:
    return "body" if p.variant is None else "face-heads" if p.role == "head" else "variants"


def normalise(ann: Annotations) -> list:
    """Write every annotated piece's outputs and fill Piece.outputs (draft pieces with no role and ignored
    pieces are skipped).
    Deletes stale <character>_*.png in body/, variants/ and face-heads/. Returns doubt strings for
    hand mirrors whose thumb side is unclear, chosen without a facing (legacy rule) or without any rule."""
    root, notes, jobs = ann.path.parent, [], []
    for key, p in ann.pieces.items():
        if p.status == "ignored":
            p.outputs = []                 # a spare piece writes nothing (its stale files go with the sweep below)
        if not p.role or p.status == "ignored":
            continue
        src = Image.open(piece_image(ann, key)).convert("RGBA")
        w, h = src.size
        img, deg, pts = _upright(p, src, {n: _px(pt, w, h) for n, pt in p.points.items()})
        # a point that did not snap still has the width (and an opening its depth) snap_all measured at `at`
        measured = {n: pt for n, pt in p.points.items() if pt.snap in ("ok", "failed")}
        widths = {n: pt.width for n, pt in measured.items() if pt.width is not None}
        depths = {n: pt.depth for n, pt in measured.items() if pt.depth is not None}
        outs = []
        for side in _sides(p):
            name = _out_name(p, side)
            if p.role == "hand":
                rule = _hand_rule(ann, p, side, pts)
                if rule is None:
                    mirror = p.mirror
                    notes.append(f"{key} ({name}): no thumb rule applies (side, thumb_tip, variant or the "
                                 f"master's thumb_side missing); mirror={mirror} as annotated")
                else:
                    mirror, margin = rule
                    if p.facing not in FACINGS:
                        notes.append(f"{key} ({name}): facing missing, mirrored by the legacy thumb-target rule "
                                     f"(mirror={mirror}); say which side of the hand is painted (palm or back)")
                    if _mirror_unclear(p, margin):
                        notes.append(f"{key} ({name}): mirror choice is ambiguous, the thumb's side is unclear "
                                     f"(margin {margin:.2f})")
            elif p.side == "either":
                mirror = side != p.painted_as
            else:
                mirror = p.mirror
            nw = img.size[0]
            outs.append(Output(name=name, file=f"{_out_dir(p)}/{ann.character}_{name}.png", mirrored=mirror,
                               rotated=deg, points={n: ((nw - x) if mirror else x, y) for n, (x, y) in pts.items()},
                               widths=dict(widths),
                               depths=dict(depths)))
        jobs.append((p, img, outs))

    files = [o.file for _, _, outs in jobs for o in outs]
    dupes = sorted({f for f in files if files.count(f) > 1})
    if dupes:
        raise AnnotationError([f"two pieces write {f}" for f in dupes])
    for d in OUT_DIRS:
        for f in (root / d).glob(f"{glob.escape(ann.character)}_*.png"):
            if f"{d}/{f.name}" not in files:
                f.unlink()
    for p, img, outs in jobs:
        for o in outs:
            (root / o.file).parent.mkdir(parents=True, exist_ok=True)
            (img.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if o.mirrored else img).save(root / o.file)
        p.outputs = outs
    return notes


def _doubt(key, reason, options) -> dict:
    return {"key": key, "reason": reason, "options": list(options)}


def _hand_leftover_tilt(ann: Annotations, key: str, p: Piece):
    """Degrees a fingertip-less hand is still off its wrist -> centroid axis after the quarter turn, else None."""
    if p.role != "hand" or "fingertip" in p.points or not p.outputs:
        return None
    img = Image.open(piece_image(ann, key)).convert("RGBA")
    w, h = img.size
    turn = _turn_deg(p, img, {n: _px(pt, w, h) for n, pt in p.points.items()})
    return None if turn is None else (turn[0] - turn[1] + 180.0) % 360.0 - 180.0


def doubts(ann: Annotations) -> list:
    """Checkpoint questions, by piece key: low confidence (one per piece, naming its failed snaps), ambiguous
    hand mirrors (read from the outputs, so run normalise first), hands without a facing, rest hands facing other
    than the master's, gesture hands no pose can show thumb up (rig_hands.hold_pose), and - keyed "master" - a draft
    master hand whose thumb_side and facing disagree (on a confirmed master that is a validation error).
    A failed snap on a piece with confidence >= CONFIDENCE_DOUBT is not a question: see snap_failed()."""
    out = []
    for key in sorted(ann.pieces):
        p = ann.pieces[key]
        if p.status == "ignored":
            continue
        label = f"piece {key} ({' · '.join(x for x in (p.role, p.variant, p.side) if x) or 'no role'})"
        if p.confidence < CONFIDENCE_DOUBT:
            # a failed snap on a confident piece is no question (check lists it under snap_failed); on a doubtful
            # piece it goes into that piece's one question
            failed = [f"{p.points[n].kind} point {n!r}" for n in sorted(p.points) if p.points[n].snap == "failed"]
            more = f"; {', '.join(failed)} did not snap, the rough point is kept" if failed else ""
            out.append(_doubt(key, f"{label}: confidence {p.confidence:.2f} is below {CONFIDENCE_DOUBT}{more}",
                              ["correct as annotated", "needs a fix"]))
        if p.role != "hand":
            continue
        tilt = _hand_leftover_tilt(ann, key, p)
        if tilt is not None and abs(tilt) > HAND_TILT_DOUBT:
            out.append(_doubt(key, f"{label}: hand turned only to the nearest quarter; leftover tilt "
                                   f"{abs(tilt):.0f}°", ["looks right", "re-annotate wrist"]))
        if p.facing not in FACINGS:
            out.append(_doubt(key, f"{label}: facing missing - the mirror follows the legacy thumb-target rule, "
                                   "which can show an impossible hand; this hand shows its", ["palm", "back"]))
        if p.variant in (None, "rest"):
            blind = [s for s in _sides(p)
                     if s in ("l", "r") and ann.master.hands.get(s, {}).get("thumb_side") is None]
            if "thumb_tip" not in p.points and any(s in ("l", "r") for s in _sides(p)):
                out.append(_doubt(key, f"{label}: the hand has no thumb_tip, so the mirror stays as annotated "
                                       f"(mirror={p.mirror}); worn at rest, the thumb points",
                                  ["away from body", "towards body"]))
            elif blind and p.facing not in FACINGS:
                out.append(_doubt(key, f"{label}: the master's {blind[0]} hand has no thumb_side, so the mirror "
                                       f"stays as annotated (mirror={p.mirror}); worn at rest, the thumb points",
                                  ["away from body", "towards body"]))
        rules = [_hand_rule(ann, p, side, o.points) for side, o in zip(_sides(p), p.outputs)]
        margins = [r[1] for r in rules if r]       # a flip does not change the margin
        if margins and _mirror_unclear(p, min(margins)):
            out.append(_doubt(key, f"{label}: the thumb's side is unclear (mirror margin {min(margins):.2f}); "
                                   "worn at rest, the thumb points", ["away from body", "towards body"]))
        if p.variant in (None, "rest") and p.facing:
            wrong = [s for s in _sides(p) if s in ("l", "r") and ann.master.hands.get(s, {}).get("facing") != p.facing]
            if wrong:
                shown = ann.master.hands.get(wrong[0], {}).get("facing")
                out.append(_doubt(key, f"{label}: shows the {p.facing} but the master's {wrong[0]} hand "
                                       + (f"shows the {shown}" if shown else "has no facing") + "; this hand shows its",
                                  ["palm", "back"]))
        for side, o in zip(_sides(p), p.outputs):     # a gesture that cannot show this hand's thumb up
            if side not in ("l", "r") or "wrist" not in o.points or "thumb_tip" not in o.points:
                continue
            thumb = rig_hands.thumb_vector(o.points["wrist"], o.points["thumb_tip"], o.points.get("fingertip"))
            h = rig_hands.hold_pose(p.variant, thumb, side)
            if h is not None and h["ok"] is False:
                out.append(_doubt(key, f"{label}: no {h['gesture']} pose shows the {p.facing or 'painted'} {o.name} "
                                       f"with its thumb up (best {min(h['errors'].values()):.0f}° off); the rig keeps "
                                       f"the {h['pose']} pose. This hand shows its", ["palm", "back"]))
                break
    for side in sorted(ann.master.hands if isinstance(ann.master.hands, dict) else ()):
        hand = ann.master.hands[side]
        problem = master_hand_conflict(side, hand) if isinstance(hand, dict) else None
        if problem and ann.master.status not in ("confirmed", "fixed"):     # confirmed: a validation error
            out.append(_doubt("master", f"master: {problem}; the master's {side} hand shows its",
                              ["palm (thumb lateral)", "back (thumb medial)"]))
    return out


def snap_failed(ann: Annotations) -> list:
    """Sorted "<key>:<point>" for every point whose snap failed, on pieces that have a role and are not
    ignored (a role-less draft's rough top/bottom points are not joints yet)."""
    return sorted(f"{k}:{n}" for k, p in ann.pieces.items() if p.role and p.status != "ignored"
                  for n, pt in p.points.items() if pt.snap == "failed")


# --- command line -----------------------------------------------------------------------------
#
#   propose <char-dir>/runs/<run> --annotations <file> [--character C] [--master PNG]
#   check <file> [--sheet <run>] [--jev]
#   confirm <file> --sheet <run> | --master
#
# Exit codes: 0 done, 2 the annotations (or the request) are wrong; the problems go to stderr.

ANN_DIR = "annotations"
SHEET_CELL = 220
SHEET_COLS = 5
SHEET_LABEL_H = 34


def _piece_files(run_dir: Path) -> list:
    """[(index, path)] of the split pieces in a run dir (files named *_<NN>.png), by index."""
    found = []
    for f in run_dir.glob("*.png"):
        m = re.search(r"_(\d+)$", f.stem)
        if m:
            found.append((int(m.group(1)), f))
    return sorted(found)


def _rough_points(img: Image.Image) -> dict:
    """Round-end candidates "top" (the end with the smaller y) and "bottom", as Points in 0..1."""
    w, h = img.size
    ys, xs = np.nonzero(_alpha(img))
    if len(xs) < 3:
        return {}
    a, b, _ = rig_snap.axis_ends(np.stack([xs + 0.5, ys + 0.5], axis=1).astype(float))
    top, bottom = (a, b) if a[1] <= b[1] else (b, a)
    return {name: Point(name, (min(1.0, max(0.0, float(p[0]) / w)), min(1.0, max(0.0, float(p[1]) / h))),
                        "round_end")
            for name, p in (("top", top), ("bottom", bottom))}


def _numbered_sheet(files: list, out: Path) -> Path:
    """Contact sheet of the split pieces on grey: each cell labelled with its index and pixel size."""
    import rig_overlay as ro            # imported here: rig_overlay imports this module
    cols = max(1, min(SHEET_COLS, len(files)))
    rows = max(1, -(-len(files) // cols))
    cell_h = SHEET_LABEL_H + SHEET_CELL
    canvas = Image.new("RGB", (cols * SHEET_CELL, rows * cell_h), ro.PAPER)
    d = ImageDraw.Draw(canvas)
    for i, (idx, f) in enumerate(files):
        ox, oy = (i % cols) * SHEET_CELL, (i // cols) * cell_h
        img = Image.open(f).convert("RGBA")
        d.rectangle([ox, oy + SHEET_LABEL_H, ox + SHEET_CELL - 1, oy + cell_h - 1], fill=ro.BG)
        s = min((SHEET_CELL - 8) / img.width, (SHEET_CELL - 8) / img.height)
        small = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
        canvas.paste(small, (ox + (SHEET_CELL - small.width) // 2,
                             oy + SHEET_LABEL_H + (SHEET_CELL - small.height) // 2), small)
        d.text((ox + 6, oy + 4), f"{idx:02d}", fill=ro.INK, font=ro.font(20))
        d.text((ox + 44, oy + 9), f"{img.width}x{img.height} px", fill=ro.INK, font=ro.font(14))
        d.rectangle([ox, oy, ox + SHEET_CELL - 1, oy + cell_h - 1], outline=(150, 150, 156))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def _master_rel(arg: str, char_dir: Path) -> str:
    p = Path(arg)
    if p.is_absolute() or (p.exists() and not (char_dir / p).exists()):
        return os.path.relpath(p.resolve(), char_dir.resolve())
    return str(p)


def cmd_propose(args) -> int:
    path = Path(args.annotations)
    char_dir = path.parent
    run_dir = Path(args.run_dir)
    run = run_dir.name
    if not run_dir.is_dir() or run_dir.resolve().parent != (char_dir / "runs").resolve():
        raise AnnotationError(f"{run_dir}: must be a directory directly under {char_dir / 'runs'}")
    files = _piece_files(run_dir)
    if not files:
        raise AnnotationError(f"{run_dir}: no split pieces (*_<NN>.png) found")
    if path.exists():
        ann = load(path)
    else:
        if not args.character:
            raise AnnotationError(f"{path} does not exist: --character is required to create it")
        ann = Annotations(version=VERSION, character=args.character, path=path, pieces={},
                          master=Master(image=_master_rel(args.master, char_dir), points={}, hands={}, layers={},
                                        status="proposed"))
    added = 0
    for idx, f in files:
        key = f"{run}/{idx:02d}"
        if key in ann.pieces:           # annotated (or already drafted) pieces are never touched
            continue
        ann.pieces[key] = Piece(key=key, role="", name="", variant=None, side="",
                                points=_rough_points(Image.open(f).convert("RGBA")), facing=None,
                                status="proposed", confidence=0)
        added += 1
    save(ann, path)
    sheet = _numbered_sheet(files, char_dir / ANN_DIR / f"{run}_numbered.png")
    print(f"{path}: {added} piece(s) drafted, {len(files) - added} already present")
    print(f"numbered contact sheet: {sheet}")
    return 0


def _runs(ann: Annotations) -> list:
    return sorted({k.rpartition("/")[0] for k in ann.pieces})


def _in_run(key: str, run: str) -> bool:
    return key.startswith(run + "/")


def cmd_check(args) -> int:
    import rig_overlay as ro            # imported here: rig_overlay imports this module
    ann = load(args.file)
    runs = _runs(ann)
    if args.sheet is not None and args.sheet not in runs:
        raise AnnotationError(f"no pieces for sheet {args.sheet!r}; sheets: {', '.join(runs) or 'none'}")
    if not (ann.path.parent / ann.master.image).is_file():
        raise AnnotationError(f"master image {ann.path.parent / ann.master.image} not found")
    snap_all(ann)
    notes = normalise(ann)
    save(ann)
    out_dir = ann.path.parent / ANN_DIR
    for n in notes:
        print(f"note: {n}")
    print(f"master overlay: {ro.render_master_overlay(ann, out_dir / 'master_overlay.png')}")
    worn = {}
    for run in ([args.sheet] if args.sheet else runs):
        print(f"{run} overlay: {ro.render_sheet_overlay(ann, run, out_dir / f'{run}_overlay.png')}")
        if any(p.role in ro.WORN_ROLES and p.status != "ignored" and _in_run(k, run) for k, p in ann.pieces.items()):
            strip, verdicts = ro.render_worn_strip(ann, run, out_dir / f"{run}_worn.png")
            print(f"{run} worn strip: {strip}")
            worn.update({name: ok for name, ok in verdicts})
    # a role-less draft is already listed in "unconfirmed"; its confidence-0 doubt would only be noise
    ds = [d for d in doubts(ann) if d["key"] == "master" or ann.pieces[d["key"]].role
          or ann.pieces[d["key"]].status != "proposed"]
    pending = unconfirmed(ann)
    failed = snap_failed(ann)
    if args.sheet:
        ds = [d for d in ds if d["key"] == "master" or _in_run(d["key"], args.sheet)]
        pending = [k for k in pending if k == "master" or _in_run(k, args.sheet)]
        failed = [f for f in failed if _in_run(f, args.sheet)]
    result = {"doubts": ds, "worn": worn, "unconfirmed": pending, "snap_failed": failed}
    if args.jev:
        result["jev"] = _jev_facing(ann, args.sheet, ds)
    print(json.dumps(result, sort_keys=True))
    return 0


def _jev_facing(ann: Annotations, sheet, ds: list) -> dict:
    """check --jev: score the hand pieces' palm/back with jev_facing (checkpoint 3) and add a doubt to ds for each
    confident call that disagrees with the annotated facing. Without a key, or when Jev fails, the check goes on
    without it. Returns {key: {"score", "facing"}} (or {"skipped": reason})."""
    import jev_client
    import jev_facing
    if not jev_client.available():
        print(jev_client.SKIP)
        return {"skipped": "no TYPESAFE_API_KEY"}
    keys = [k for k, p in sorted(ann.pieces.items()) if p.role == "hand" and p.status != "ignored"
            and (sheet is None or _in_run(k, sheet))]
    try:
        res = jev_facing.score_pieces({k: piece_image(ann, k) for k in keys},
                                      cache=ann.path.parent / ANN_DIR / "jev_cache.jsonl")
    except Exception as e:              # noqa: BLE001 - an optional reviewer: report it, never block the check
        print(f"jev: skipped ({e})")
        return {"skipped": str(e)}
    for k in keys:
        p = ann.pieces[k]
        q = jev_facing.facing_doubt(p.facing, res.get(k))
        if q:
            label = f"piece {k} ({' · '.join(x for x in (p.role, p.variant, p.side) if x)})"
            ds.append(_doubt(k, f"{label}: {q}", ["palm", "back"]))
    return {k: {"score": r["score"], "facing": r["facing"]} for k, r in res.items()}


def cmd_confirm(args) -> int:
    ann = load(args.file)
    if args.master:
        if ann.master.status == "proposed":
            ann.master.status = "confirmed"
        what = "master"
    else:
        keys = sorted(k for k in ann.pieces if _in_run(k, args.sheet))
        if not keys:
            raise AnnotationError(f"no pieces for sheet {args.sheet!r}; sheets: {', '.join(_runs(ann)) or 'none'}")
        roleless = [k for k in keys if ann.pieces[k].status == "proposed" and not ann.pieces[k].role]
        if roleless:
            raise AnnotationError([f"{k}: has no role yet, fill it in before confirming" for k in roleless])
        for k in keys:
            if ann.pieces[k].status == "proposed":
                ann.pieces[k].status = "confirmed"
        what = f"sheet {args.sheet}"
    errs = validate(ann)
    if errs:
        raise AnnotationError(errs)
    save(ann)
    print(f"{what} confirmed ({args.file})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Annotate, check and confirm the rig annotations file.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose", help="draft the pieces of a split run (role blank, rough top/bottom points)")
    p.add_argument("run_dir", help="<char-dir>/runs/<split-run>")
    p.add_argument("--annotations", required=True, help="the annotations file (created when missing)")
    p.add_argument("--character", help="character name; required when the file is created")
    p.add_argument("--master", default="master.png", help="master image, used when the file is created")
    p.set_defaults(fn=cmd_propose)
    p = sub.add_parser("check", help="validate, snap, normalise, save, render the overlays; last line is JSON")
    p.add_argument("file")
    p.add_argument("--sheet", help="only this split run's overlay and worn strip")
    p.add_argument("--jev", action="store_true",
                   help="also ask Jev palm or back for the hand pieces (jev_facing.py); skipped without a key")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("confirm", help="mark a sheet's pieces, or the master, confirmed")
    p.add_argument("file")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--sheet", help="split run to confirm")
    g.add_argument("--master", action="store_true")
    p.set_defaults(fn=cmd_confirm)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except AnnotationError as e:
        print("\n".join(e.problems), file=sys.stderr)
        return 2


if __name__ == "__main__":
    # run as the module (not as __main__) so rig_overlay shares one copy of these classes
    import rig_annotations
    raise SystemExit(rig_annotations.main())
