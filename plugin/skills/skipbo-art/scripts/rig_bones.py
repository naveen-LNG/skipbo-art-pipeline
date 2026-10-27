"""rig_bones.py - the skeleton (spine_rig.py stages 3c, 3d, 4): each piece's parent, a pivot for every piece the
placement stages left without one, hidden roots under the parent for pieces drawn behind it, and the bones.

  pivots(pl, annotated, cut_from_master)   3c: pivot at the overlap with the parent
  hidden_roots(pl, annotated)              3d: antlers, ears, tail get a root painted under their parent
  bones, world, order = skeleton(pl, annotated)

pl: rig_pieces.Placement. annotated: built from annotations (feet may hang from the hips).
"""
from __future__ import annotations

import math
import re

import numpy as np
from PIL import Image

from rig_frame import centroid, far_point, fill_from, grow
from rig_pieces import Placement


def parent_of(pl: Placement, name: str, annotated: bool) -> str:
    """The bone piece `name` hangs from ("root" for the hips)."""
    pieces, prole = pl.pieces, pl.prole
    if name.endswith("_patch"):
        return name[: -len("_patch")]
    want, _ = prole(name)
    if want == "root":
        return "root"
    if want == "head" and prole(name)[1] != "hat":  # antlers, ears: attach to the head piece they overlap most
        heads_ = [n for n in pieces if prole(n)[1] in ("head", "hat") and n != name]
        if heads_:
            return max(heads_, key=lambda h: int((pieces[name]["mask"] & pieces[h]["mask"]).sum()))
    side = name[-2:] if re.search(r"_(l|r)$", name) else ""
    for cand_name in (f"{want}{side}", want):
        if cand_name in pieces:
            return cand_name
    for n in pieces:
        if prole(n)[1] == want or re.sub(r"_(l|r)$", "", n) == want:
            return n
    if annotated and want == "leg" and "hips" in pieces:   # feet without leg pieces (painted trouser cuffs)
        return "hips"
    return "torso" if "torso" in pieces and name != "torso" else "root"


def pivots(pl: Placement, annotated: bool, cut_from_master: bool):
    """Remaining pieces: pivot at the overlap with their parent (torso and head: pointing up). A generated piece
    that doesn't touch its parent is pinned onto it first."""
    pieces, joints, bone_dir, U = pl.pieces, pl.joints, pl.bone_dir, pl.ff.U
    for n in pieces:
        if n in joints:
            continue
        par = parent_of(pl, n, annotated)
        lay = pl.prole(n)[1]
        if lay in ("torso", "head"):
            ov = pieces[n]["mask"] & pieces[par]["mask"] if par in pieces else None
            c = centroid(ov) if ov is not None and ov.any() else None
            if c is None:
                ys_, xs_ = np.nonzero(pieces[n]["mask"])
                c = np.array([xs_.mean(), np.percentile(ys_, 90)])
            joints[n], bone_dir[n] = c, np.array([0.0, -1.0])
            continue
        pm = pieces[par]["mask"] if par in pieces else None
        if pm is not None and not cut_from_master and not (pieces[n]["mask"] & grow(pm, int(2 * U))).any():
            # a generated piece that doesn't touch its parent (a bell beside a regenerated scarf): pin it on
            pys, pxs = np.nonzero(pm)
            c_ = centroid(pieces[n]["mask"])
            i_ = np.argmin((pxs - c_[0]) ** 2 + (pys - c_[1]) ** 2)
            target = np.array([pxs[i_], pys[i_]], float)
            nys, nxs = np.nonzero(pieces[n]["mask"])
            j_ = np.argmin((nxs - target[0]) ** 2 + (nys - target[1]) ** 2)
            dv = target - np.array([nxs[j_], nys[j_]], float)          # touch at the nearest points...
            inward = target - (c_ + dv)
            dv += inward / (np.linalg.norm(inward) + 1e-9) * 6 * U     # ...then overlap a little
            pl.shift(n, dv)
            print(f"  {n}: not touching {par}; pinned onto it")
        ov = None
        for r_ in (0, 4, 10, 20, 40):
            if pm is None:
                break
            ov = pieces[n]["mask"] & grow(pm, int(r_ * U)) if r_ else pieces[n]["mask"] & pm
            if ov.any():
                break
        c = centroid(ov) if ov is not None and ov.any() else centroid(pieces[n]["mask"])
        joints[n] = c
        bone_dir[n] = far_point(pieces[n]["mask"], c) - c


