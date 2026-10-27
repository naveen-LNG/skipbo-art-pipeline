#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""rig_worn.py - make worn items read as worn in a 2D cut-out rig (spine_rig.py --annotations).

A boot drawn over the leg (or over the hips, when the trouser legs are part of the hips) as ONE layer reads as an
object stuck in front of the leg: its dark inside covers the trouser leg. Spine's asset guide: "avoid drawing
elements that will appear in front of and behind an object on the same layer". Toon Boom (invert cutters) and Spine
(clipping attachments) can mask at runtime, but clipping is CPU-expensive, so the split is made once, here:

  back   the inside of the ankle opening plus the back (upper) half of its rim band: drawn BEHIND the leg/hips;
  shell  everything else (the front lip and the boot itself): drawn in front, on the same bone.

The leg's end, drawn between the two, then shows inside the opening and disappears behind the front lip.

Which ellipse. An output carries its ankle opening as points["ankle"], widths["ankle"], depths["ankle"] (output px;
feet are upright). The opening's width is the rim's width, but its point is wherever the opening snapped - on the
real fox it sits near the TOP edge of the opening (the inside spans 14-43 px below a point at 16.6, the front lip
44-51), and depth/2 (34 px) is how deep the opening goes, not how tall it looks. An ellipse centred on the point
with semi-axes width/2 x depth/2 would put the front lip behind the trousers. So the painted inside is found first:
the dark region the rim encloses near the point (find_inside). When it is found ("inside"):
  inside = that region (grown 1 px) plus its bounding ellipse;
  band   = the part above the inside's centre line of the ellipse RIM_GROW x (width/2, the height from that centre
           line to the top of the boot);
otherwise ("ellipse": no painted inside - a tiptoe boot seen tilted, a flat colour) the cut follows the piece's own
top silhouette (top_arc): across the opening's width each column's topmost opaque pixel, fitted with the upper half
of a sheared ellipse through the opening's two ends; the back part is the band between that top and the lower half
of the same ellipse, depth/2 below its chord, so the back lip and the front lip are smooth arcs whatever the tilt.
(An ellipse centred on the ankle point, the earlier rule and still the fallback when the fit fails or is refused,
left an L-shaped corner where it met the fox tiptoe's tilted top.) Where that front lip meets the outline at the
opening's ends the shell thins to a wedge, which goes behind whole (drop_thin_lip_ends).
The shell's cut edge is feathered over ~2 px and the back part carries the rest of the alpha there, so where nothing
lies between them the two composite to the original image (no hairline along the cut).
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

RIM_GROW = 1.12           # the rim band: this x the opening's ellipse
INSIDE_CONTRAST = 0.06    # luminance (0..1) the inside must be darker than the pixels around it
INSIDE_MIN_SPAN = 0.4     # the inside must span at least this fraction of the opening's width
INSIDE_OPEN_EDGE = 0.05   # at most this fraction of the pixels just around the inside may be transparent (enclosed)
SEARCH_GROW = 1.5         # the inside is looked for within the opening's ellipse, this x taller
OPENING_DEPTH_FRAC = 0.35  # depth when an output has a width but no depth (rig_annotations' default)
LUM = np.array([0.299, 0.587, 0.114], dtype=np.float32)


# ------------------------------------------------------------------ masks

def ellipse_mask(shape, cx: float, cy: float, a: float, b: float) -> np.ndarray:
    """Pixels whose centres (continuous coordinates: pixel i spans i..i+1) lie inside the axis-aligned ellipse."""
    h, w = shape
    yy, xx = np.mgrid[:h, :w].astype(np.float32) + 0.5
    return ((xx - cx) / max(a, 1e-6)) ** 2 + ((yy - cy) / max(b, 1e-6)) ** 2 <= 1.0


def dilate(m: np.ndarray, r: int) -> np.ndarray:
    """Binary dilation by r px (square), without wrapping round the edges."""
    out = m.copy()
    for _ in range(r):
        g = out.copy()
        g[1:] |= out[:-1]
        g[:-1] |= out[1:]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        out = g
    return out


def components(mask: np.ndarray) -> list:
    """Connected components (4-neighbour) of a boolean mask, largest first, as boolean masks."""
    out = []
    if not mask.any():
        return out
    im = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8)).copy()
    label = 0
    while True:
        arr = np.asarray(im)
        left = np.argwhere(arr == 255)
        if not len(left):
            break
        label = label % 250 + 1
        y, x = left[0]
        ImageDraw.floodfill(im, (int(x), int(y)), label)
        comp = (np.asarray(im) == label) & (arr == 255)
        out.append(comp)
        im = Image.fromarray(np.where(comp, 0, np.asarray(im)).astype(np.uint8)).copy()   # retire the label
    return sorted(out, key=lambda c: -int(c.sum()))


