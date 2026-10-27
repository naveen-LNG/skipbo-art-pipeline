"""pro_mesh.py - mesh layouts for spine_pro.py, in attachment-image pixels.

Two layouts, both an R x C lattice of vertices (so the animator gets a clean quad mesh with the hull first, as the
Spine editor builds them):
  strip(...)  rows perpendicular to a polyline (a tail's medial axis, a torso's spine), each row as wide as the
              alpha beside it plus a margin; rows can be forced onto given arc positions so that bone pivots sit on
              vertex rows (Arman: "bones sit on vertex rows")
  grid(...)   an axis-aligned grid over the alpha's bounding box, with lines forced through given points (ear pivots)
The images are padded when a vertex falls outside them (pad_image), so every uv lies inside its image.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image


def lattice(P: np.ndarray) -> tuple:
    """P: (R, C, 2) vertex positions. Returns (points (n, 2) with the hull first, triangles (m, 3), hull count).
    Hull order: row 0 left to right, last column down, last row right to left, first column up."""
    R, C = P.shape[:2]
    hull = [(0, j) for j in range(C)] + [(i, C - 1) for i in range(1, R)] + \
           [(R - 1, j) for j in range(C - 2, -1, -1)] + [(i, 0) for i in range(R - 2, 0, -1)]
    inner = [(i, j) for i in range(1, R - 1) for j in range(1, C - 1)]
    order = hull + inner
    idx = {rc: k for k, rc in enumerate(order)}
    pts = np.array([P[i, j] for i, j in order], dtype=float)
    tris = []
    for i in range(R - 1):
        for j in range(C - 1):
            a, b, c, d = idx[(i, j)], idx[(i, j + 1)], idx[(i + 1, j)], idx[(i + 1, j + 1)]
            tris += [(a, b, d), (a, d, c)]
    return pts, np.array(tris, dtype=int), len(hull)


def signed_areas(pts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    p = pts[tris]
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    return 0.5 * (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])


def _arc(P: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])


def point_at(P: np.ndarray, s: float) -> tuple:
    """Point and unit tangent at arc length s along polyline P (extrapolated straight past both ends)."""
    S = _arc(P)
    k = int(np.clip(np.searchsorted(S, s) - 1, 0, len(P) - 2))
    seg = P[k + 1] - P[k]
    L = max(1e-9, np.linalg.norm(seg))
    tang = seg / L
    return P[k] + tang * (s - S[k]), tang


def smooth_tangent(P: np.ndarray, s: float, win: float) -> np.ndarray:
    ts = [point_at(P, s + d)[1] for d in np.linspace(-win, win, 5)]
    t = np.mean(ts, axis=0)
    return t / max(1e-9, np.linalg.norm(t))


def project(P: np.ndarray, pts: np.ndarray) -> tuple:
    """Arc position s and signed distance d (left of the direction of travel positive) of each point on polyline P;
    the first and last segments extend past the ends."""
    S = _arc(P)
    best_d = np.full(len(pts), np.inf)
    s_out, d_out = np.zeros(len(pts)), np.zeros(len(pts))
    for k in range(len(P) - 1):
        a, b = P[k], P[k + 1]
        seg = b - a
        L2 = max(1e-9, float(seg @ seg))
        t = ((pts - a) @ seg) / L2
        lo = -np.inf if k == 0 else 0.0
        hi = np.inf if k == len(P) - 2 else 1.0
        t = np.clip(t, lo, hi)
        foot = a + t[:, None] * seg
        diff = pts - foot
        dist = np.linalg.norm(diff, axis=1)
        better = dist < best_d
        L = math.sqrt(L2)
        sign = np.sign(seg[0] * diff[:, 1] - seg[1] * diff[:, 0])
        best_d = np.where(better, dist, best_d)
        s_out = np.where(better, S[k] + t * L, s_out)
        d_out = np.where(better, sign * dist, d_out)
    return s_out, d_out


def alpha_points(alpha: np.ndarray, step: int = 2, thr: int = 16) -> np.ndarray:
    ys, xs = np.nonzero(alpha[::step, ::step] > thr)
    return np.stack([xs * step + 0.5 * step, ys * step + 0.5 * step], 1).astype(float)


def medial_axis(alpha: np.ndarray, root, tip, n: int = 6) -> np.ndarray:
    """A polyline from root to tip through the centroids of the alpha's slices across the root->tip line."""
    pts = alpha_points(alpha)
    root, tip = np.asarray(root, float), np.asarray(tip, float)
    P0 = np.stack([root, tip])
    s, d = project(P0, pts)
    L = np.linalg.norm(tip - root)
    u = (tip - root) / max(1e-9, L)
    nrm = np.array([-u[1], u[0]])
    out = [root]
    for k in range(1, n):
        c = L * k / n
        sel = np.abs(s - c) < L / (2 * n)
        off = float(np.median(d[sel])) if sel.sum() > 10 else 0.0
        out.append(root + u * c + nrm * off)
    out.append(tip)
    P = np.array(out)
    # light smoothing of the interior points
    Q = P.copy()
    for k in range(1, len(P) - 1):
        Q[k] = 0.25 * P[k - 1] + 0.5 * P[k] + 0.25 * P[k + 1]
    return Q


