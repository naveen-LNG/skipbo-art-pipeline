"""rig_chain.py - generated limbs (the default legacy path, spine_rig.py stage 3a'): every limb piece keeps its
painted image. A pivot is the centre of the round end where a piece joins its parent; each child is moved so its
round end is concentric with its parent's, the way a cut-out rig is pinned, so joints stay closed at any angle.

  chain_arms(pl, pal, half_w)   upper arm in the torso, forearm on the elbow, hand from the wrist (sized to the master)
  stand_legs(pl, top)           feet on the master's ground, legs from the boot tops to the hips' leg openings

pl: rig_pieces.Placement; pal: rig_colours.Palette; half_w, top: rig_match.MasterFrame's (work px).
"""
from __future__ import annotations

import math
import re

import numpy as np

from rig_colours import Palette
from rig_frame import axis_ends, centroid, far_point, grow, main_body
from rig_pieces import Placement, end_centre, top_centre


def _tail_mask(pl: Placement) -> np.ndarray:
    """Every tail piece, grown 3 work px: the master's tail is no hand or foot."""
    tail_m = np.zeros((pl.ff.H, pl.ff.W), bool)
    for n_ in pl.pieces:
        if re.sub(r"_(l|r)$", "", n_) == "tail":
            tail_m |= grow(pl.pieces[n_]["mask"], int(3 * pl.ff.U))
    return tail_m


def _body_centre(pl: Placement):
    torso_m = pl.pieces["torso"]["mask"] if "torso" in pl.pieces else None
    return centroid(torso_m) if torso_m is not None else np.array([pl.ff.mid, 0.4 * pl.ff.ground])


def chain_arms(pl: Placement, pal: Palette, half_w: float):
    """Each side's upper arm, forearm and hand pinned end to end from the shoulder."""
    ff, placed, pieces, joints, bone_dir = pl.ff, pl.placed, pl.pieces, pl.joints, pl.bone_dir
    fgF, U, Hf, Wf, midF = ff.fg, ff.U, ff.H, ff.W, ff.mid
    tail_m0 = _tail_mask(pl)
    torso_m = pieces["torso"]["mask"] if "torso" in pieces else None
    for side in ("l", "r"):
        chain = [p_ for p_ in (f"upperarm_{side}", f"forearm_{side}", f"hand_{side}") if p_ in pieces]
        if not chain or not chain[0].startswith("upperarm"):
            continue
        ua = chain[0]
        S = pl.painted_ends(ua)[0]
        if torso_m is not None:          # the shoulder pivot has to sit inside the torso: slide the arm inwards
            step, moved = np.array([np.sign(midF - S[0]), 0.0]), np.zeros(2)
            while abs(moved[0]) < 0.25 * half_w * U:
                q = (S + moved).astype(int)
                if torso_m[min(Hf - 1, q[1]), min(Wf - 1, q[0])]:
                    break
                moved += step * U
            if moved.any():
                for p_ in chain:
                    moved_ = pl.shift(p_, moved)
                S = S + moved_
        joints[ua] = S
        for i_, p_ in enumerate(chain):
            nxt = chain[i_ + 1] if i_ + 1 < len(chain) else None
            if i_:
                E_ = joints[chain[i_ - 1]] + bone_dir[chain[i_ - 1]]
                if p_.startswith("hand"):                    # a hand continues its forearm's line from the wrist,
                    dn_ = bone_dir[chain[i_ - 1]] / (np.linalg.norm(bone_dir[chain[i_ - 1]]) + 1e-9)   # tucked a
                    _, _, fw_ = axis_ends(np.stack(np.nonzero(pieces[chain[i_ - 1]]["mask"])[::-1], 1).astype(np.float32))
                    pl.pin(p_, E_ + dn_ * 0.25 * fw_, E_ + bone_dir[chain[i_ - 1]])   # quarter cuff-width under it
                    # size: sheets often paint hands small. Measure the master's hand (pixels near the matched
                    # hand that look like hand, not sleeve, body or tail) and scale the painted hand to that area.
                    cen = centroid(pieces[p_]["mask"])
                    near = ff.disk(cen, 1.6 * math.sqrt(pieces[p_]["mask"].sum()))
                    others = [pal.src(n_) for n_ in placed if pl.prole(n_)[1] in ("forearm", "arm", "torso", "hips")]   # tail: excluded by position
                    ref = pal.keep_classes(fgF & near & ~tail_m0, [pal.src(p_)], others) if others else fgF & near
                    ref = main_body(ref) if ref.any() else ref
                    k_ = float(np.clip(math.sqrt(ref.sum() / max(1, pieces[p_]["mask"].sum())), 1.0, 1.6))
                    if k_ > 1.05:
                        pieces[p_]["unit"] *= k_
                        pl.pin(p_, E_ + dn_ * 0.25 * fw_, E_ + bone_dir[chain[i_ - 1]])
                        print(f"  {p_}: scaled x{k_:.2f} to the master's hand size")
                else:                                        # forearm: its painted-top end on the elbow, keeping
                    P_, D_, _ = pl.painted_ends(p_)          # the direction it was matched at (a bent elbow stays bent)
                    dirn = D_ - P_
                    if np.dot(dirn, bone_dir[chain[i_ - 1]]) < 0:   # matched pointing back up the arm: straighten it
                        dirn = bone_dir[chain[i_ - 1]]
                    pl.pin(p_, E_, E_ + dirn)
                joints[p_] = E_
            D = pl.painted_ends(p_)[1] if nxt else far_point(pieces[p_]["mask"], joints[p_])
            bone_dir[p_] = D - joints[p_]