def _otsu(v: np.ndarray) -> float:
    hist, edges = np.histogram(v, bins=64, range=(0.0, 1.0))
    p = hist.astype(np.float64) / max(1, hist.sum())
    mids = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(p)
    m0 = np.cumsum(p * mids)
    mt = m0[-1]
    w1 = 1 - w0
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mt * w0 - m0) ** 2 / (w0 * w1)
    between[~np.isfinite(between)] = 0
    return float(edges[int(np.argmax(between)) + 1])


# ------------------------------------------------------------------ the opening

def find_inside(rgba: np.ndarray, at, width: float, depth: float):
    """The painted inside of an opening: the dark region its rim encloses near `at` (output px), or None.
    rgba: uint8 H x W x 4. Darker than its surroundings by INSIDE_CONTRAST, at least INSIDE_MIN_SPAN x width wide,
    centred within a third of the width of `at`, and enclosed (at most INSIDE_OPEN_EDGE of the pixels around it are
    transparent: a shaded side of the shaft runs into the outline and is not an inside)."""
    alpha = rgba[..., 3] > 127
    lum = (rgba[..., :3].astype(np.float32) / 255) @ LUM
    a, b = width / 2, depth / 2
    region = ellipse_mask(alpha.shape, at[0], at[1], a, SEARCH_GROW * b) & alpha
    if region.sum() < 20:
        return None
    dark = region & (lum < _otsu(lum[region]))

    def dist(c):                                       # nearest pixel of a component to the point (pixel centres)
        ys, xs = np.nonzero(c)
        return float(np.min((xs + 0.5 - at[0]) ** 2 + (ys + 0.5 - at[1]) ** 2))
    for comp in sorted(components(dark), key=dist):    # the inside nearest the point, not the biggest dark patch
        if comp.sum() < 20:
            continue
        ys, xs = np.nonzero(comp)
        if abs((xs.min() + xs.max() + 1) / 2 - at[0]) > width / 3 or (xs.max() - xs.min() + 1) < INSIDE_MIN_SPAN * width:
            continue
        ring = dilate(comp, 2) & ~comp
        if (ring & ~alpha).sum() > INSIDE_OPEN_EDGE * ring.sum():
            continue
        around = dilate(comp, 4) & ~comp & alpha
        if not around.any() or lum[around].mean() - lum[comp].mean() < INSIDE_CONTRAST:
            continue
        return comp
    return None


ARC_MIN_COLS = 8          # top_arc needs at least this many opaque columns across the opening
ARC_TOL = 2.0             # px: an end column whose top lies more than this (or 3 x the median residual) below the arc
ARC_ITER = 10             # is a side wall; at most this many fits
ARC_JUMP = 0.08           # x width: a step between neighbouring columns' tops beyond this is a side wall
ARC_MIN_SPAN = 0.6        # x width: a fit spanning less than this is not the opening's top (loop, notch)
ARC_SPAN = 1.15           # columns within this x width/2 of the ankle point are candidates: the annotated width can
#                           fall a few px short of the painted top (the fox tiptoe's right end); side walls are dropped


