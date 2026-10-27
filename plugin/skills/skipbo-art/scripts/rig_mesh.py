#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""rig_mesh.py - a whole-sleeve drawing (annotation role `arm`) as a two-bone weighted Spine mesh (spine_rig.py).

The strip (strip):
  - rows across the sleeve's axis (shoulder -> wrist, image px), from beyond the shoulder end to beyond the cuff: every
    ROW_NEAR x sleeve width within ROWS_NEAR of the elbow (23 rows, the bend bands), every ROW_MID out to ROWS_MID,
    then ROW_FAR;
  - two vertices per row on the sleeve's outline (the alpha's extent across the axis over the row and its neighbours,
    1 px out, so the straight edges between rows never cut a painted pixel), the elbow's row through the elbow point;
  - every vertex lies on the hull: Spine's hull order (left column shoulder -> cuff, right column back up), and two
    triangles per pair of rows.
The width fit (width_fit, fitted): a sleeve sheet paints at its own proportions (the fox's sleeve is fatter for its
length than the master's), so each half's thickness is measured on the master across its axis (shoulder -> elbow at
FIT_FRACS["upper"], elbow -> wrist above the cuff at FIT_FRACS["lower"]) and the bind geometry (not the texture) is
scaled across the strip's axis to it: factor = master / sleeve thickness, clamped to WIDTH_FIT_MIN..1 (never
widened; below the clamp spine_rig raises sleeve_too_wide), the two halves' factors and offsets blended across the
elbow over +-FIT_BLEND sleeve widths. When both halves are measured each is centred on the master's tube (which runs
on through the elbow); when either is not, neither moves sideways - each scales about the drawing's own tube centre -
so there is no sideways jog at the elbow. A master edge is where the colour steps to something else (or the
background starts; a step back into the same cloth - a knit ripple, shading - is not one); an edge whose far side is
a part drawn over the sleeve (a vest, straps, a sweater body of the same yarn: `above`) hides the sleeve's own unless
a crease shows at that part's outline, so such a sample is not measured, and a half with fewer than FIT_MIN_SAMPLES
measured samples is left as painted. Along the axis nothing moves: the length still comes from the joint line-up.
The motion (choose): with the forearm turned by phi (degrees, its rotation from the setup pose, Spine's counterclockwise)
each vertex turns by phi about its own centre: P = P0 + (R(phi) - I) u. Plain linear blend skinning is u = w (P0 - O),
w the forearm weight, O the elbow (the forearm bone's origin). A wide bend folds the inner side of the elbow there
(spec: a +-0.5-width smoothstep folds from ~70 deg), and LBS pulls the outer side of a wide bend in onto the chord (an
angular outer elbow), so:
  - DEFAULT (both columns +-0.5, no shift: the spec's weights) is used when it keeps every triangle's orientation over
    the needed elbow range (the largest bend any animation uses + FOLD_MARGIN, each way);
  - else the smooth design (smooth): each vertex's u is the least-squares fit, over the needed range in FIT_STEP
    steps (the bends within HOLD_SPREAD of the animations' holds weighted HOLD_WEIGHT more), of a tube bent like a
    beam over a band (x sleeve width around the elbow, converted to setup units by units_per_px; band_px caps its top
    at the shoulder point, so the rows above it never move): its centre line turns smoothly (smoothstep) through the
    band, cross-sections stay square to it, the line that keeps its length sits NEUTRAL x the half width toward the
    inside of each bend (the outer side stretches into a round elbow), and the forearm beyond the band turns exactly
    with its bone. Each column is the inside of one bend and the outside of the other, so the fit gives each vertex
    a centre that rounds its outside in one direction and tucks it in the other, from the static binds alone. (A
    vertex can only circle its centre at the elbow's rate, so it moves as far bending in as bending out: past ~80
    deg the fit alone can fold the inside of the bend.) The crease fill (fill_crease) then pushes the inner edge out
    to the corner where the upper arm's and forearm's inner sides meet, refitting FILL_ROUNDS times, so no gap opens
    in the crease (notch: what lies behind would show there). A smooth design must keep every triangle at AREA_KEEP
    of its setup area and the elbow pivot inside the bent outline (pivot_kept: spine_qa's joints check); when the
    filled one does not, the plain one is tried, and when that folds too, a fold-free grid design below is blended in
    (without the fill), its share a bump around the elbow (blend), the least that is fold-free over the need, against
    the first PARTNERS grid designs. Bands (SMOOTH_BANDS, their tops at most BAND_REACH of the way up to the shoulder)
    are tried shortest first: a closed crease (notch <= NOTCH_MAX at the holds) beats an open one, then a longer band
    wins only by rounding the outer elbow (corner) by more than CORNER_TIE degrees - so the bend stays at the elbow
    instead of bowing the upper arm from the shoulder;
  - the grid (choose_grid) is the fallback and the blend partner: each column (each side of the sleeve) gets its band
    [lo, hi] over which w runs 0 -> 1 (smoothstep) and its pivot shift k: the column turns about Q = O + k (E_col - O)
    instead of O (E_col: that column's vertex on the elbow row), which fans the inner side of a bend about its corner
    instead of pushing it through itself; below the band the pivot slides back to O over FADES sleeve widths (1, or
    0.5 for a short forearm), so the cuff turns with the forearm bone. The cheapest grid design (narrowest bands, then
    the smallest shifts) that is fold-free, else the one that covers the most (a doubt for spine_rig).
Spine's weights (attachment): a vertex is bound to both bones, upper arm (1 - omega) and forearm (omega), with bind
positions chosen so that sum(weight x bone x bind) is exactly P0 at the setup pose and P0 + (R - I) u when the forearm
turns. omega gives each triangle to the bone on its side of the elbow row (spine_qa splits a mesh's pixels by the
largest mean weight): <= 0.45 above it, 0.5 on it, >= 0.55 below it (a vertex that moves with only one bone is bound
to that bone alone).
Coordinates: image px (x right, y down) for the drawing; the setup positions P0, O and bone frames are Spine units
(y up), already placed by the caller.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image

ROWS_NEAR, ROW_NEAR = 1.1, 0.1      # x sleeve width: dense rows within this of the elbow (the bend bands), this far apart
ROWS_MID, ROW_MID = 1.8, 0.3
ROW_FAR = 0.5
OUTLINE_PAD = 1.0                   # px outside the painted extent
FOLD_MARGIN = 10.0                  # deg beyond the largest bend the animations use
FADES = (1.0, 0.5)                  # x sleeve width below a shifted column's band over which its pivot returns to O
OMEGA_SPLIT = (0.45, 0.5, 0.55)     # Spine weight caps above / on / below the elbow row
OMEGA_EDGE = 0.05                   # a shifted vertex that still needs both bones keeps this much of each
DEFAULT = ((0.0, -0.5, 0.5), (0.0, -0.5, 0.5), 1.0)  # per column (left, right): (pivot shift k, band lo, band hi); fade
GRID_K = (0.0, 0.5, 0.8, 1.0)
GRID_LO = (0.0, -0.3, -0.6, -0.9, -1.2, -1.5, -1.8)   # plus 0.1 below the shoulder (a short upper arm's widest band)
GRID_HI = (0.1, 0.3, 0.6, 0.9)
# x sleeve width around the elbow (band_px caps them at the shoulder point and the wrist)
SMOOTH_BANDS = tuple((lo, hi) for lo in (-0.8, -1.0, -1.2, -1.4) for hi in (0.6, 0.8, 1.0))
BAND_REACH = 0.85                   # a band's top reaches at most this share of the way up from elbow to shoulder
NEUTRAL = 0.8                       # x half width: the bend's length-keeping line, toward the inside of each bend
CREASE_FILL = 0.0                   # x width past the crease corner its fill aims (None: no fill)
NOTCH_MAX = 0.01                    # x width: a crease left open by more than this at a hold (notch) is a gap
FILL_SPREAD = 2.0                   # rows: the reach of the crease fill's bump (fill_crease)
HOLD_WEIGHT = 16.0                  # extra least-squares weight on the bends near the animations' holds
HOLD_SPREAD = 12.0                  # deg: how far either side of a hold its extra weight reaches
FILL_ROUNDS = 4                     # refits that push the crease fill into the least-squares motion
FIT_STEP = 4.0                      # deg between the bends the smooth design is fitted at
BLEND_SIGMAS = (0.25, 0.4, 0.6, 1.0, None)   # x sleeve width: how far from the elbow the grid's share reaches
BLEND_STEP = 0.05                   # the grid's peak share grows in these steps
PARTNERS = 12                       # fold-free grid designs tried as the smooth design's blend partner
AREA_KEEP = 0.05                    # a smooth design's triangles keep this x their setup area over the need
PIVOT_MARGIN = 0.12                 # x sleeve width: the elbow pivot stays this far inside the bent outline
CORNER_ROWS = 1.2                   # x sleeve width around the elbow: the rows whose outline corner() judges
CORNER_TIE = 2.0                    # deg: a longer band must round the elbow by more than this to beat a shorter one
WIDTH_FIT_MIN = 0.65                # a sleeve half is narrowed to at most this (sleeve_too_wide beyond); never widened
SLEEVE_THIN = 1.2                   # master / drawing thickness above this: the drawing is too thin and is NOT widened
                                    # (sleeve_too_thin): the cuff then reads smaller than the hand (the beaver: 1.34;
                                    # the approved fox 1.07, moose 1.15)
FIT_FRACS = {"upper": (0.4, 0.5, 0.6), "lower": (0.25, 0.35, 0.45)}   # along shoulder->elbow, elbow->wrist (above the cuff)
FIT_MIN_SAMPLES = 2
FIT_BLEND = 0.5                     # x sleeve width each side of the elbow over which the halves' fits blend
EDGE_STEP, EDGE_JUMP, EDGE_SAME = 3, 0.12, 0.25   # px back; RGB (0..1) step that is an edge; far side "the same cloth"


@dataclass
class Strip:
    """A sleeve's vertex strip. ts: row offsets along the axis from the elbow (image px, toward the wrist positive);
    uv: (2N, 2) image px in hull order (left column rows 0..N-1, then the right column rows N-1..0); triangles: flat
    vertex indices; width: the sleeve's width at the elbow (px); t_shoulder, t_wrist: the joints' offsets."""
    ts: np.ndarray
    uv: np.ndarray
    triangles: list
    width: float
    t_shoulder: float
    t_wrist: float
    axis: tuple

    def row(self) -> np.ndarray:
        """Row index of every vertex (hull order)."""
        n = len(self.ts)
        return np.concatenate([np.arange(n), np.arange(n)[::-1]])

    def col(self) -> np.ndarray:
        n = len(self.ts)
        return np.concatenate([np.zeros(n, int), np.ones(n, int)])


@dataclass
class Motion:
    """The chosen design and its motion: P0 (2N, 2) setup positions, u (2N, 2) levers, w (2N,) forearm weights
    (motion), q (2N,) the share of the column's pivot shift still applied; covered: the fold-free (lo, hi) degrees
    found (capped at the need), ok: covers the need."""
    design: tuple
    P0: np.ndarray
    u: np.ndarray
    w: np.ndarray
    q: np.ndarray
    covered: tuple
    ok: bool


def _unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-9)


def smoothstep(x) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def row_offsets(t_lo: float, t_hi: float, w: float) -> np.ndarray:
    """Row offsets (px from the elbow along the axis): t_lo and t_hi themselves (the strip's ends), the elbow row 0,
    every ROW_NEAR x w within ROWS_NEAR x w, ROW_MID x w out to ROWS_MID x w, then ROW_FAR x w; rows closer than
    ROW_NEAR / 2 x w to an end are dropped."""
    ts = set()
    for sgn, end in ((-1, t_lo), (1, t_hi)):
        x = 0.0
        while True:
            step = ROW_NEAR if x < ROWS_NEAR - 1e-9 else ROW_MID if x < ROWS_MID - 1e-9 else ROW_FAR
            x = round(x + step, 6)
            if x * w >= abs(end) - 0.5 * ROW_NEAR * w:
                break
            ts.add(sgn * x * w)
    ts.add(0.0)
    return np.array(sorted([t_lo] + [t for t in ts if t_lo < t < t_hi] + [t_hi]))


def strip(alpha: np.ndarray, S, E, W) -> Strip:
    """The vertex strip of a sleeve drawing (alpha: H x W bool, painted pixels) with shoulder S, elbow E, wrist W
    (image px). The axis runs S -> W; the elbow row crosses it at E's projection."""
    S, E, W = (np.asarray(p, float) for p in (S, E, W))
    u = _unit(W - S)
    n = np.array([u[1], -u[0]])                         # across: image right for a sleeve hanging down
    E = S + u * float((E - S) @ u)                    # the elbow row crosses the axis
    ys, xs = np.nonzero(alpha)
    P = np.stack([xs + 0.5, ys + 0.5], 1)
    t, s = (P - E) @ u, (P - E) @ n
    mid = np.abs(t) <= 1.0
    width = float(np.ptp(s[mid]) + 1.0) if mid.any() else float(np.ptp(s) + 1.0)
    ts = row_offsets(float(t.min()) - OUTLINE_PAD, float(t.max()) + OUTLINE_PAD, width)
    N = len(ts)
    left, right = np.zeros(N), np.zeros(N)
    for k in range(N):
        a, b = ts[max(0, k - 1)], ts[min(N - 1, k + 1)]
        sel = (t >= a) & (t <= b)
        if not sel.any():                              # a gap in the drawing: the nearest painted pixels' extent
            sel = np.abs(t - ts[k]) <= np.abs(t - ts[k]).min() + 1.0
        left[k], right[k] = s[sel].min() - OUTLINE_PAD, s[sel].max() + OUTLINE_PAD
    h, w_ = alpha.shape
    Lp = E + ts[:, None] * u + left[:, None] * n
    Rp = E + ts[:, None] * u + right[:, None] * n
    uv = np.concatenate([Lp, Rp[::-1]])
    uv = np.stack([np.clip(uv[:, 0], 0, w_), np.clip(uv[:, 1], 0, h)], 1)
    L = lambda k: k                                     # noqa: E731
    R = lambda k: 2 * N - 1 - k                         # noqa: E731
    tris = []
    for k in range(N - 1):
        tris += [L(k), R(k), L(k + 1), R(k), R(k + 1), L(k + 1)]
    return Strip(ts, uv, tris, width, float((S - E) @ u), float((W - E) @ u), (tuple(u), tuple(n)))


# ------------------------------------------------------------------ the width fit

def axis_frame(S, E, W) -> tuple:
    """(origin, u, n): the strip's axis frame in image px - u along S -> W, n across it (image right for a sleeve
    hanging down), the origin where the elbow row crosses the axis."""
    S, E, W = (np.asarray(p, float) for p in (S, E, W))
    u = _unit(W - S)
    return S + u * float((E - S) @ u), u, np.array([u[1], -u[0]])


def _edge(rgb: np.ndarray, fg: np.ndarray, C, n, ref, reach: float, above) -> float | None:
    """Distance (px) from C along unit n to the sleeve's edge on the master: the background starts, or the colour
    steps by more than EDGE_JUMP over EDGE_STEP px to something that is not the same cloth (within EDGE_SAME of the
    sleeve's colour ref: a step back into the same cloth is a ripple - knit, shading - and the walk goes on). Against
    a part drawn over the sleeve (`above`) a step to the same cloth is a crease or seam, an edge, but only within
    2 x EDGE_STEP of where the walk goes in under that part: a step found deeper in is the part's own shading, not
    the sleeve's edge. None when that edge is hidden: the step's far side is such a part and not the same cloth, the
    walk goes that far in under one with no crease, it starts on one (the sample point is not on the visible
    sleeve), or it leaves the picture / reach.
    A heuristic on painted colour, with known limits: a strong highlight or shadow band inside the sleeve (a step
    over EDGE_JUMP to beyond EDGE_SAME) reads as an edge and under-measures; a sleeve painted the same colour as what
    lies next to it (within EDGE_SAME, with no stronger outline) is walked past and over-measures (never widened: a
    factor caps at 1); and a neighbour within EDGE_SAME of the sleeve's colour counts as the same cloth even when it
    is another part."""
    H, W_ = fg.shape

    def at(d):
        x, y = int(math.floor(C[0] + d * n[0])), int(math.floor(C[1] + d * n[1]))
        return (y, x) if 0 <= x < W_ and 0 <= y < H else None

    def over(q):
        return above is not None and bool(above[q])

    p = at(0)
    if p is None or not fg[p] or over(p):
        return None
    back = [rgb[p]] * EDGE_STEP
    under = None                                           # where the walk went in under a part drawn over the sleeve
    for d in range(1, int(reach) + 1):
        q = at(d)
        if q is None:
            return None
        if not fg[q]:
            return d - 0.5
        if over(q):
            under = d if under is None else under
            if d - under > 2 * EDGE_STEP:                  # past the part's outline: the sleeve's own edge is hidden
                return None
        c = rgb[q]
        if float(np.linalg.norm(c - back[-EDGE_STEP])) > EDGE_JUMP:
            b = at(d + 2 * EDGE_STEP)                      # the far side of the step
            if b is None:
                return None
            same = bool(fg[b]) and float(np.linalg.norm(rgb[b] - ref)) < EDGE_SAME
            if over(b) and fg[b] and not same:
                return None
            if same and not over(b):                       # a ripple in the cloth (knit, shading), not an edge
                back.append(c)
                continue
            # the edge: half way through the step from the inside colour to the far side's (an anti-aliased ramp)
            c_in, c_out = back[-EDGE_STEP], rgb[b]
            half = 0.5 * float(np.linalg.norm(c_out - c_in))
            for e in range(max(1, d - EDGE_STEP), d + 2 * EDGE_STEP + 1):
                qe = at(e)
                if not fg[qe] or float(np.linalg.norm(rgb[qe] - c_in)) >= half:
                    return e - 0.5
            return d - 0.5
        back.append(c)
    return None


def master_edges(rgb: np.ndarray, fg: np.ndarray, A, B, f: float, above=None) -> tuple | None:
    """(lo, hi): the master sleeve's edges across A -> B (master px) at A + f (B - A), signed along n = (u_y, -u_x)
    from that point; None when either edge is hidden (_edge). rgb: H x W x 3 in 0..1, fg: the master's silhouette,
    above: the pixels of parts drawn over the sleeve (or None)."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    u = _unit(B - A)
    n = np.array([u[1], -u[0]])
    C = A + f * (B - A)
    x0, y0 = int(math.floor(C[0])), int(math.floor(C[1]))
    patch = rgb[max(0, y0 - 4): y0 + 5, max(0, x0 - 4): x0 + 5].reshape(-1, 3)
    if not len(patch):
        return None
    ref = np.median(patch, 0)
    reach = float(np.linalg.norm(B - A))
    hi, lo = _edge(rgb, fg, C, n, ref, reach, above), _edge(rgb, fg, C, -n, ref, reach, above)
    return None if hi is None or lo is None else (-lo, hi)


def width_fit(rgb: np.ndarray, fg: np.ndarray, M: tuple, alpha: np.ndarray, I: tuple, gs: float, above=None) -> dict:
    """Each half's across-axis fit of a sleeve drawing (alpha, its shoulder / elbow / wrist I = (S, E, W) image px) to
    the master's sleeve (M = its shoulder / elbow / wrist, master px; gs: master px per drawing px across the axis).
    Per half {"factor", "offset_px" (image px along n: where the narrowed tube's centre moves), "raw" (master /
    drawing thickness, the median over the measured samples; None when fewer than FIT_MIN_SAMPLES), "samples"}, plus
    the axis frame and the elbow blend half-width (image px) that fitted() needs."""
    S, E, W = (np.asarray(p, float) for p in I)
    Ms, Me, Mw = (np.asarray(p, float) for p in M)
    O, u, n = axis_frame(S, E, W)
    ys, xs = np.nonzero(alpha)
    P = np.stack([xs + 0.5, ys + 0.5], 1)
    t, s = (P - O) @ u, (P - O) @ n
    mid = np.abs(t) <= 1.0
    width = float(np.ptp(s[mid]) + 1.0) if mid.any() else float(np.ptp(s) + 1.0)
    out = {"frame": {"origin": O.tolist(), "u": u.tolist(), "n": n.tolist()}, "blend_px": FIT_BLEND * width}
    got_ = {}
    for half, (a, b, ma, mb) in (("upper", (S, E, Ms, Me)), ("lower", (E, W, Me, Mw))):
        got = []
        for f in FIT_FRACS[half]:
            me = master_edges(rgb, fg, ma, mb, f, above)
            Q = a + f * (b - a)
            sel = np.abs(t - float((Q - O) @ u)) <= 1.5
            if me is None or not sel.any():
                continue
            off = float((Q - O) @ n)                       # the half's own axis against the strip's, here
            e_lo, e_hi = off + me[0] / gs, off + me[1] / gs
            s_lo, s_hi = float(s[sel].min()), float(s[sel].max()) + 1.0
            got.append(((e_hi - e_lo) / (s_hi - s_lo), (e_lo + e_hi) / 2, (s_lo + s_hi) / 2))
        got_[half] = got
    # Re-centring: only when both halves are measured (each onto the master's tube, which runs on through the
    # elbow); otherwise each half scales about the drawing's own tube centre, so neither half jogs sideways.
    both = all(len(g) >= FIT_MIN_SAMPLES for g in got_.values())
    for half, got in got_.items():
        raw = float(np.median([g[0] for g in got])) if len(got) >= FIT_MIN_SAMPLES else None
        k = 1.0 if raw is None or raw >= 1.0 else max(raw, WIDTH_FIT_MIN)
        if both:
            off = float(np.median([c_e - k * c_s for _, c_e, c_s in got]))
        else:
            off = float(np.median([(1 - k) * c_s for _, _, c_s in got])) if got and k < 1.0 else 0.0
        out[half] = {"factor": k, "offset_px": off, "raw": raw, "samples": len(got)}
    return out


def fitted(P: np.ndarray, fit: dict | None) -> np.ndarray:
    """Image points P (k x 2) moved across the strip's axis by a width fit: s -> factor x s + offset, each half's,
    blended (smoothstep) over +-blend_px around the elbow row; along the axis nothing moves."""
    P = np.asarray(P, float)
    if not fit:
        return P.copy()
    O, u, n = (np.asarray(fit["frame"][k], float) for k in ("origin", "u", "n"))
    t, s = (P - O) @ u, (P - O) @ n
    w = smoothstep((t + fit["blend_px"]) / (2 * fit["blend_px"]))
    up, lo = fit["upper"], fit["lower"]
    k = (1 - w) * up["factor"] + w * lo["factor"]
    b = (1 - w) * up["offset_px"] + w * lo["offset_px"]
    return O + t[:, None] * u + (k * s + b)[:, None] * n


def fit_image(img: Image.Image, fit: dict | None) -> Image.Image:
    """The drawing as fitted() moves it (nearest pixel): the placed sleeve's mask, for placement and draw-order
    geometry; the texture itself is never resampled (the mesh's bind positions carry the fit)."""
    if not fit:
        return img
    a = np.asarray(img.convert("RGBA"))
    H, W_ = a.shape[:2]
    O, u, n = (np.asarray(fit["frame"][k], float) for k in ("origin", "u", "n"))
    yy, xx = np.mgrid[:H, :W_] + 0.5
    Q = np.stack([xx.ravel(), yy.ravel()], 1)
    t, s2 = (Q - O) @ u, (Q - O) @ n
    w = smoothstep((t + fit["blend_px"]) / (2 * fit["blend_px"]))
    up, lo = fit["upper"], fit["lower"]
    k = (1 - w) * up["factor"] + w * lo["factor"]
    b = (1 - w) * up["offset_px"] + w * lo["offset_px"]
    src = O + t[:, None] * u + ((s2 - b) / k)[:, None] * n
    xi, yi = np.floor(src[:, 0]).astype(int), np.floor(src[:, 1]).astype(int)
    ok = (xi >= 0) & (xi < W_) & (yi >= 0) & (yi < H)
    out = np.zeros_like(a).reshape(-1, 4)
    out[ok] = a[yi[ok], xi[ok]]
    return Image.fromarray(out.reshape(H, W_, 4), "RGBA")


# ------------------------------------------------------------------ motion and folds

def motion(st: Strip, design: tuple, Pu: np.ndarray, Pf: np.ndarray, O) -> tuple:
    """(P0, u, w, q) of a design. Pu, Pf: (2N, 2) where the upper-arm and forearm placements put each vertex at the
    setup pose; O: the elbow (forearm bone origin), Spine units."""
    O = np.asarray(O, float)
    rows, cols = st.row(), st.col()
    t = st.ts[rows] / st.width
    k = np.array([design[c][0] for c in cols])
    lo = np.array([design[c][1] for c in cols])
    hi = np.array([design[c][2] for c in cols])
    w = smoothstep((t - lo) / (hi - lo))
    q = np.where(k > 0, 1.0 - smoothstep((t - hi) / design[2]), 0.0)
    P0 = (1 - w)[:, None] * Pu + w[:, None] * Pf
    n, e = len(st.ts), int(np.argmin(np.abs(st.ts)))           # the elbow row's left and right vertices
    corner = np.where((cols == 0)[:, None], P0[e], P0[2 * n - 1 - e])
    Q = O + (corner - O) * (k * q)[:, None]
    u = w[:, None] * (P0 - Q)
    return P0, u, w, q


def _areas(P: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Signed areas of triangles over a stack of poses: P (..., V, 2) -> (..., T)."""
    a, b, c = P[..., tris[:, 0], :], P[..., tris[:, 1], :], P[..., tris[:, 2], :]
    e1, e2 = b - a, c - a
    return e1[..., 0] * e2[..., 1] - e1[..., 1] * e2[..., 0]


def coverage(P0: np.ndarray, u: np.ndarray, tris, need: tuple, keep: float = 0.0) -> tuple:
    """(lo, hi): how far (degrees, from 0 toward need[0] <= 0 and toward need[1] >= 0, in 1-degree steps and at the
    need itself) the elbow turns before a triangle's signed area changes sign or vanishes (spine_qa's mesh_fold) - or,
    with keep > 0, shrinks below keep x its setup area (headroom for the binds' rounding in the skeleton file)."""
    tris = np.asarray(tris).reshape(-1, 3)
    a0 = _areas(P0, tris)
    ref = np.sign(a0) / np.maximum(np.abs(a0), 1e-12) if keep > 0 else np.sign(a0)
    floor = keep if keep > 0 else 0.0
    out = []
    for end in need:
        if abs(end) < 1e-9:
            out.append(0.0)
            continue
        degs = np.append(np.arange(1.0, abs(end), 1.0), abs(end)) * math.copysign(1.0, end)
        r = np.radians(degs)
        c, s = np.cos(r)[:, None], np.sin(r)[:, None]
        Px = P0[None, :, 0] + (c - 1) * u[None, :, 0] - s * u[None, :, 1]
        Py = P0[None, :, 1] + s * u[None, :, 0] + (c - 1) * u[None, :, 1]
        bad = ((_areas(np.stack([Px, Py], -1), tris) * ref) <= floor).any(1)
        first = int(np.argmax(bad)) if bad.any() else len(degs)
        out.append(0.0 if first == 0 else float(degs[first - 1]))
    return tuple(out)


def candidates(st: Strip) -> list:
    """DEFAULT, then the grid's designs that fit on the sleeve (a band starts below the shoulder and, with its pivot's
    fade, ends by the wrist), cheapest first: total band width + 0.5 x total pivot shift (+ 0.25 for the short fade,
    which a sleeve whose forearm is short against its width needs)."""
    top, bottom = st.t_shoulder / st.width, st.t_wrist / st.width
    out = []
    los = sorted(set(GRID_LO) | {round(top + 0.1, 2)}, reverse=True)
    for fade in FADES:
        cols = [(k, lo, hi) for k in GRID_K for lo in los for hi in GRID_HI
                if lo >= top and hi + (fade if k else 0.0) <= bottom]
        out += [(a, b, fade) for a in cols for b in cols if fade == FADES[0] or a[0] or b[0]]
    out.sort(key=lambda d: ((d[0][2] - d[0][1]) + (d[1][2] - d[1][1]) + 0.5 * (d[0][0] + d[1][0])
                            + (0.25 if d[2] != FADES[0] else 0.0), d))
    return [DEFAULT] + [d for d in out if d != DEFAULT]


def _covers(cov: tuple, need: tuple) -> bool:
    return cov[0] <= need[0] + 1e-9 and cov[1] >= need[1] - 1e-9


def grid_scan(st: Strip, Pu: np.ndarray, Pf: np.ndarray, O, need: tuple, limit: int = 1) -> tuple:
    """(fold-free, fallback): the first `limit` grid designs (candidates' order, DEFAULT first) whose motion keeps
    every triangle's orientation over need = (lo <= 0, hi >= 0) degrees of elbow turn, as Motions; and, when none
    does, the one covering the largest share of the need (ok False), else None."""
    need = (min(0.0, float(need[0])), max(0.0, float(need[1])))
    oks, best, best_score = [], None, -1.0
    for d in candidates(st):
        P0, u, w, q = motion(st, d, Pu, Pf, O)
        cov = coverage(P0, u, st.triangles, need)
        if _covers(cov, need):
            oks.append(Motion(d, P0, u, w, q, cov, True))
            if len(oks) >= limit or d == DEFAULT:             # the spec default needs nothing else
                break
            continue
        score = min(cov[0] / need[0] if need[0] else 1.0, cov[1] / need[1] if need[1] else 1.0)
        if not oks and score > best_score:
            best, best_score = Motion(d, P0, u, w, q, cov, False), score
    return oks, (None if oks else best)


def choose_grid(st: Strip, Pu: np.ndarray, Pf: np.ndarray, O, need: tuple) -> Motion:
    """The first fold-free grid design over the need (DEFAULT first), else the one covering the most (grid_scan)."""
    oks, fallback = grid_scan(st, Pu, Pf, O, need)
    return oks[0] if oks else fallback


def _rot(phi: float) -> np.ndarray:
    c, s = math.cos(phi), math.sin(phi)
    return np.array([[c, -s], [s, c]])


def beam(t: np.ndarray, s: np.ndarray, d, a, O, phi: float, lo: float, hi: float, s0: float) -> np.ndarray:
    """Where a tube bent like a beam puts the points at (t along d from O, s across along a = d turned +90 deg), for an
    elbow turn of phi (radians, counterclockwise): the line s = s0 keeps its length and turns by phi x smoothstep over
    [lo, hi] (px along d), cross-sections stay square to it, and the gap that leaves at the band's end against the
    forearm turned rigidly about O is spread over the band, so beyond it the points turn exactly with the forearm bone
    and before it they stay put."""
    d, a, O = (np.asarray(x, float) for x in (d, a, O))
    taus = np.linspace(lo, hi, 257)
    th = phi * smoothstep((taus - lo) / (hi - lo))
    dirs = np.cos(th)[:, None] * d + np.sin(th)[:, None] * a
    c = O + lo * d + s0 * a + np.vstack([np.zeros(2), np.cumsum((dirs[1:] + dirs[:-1]) / 2 * np.diff(taus)[:, None], 0)])
    Rd, Ra = math.cos(phi) * d + math.sin(phi) * a, math.cos(phi) * a - math.sin(phi) * d
    gap = c[-1] - (O + hi * Rd + s0 * Ra)
    tc = np.clip(t, lo, hi)
    w = smoothstep((tc - lo) / (hi - lo))
    ci = np.stack([np.interp(tc, taus, c[:, 0]), np.interp(tc, taus, c[:, 1])], 1)
    ai = np.cos(phi * w)[:, None] * a - np.sin(phi * w)[:, None] * d
    bent = ci + (s - s0)[:, None] * ai - w[:, None] * gap
    still = O + t[:, None] * d + s[:, None] * a
    turned = O + t[:, None] * Rd + s[:, None] * Ra
    return np.where((t <= lo)[:, None], still, np.where((t >= hi)[:, None], turned, bent))


def units_per_px(st: Strip, Pu: np.ndarray) -> float:
    """Setup units per image px along the sleeve's axis: the upper-arm placement Pu against the strip's uvs (an affine
    least-squares fit over the rows above the elbow, where a width fit only squeezes across the axis), measured along
    the strip's axis."""
    rows = st.row()
    sel = st.ts[rows] < 0
    if sel.sum() < 3:
        sel = np.ones(len(rows), bool)
    X = np.hstack([st.uv[sel], np.ones((int(sel.sum()), 1))])
    A = np.linalg.lstsq(X, Pu[sel], rcond=None)[0][:2].T          # Pu ~ A uv + b
    return float(np.linalg.norm(A @ np.asarray(st.axis[0], float)))


def band_px(st: Strip, band: tuple) -> tuple:
    """A band (lo, hi) x sleeve width as image px along the axis from the elbow, its top capped at the shoulder point
    (the rows above it stay rigid with the upper arm) and its bottom at the wrist."""
    return max(band[0] * st.width, st.t_shoulder), min(band[1] * st.width, st.t_wrist)


def _inner_col(st: Strip, inner: int) -> np.ndarray:
    n = len(st.ts)
    return np.arange(n) if inner == 0 else np.arange(2 * n - 1, n - 1, -1)    # rows 0..n-1 of that column


def crease_corner(st: Strip, P0: np.ndarray, P: np.ndarray, phi: float, inner: int, i_lo: int, i_hi: int):
    """C: where the upper arm's inner side meets the forearm's in the bent sleeve P (elbow turned by phi radians) -
    the line through the inner column's vertex at row i_lo along the upper arm's setup axis (row centres 0 -> i_lo),
    and the one through its vertex at row i_hi along the forearm's (row centres i_hi -> last) turned by phi. None when
    they are parallel."""
    n = len(st.ts)
    col = _inner_col(st, inner)
    mid = (P0[:n] + P0[n:][::-1]) / 2
    du, df = _unit(mid[i_lo] - mid[0]), _rot(phi) @ _unit(mid[n - 1] - mid[i_hi])
    A, B = P[col[i_lo]], P[col[i_hi]]
    M = np.array([du, -df]).T
    if abs(np.linalg.det(M)) < 1e-6:
        return None
    return A + np.linalg.solve(M, B - A)[0] * du


def fill_crease(st: Strip, P0: np.ndarray, P: np.ndarray, O, phi: float, inner: int, i_lo: int, i_hi: int,
                margin: float) -> np.ndarray:
    """A bent sleeve's vertices P with the inside of the bend filled to its corner C (crease_corner). When the inner
    edge rounds off short of C - a gap in the crease where what lies behind would show - the inner column's vertex
    nearest C is pushed out past it by `margin` along C - O, and its neighbours less (a bump of FILL_SPREAD rows; the
    band's end rows stay on their straight sides): the cloth bunching into the crease."""
    col = _inner_col(st, inner)
    C = crease_corner(st, P0, P, phi, inner, i_lo, i_hi)
    if C is None or i_hi - i_lo < 2:
        return P
    out_dir = _unit(C - np.asarray(O, float))
    goal = C + margin * out_dir
    if _inside(P, goal):
        return P
    rows = np.arange(i_lo, i_hi + 1)
    edge = P[col[rows]]
    j = 1 + int(np.argmin(np.linalg.norm(edge[1:-1] - C, axis=1)))
    bump = np.exp(-((rows - rows[j]) / FILL_SPREAD) ** 2)
    bump[[0, -1]] = 0.0
    P = P.copy()
    P[col[rows]] += bump[:, None] * (goal - edge[j])
    return P


def smooth(st: Strip, Pu: np.ndarray, Pf: np.ndarray, O, need: tuple, band: tuple, neutral: float = None,
           fill: float | None = CREASE_FILL) -> Motion:
    """The smooth design over band (lo, hi) x sleeve width (module doc; band_px): u fitted by least squares to beam()
    over the need's bends, the band converted to setup units (units_per_px); w is the band's smoothstep (it only
    decides which bone owns each triangle, omegas). design[1:3] is the band actually used, in sleeve widths."""
    O = np.asarray(O, float)
    nu = NEUTRAL if neutral is None else float(neutral)
    n = len(st.ts)
    lo, hi = band_px(st, band)
    k = units_per_px(st, Pu)
    rows = st.row()
    w = smoothstep((st.ts[rows] - lo) / (hi - lo))
    P0 = (1 - w)[:, None] * Pu + w[:, None] * Pf
    ends = P0[rows == n - 1].mean(0) - P0[rows == 0].mean(0)
    d = ends / max(float(np.linalg.norm(ends)), 1e-9)
    a = np.array([-d[1], d[0]])
    t, s = (P0 - O) @ d, (P0 - O) @ a
    e = int(np.argmin(np.abs(st.ts)))
    half = abs(s[e] - s[2 * n - 1 - e]) / 2
    phis = np.radians(np.append(np.arange(need[0], need[1] + 1e-9, FIT_STEP), need[1]))
    i_lo, i_hi = int(np.argmin(np.abs(st.ts - lo))), int(np.argmin(np.abs(st.ts - hi)))
    side = 0 if s[:n].mean() > s[n:].mean() else 1         # the column on +a: the inside of a counterclockwise bend
    phis = [float(ph) for ph in phis if abs(ph) > 1e-6]
    tgts = [beam(t, s, d, a, O, ph, lo * k, hi * k, math.copysign(nu * half, ph)) for ph in phis]

    holds = [math.radians(h) for h in (need[0] + FOLD_MARGIN, need[1] - FOLD_MARGIN) if abs(h) > 1.0]
    wts = [1.0 + HOLD_WEIGHT * sum(math.exp(-((ph - h) / math.radians(HOLD_SPREAD)) ** 2) for h in holds)
           for ph in phis]

    def fit(targets):
        num, den = np.zeros_like(P0), 0.0
        for ph, tgt, wt in zip(phis, targets, wts):
            num += wt * ((tgt - P0) @ (_rot(ph) - np.eye(2)))     # (R^T - I) b, row-wise
            den += wt * 2 * (1 - math.cos(ph))
        return num / max(den, 1e-12)

    u = fit(tgts)
    for _ in range(FILL_ROUNDS if fill is not None else 0):
        # the least-squares lever is one compromise for both bend directions: push the targets by what the fitted
        # motion still lacks at the crease, and fit again
        moved = False
        for i, ph in enumerate(phis):
            P = P0 + u @ (_rot(ph) - np.eye(2)).T
            want = fill_crease(st, P0, P, O, ph, side if ph > 0 else 1 - side, i_lo, i_hi, fill * 2 * half)
            if not np.allclose(want, P):
                tgts[i] = tgts[i] + (want - P)
                moved = True
        if not moved:
            break
        u = fit(tgts)
    used = (round(lo / st.width, 2), round(hi / st.width, 2))
    return Motion(("smooth", used[0], used[1], nu, 0.0, None, fill), P0, u, w, np.zeros(len(w)),
                  coverage(P0, u, st.triangles, need), False)


def pivot_kept(P0: np.ndarray, u: np.ndarray, O, margin: float, need: tuple, step: float = 2.0) -> bool:
    """Does the elbow pivot O stay inside the bent outline (the hull: every vertex, in order), at least `margin` from
    its edge, at every turn over the need (step degrees and the ends)? spine_qa's joints check wants the pivot covered;
    a bend that rolls the tube off it leaves a hole in the crease."""
    O = np.asarray(O, float)
    degs = np.unique(np.concatenate([np.arange(need[0], need[1] + 1e-9, step), [need[0], need[1], 0.0]]))
    r = np.radians(degs)
    c, s = np.cos(r)[:, None], np.sin(r)[:, None]
    P = np.stack([P0[None, :, 0] + (c - 1) * u[None, :, 0] - s * u[None, :, 1],
                  P0[None, :, 1] + s * u[None, :, 0] + (c - 1) * u[None, :, 1]], -1)          # (k, V, 2)
    A, B = P, np.roll(P, -1, axis=1)
    cross = (A[..., 1] > O[1]) != (B[..., 1] > O[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        xs = A[..., 0] + (O[1] - A[..., 1]) * (B[..., 0] - A[..., 0]) / (B[..., 1] - A[..., 1])
    inside = ((cross & (O[0] < xs)).sum(1) % 2) == 1
    AB, AO = B - A, O - A
    tt = np.clip((AO * AB).sum(-1) / np.maximum((AB * AB).sum(-1), 1e-12), 0, 1)
    dist = np.linalg.norm(AO - tt[..., None] * AB, axis=-1).min(1)
    return bool((inside & (dist >= margin)).all())


def blend(st: Strip, sm: Motion, grid: Motion, need: tuple, keep=None):
    """The least of the grid design blended into the smooth one that keeps every triangle unfolded over the need: the
    grid's share per vertex is a bump around the elbow, exp(-(t / sigma)^2) for sigma in BLEND_SIGMAS (x sleeve width;
    None: everywhere alike), scaled in steps of BLEND_STEP - the smallest mean share wins. (P0, u, w, q, shares), or
    None when even the grid alone folds. keep: (O, margin) for pivot_kept, also required."""
    if not grid.ok:
        return None
    t = st.ts[st.row()] / st.width
    best = None
    for sig in BLEND_SIGMAS:
        g = np.ones(len(t)) if sig is None else np.exp(-(t / sig) ** 2)
        for k in range(1, int(round(1 / BLEND_STEP)) + 1):
            beta = np.clip(k * BLEND_STEP * g, 0.0, 1.0)
            if best is not None and beta.mean() >= best[4].mean() - 1e-12:
                break
            P0 = (1 - beta)[:, None] * sm.P0 + beta[:, None] * grid.P0
            u = (1 - beta)[:, None] * sm.u + beta[:, None] * grid.u
            if _covers(coverage(P0, u, st.triangles, need, AREA_KEEP), need) and \
                    (keep is None or pivot_kept(P0, u, *keep, need)):
                best = (P0, u, (1 - beta) * sm.w + beta * grid.w, beta * grid.q, beta)
                break
    return best


def _turns(c: np.ndarray) -> np.ndarray:
    seg = np.diff(c, axis=0)
    return (np.diff(np.degrees(np.arctan2(seg[:, 1], seg[:, 0]))) + 180) % 360 - 180


def notch(st: Strip, P0: np.ndarray, u: np.ndarray, band: tuple, degs) -> float:
    """How far (x the elbow's width) the inside of the bend leaves its corner open at these elbow turns (degrees): 0
    when the crease corner C (crease_corner, the band's end rows) is covered by the bent sleeve, else C's distance to
    the sleeve's inner edge - the gap in the crease where the torso behind would show."""
    n = len(st.ts)
    lo, hi = band_px(st, band)
    i_lo, i_hi = int(np.argmin(np.abs(st.ts - lo))), int(np.argmin(np.abs(st.ts - hi)))
    e = int(np.argmin(np.abs(st.ts)))
    W = max(float(np.linalg.norm(P0[e] - P0[2 * n - 1 - e])), 1e-9)
    worst = 0.0
    for deg in degs:
        phi = math.radians(deg)
        P = P0 + u @ (_rot(phi) - np.eye(2)).T
        cols = [P[_inner_col(st, 0)], P[_inner_col(st, 1)]]
        inner = min((0, 1), key=lambda j: float(np.linalg.norm(np.diff(cols[j][i_lo:i_hi + 1], axis=0), axis=1).sum()))
        C = crease_corner(st, P0, P, phi, inner, i_lo, i_hi)
        if C is None or _inside(P, C):
            continue
        seg = cols[inner][i_lo:i_hi + 1]
        S0, S1 = seg[:-1], seg[1:]
        AB, AC = S1 - S0, C - S0
        tt = np.clip((AC * AB).sum(1) / np.maximum((AB * AB).sum(1), 1e-12), 0, 1)
        worst = max(worst, float(np.linalg.norm(AC - tt[:, None] * AB, axis=1).min()) / W)
    return worst


def _inside(poly: np.ndarray, p) -> bool:
    """Is point p inside the polygon (even-odd)?"""
    A, B = poly, np.roll(poly, -1, axis=0)
    cross = (A[:, 1] > p[1]) != (B[:, 1] > p[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        xs = A[:, 0] + (p[1] - A[:, 1]) * (B[:, 0] - A[:, 0]) / (B[:, 1] - A[:, 1])
    return bool((cross & (p[0] < xs)).sum() % 2)


def corner(st: Strip, P0: np.ndarray, u: np.ndarray, degs) -> float:
    """How angular the outside of the elbow gets at these elbow turns (degrees): over the rows within CORNER_ROWS
    sleeve widths of the elbow, the outer (longer) edge's turn at each vertex beyond the turn the drawing already has
    there at the setup pose (a cuff's step, a painted crease), the largest, plus twice its largest turn the wrong way
    (a dent). 0 for any sleeve at the setup pose."""
    n = len(st.ts)
    near = np.abs(st.ts) <= CORNER_ROWS * st.width
    cols0 = [P0[:n][near], P0[n:][::-1][near]]
    worst = 0.0
    for deg in degs:
        P = P0 + u @ (_rot(math.radians(deg)) - np.eye(2)).T
        cols = [P[:n][near], P[n:][::-1][near]]
        i = max((0, 1), key=lambda j: float(np.linalg.norm(np.diff(cols[j], axis=0), axis=1).sum()))
        if len(cols[i]) < 3:
            continue
        turn = (_turns(cols[i]) - _turns(cols0[i]) + 180) % 360 - 180
        sign = math.copysign(1.0, float(turn.sum()))
        worst = max(worst, float(np.abs(turn).max()) + 2 * max(0.0, -float((turn * sign).min())))
    return worst


def choose(st: Strip, Pu: np.ndarray, Pf: np.ndarray, O, need: tuple) -> Motion:
    """DEFAULT when it is fold-free over need = (lo <= 0, hi >= 0) degrees; else the smooth design (module doc): per
    band (SMOOTH_BANDS, its top at most BAND_REACH of the way up to the shoulder point), alone when it keeps every
    triangle at AREA_KEEP of its area and the elbow pivot covered (pivot_kept), else blended (blend) with whichever
    of the first PARTNERS fold-free grid designs leaves the roundest elbow. Across bands, shortest first, a longer
    band wins only by rounding the outer elbow (corner, at the animations' own largest bends: the need less
    FOLD_MARGIN) by more than CORNER_TIE degrees - so the bend stays near the elbow instead of bowing the whole
    upper arm from the shoulder. Else the grid's choice (choose_grid)."""
    need = (min(0.0, float(need[0])), max(0.0, float(need[1])))
    partners, fallback = grid_scan(st, Pu, Pf, O, need, PARTNERS)
    if partners and partners[0].design == DEFAULT:
        return partners[0]
    holds = [d for d in (need[0] + FOLD_MARGIN, need[1] - FOLD_MARGIN) if abs(d) > 1.0] or [need[0], need[1]]
    reach = BAND_REACH * st.t_shoulder / st.width
    bands = sorted({(round(max(lo, reach), 2), round(min(hi, st.t_wrist / st.width), 2)) for lo, hi in SMOOTH_BANDS},
                   key=lambda b: (b[1] - b[0], -b[0]))
    n, e = len(st.ts), int(np.argmin(np.abs(st.ts)))
    best, best_score = None, None
    for band in bands:
        if band[1] - band[0] < 0.5:
            continue
        gap = lambda P0_, u_: notch(st, P0_, u_, band, holds) > NOTCH_MAX      # noqa: E731
        found = []
        for fill in (CREASE_FILL, None):
            sm = smooth(st, Pu, Pf, O, need, band, fill=fill)
            keep = (O, PIVOT_MARGIN * float(np.linalg.norm(sm.P0[e] - sm.P0[2 * n - 1 - e])))
            if _covers(coverage(sm.P0, sm.u, st.triangles, need, AREA_KEEP), need) and \
                    pivot_kept(sm.P0, sm.u, *keep, need):
                found.append((gap(sm.P0, sm.u), corner(st, sm.P0, sm.u, holds), 0.0,
                              Motion(sm.design, sm.P0, sm.u, sm.w, sm.q, coverage(sm.P0, sm.u, st.triangles, need),
                                     True)))
            if found or fill is None:
                break
        if not found:                               # blended with a grid design: without the crease fill
            for gp in partners:
                fixed = blend(st, sm, gp, need, keep)
                if fixed is None:
                    continue
                P0, u, w, q, beta = fixed
                share = round(float(beta.mean()), 3)
                found.append((gap(P0, u), corner(st, P0, u, holds), share,
                              Motion(sm.design[:4] + (share, gp.design, None), P0, u, w, q,
                                     coverage(P0, u, st.triangles, need), True)))
        if not found:
            continue
        open_, score, _, m = min(found, key=lambda x: x[:3])
        if best is None or (open_, score) < (best_score[0], best_score[1] - CORNER_TIE):
            best, best_score = m, (open_, score)
    return best if best is not None else (partners[0] if partners else fallback)


# ------------------------------------------------------------------ the Spine attachment

def _local(frame, P) -> np.ndarray:
    """Spine units -> a bone's local coordinates; frame = ((x, y) origin, world angle in degrees), no scale."""
    (ox, oy), ang = frame
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    d = np.asarray(P, float) - (ox, oy)
    return np.array([c * d[0] + s * d[1], -s * d[0] + c * d[1]])


def omegas(st: Strip, m: Motion, O) -> np.ndarray:
    """Spine weight on the forearm per vertex (module doc): which bone owns each triangle, not how it moves."""
    t = st.ts[st.row()]
    above, on, below = OMEGA_SPLIT
    om = np.where(t < -1e-6, np.minimum(m.w, above), np.where(t > 1e-6, np.maximum(m.w, below), on))
    pure_f = np.linalg.norm(m.u - (m.P0 - np.asarray(O, float)), axis=1) < 1e-9
    om = np.where((om >= 1.0) & ~pure_f, 1.0 - OMEGA_EDGE, om)
    moving = np.linalg.norm(m.u, axis=1) >= 1e-9
    om = np.where((om <= 0.0) & moving, OMEGA_EDGE, om)
    if m.design[0] == "smooth":
        # a smooth design's lever u is not w x a bounded vector: the forearm bind Y = O + u / omega would run off to
        # where the file's rounded weight (4 decimals) moves the vertex visibly, so a moving vertex keeps OMEGA_EDGE
        om = np.where(moving & ~pure_f, np.clip(om, OMEGA_EDGE, 1.0 - OMEGA_EDGE), om)
    return om


def attachment(st: Strip, m: Motion, upper: tuple, fore: tuple, i_upper: int, i_fore: int, size: tuple) -> dict:
    """The Spine 4.2 mesh attachment: uvs, triangles, weighted vertices, hull (every vertex), width, height.
    upper, fore: the bones' setup frames ((x, y), world angle) in Spine units; i_*: their indices in the bone list."""
    O = np.asarray(fore[0], float)
    om = omegas(st, m, O)
    verts = []
    for P0, u, o in zip(m.P0, m.u, om):
        if o <= 0.0:
            verts += [1, i_upper, *np.round(_local(upper, P0), 3).tolist(), 1]
        elif o >= 1.0:
            verts += [1, i_fore, *np.round(_local(fore, P0), 3).tolist(), 1]
        else:
            Y = O + u / o                                    # turns with the forearm: o (R - I)(Y - O) = (R - I) u
            Z = (P0 - o * Y) / (1 - o)                       # still with the upper arm: the setup sum is P0
            verts += [2, i_upper, *np.round(_local(upper, Z), 3).tolist(), round(1 - float(o), 4),
                      i_fore, *np.round(_local(fore, Y), 3).tolist(), round(float(o), 4)]
    W, H = size
    uvs = np.round(st.uv / (W, H), 6).ravel().tolist()
    return {"type": "mesh", "uvs": uvs, "triangles": list(map(int, st.triangles)), "vertices": verts,
            "hull": len(st.uv), "width": int(W), "height": int(H)}


def split_at_elbow(img: Image.Image, S, E, W) -> tuple:
    """(upper, lower): img with its alpha cleared past the elbow row (along S -> W) and before it."""
    a = np.asarray(img.convert("RGBA")).copy()
    u = _unit(np.asarray(W, float) - np.asarray(S, float))
    yy, xx = np.mgrid[:a.shape[0], :a.shape[1]] + 0.5
    t = (xx - E[0]) * u[0] + (yy - E[1]) * u[1]
    up, lo = a.copy(), a.copy()
    up[..., 3] = np.where(t < 0, a[..., 3], 0)
    lo[..., 3] = np.where(t >= 0, a[..., 3], 0)
    return Image.fromarray(up, "RGBA"), Image.fromarray(lo, "RGBA")


def info(st: Strip, m: Motion, need: tuple) -> dict:
    """What report.json records about a mesh. A smooth design's band is in sleeve widths from the elbow (as used:
    capped at the shoulder point), with its outer elbow's corner (deg) and its crease's gap (x width) at the holds."""
    col = lambda c: {"pivot_shift": c[0], "band": [c[1], c[2]]}      # noqa: E731
    grid = lambda g: {"left": col(g[0]), "right": col(g[1]), "fade": g[2]}      # noqa: E731
    if m.design[0] == "smooth":
        _, lo, hi, nu, share, g, fill = m.design
        holds = [d for d in (need[0] + FOLD_MARGIN, need[1] - FOLD_MARGIN) if abs(d) > 1.0] or list(need)
        design = {"smooth": {"band": [lo, hi], "neutral": nu, "grid_share": share, "crease_fill": fill is not None,
                             "outer_corner_deg": round(corner(st, m.P0, m.u, holds), 1),
                             "crease_gap": round(notch(st, m.P0, m.u, (lo, hi), holds), 3)},
                  "grid": grid(g) if g else None, "default": False}
    else:
        design = {**grid(m.design), "default": m.design == DEFAULT}
    return {"rows": len(st.ts), "vertices": len(st.uv), "width_px": round(st.width, 1), "design": design,
            "need_deg": [round(float(need[0]), 1), round(float(need[1]), 1)],
            "covered_deg": [round(float(m.covered[0]), 1), round(float(m.covered[1]), 1)], "fold_free": bool(m.ok)}