def stand_legs(pl: Placement, top: float):
    """The hips' pivot, then the legs assembled from the feet up: the feet stay where the master stands, each leg
    runs from its boot top towards its leg opening in the hips, and the leg's top tucks under the hips (drawn over
    it). top: the silhouette's top, work px."""
    ff, pieces, joints, bone_dir = pl.ff, pl.pieces, pl.joints, pl.bone_dir
    fgF, U, Hf, Wf, midF, groundF = ff.fg, ff.U, ff.H, ff.W, ff.mid, ff.ground
    hips_c = centroid(pieces["hips"]["mask"]) if "hips" in pieces else _body_centre(pl)
    if "hips" in pieces:
        joints["hips"], bone_dir["hips"] = hips_c, np.array([0.0, -1.0])
    tail_m = _tail_mask(pl)
    yy_f, xx_f = np.mgrid[:Hf, :Wf]
    for side, sgn in (("l", 1), ("r", -1)):
        leg = f"leg_{side}"
        foot = next((f"{f_}_{side}" for f_ in ("hoof", "foot", "shoe", "boot") if f"{f_}_{side}" in pieces), None)
        if leg not in pieces:
            continue
        if foot:   # stand the foot where the master's foot meets the ground on that side (a same-coloured tail can't lure it)
            contact = fgF & ~tail_m & ((xx_f - midF) * sgn > 0) & (yy_f >= groundF - 0.04 * (groundF - top * U))
            if contact.any():
                cy_, cx_ = np.nonzero(contact)
                fy_, fx_ = np.nonzero(pieces[foot]["mask"])
                bottom = fy_.max()
                pl.shift(foot, np.array([cx_.mean() - fx_[fy_ >= bottom - 4 * U].mean(), cy_.max() - bottom]))
        if "hips" in pieces:
            hm = pieces["hips"]["mask"]
            yy_, xx_ = np.nonzero(hm)
            half_ = (xx_ - midF) * sgn > 0
            y_lo = np.percentile(yy_[half_], 80)
            sel = half_ & (yy_ >= y_lo)
            Hop = np.array([xx_[sel].mean(), yy_[sel].mean()])     # the leg opening at the bottom of the hips
        else:
            Hop = end_centre(pieces[leg]["mask"], hips_c)
        if foot:
            A = top_centre(pieces[foot]["mask"])            # a leg slanting more than 8 degrees pokes out of its
            max_dx = math.tan(math.radians(8)) * abs(A[1] - Hop[1])   # boot: bring the foot in under its hip
            if abs(A[0] - Hop[0]) > max_dx:
                pl.shift(foot, np.array([(A[0] - Hop[0]) - math.copysign(max_dx, A[0] - Hop[0]), 0.0]) * -1)
                A = top_centre(pieces[foot]["mask"])        # ankle pivot, half a shaft width inside the boot
            fy_, fx_ = np.nonzero(pieces[foot]["mask"])
            rim = np.array([A[0], fy_.min() + 0.5 * (A[1] - fy_.min())])
            Lp, Ld, lw = pl.pin(leg, rim, Hop, use_end="distal")   # leg's round end just inside the rim: no poking out
            gap = float(np.linalg.norm(A - Hop) - np.linalg.norm(A - Lp))
            if gap > 0:                                             # leg too short to reach the hips: lift leg and foot
                up = (Hop - A) / np.linalg.norm(Hop - A) * gap
                pl.shift(leg, up)
                pl.shift(foot, up)
                A = A + up
                print(f"  {leg}: {gap / U:.0f} work px short of the hips; leg and {foot} lifted")
            joints[leg], bone_dir[leg] = Hop, A - Hop
            joints[foot], bone_dir[foot] = A, far_point(pieces[foot]["mask"], A) - A
        else:
            joints[leg] = end_centre(pieces[leg]["mask"], hips_c)
            bone_dir[leg] = far_point(pieces[leg]["mask"], joints[leg]) - joints[leg]
