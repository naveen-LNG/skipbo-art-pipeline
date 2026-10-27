"""rig_cut.py - the legacy --cut-from-master path (spine_rig.py stages 3a, 3b, 3e): arms, hands, hips, legs and feet
are cut out of the master itself, the generated parts serving only as colour references (rig_colours).

  cut_arms(pl, pal)                     shoulder S, elbow E, wrist W; capsule ends at E and W
  cut_lower_body(pl, pal, half_w)       hips above the crotch, legs below, feet below the ankle
  patches = orphan_patches(pl, pal)     master pixels no piece covers become static patches

pl: rig_pieces.Placement (pieces, joints and bone_dir are filled in); pal: rig_colours.Palette.
"""
from __future__ import annotations

import re

import numpy as np

from rig_colours import Palette
from rig_frame import centroid, far_point, fill_from, grow
from rig_pieces import Placement


def body_cover(pl: Placement) -> np.ndarray:
    """What the matched torso, head, neckwear, props and hats cover: no limb is cut from there."""
    cover = np.zeros((pl.ff.H, pl.ff.W), bool)
    for n in pl.placed:
        if pl.prole(n)[1] in ("torso", "head", "neckwear", "front", "hat"):
            cover |= pl.masks[n]
    return cover


def cut_arms(pl: Placement, pal: Palette):
    """Arms from the master: shoulder S, elbow E, wrist W; capsule ends at E and W."""
    ff, placed, masks, joints, bone_dir = pl.ff, pl.placed, pl.masks, pl.joints, pl.bone_dir
    fgF, rgbF, alphaF, U, Hf, Wf, midF = ff.fg, ff.rgb, ff.alpha, ff.U, ff.H, ff.W, ff.mid
    disk, recentre, prole = ff.disk, ff.recentre, pl.prole
    cover = body_cover(pl)
    for side in ("l", "r"):
        ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
        if not all(x in placed for x in (ua, hd)):
            continue
        has_fa = fa in placed                                  # a sheet may give one whole sleeve per arm
        U_arm = grow(masks[ua] | (masks[fa] if has_fa else masks[ua]) | masks[hd], int(10 * U))
        R = fgF & U_arm & ~masks.get("torso", np.zeros_like(fgF)) & ~cover
        neighbours = [n_ for n_ in placed if prole(n_)[1] in ("torso", "neckwear")]  # what an arm borders in a front rest pose
        R = pal.keep_classes(R, [pal.src(ua), pal.src(fa if has_fa else ua), pal.src(hd)], [pal.src(n_) for n_ in neighbours])
        src_hd = pal.src(hd)
        src_fa = pal.src(fa) if has_fa else pal.src(ua)
        hand_reg = pal.split(R, grow(masks[hd], int(6 * U)), src_hd, src_fa)
        sleeve = R & ~hand_reg
        torso_m = masks.get("torso", np.zeros_like(fgF))
        contact = sleeve & grow(torso_m, int(4 * U))
        if contact.any():
            cy_ = np.nonzero(contact)[0]
            contact &= (np.mgrid[:Hf, :1][0] <= np.percentile(cy_, 30))   # top of the arm-to-body contact
        S = centroid(contact)
        W = centroid(grow(hand_reg, int(3 * U)) & sleeve)
        if S is None or W is None:
            continue
        d = W - S
        S, rS = recentre(S, d, sleeve)
        W, rW = recentre(W, d, R)
        E, rE = recentre((S + W) / 2, d, sleeve)
        for _ in range(2):   # centre the wrist across the forearm's own direction, not the whole arm's
            W, rW = recentre(W, W - E, R)
            E, rE = recentre(E, W - S, sleeve)
        dn = d / np.linalg.norm(d)
        yy, xx = np.mgrid[:Hf, :Wf]
        proj_E = (xx - E[0]) * dn[0] + (yy - E[1]) * dn[1]
        cap_E, cap_W = disk(E, rE) & sleeve, disk(W, rW * 1.05) & R
        # shoulder pivot: step horizontally towards the body until safely inside the torso (not the scarf)
        step = np.array([np.sign(midF - S[0]), 0.0])
        S_in = S.copy()
        neck_m = np.zeros_like(fgF)
        for n_ in placed:
            if prole(n_)[1] == "neckwear":
                neck_m |= masks[n_]
        for _ in range(int(rS * 2)):
            x_, y_ = int(S_in[0]), int(S_in[1])
            if torso_m[y_, x_] and torso_m[min(Hf - 1, y_ + int(4 * U)), x_] and not neck_m[y_, x_] and abs(S_in[0] - S[0]) > 6 * U:
                break
            S_in = S_in + step
        if neck_m[int(S_in[1]), int(S_in[0])]:          # still under the scarf: drop below it
            while S_in[1] < Hf - 1 and neck_m[int(S_in[1]), int(S_in[0])]:
                S_in = S_in + np.array([0.0, 1.0])
        cap_S = disk(S_in, rS * 1.8) & (sleeve | torso_m | fgF)   # hidden under the torso: generous is free
        upper = (sleeve & (proj_E < 0)) | cap_E | cap_S
        cols = fill_from(rgbF, sleeve, cap_S, int(rS * 2))
        pl.from_master(ua, upper, cols, alpha_override=np.where(cap_S & ~sleeve, 1.0, alphaF))
        pl.from_master(fa, (sleeve & (proj_E >= 0)) | cap_E | (disk(W, rW) & R))
        pl.from_master(hd, hand_reg | cap_W)
        joints[ua], joints[fa], joints[hd] = S_in, E, W
        bone_dir[ua], bone_dir[fa] = E - S_in, W - E
        bone_dir[hd] = far_point(hand_reg, W) - W


