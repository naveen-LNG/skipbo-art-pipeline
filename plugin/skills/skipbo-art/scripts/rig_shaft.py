"""rig_shaft.py - a hidden shaft rising from a foot's ankle opening under the trouser cuff (spine_rig.py --annotations).

A leg-less rig (hips with no leg pieces, master.layers leg: in_hips one-piece trousers included) hangs the feet under
the hips, their ankle opening at the master's ankle. The body sheet paints a boot only as tall as the master's visible
boot, so at rest the boot's top barely tucks under the cuff, and when walk / run bob the hips up (the feet planted)
the boots come out from under the trousers (spine_qa: detached, unstitched). Every trousered character worked around
it by hand: the red panda stretched its boots' shafts (make_boots.py), the bear painted a honey-fur ankle stub under
its clogs and its tiptoe (make_parts.py section 4, tools/make_tiptoe.py).

Here the foot gets the part a real boot has: a shaft rising SHAFT_UP x body height above its ankle opening, as wide
as the opening, in the foot's own colours (each column the median colour of the lighter half of its opaque pixels
just below the opening, so the painted inside's dark is left out and the boot's side-to-side shading carries up). It
is drawn behind the foot, and at rest it is kept only where the placed hips cover it (eroded HIDE_ERODE px), within
one straight band inside the narrowest trouser row it rises through (band), so the setup pose looks exactly as before
and a stepping foot's growth doesn't push it out beside a wider cuff (the beaver's run, clipped to the hips alone).
The image grows by `rows` px at the top and every annotated point moves down by as much. Pose variants (a tiptoe) get
the same shaft, the same height in master px, kept where the rest's is kept (rig_variants.with_shaft).

  wanted(ann, has_legs, has_hips)                          leg-less, feet under the hips
  opening_width(img, ankle)                                an opening with no annotated width: its row's opaque run
  shaft = layer(img, ankle, width, depth, rows)            the shaft alone on the foot's canvas, grown `rows` at the top
  keep = band(hidden, ankle_x, width, bottom)              under the hips and inside the trouser leg's narrowest row
  img = compose(img, shaft, rows, keep)                    the foot over the shaft, kept where `keep` (canvas px)
"""
from __future__ import annotations

import numpy as np
from PIL import Image

SHAFT_UP = 0.06           # of body height: how far the shaft rises above the ankle opening (run bobs the hips 0.022)
SAMPLE_DOWN = 0.5         # the colours are sampled from the opening down this x its width (below its depth)
HIDE_ERODE = 2            # px: the shaft is kept this far inside the hips' silhouette (its antialiased rim shows)
SIDE_INSET = 0.08         # of the opening's width: the band stays this far inside the trouser leg on each side (walk /
                          # run scale a stepping foot up to 1.08 about its ankle, and sway it against the hips)
FEATHER = 1.0             # px: the shaft's sides fade over this


def wanted(ann, has_legs: bool, has_hips: bool) -> bool:
    """Leg-less, hips placed, feet drawn under the hips (foot: over_hips draws the boots over the trouser legs, which
    ride with the hips: rig_anim.loose_foot)."""
    return ann is not None and not has_legs and has_hips and ann.master.layers.get("foot") != "over_hips"


def colours(a: np.ndarray, ankle, width: float, depth: float, x0: int, x1: int) -> np.ndarray:
    """(x1 - x0, 3) float RGB: per column the median of the lighter half of the opaque pixels from the opening's
    bottom (ankle y + depth / 2) down SAMPLE_DOWN x width; columns with none take their nearest neighbour's."""
    h = a.shape[0]
    y0 = int(np.clip(round(ankle[1] + depth / 2), 0, h - 1))
    y1 = int(np.clip(round(y0 + SAMPLE_DOWN * width), y0 + 1, h))
    out = np.full((x1 - x0, 3), np.nan, np.float32)
    for i, x in enumerate(range(x0, x1)):
        col = a[y0:y1, x]
        col = col[col[:, 3] > 200, :3].astype(np.float32)
        if len(col) < 2:
            continue
        lum = col @ np.array([0.299, 0.587, 0.114], np.float32)
        out[i] = np.median(col[lum >= np.median(lum)], axis=0)
    ok = ~np.isnan(out[:, 0])
    if not ok.any():                                   # nothing below the opening: the foot's own median colour
        solid = a[..., 3] > 200
        out[:] = np.median(a[solid, :3], axis=0) if solid.any() else 128
        return out
    idx = np.nonzero(ok)[0]
    near = idx[np.abs(np.arange(len(out))[:, None] - idx[None, :]).argmin(1)]
    out = out[near]
    k = max(1, int(round(0.08 * len(out))))            # a little smoothing across: no single-column stripes
    pad = np.pad(out, ((k, k), (0, 0)), mode="edge")
    return np.stack([np.convolve(pad[:, c], np.ones(2 * k + 1) / (2 * k + 1), "valid") for c in range(3)], 1)