def hidden_roots(pl: Placement, annotated: bool):
    """Pieces drawn behind their parent (antlers, horns, ears, tail) get a hidden root under the parent, painted in
    their own colours, so the joint stays closed when they rotate."""
    pieces, joints, ff = pl.pieces, pl.joints, pl.ff
    for n in list(pieces):
        par = parent_of(pl, n, annotated)
        pc = pieces[n]
        if pl.prole(n)[1] != "back" or par not in pieces or pc["angle"]:
            continue
        arr = np.asarray(pc["img"], dtype=np.float32) / 255.0
        h_, w_ = arr.shape[:2]
        f = pc["unit"] / ff.unit                            # full-res px per image px
        jx, jy = (joints[n][0] - pc["cx"]) / f + w_ / 2, (joints[n][1] - pc["cy"]) / f + h_ / 2
        r_img = 0.16 * max(w_, h_)
        yy_, xx_ = np.mgrid[:h_, :w_]
        fx = np.clip((pc["cx"] + (xx_ - w_ / 2) * f).astype(int), 0, ff.W - 1)
        fy = np.clip((pc["cy"] + (yy_ - h_ / 2) * f).astype(int), 0, ff.H - 1)
        hidden = pieces[par]["mask"][fy, fx]
        root = ((xx_ - jx) ** 2 + (yy_ - jy) ** 2 <= r_img ** 2) & hidden
        have = arr[..., 3] > 0.5
        if not root.any():
            continue
        cols = fill_from(arr[..., :3], have, root, int(r_img * 2))
        out_ = np.dstack([np.where(root[..., None] & ~have[..., None], cols, arr[..., :3]), np.where(root & ~have, 1.0, arr[..., 3])])
        pc["img"] = Image.fromarray((out_ * 255).astype(np.uint8), "RGBA")


def world_angle(d):
    """World angle of a full-res direction (y down), degrees with y up as in Spine."""
    return math.degrees(math.atan2(-d[1], d[0]))


def skeleton(pl: Placement, annotated: bool) -> tuple:
    """The bones, parents first (world angle from the joint towards the far end of the piece; y up in Spine).
    Returns (bones: Spine bone list, world: bone -> ((x, y) units, world angle), order: bone names parent-first)."""
    pieces, joints, bone_dir, ff = pl.pieces, pl.joints, pl.bone_dir, pl.ff
    order = []

    def visit(n):
        if n in order or n == "root":
            return
        visit(parent_of(pl, n, annotated))
        order.append(n)
    for n in pieces:
        if not n.endswith("_patch"):
            visit(n)
    bones, world = [{"name": "root"}], {"root": ((0.0, 0.0), 0.0)}
    for n in order:
        par = parent_of(pl, n, annotated)
        (px, py), prot = world[par]
        wx, wy = ff.units(joints[n])
        ang = world_angle(bone_dir[n])
        c_, s_ = math.cos(math.radians(-prot)), math.sin(math.radians(-prot))
        dx, dy = wx - px, wy - py
        length = float(np.linalg.norm(bone_dir[n])) * ff.unit
        bones.append({"name": n, "parent": par, "x": round(dx * c_ - dy * s_, 2), "y": round(dx * s_ + dy * c_, 2),
                      "rotation": round(ang - prot, 2), "length": round(length, 1)})
        world[n] = ((wx, wy), ang)
    return bones, world, order
