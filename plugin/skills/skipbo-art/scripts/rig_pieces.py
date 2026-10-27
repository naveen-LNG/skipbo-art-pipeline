"""rig_pieces.py - the pieces of a rig being placed (spine_rig.py stage 3) and the moves on them.

A piece is {"img": PIL RGBA, "cx", "cy" (full-res centre), "unit" (Spine units per image px), "angle", "mask"
(full-res rest-pose mask)}; annotation-placed pieces add "unit_y" and sleeve meshes "mesh" / "mesh_of"
(rig_place). Each piece gets a pivot (joints) and a direction from the pivot to its far end (bone_dir).

Limb pieces are pinned like a cut-out: pin() turns and moves a piece so the centre of one of its round ends lands
on a point, painted_ends() finds those centres from how the piece was painted (joint end up).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from rig_frame import FullFrame, axis_ends, grow, main_body
from rig_image import solidify
from rig_roles import role


@dataclass
class Placement:
    """Stage 3's working state. placed / masks: the colour-matched parts (rig_match) and their full-res masks;
    roles: the annotated roles (rig_roles.ann_roles; None: guessed from the names)."""
    ff: FullFrame
    placed: dict
    masks: dict
    roles: dict | None = None
    pieces: dict = field(default_factory=dict)
    joints: dict = field(default_factory=dict)
    bone_dir: dict = field(default_factory=dict)

    def prole(self, n: str) -> tuple[str, str]:
        """(bone parent role, draw layer) of part n: annotated (roles) with --annotations, else from its name."""
        return role(n, self.roles)

    def add_generated(self, g: float):
        """A piece per colour-matched part, keeping its painted image (g: work px per part px)."""
        U = self.ff.U
        for n, m in self.placed.items():
            self.pieces[n] = {"img": solidify(Image.open(m["src"])), "cx": m["cx"] * U, "cy": m["cy"] * U,
                              "unit": m["scale"] / g, "angle": m["angle"], "mask": self.masks[n]}

    def from_master(self, name: str, region: np.ndarray, colours: np.ndarray | None = None, alpha_override=None,
                    clean: bool = True):
        """Piece `name` cut out of the master: the pixels of region (cleaned of 1-3 px lines and specks unless
        clean is False), coloured from colours (default the master) with the master's soft alpha (or
        alpha_override). Nothing is added when the region ends up empty."""
        ff = self.ff
        if clean:                                           # drop 1-3 px lines and specks (anti-alias fringe)
            r_open = max(2, int(1.5 * ff.U))
            opened = region & grow(~grow(~region, r_open), r_open)
            region = opened if opened.sum() > 0.5 * region.sum() else region
            region = main_body(region)
        ys_, xs_ = np.nonzero(region)
        if not len(ys_):
            return
        y0, y1, x0, x1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
        col = (colours if colours is not None else ff.rgb)[y0:y1, x0:x1]
        al = (alpha_override if alpha_override is not None else ff.alpha)[y0:y1, x0:x1] * region[y0:y1, x0:x1]
        rgba = np.dstack([col, al])
        img = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA")
        self.pieces[name] = {"img": img, "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "unit": ff.unit, "angle": 0.0,
                             "mask": region}

    def shift(self, n: str, dv):
        """Move piece n by dv, rounded to whole px; returns the move made."""
        Hf, Wf = self.ff.H, self.ff.W
        pieces = self.pieces
        dx, dy = int(round(dv[0])), int(round(dv[1]))
        m = pieces[n]["mask"]
        out = np.zeros_like(m)
        out[max(0, dy): Hf + min(0, dy), max(0, dx): Wf + min(0, dx)] = m[max(0, -dy): Hf + min(0, -dy), max(0, -dx): Wf + min(0, -dx)]
        pieces[n]["mask"], pieces[n]["cx"], pieces[n]["cy"] = out, pieces[n]["cx"] + dx, pieces[n]["cy"] + dy
        return np.array([dx, dy], float)

    def painted_ends(self, n: str):
        """World positions of a placed limb's two round-end centres, told apart by how it was painted (joint end up):
        (proximal, distal, width). Distance-based guesses flip a piece that was matched too high."""
        pc = self.pieces[n]
        al = np.asarray(pc["img"])[..., 3] > 127
        ys_, xs_ = np.nonzero(al)
        e1, e2, width = axis_ends(np.stack([xs_, ys_], 1).astype(np.float32))
        top_, bot_ = (e1, e2) if e1[1] <= e2[1] else (e2, e1)
        L = float(np.linalg.norm(bot_ - top_))
        d = (bot_ - top_) / (L + 1e-9)
        f = pc["unit"] / self.ff.unit
        c, s_ = math.cos(math.radians(pc["angle"])), math.sin(math.radians(pc["angle"]))
        def M(p_):
            v = (p_ - np.array([pc["img"].width / 2, pc["img"].height / 2])) * f
            return np.array([pc["cx"], pc["cy"]]) + np.array([c * v[0] + s_ * v[1], -s_ * v[0] + c * v[1]])
        return M(top_ + d * min(width / 2, 0.45 * L)), M(bot_ - d * min(width / 2, 0.45 * L)), width * f

    def pin(self, n: str, P, Q, use_end: str = "proximal"):
        """Re-place piece n so the centre of its round `use_end` lands on P and its axis points from P towards Q.
        (proximal = the end at the top of the painted piece, which faces the body.) Returns its two round-end
        centres and its width, full-res px."""
        Hf, Wf = self.ff.H, self.ff.W
        pc = self.pieces[n]
        al = np.asarray(pc["img"])[..., 3] > 127
        ys_, xs_ = np.nonzero(al)
        pts = np.stack([xs_, ys_], 1).astype(np.float32)
        e1, e2, width = axis_ends(pts)
        top_, bot_ = (e1, e2) if e1[1] <= e2[1] else (e2, e1)
        L = float(np.linalg.norm(bot_ - top_))
        d = (bot_ - top_) / (L + 1e-9)
        Jp, Jd = top_ + d * min(width / 2, 0.45 * L), bot_ - d * min(width / 2, 0.45 * L)
        J, other = (Jp, Jd) if use_end == "proximal" else (Jd, Jp)
        vis = lambda v: math.degrees(math.atan2(-v[1], v[0]))   # noqa: E731
        ang = vis(np.asarray(Q) - np.asarray(P)) - vis(other - J)
        f = pc["unit"] / self.ff.unit                            # full-res px per image px
        c, s_ = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        v = (J - np.array([pc["img"].width / 2, pc["img"].height / 2])) * f
        C = np.asarray(P, float) - np.array([c * v[0] + s_ * v[1], -s_ * v[0] + c * v[1]])
        im = pc["img"].resize((max(1, round(pc["img"].width * f)), max(1, round(pc["img"].height * f))), Image.LANCZOS).rotate(ang, Image.BICUBIC, expand=True)
        a_ = np.asarray(im)[..., 3] > 127
        mm = np.zeros((Hf, Wf), bool)
        x0, y0 = int(round(C[0] - im.width / 2)), int(round(C[1] - im.height / 2))
        xs_s, ys_s = slice(max(0, x0), min(Wf, x0 + im.width)), slice(max(0, y0), min(Hf, y0 + im.height))
        mm[ys_s, xs_s] = a_[ys_s.start - y0: ys_s.stop - y0, xs_s.start - x0: xs_s.stop - x0]
        pc.update({"angle": ang, "cx": float(C[0]), "cy": float(C[1]), "mask": mm})
        M = lambda p_: C + np.array([c * (p_[0] - pc["img"].width / 2) * f + s_ * (p_[1] - pc["img"].height / 2) * f,   # noqa: E731
                                     -s_ * (p_[0] - pc["img"].width / 2) * f + c * (p_[1] - pc["img"].height / 2) * f])
        return M(Jp), M(Jd), width * f


def end_centre(mask: np.ndarray, toward):
    """Centre of the round end of a limb mask nearest `toward`: the end point stepped inwards by half the width."""
    ys_, xs_ = np.nonzero(mask)
    e1, e2, width = axis_ends(np.stack([xs_, ys_], 1).astype(np.float32))
    end, other = (e1, e2) if np.linalg.norm(e1 - toward) <= np.linalg.norm(e2 - toward) else (e2, e1)
    L = float(np.linalg.norm(other - end))
    return end + (other - end) / (L + 1e-9) * min(width / 2, 0.45 * L)


def top_centre(mask: np.ndarray):
    """Ankle/wrist pivot of a near-upright foot or boot: the middle of its top edge, half the shaft width down."""
    ys_, xs_ = np.nonzero(mask)
    r0 = ys_.min() + max(1, int(0.06 * np.ptp(ys_)))
    row = np.nonzero(mask[r0])[0]
    return np.array([row.mean(), ys_.min() + (np.ptp(row) + 1) / 2])