def top_arc(solid: np.ndarray, at, width: float, depth: float | None = None):
    """The opening's top as the piece's own silhouette shows it (no painted inside: a tiptoe boot seen tilted).
    Columns whose centres lie within ARC_SPAN x width/2 of at[0] and hold opaque pixels span the opening (x0..x1,
    centre cx, half-width a); each one's topmost opaque row is the top contour, fitted by least squares with the
    upper half of a vertically sheared ellipse through the opening's two ends:
        top(x) = p0 + p1 (x - cx) - h sqrt(1 - u^2),  u = (x - cx) / a   (h >= 0)
    p0 + p1 (x - cx) is the chord between the ends (the opening's tilt). The shaft's side walls are not the opening:
    the contour is first cut to the unbroken run of columns around the ankle point whose tops step by at most
    ARC_JUMP x width (a wall drops away much faster), then a column at either end whose top lies well below the
    fitted arc is dropped too (the span shrinks) and the fit repeated. Returns (cx, a, p0, p1, h) or None when
    fewer than ARC_MIN_COLS columns are left, or when the fit is not this opening's top (_arc_sane: a pull-on loop,
    a notch or a buckle captured the run) - back_mask then falls back to the snapped opening's ellipse."""
    cols = np.nonzero(solid.any(0))[0]
    cols = cols[np.abs(cols + 0.5 - at[0]) <= ARC_SPAN * width / 2]
    if len(cols) < ARC_MIN_COLS:
        return None
    ys_all = np.array([np.argmax(solid[:, c]) for c in cols], np.float64)
    jump = max(ARC_TOL, ARC_JUMP * width)
    k = int(np.argmin(np.abs(cols + 0.5 - at[0])))
    i0, i1 = k, k + 1
    while i0 > 0 and cols[i0 - 1] == cols[i0] - 1 and abs(ys_all[i0 - 1] - ys_all[i0]) <= jump:
        i0 -= 1
    while i1 < len(cols) and cols[i1] == cols[i1 - 1] + 1 and abs(ys_all[i1] - ys_all[i1 - 1]) <= jump:
        i1 += 1
    fit = None
    for _ in range(ARC_ITER):
        if i1 - i0 < ARC_MIN_COLS:
            return _arc_sane(fit, at, width, depth)
        x0, x1 = float(cols[i0]), float(cols[i1 - 1] + 1)
        cx, a = (x0 + x1) / 2, (x1 - x0) / 2
        xs, ys = cols[i0:i1] + 0.5, ys_all[i0:i1]
        e = np.sqrt(np.clip(1 - ((xs - cx) / a) ** 2, 0, 1))
        p0, p1, h = np.linalg.lstsq(np.stack([np.ones_like(xs), xs - cx, -e], 1), ys, rcond=None)[0]
        if h < 0:                                      # a flat or sagging top: the chord alone
            (p0, p1), h = np.linalg.lstsq(np.stack([np.ones_like(xs), xs - cx], 1), ys, rcond=None)[0], 0.0
        fit = (cx, a, float(p0), float(p1), float(h))
        r = ys - (p0 + p1 * (xs - cx) - h * e)         # > 0: the contour lies below the arc
        tol = max(ARC_TOL, 3 * float(np.median(np.abs(r))))
        j0, j1 = 0, len(r)
        while j0 < j1 and r[j0] > tol:
            j0 += 1
        while j1 > j0 and r[j1 - 1] > tol:
            j1 -= 1
        if j0 == 0 and j1 == len(r):
            break
        i0, i1 = i0 + j0, i0 + j1
    return _arc_sane(fit, at, width, depth)


def _arc_sane(fit, at, width: float, depth: float | None):
    """fit, or None when it can't be the opening's top: it spans less than ARC_MIN_SPAN x the annotated width (a
    loop rising from the top centre, a notch cut into it), or its chord at the ankle point's x lies more than the
    opening's depth from the point's height."""
    if fit is None:
        return None
    cx, a, p0, p1, h = fit
    depth = depth if depth else OPENING_DEPTH_FRAC * width
    if 2 * a < ARC_MIN_SPAN * width or abs(p0 + p1 * (at[0] - cx) - at[1]) > depth:
        return None
    return fit


