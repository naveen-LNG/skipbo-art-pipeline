"""rig_frame.py - the master at full resolution, where spine_rig.py places its pieces (stage 3), and the mask
helpers the placement stages share.

Positions are full-resolution master px, y down; FullFrame.units turns them into Spine units (y up, origin on the
centre line at the ground).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw


@dataclass
class FullFrame:
    """The master at full resolution."""
    rgb: np.ndarray      # master RGB, float 0..1
    alpha: np.ndarray    # soft silhouette 0..1 (distance from the background colour)
    fg: np.ndarray       # alpha > 0.5
    U: float             # full-res px per work px (rig_match.WORK_H)
    unit: float          # Spine units (part px) per full-res px
    mid: float           # the centre line, x
    ground: float        # the ground line, y

    @property
    def W(self) -> int:
        return self.rgb.shape[1]

    @property
    def H(self) -> int:
        return self.rgb.shape[0]

    def units(self, P):
        """Full-res point -> Spine units."""
        return ((P[0] - self.mid) * self.unit, (self.ground - P[1]) * self.unit)

    def full_mask(self, m: dict) -> np.ndarray:
        """Placed part's opaque area as a full-res boolean mask."""
        Hf, Wf, U = self.H, self.W, self.U
        mm = np.zeros((Hf, Wf), bool)
        a_ = Image.fromarray(((m["tpl"][..., 3] > 0.5) * 255).astype(np.uint8))
        w, h = max(1, round(a_.width * U)), max(1, round(a_.height * U))
        a_ = np.asarray(a_.resize((w, h), Image.NEAREST)) > 0
        x0, y0 = round(m["x"] * U), round(m["y"] * U)
        xs_, ys_ = slice(max(0, x0), min(Wf, x0 + w)), slice(max(0, y0), min(Hf, y0 + h))
        mm[ys_, xs_] = a_[ys_.start - y0: ys_.stop - y0, xs_.start - x0: xs_.stop - x0]
        return mm

    def disk(self, c, r) -> np.ndarray:
        yy, xx = np.ogrid[:self.H, :self.W]
        return (xx - c[0]) ** 2 + (yy - c[1]) ** 2 <= r * r

    def recentre(self, P, d, region: np.ndarray):
        """Move P across the limb (perpendicular to d) to the middle of region; return (P, half-width)."""
        n = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-9)
        w = []
        for sgn in (1, -1):
            t = 0
            while t < 400:
                q = P + sgn * n * (t + 1)
                x_, y_ = int(round(q[0])), int(round(q[1]))
                if not (0 <= x_ < self.W and 0 <= y_ < self.H) or not region[y_, x_]:
                    break
                t += 1
            w.append(t)
        return P + n * (w[0] - w[1]) / 2, max(4.0, (w[0] + w[1]) / 2)


def full_frame(master_rgb: np.ndarray, frame, g: float) -> FullFrame:
    """The full-res frame of a master (RGB 0..1) whose working frame is `frame` (rig_match.MasterFrame), with g
    work px per part px."""
    k = frame.k
    U = 1.0 / k                       # full-res px per work px
    rgbF = master_rgb
    border = np.concatenate([rgbF[0], rgbF[-1], rgbF[:, 0], rgbF[:, -1]])
    bgc = np.median(border, axis=0)
    dist = np.linalg.norm(rgbF - bgc, axis=2)
    alphaF = np.clip((dist - 0.03) / 0.05, 0, 1)       # soft silhouette
    return FullFrame(rgbF, alphaF, alphaF > 0.5, U, k / g, frame.mid_x * U, frame.ground_y * U)


# ------------------------------------------------------------------ masks

def grow(m: np.ndarray, r: int) -> np.ndarray:
    """Binary dilation by r px (square), via cumulative max over shifted copies."""
    out = m.copy()
    step = 1
    while step <= r:
        out = out | np.roll(out, step, 0) | np.roll(out, -step, 0)
        out = out | np.roll(out, step, 1) | np.roll(out, -step, 1)
        step *= 2
    return out


def centroid(m: np.ndarray):
    ys_, xs_ = np.nonzero(m)
    return np.array([xs_.mean(), ys_.mean()]) if len(xs_) else None


def far_point(m: np.ndarray, P):
    """The pixel of m farthest from P."""
    ys_, xs_ = np.nonzero(m)
    i = np.argmax((xs_ - P[0]) ** 2 + (ys_ - P[1]) ** 2)
    return np.array([xs_[i], ys_[i]], float)


def fill_from(colour_src: np.ndarray, have: np.ndarray, want: np.ndarray, iters: int) -> np.ndarray:
    """Extend colours from `have` into `want` by nearest-neighbour propagation (hidden joint caps).
    Works on the bounding box of `want` (+margin) and runs until every wanted pixel is filled."""
    out = colour_src.copy()
    ys_, xs_ = np.nonzero(want)
    if not len(ys_):
        return out
    pad = 4
    y0, y1 = max(0, ys_.min() - pad), min(want.shape[0], ys_.max() + pad + 1)
    x0, x1 = max(0, xs_.min() - pad), min(want.shape[1], xs_.max() + pad + 1)
    col = colour_src[y0:y1, x0:x1].copy()
    known = have[y0:y1, x0:x1].copy()
    want = want[y0:y1, x0:x1]
    if not known.any():
        return out
    for _ in range(4000):
        todo = want & ~known
        if not todo.any():
            break
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            src_known = np.roll(np.roll(known, dy, 0), dx, 1)
            take = todo & src_known
            col[take] = np.roll(np.roll(col, dy, 0), dx, 1)[take]
            known = known | take
            todo = want & ~known
    out[y0:y1, x0:x1] = col
    return out


def main_body(region: np.ndarray) -> np.ndarray:
    """Largest connected component of a region (drops detached islands, e.g. tail bits in a paw)."""
    ys_, xs_ = np.nonzero(region)
    if not len(ys_):
        return region
    y0, y1, x0, x1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
    im = Image.fromarray(np.where(region[y0:y1, x0:x1], 255, 0).astype(np.uint8)).copy()   # writable
    best, best_area = None, 0
    for k in range(1, 200):
        arr = np.asarray(im)
        left_ = np.argwhere(arr == 255)
        if not len(left_):
            break
        y_, x_ = left_[0]
        ImageDraw.floodfill(im, (int(x_), int(y_)), k)
        comp = (np.asarray(im) == k) & (arr == 255)
        if comp.sum() > best_area:
            best, best_area = comp, int(comp.sum())
    out = np.zeros_like(region)
    out[y0:y1, x0:x1] = best
    return out


def axis_ends(pts: np.ndarray):
    """(end, other end, width) of a point cloud along its principal axis (2nd / 98th percentiles; width 5-95%)."""
    c = pts.mean(0)
    u, s, vt = np.linalg.svd(pts - c, full_matrices=False)
    d = vt[0]
    proj = (pts - c) @ d
    perp = (pts - c) @ vt[1]
    width = np.percentile(perp, 95) - np.percentile(perp, 5)
    return c + d * np.percentile(proj, 2), c + d * np.percentile(proj, 98), width