def cut_lower_body(pl: Placement, pal: Palette, half_w: float):
    """Lower body from the master: hips above the crotch, legs below, feet below the ankle (half_w: the
    silhouette's half width, work px). Needs matched hips, both legs and a torso."""
    ff, placed, masks, pieces, joints, bone_dir = pl.ff, pl.placed, pl.masks, pl.pieces, pl.joints, pl.bone_dir
    fgF, rgbF, alphaF, U, Hf, Wf, midF = ff.fg, ff.rgb, ff.alpha, ff.U, ff.H, ff.W, ff.mid
    disk, recentre, prole = ff.disk, ff.recentre, pl.prole
    if not ("hips" in placed and all(f"leg_{s_}" in placed for s_ in ("l", "r")) and "torso" in placed):
        return
    cover = body_cover(pl)
    torso_m = masks.get("torso", np.zeros_like(fgF))
    # everything below the torso's bottom edge; the generated legs/hips are only colour references
    col0 = int(round(midF))
    yb0 = int(np.nonzero(torso_m[:, col0])[0].max()) if torso_m[:, col0].any() else int(centroid(masks["hips"])[1])
    yy0 = np.mgrid[:Hf, :1][0]
    LB = fgF & (yy0 >= yb0 - int(0.06 * np.ptp(np.nonzero(torso_m[:, col0])[0] if torso_m[:, col0].any() else [0, 100]))) & ~torso_m & ~cover
    tails = [n_ for n_ in placed if re.sub(r"_(l|r)$", "", n_) == "tail"]
    for n_ in tails:                                       # keep the tail out of the hips/leg cuts
        LB &= ~masks[n_]
    for n_ in [n_ for n_ in pieces if prole(n_)[1] in ("arm", "forearm", "hand")]:
        LB &= ~grow(pieces[n_]["mask"], int(2 * U))
    lb_keep = [pal.src(n_) for n_ in placed if prole(n_)[1] in ("hips", "leg", "foot")]
    if tails and lb_keep:   # colour test only around the tail: elsewhere it would eat shaded boots
        near_tail = np.zeros_like(fgF)
        for n_ in tails:
            near_tail |= grow(masks[n_], int(12 * U))
        LB = (LB & ~near_tail) | pal.keep_classes(LB & near_tail, lb_keep, [pal.src(n_) for n_ in tails])
    # crotch: the highest point where background starts between the legs, near the centre line
    col_x = int(round(midF))
    yb = int(np.nonzero(torso_m[:, col_x])[0].max()) if torso_m[:, col_x].any() else int(centroid(masks["hips"])[1])
    crotch, best_x = Hf - 1, col_x
    for cx_ in range(col_x - int(0.08 * half_w * U), col_x + int(0.08 * half_w * U) + 1, max(1, int(U))):
        c_ = yb
        while c_ < Hf - 1 and fgF[c_, cx_]:
            c_ += 1
        if c_ < crotch:
            crotch, best_x = c_, cx_
    col_x = best_x
    yy, xx = np.mgrid[:Hf, :Wf]
    hips_reg = LB & (yy < crotch)
    torso_h = int(np.ptp(np.nonzero(torso_m[:, col_x])[0])) if torso_m[:, col_x].any() else int(60 * U)
    hips_cap = (grow(hips_reg, int(6 * U)) | (torso_m & (yy > yb - 0.12 * torso_h))) & (fgF | torso_m) & (yy < crotch + int(6 * U))
    hips_cap &= grow(hips_reg, int(0.14 * torso_h) + 1)
    pl.from_master("hips", hips_reg | (hips_cap & torso_m), fill_from(rgbF, hips_reg, hips_cap & torso_m, int(12 * U)),
                   alpha_override=np.where(hips_cap & torso_m & ~hips_reg, 1.0, alphaF))
    joints["hips"] = np.array([midF, (yb + crotch) / 2])
    joints["torso"], bone_dir["torso"] = np.array([midF, yb - 0.05 * torso_h]), np.array([0.0, -1.0])
    bone_dir["hips"] = np.array([0.0, -1.0])
    for side, sgn in (("r", -1), ("l", 1)):
        leg, foot = f"leg_{side}", next((f"{f_}_{side}" for f_ in ("hoof", "foot", "shoe", "boot") if f"{f_}_{side}" in placed), None)
        half = (xx - midF) * sgn > 0
        legs_reg = LB & (yy >= crotch) & half
        src_foot = pal.src(foot) if foot else None
        src_leg = pal.src(leg)
        foot_col = pal.split(legs_reg, legs_reg, src_foot, src_leg) if foot else np.zeros_like(fgF)
        if foot_col.any():   # clean horizontal ankle cut at the top of the hoof (legs hang near-vertical at rest)
            ankle_y = np.percentile(np.nonzero(foot_col)[0], 8)
            leg_len = ankle_y - crotch
            foot_reg = legs_reg & ((yy >= ankle_y) | (foot_col & (yy >= ankle_y - 0.15 * leg_len)))
        else:
            foot_reg = foot_col
        trouser = legs_reg & ~foot_reg
        top_row = trouser[crotch + int(10 * U)]
        xs_top = np.nonzero(top_row)[0]
        if not len(xs_top):
            continue
        Hj = np.array([xs_top.mean(), crotch - 2])
        A = centroid(grow(foot_reg, int(3 * U)) & trouser) if foot and foot_reg.any() else None
        if A is None:
            print(f"  ! {leg}: no foot pixels found below the trouser; foot left as generated")
            foot = None
            A = far_point(trouser, Hj)
        d = A - Hj
        _, rH = recentre(Hj + d * 0.08, d, trouser)
        A, rA = recentre(A, d, trouser)
        cap_H = disk(Hj, rH * 1.1) & (trouser | hips_reg | torso_m)
        cols = fill_from(rgbF, trouser, cap_H, int(rH * 2))
        pl.from_master(leg, trouser | cap_H | (disk(A, rA) & trouser), cols, alpha_override=np.where(cap_H & ~trouser, 1.0, alphaF))
        joints[leg], bone_dir[leg] = Hj, d
        if foot:
            pl.from_master(foot, foot_reg | (disk(A, rA * 1.05) & legs_reg))
            joints[foot], bone_dir[foot] = A, far_point(foot_reg, A) - A