def back_mask(rgba: np.ndarray, at, width: float, depth: float | None):
    """(mask of the back part, info) for an upright foot image with its ankle opening at `at` (output px).
    info: {"method": "inside" | "ellipse", "ellipse": [cx, cy, a, b] of the inside (for "ellipse": its centre on the
    chord, half its width and its lower semi-axis), "band": [cx, cy, a, b] (for "ellipse": the fitted top's height
    above the chord), and for "ellipse" "tilt": the chord's slope}."""
    depth = depth if depth else OPENING_DEPTH_FRAC * width
    shape = rgba.shape[:2]
    any_alpha = rgba[..., 3] > 0
    solid = rgba[..., 3] > 127
    comp = find_inside(rgba, at, width, depth)
    arc = top_arc(solid, at, width, depth) if comp is None else None
    yy, xx = np.mgrid[:shape[0], :shape[1]].astype(np.float64) + 0.5
    if comp is not None:
        ys, xs = np.nonzero(comp)
        cx, cy = (xs.min() + xs.max() + 1) / 2, (ys.min() + ys.max() + 1) / 2
        a_in, b_in = (xs.max() - xs.min() + 1) / 2, (ys.max() - ys.min() + 1) / 2
        inside = dilate(comp, 1) | ellipse_mask(shape, cx, cy, a_in + 0.5, b_in + 0.5)
        cols = solid[:, max(0, int(cx - a_in / 4)): int(cx + a_in / 4) + 1]
        rows = np.nonzero(cols.any(1))[0]
        top = float(rows.min()) if len(rows) else cy - b_in
        a_out, b_up = max(width / 2, a_in), max(cy - top, b_in)
        band = ellipse_mask(shape, cx, cy, RIM_GROW * a_out, RIM_GROW * b_up) & (yy < cy)
        back = (inside | band) & any_alpha
        info = {"method": "inside", "ellipse": [cx, cy, a_in, b_in],
                "band": [cx, cy, RIM_GROW * a_out, RIM_GROW * b_up]}
    elif arc is not None:
        # No painted inside: the back part is the band between the piece's own top contour and a lower arc, the lower
        # half of the same sheared ellipse (centre on the chord, the same width) going depth/2 below the chord. Both
        # lips are smooth curves through the opening's two ends whatever the tilt (an ellipse centred on the ankle
        # point left an L-shaped corner where it met a tilted top: the fox's tiptoe)
        cx, a, p0, p1, h = arc
        u = (xx - cx) / a
        low = p0 + p1 * (xx - cx) + depth / 2 * np.sqrt(np.clip(1 - u * u, 0, 1))
        back = (np.abs(u) <= 1) & (yy <= low) & any_alpha
        info = {"method": "ellipse", "ellipse": [cx, p0, a, depth / 2], "band": [cx, p0, a, h], "tilt": round(p1, 4)}
    else:                                              # no fit, or refused (_arc_sane): the snapped ellipse
        cx, cy = float(at[0]), float(at[1])
        inside = ellipse_mask(shape, cx, cy, width / 2, depth / 2)
        band = ellipse_mask(shape, cx, cy, RIM_GROW * width / 2, RIM_GROW * depth / 2) & (yy < cy)
        back = (inside | band) & any_alpha
        info = {"method": "ellipse", "ellipse": [cx, cy, width / 2, depth / 2],
                "band": [cx, cy, RIM_GROW * width / 2, RIM_GROW * depth / 2]}
    # no detached islands on either side of the cut: stray bits of the shell go behind, then stray bits of the back
    # (a corner of the band reaching round the outline) come to the front
    for c in components(solid & ~back)[1:]:
        back |= dilate(c, 1) & any_alpha
    for c in components(solid & back)[1:]:
        back &= ~dilate(c, 1)
    info = {k: [round(float(x), 2) for x in v] if isinstance(v, list) else v for k, v in info.items()}
    return back, info



TIP_THIN = 3              # back-part pixels thinner than 2 x this (a morphological opening removes them) ...
TIP_NEAR = 4              # ... and further than this from what survives are thin tips: they go to the shell


def _box(m: np.ndarray, r: int, outside: bool = False) -> np.ndarray:
    """Square (2r+1) binary dilation; pixels beyond the edge count as `outside`."""
    h, w = m.shape
    p = np.pad(m, r, constant_values=outside)
    out = np.zeros_like(m)
    for dy in range(2 * r + 1):
        for dx in range(2 * r + 1):
            out |= p[dy: dy + h, dx: dx + w]
    return out


def _thin(alpha: np.ndarray) -> np.ndarray:
    """Pixels of one part (alpha > 0) away from its opened body: spine_qa's slivers (TIP_THIN, TIP_NEAR)."""
    core = _box(~_box(~(alpha > 127), TIP_THIN, outside=True), TIP_THIN)
    return (alpha > 0) & ~_box(core, TIP_NEAR)


def _lip_ends(shell_a: np.ndarray, back_a: np.ndarray) -> np.ndarray:
    """The shell's thin bits (_thin) whose component touches the back part: the front lip's wedge ends."""
    near = _box(back_a > 0, 1)
    ends = np.zeros(shell_a.shape, bool)
    for c in components(_thin(shell_a)):
        if (c & near).any():
            ends |= c
    return ends


def drop_thin_tips(shell_a: np.ndarray, back_a: np.ndarray, a8: np.ndarray) -> tuple:
    """The back part's crescent band thins to a few pixels at the rim's two ends; with the feathered cut those ends are
    faint slivers that belong to neither part (spine_qa's slivers check: the same opening, TIP_THIN, and TIP_NEAR).
    The leg never reaches the rim's outer ends, so those pixels go to the shell whole: shell alpha = the image's, back
    alpha = 0 (the composite is unchanged). Returns (shell alpha, back alpha, pixels moved)."""
    tips = _thin(back_a)
    shell_a, back_a = shell_a.copy(), back_a.copy()
    shell_a[tips], back_a[tips] = a8[tips], 0
    return shell_a, back_a, int(tips.sum())


