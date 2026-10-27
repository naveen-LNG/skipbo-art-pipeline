#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""rig_snap.py - snap rough joint points to exact geometry on a part's alpha mask.

The agent writes a rough point near a limb end or an opening; code finds the exact spot:
  snap_round_end   centre of a round limb end (circle fitted to the outline)
  snap_opening     centre and width of an opening rim (boot top, sleeve cuff)
  cross_width      the piece's width across its principal axis at a point (for a round end that did not snap)

`alpha` is a boolean (H, W) array, True = opaque. Points are (x, y) in pixels, y down.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


def principal_axis(pts: np.ndarray):
    """(centre, along, across) of an (N, 2) point set: its mean and the unit vectors along and across its
    principal axis."""
    c = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    return c, vt[0], vt[1]


def axis_ends(pts: np.ndarray):
    c, d, across = principal_axis(pts)
    proj = (pts - c) @ d
    perp = (pts - c) @ across
    width = np.percentile(perp, 95) - np.percentile(perp, 5)
    return c + d * np.percentile(proj, 2), c + d * np.percentile(proj, 98), width


CROSS_BAND = 1.0        # cross_width takes the opaque pixels within this many px (along the axis) of the point
CROSS_GAP = 2.0         # ... and splits them into separate runs at gaps wider than this (px, across the axis)


class _Slicer:
    """The opaque pixels sorted along an axis, so a slice across it at any point costs only its band."""

    def __init__(self, alpha: np.ndarray, axis):
        ys, xs = np.nonzero(alpha)
        self.ok = len(xs) >= 3
        if not self.ok:
            return
        pts = np.stack([xs, ys], 1).astype(np.float64)
        c, d, across = principal_axis(pts)
        if axis is not None:
            n = float(np.hypot(*axis))
            if n < 1e-9:
                self.ok = False
                return
            d = np.array([axis[0] / n, axis[1] / n])
            across = np.array([-d[1], d[0]])
        rel = pts - c
        along = rel @ d
        order = np.argsort(along)
        self.c, self.d, self.across = c, d, across
        self.along, self.acr = along[order], (rel @ across)[order]

    def width(self, p: np.ndarray) -> float:
        """Width of the opaque run across the axis through p (the run containing p, or the nearest one); a
        slice with no material at all is replaced by the nearest one that has some."""
        q = p - self.c
        s = float(q @ self.d)
        lo = np.searchsorted(self.along, s - CROSS_BAND, side="left")
        hi = np.searchsorted(self.along, s + CROSS_BAND, side="right")
        if hi <= lo:
            k = int(np.clip(np.searchsorted(self.along, s), 0, len(self.along) - 1))
            if k > 0 and abs(self.along[k - 1] - s) < abs(self.along[k] - s):
                k -= 1
            s = float(self.along[k])
            lo = np.searchsorted(self.along, s - CROSS_BAND, side="left")
            hi = np.searchsorted(self.along, s + CROSS_BAND, side="right")
        v = np.sort(self.acr[lo:hi])
        breaks = np.nonzero(np.diff(v) > CROSS_GAP)[0]
        starts, ends = np.r_[0, breaks + 1], np.r_[breaks, len(v) - 1]
        at = float(q @ self.across)
        gap = np.maximum(v[starts] - at, 0) + np.maximum(at - v[ends], 0)     # 0 for the run containing p
        k = int(gap.argmin())
        return float(v[ends[k]] - v[starts[k]] + 1)        # +1: pixels have extent


def _enter(alpha: np.ndarray, p: np.ndarray, step: np.ndarray) -> np.ndarray:
    """p if it is opaque, else where the ray p + t*step first enters the piece (p when it never does)."""
    if _opaque_at(alpha, *p):
        return p
    h, w = alpha.shape
    for t in np.arange(0.5, float(h + w), 0.5):
        r = p + step * t
        if _opaque_at(alpha, r[0], r[1]):
            return r
    return p