def opening_width(img: Image.Image, ankle) -> float:
    """An ankle opening without an annotated width: the opaque run across the ankle point's row."""
    a = np.asarray(img.convert("RGBA"))[..., 3] > 127
    y = int(np.clip(round(ankle[1]), 0, a.shape[0] - 1))
    xs = np.nonzero(a[y])[0]
    return float(np.ptp(xs) + 1) if len(xs) else 0.5 * a.shape[1]


def layer(img: Image.Image, ankle, width: float, depth: float, rows: int) -> np.ndarray:
    """The shaft alone, (h + rows, w, 4) float RGBA on the foot's canvas grown `rows` px at the top: as wide as the
    opening (`width`, centred on the ankle point), from the top down into the opening (ankle y + depth / 2)."""
    a = np.asarray(img.convert("RGBA"))
    h, w = a.shape[:2]
    cx = float(ankle[0])
    x0, x1 = int(np.floor(max(0.0, cx - width / 2))), int(np.ceil(min(float(w), cx + width / 2)))
    H = h + rows
    out = np.zeros((H, w, 4), np.float32)
    if x1 > x0:
        bottom = int(np.clip(round(rows + ankle[1] + depth / 2), 1, H))
        out[:bottom, x0:x1, :3] = colours(a, ankle, width, depth, x0, x1)[None]
        xs = np.arange(x0, x1) + 0.5
        out[:bottom, x0:x1, 3] = 255 * np.clip((width / 2 - np.abs(xs - cx)) / FEATHER, 0, 1)[None]   # soft sides
    return out


def band(hidden: np.ndarray, cx: float, width: float, bottom: int) -> np.ndarray:
    """Where the shaft may go: `hidden` (bool, canvas px: under the hips at rest) cut to one straight band down the
    canvas, inside the narrowest run of `hidden` through column cx over the rows above `bottom` (the trouser leg
    above a wider turned-up cuff), inset SIDE_INSET x width each side. Clipped to `hidden` alone, a shaft as wide as
    a cuff poked out beside the leg above it when the stepping foot rose and grew (the beaver's run)."""
    h, w = hidden.shape
    x = int(np.clip(round(cx), 0, w - 1))
    lo, hi = [], []
    for y in range(min(bottom, h)):
        row = hidden[y]
        if not row[x]:
            continue
        gaps = np.nonzero(~row)[0]
        left, right = gaps[gaps < x], gaps[gaps > x]
        lo.append(left.max() + 1 if len(left) else 0)
        hi.append(right.min() if len(right) else w)
    out = np.zeros_like(hidden)
    if not lo:
        return out
    m = SIDE_INSET * width
    xs = np.arange(w) + 0.5
    out[:, (xs >= max(lo) + m) & (xs <= min(hi) - m)] = True
    return out & hidden


def compose(img: Image.Image, shaft: np.ndarray, rows: int, hidden: np.ndarray | None = None) -> Image.Image:
    """The foot drawn over its shaft, the shaft kept only where `hidden` (bool, canvas px; None: all of it)."""
    s = shaft.copy()
    if hidden is not None:
        s[..., 3] *= hidden
    out = Image.fromarray(s.astype(np.uint8), "RGBA")
    out.alpha_composite(img.convert("RGBA"), (0, rows))
    return out