def drop_thin_lip_ends(shell_a: np.ndarray, back_a: np.ndarray, a8: np.ndarray) -> tuple:
    """The arc cut (top_arc) runs out to the silhouette at the opening's two ends, where the front lip meets the
    outline at a sharp angle: the shell thins there to a wedge, a sliver (the fox tiptoe: 75 + 72 px). Shell pixels
    away from the shell's opened body (TIP_THIN, TIP_NEAR) and touching the back part go behind whole: back alpha =
    the image's, shell alpha = 0 (the composite is unchanged; the leg never reaches the rim's ends).
    Returns (shell alpha, back alpha, pixels moved)."""
    ends = _lip_ends(shell_a, back_a)
    shell_a, back_a = shell_a.copy(), back_a.copy()
    back_a[ends], shell_a[ends] = a8[ends], 0
    return shell_a, back_a, int(ends.sum())


def split(img: Image.Image, at, width: float, depth: float | None):
    """(shell, back, info): the foot image cut at its ankle opening. Both keep the image's size and place (the same
    region attachment transform). Where the shell's feathered cut edge is partly transparent, the back part carries
    the rest of the alpha, so the shell drawn over the back composites to the original alpha. Transparent pixels keep
    their colour (the runtime samples straight alpha bilinearly)."""
    arr = np.asarray(img.convert("RGBA")).copy()
    back, info = back_mask(arr, at, width, depth)
    a8 = arr[..., 3]
    # the shell's cut edge is feathered over ~2 px (a binary cut along a pixel-thresholded inside stair-steps):
    # coverage falls from 1 to 0 as a 5x5 tent-blurred back mask rises from 0.25 to 0.75 (0.5 on the cut)
    soft = back.astype(np.float32)
    for _ in range(2):
        p = np.pad(soft, 1, mode="edge")
        soft = sum(p[1 + dy: p.shape[0] - 1 + dy, 1 + dx: p.shape[1] - 1 + dx]
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9
    cover = np.clip((0.75 - soft) * 2, 0, 1)
    a = a8.astype(np.float32) / 255
    s_ = a * cover                                     # the shell's alpha
    # the back's alpha b completes it: s + b (1 - s) = a, i.e. b = (a - s) / (1 - s); none under an opaque shell
    with np.errstate(divide="ignore", invalid="ignore"):
        b_ = np.where(s_ < 1 - 1e-6, (a - s_) / (1 - s_), 0.0)
    shell_a = np.round(s_ * 255).astype(np.uint8)
    back_a = np.round(np.clip(b_, 0, 1) * 255).astype(np.uint8)
    # The back's thin crescent tips go to the shell (drop_thin_tips); with the arc cut the front lip's thin end
    # wedges go behind (drop_thin_lip_ends). Both are judged once, on the cut's own masks, and applied together with
    # a fixed priority - a pixel both would move (where the feathered ends overlap) goes to the shell - so neither
    # clean-up sees the other's result: no ping-pong, the same output whatever the order.
    tips = _thin(back_a)
    ends = (_lip_ends(shell_a, back_a) & ~tips) if "tilt" in info else np.zeros_like(tips)
    shell_a, back_a = shell_a.copy(), back_a.copy()
    shell_a[tips], back_a[tips] = a8[tips], 0
    back_a[ends], shell_a[ends] = a8[ends], 0
    tips = int(tips.sum())
    if "tilt" in info:
        info["lip_ends_px"] = int(ends.sum())
    shell, rear = arr.copy(), arr.copy()
    shell[..., 3], rear[..., 3] = shell_a, back_a
    info["tips_px"] = tips
    info["back_px"] = int((back_a > 127).sum())
    info["shell_px"] = int((shell_a > 127).sum())
    return Image.fromarray(shell, "RGBA"), Image.fromarray(rear, "RGBA"), info


# ------------------------------------------------------------------ annotations

def feet_worn(ann, has_legs: bool) -> bool:
    """Whether the feet are drawn over a leg: over leg pieces, or over the hips (master.layers foot over_hips) when
    the trouser legs are part of the hips. A foot drawn under the hips (the moose) is not split."""
    return has_legs or ann.master.layers.get("foot") == "over_hips"


def opening(ann, name: str):
    """(ankle point, width or None, depth or None) of the foot output `name`, or None if it is not a foot with an
    annotated ankle."""
    for p in ann.pieces.values():
        if p.role != "foot":
            continue
        for o in p.outputs:
            if o.name == name and "ankle" in o.points:
                return tuple(o.points["ankle"]), o.widths.get("ankle"), o.depths.get("ankle")
    return None