def cross_width(alpha: np.ndarray, p: Tuple[float, float],
                axis: Optional[Tuple[float, float]] = None) -> Optional[float]:
    """The piece's width at p: the extent of the opaque run across `axis` (default: the piece's principal
    axis, the axis_ends direction) through p's position along it. The run that contains p, or the nearest one,
    is measured, so a thumb or a second limb on the same slice does not add to it. A transparent p (a rough
    point just outside the outline) is first moved along the axis (along `axis` itself when given, else toward
    the centroid) to where it enters the material; failing that the nearest slice with material is measured.
    None for an (almost) empty mask or a zero axis. Used for a round end whose snap failed, so it still has a
    width; openings use opening_cross_width."""
    sl = _Slicer(alpha, axis)
    if not sl.ok:
        return None
    p = np.asarray(p, dtype=np.float64)
    step = sl.d if axis is not None or float((sl.c - p) @ sl.d) >= 0 else -sl.d
    return sl.width(_enter(alpha, p, step))


def opening_cross_width(alpha: np.ndarray, p: Tuple[float, float],
                        inward: Tuple[float, float]) -> Optional[float]:
    """An opening's width measured from a rough point p when its snap failed: cross_width across `inward`
    at p (moved onto the piece along `inward` if it is outside), then followed inward over a
    rounded-off rim like snap_opening's (opening_window_width). None for an (almost) empty mask or a zero axis."""
    sl = _Slicer(alpha, inward)
    if not sl.ok:
        return None
    q = _enter(alpha, np.asarray(p, dtype=np.float64), sl.d)
    return opening_window_width(sl.width(q), lambda t: sl.width(q + sl.d * t),
                                lambda t: _opaque_at(alpha, *(q + sl.d * t)))


SNAP_RADIUS_FRAC = 0.6      # search radius = this x the piece's own width (see piece_width)
MIN_ARC_DEG = 120.0         # a round end must show at least this much arc around the fitted centre
MIN_ARC_POINTS = 0.5        # ... and at least this share of the in-radius outline must lie on the circle


@dataclass
class SnapResult:
    at: Tuple[float, float]
    width: Optional[float] = None
    depth: Optional[float] = None


def boundary(alpha: np.ndarray) -> np.ndarray:
    """(N, 2) xy of the opaque pixels that have a transparent 4-neighbour (outside the image counts as transparent)."""
    a = np.asarray(alpha, dtype=bool)
    p = np.pad(a, 1, constant_values=False)
    inner = p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    ys, xs = np.nonzero(a & ~inner)
    return np.stack([xs, ys], 1)


MIN_WIDTH_PIXELS = 20       # fewer opaque pixels than this: no axis to measure, use the box short side
MIN_ELONGATION = 1.5        # principal-axis spread ratio below which the piece has no reliable axis (a boot, a fist)


def piece_width(alpha: np.ndarray) -> float:
    """The piece's own width: the opaque pixels' extent across their principal axis (0.0 for an empty mask).

    Unlike the axis-aligned box, this does not grow when a limb is painted at a tilt. A piece with fewer
    than MIN_WIDTH_PIXELS opaque pixels, or one that is not elongated (its principal axis is
    ill-defined), gets the box's short side instead.
    """
    ys, xs = np.nonzero(alpha)
    if len(xs) == 0:
        return 0.0
    box = float(min(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1))
    if len(xs) < MIN_WIDTH_PIXELS:
        return box
    pts = np.stack([xs, ys], 1).astype(np.float64)
    c = pts.mean(0)
    _, s, vt = np.linalg.svd(pts - c, full_matrices=False)
    if s[0] < MIN_ELONGATION * s[1]:
        return box
    perp = (pts - c) @ vt[1]
    return float(perp.max() - perp.min() + 1)      # +1: pixels have extent


def search_radius(alpha: np.ndarray) -> float:
    """SNAP_RADIUS_FRAC x piece_width(alpha) (0.0 for an empty mask)."""
    return SNAP_RADIUS_FRAC * piece_width(alpha)


def inward_axis(alpha: np.ndarray, p: Tuple[float, float]) -> Tuple[float, float]:
    """Unit vector from p towards the centroid of the opaque pixels."""
    ys, xs = np.nonzero(alpha)
    if len(xs) == 0:
        return (0.0, 1.0)
    v = np.array([xs.mean() - p[0], ys.mean() - p[1]])
    n = float(np.hypot(*v))
    if n < 1e-9:
        return (0.0, 1.0)
    return (float(v[0] / n), float(v[1] / n))