def strip(alpha: np.ndarray, P: np.ndarray, row_s: list, cols: int, margin: float) -> tuple:
    """Rows of `cols` vertices perpendicular to polyline P at arc positions row_s (image px). Each row reaches the alpha
    beside it (+ margin) on both sides. Returns (lattice (R, C, 2), ok) where ok = no quad folds."""
    pts = alpha_points(alpha)
    s, d = project(P, pts)
    row_s = sorted(row_s)
    gaps = np.diff(row_s)
    left, right = [], []
    for i, rs in enumerate(row_s):
        w = max(gaps[max(0, i - 1)] if len(gaps) else 1.0, gaps[min(len(gaps) - 1, i)] if len(gaps) else 1.0)
        sel = np.abs(s - rs) <= w
        left.append(max(float(d[sel].max(initial=0.0)), 0.0) + margin)
        right.append(max(float(-d[sel].min(initial=0.0)), 0.0) + margin)
    left = np.maximum.reduce([np.array(left), np.roll(left, 1), np.roll(left, -1)])
    right = np.maximum.reduce([np.array(right), np.roll(right, 1), np.roll(right, -1)])
    win = (row_s[-1] - row_s[0]) / max(4, len(row_s))
    rows = []
    for i, rs in enumerate(row_s):
        c, _ = point_at(P, rs)
        t = smooth_tangent(P, rs, win)
        n = np.array([-t[1], t[0]])
        rows.append([c + n * (-right[i] + (left[i] + right[i]) * j / (cols - 1)) for j in range(cols)])
    L = np.array(rows)
    pts_, tris, _ = lattice(L)
    a = signed_areas(pts_, tris)
    ok = bool((a > 0).all() or (a < 0).all())
    return L, ok


def grid(alpha: np.ndarray, nx: int, ny: int, margin: float, force: list = ()) -> np.ndarray:
    """An (ny, nx) lattice over the alpha's bounding box (+ margin), lines moved onto the forced points' x and y."""
    ys, xs = np.nonzero(alpha > 16)
    x0, x1 = xs.min() - margin, xs.max() + 1 + margin
    y0, y1 = ys.min() - margin, ys.max() + 1 + margin
    gx, gy = list(np.linspace(x0, x1, nx)), list(np.linspace(y0, y1, ny))
    for fx, fy in force:
        for g, f in ((gx, fx), (gy, fy)):
            if g[0] < f < g[-1]:
                k = 1 + int(np.argmin([abs(v - f) for v in g[1:-1]]))
                g[k] = f
    gx, gy = sorted(gx), sorted(gy)
    return np.array([[(x, y) for x in gx] for y in gy], dtype=float)


def pad_image(img: Image.Image, pts: np.ndarray, extra: int = 2) -> tuple:
    """Pad img (transparent) so every point lies inside; returns (padded image, (dx, dy) shift added to px coords)."""
    W, H = img.size
    lo = np.floor(pts.min(0)).astype(int)
    hi = np.ceil(pts.max(0)).astype(int)
    dx, dy = max(0, -lo[0] + extra), max(0, -lo[1] + extra)
    W2, H2 = max(W + dx, hi[0] + dx + extra), max(H + dy, hi[1] + dy + extra)
    if (dx, dy, W2, H2) == (0, 0, W, H):
        return img, (0, 0)
    out = Image.new("RGBA", (int(W2), int(H2)), (0, 0, 0, 0))
    out.paste(img, (int(dx), int(dy)))
    return out, (int(dx), int(dy))