def orphan_patches(pl: Placement, pal: Palette) -> dict:
    """Orphans: master pixels no piece covers in the rest pose (e.g. a vest edge the generated torso doesn't reach)
    become static patches <owner>_patch on the torso or hips they resemble, drawn just above it (never the head:
    expressions swap there). Returns patch -> owner."""
    ff, pieces, joints, bone_dir = pl.ff, pl.pieces, pl.joints, pl.bone_dir
    patches = {}
    covered = np.zeros((ff.H, ff.W), bool)
    for pc in pieces.values():
        covered |= pc["mask"]
    orphan = ff.fg & ~covered
    owners = [n for n in pieces if n in pl.placed and pl.prole(n)[1] in ("torso", "hips")]
    if orphan.sum() > 50 and owners:
        dists = np.stack([np.linalg.norm(ff.rgb - pal.mean(pal.src(o)), axis=2) for o in owners])
        best = np.argmin(dists, axis=0)
        for i, o in enumerate(owners):
            reg = orphan & (best == i) & grow(pieces[o]["mask"], int(12 * ff.U))
            if reg.sum() > 30:
                pl.from_master(f"{o}_patch", reg, clean=False)
                if f"{o}_patch" not in pieces:
                    continue
                patches[f"{o}_patch"] = o
                joints[f"{o}_patch"], bone_dir[f"{o}_patch"] = joints.get(o, centroid(reg)), np.array([0.0, -1.0])
    return patches