def _opaque_at(alpha: np.ndarray, x: float, y: float) -> bool:
    ix, iy = int(np.floor(x + 0.5)), int(np.floor(y + 0.5))
    h, w = alpha.shape
    return 0 <= ix < w and 0 <= iy < h and bool(alpha[iy, ix])


def snap_round_end(alpha: np.ndarray, p: Tuple[float, float], radius: float) -> Optional[SnapResult]:
    """Fit a circle to the outline within `radius` of p; return its centre and width (2r).

    Returns None unless the fit is trustworthy: >= 12 outline pixels, r within [0.15, 1.5] x radius,
    the points on the circle cover >= 120 degrees of arc and >= half of the in-radius outline, and the
    centre is opaque. Callers use radius = search_radius(alpha).
    """
    b = boundary(alpha).astype(np.float64)
    if len(b) == 0:
        return None
    b = b[np.hypot(b[:, 0] - p[0], b[:, 1] - p[1]) <= radius]
    if len(b) < 12:
        return None
    o = b.mean(0)
    q = b - o
    keep = np.ones(len(q), dtype=bool)

    def fit(sel):
        qs = q[sel]
        if len(qs) < 12:
            return None
        # algebraic (Kasa) fit: x^2 + y^2 + D x + E y + F = 0, on centred coordinates
        A = np.c_[qs[:, 0], qs[:, 1], np.ones(len(qs))]
        rhs = -(qs[:, 0] ** 2 + qs[:, 1] ** 2)
        (D, E, F), *_ = np.linalg.lstsq(A, rhs, rcond=None)
        cx, cy = -D / 2, -E / 2
        r2 = cx * cx + cy * cy - F
        if r2 <= 0:
            return None
        return cx, cy, float(np.sqrt(r2))

    def on_circle(cx, cy, r):
        res = np.abs(np.hypot(q[:, 0] - cx, q[:, 1] - cy) - r)
        return res <= max(1.5, 0.06 * r)

    res_fit = fit(keep)
    for _ in range(6):
        if res_fit is None:
            return None
        # drop outline that is not on the circle (straight sides running off the round end), refit
        nk = on_circle(*res_fit)
        if (nk == keep).all():
            break
        keep = nk
        res_fit = fit(keep)
    else:
        # did not converge: one last trim and refit so the result matches the points we gate on
        if res_fit is None:
            return None
        keep = on_circle(*res_fit)
        res_fit = fit(keep)
    if res_fit is None:
        return None
    cx, cy, r = res_fit
    if not (0.15 * radius <= r <= 1.5 * radius):
        return None
    # fit-quality gate: a real round end shows a good share of the outline on the circle, spread over enough arc
    if keep.sum() < MIN_ARC_POINTS * len(q):
        return None
    ang = np.sort(np.arctan2(q[keep, 1] - cy, q[keep, 0] - cx))
    gaps = np.diff(np.r_[ang, ang[0] + 2 * np.pi])
    if 360.0 - np.degrees(gaps.max()) < MIN_ARC_DEG:
        return None
    centre = (float(cx + o[0]), float(cy + o[1]))
    if not _opaque_at(alpha, *centre):
        return None
    return SnapResult(at=centre, width=2 * r)


def snap_opening(alpha: np.ndarray, p: Tuple[float, float], inward: Tuple[float, float],
                 radius: float, depth_frac: float = 0.35) -> Optional[SnapResult]:
    """Find the rim of an opening near p and measure it.

    Walks from p against `inward` to the piece's edge, steps 0.05*radius back inside, and measures the
    alpha extent perpendicular to `inward` there. `at` is that extent's midpoint; `width` is that extent,
    followed inward over a rounded-off rim by opening_window_width() (the rim's own slice reads narrow),
    `depth` = depth_frac * width. None if p is more than `radius` from any opaque pixel.
    The walk and the extent stop at the first transparent sample, so interior holes cut them short.
    `inward` is trusted as given: callers pass the opening's axis toward its partner point
    (rig_annotations.opening_inward) or, without one, inward_axis(alpha, p); not a guess.
    """
    alpha = np.asarray(alpha, dtype=bool)
    n = float(np.hypot(*inward))
    if n < 1e-9:
        return None
    d = np.array([inward[0] / n, inward[1] / n])
    perp = np.array([-d[1], d[0]])
    p = np.array(p, dtype=np.float64)
    h, w = alpha.shape
    step = 0.25

    # nearest opaque pixel within radius (None -> reject)
    x0, x1 = max(0, int(p[0] - radius) - 1), min(w, int(p[0] + radius) + 2)
    y0, y1 = max(0, int(p[1] - radius) - 1), min(h, int(p[1] + radius) + 2)
    ys, xs = np.nonzero(alpha[y0:y1, x0:x1])
    if len(xs) == 0:
        return None
    dist = np.hypot(xs + x0 - p[0], ys + y0 - p[1])
    k = int(dist.argmin())
    if dist[k] > radius:
        return None

    # start on opaque material: p itself, or where the inward ray from p first hits it, else the nearest pixel
    start = p
    if not _opaque_at(alpha, *p):
        start = None
        t = 0.0
        while t <= radius:
            t += step
            if _opaque_at(alpha, *(p + d * t)):
                start = p + d * t
                break
        if start is None:
            start = np.array([xs[k] + x0, ys[k] + y0], dtype=np.float64)

    # walk against inward to the last opaque sample: the rim
    t = 0.0
    limit = float(h + w)
    while t < limit and _opaque_at(alpha, *(start - d * (t + step))):
        t += step
    rim = start - d * t
    q = rim + d * (0.05 * radius)

    # alpha extent perpendicular to inward through a point
    def reach(c, sign):
        s = 0.0
        while s < limit and _opaque_at(alpha, *(c + sign * perp * (s + step))):
            s += step
        return s + step / 2   # the edge lies within one step past the last opaque sample
    lo, hi = reach(q, -1), reach(q, +1)
    mid = q + perp * (hi - lo) / 2
    sl = _Slicer(alpha, tuple(d))                    # the window's slices, measured from the sorted pixels
    width = opening_window_width(lo + hi, lambda t: sl.width(q + d * t), lambda t: _opaque_at(alpha, *(q + d * t)))
    return SnapResult(at=(float(mid[0]), float(mid[1])), width=float(width), depth=float(depth_frac * width))


ROUNDOFF_STEP = 3.0     # px between the slices that follow a rounded-off rim inward
ROUNDOFF_SLOPE = 0.5    # ... while the width still grows by at least this many px per px inward
ROUNDOFF_MAX = 0.5      # ... and at most this x the width reached so far
ROUNDOFF_CAP = 1.6      # the window's width never exceeds this x the rim's own width


def opening_window_width(rim_width: float, width_at, inside) -> float:
    """The opening's width, following a rounded-off rim inward. A painted rim is often rounded (a leg's
    bottom, a cuff drawn as an ellipse), so the slice at the rim reads narrow. Walk inward in ROUNDOFF_STEP px
    steps while the width grows steeply (>= ROUNDOFF_SLOPE px per px: still on the round-off) and stop as soon
    as it levels off, so a straight cuff keeps its rim width. A piece that keeps flaring steeply (a hand or
    boot widening further in) is followed too, but only as far as ROUNDOFF_CAP x the rim width (the result
    is clamped there) and ROUNDOFF_MAX x the width in depth. width_at(t) measures the slice t px inward,
    inside(t) says whether its centre is on the piece."""
    width, t = rim_width, ROUNDOFF_STEP
    cap = ROUNDOFF_CAP * rim_width
    while t <= ROUNDOFF_MAX * width and inside(t):
        nxt = width_at(t)
        if nxt - width < ROUNDOFF_SLOPE * ROUNDOFF_STEP:
            break
        if nxt >= cap:
            return cap
        width, t = nxt, t + ROUNDOFF_STEP
    return width
