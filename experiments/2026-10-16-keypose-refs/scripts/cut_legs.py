"""Cut the lower body (belt, trousers, boots) out of a key-pose reference as a whole-legs pose variant.

  uv run --with numpy --with pillow --with scipy scripts/cut_legs.py refs/hurdle_crouch.png out.png x0 y0 x1 y1

The box (reference px) holds the legs; inside it only trouser yellow, boot red and the belt band are kept (the tail,
paws, hurdle posts and the grey background drop out by colour), holes are filled, and the edge is softened. Prints
JSON: the belt's top centre and width and the soles' y, in the cut image's px (the rig scales by belt width and puts
the belt on the rest belt).
"""
import json
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def hsv(rgb):
    r, g, b = [rgb[..., i] / 255.0 for i in range(3)]
    mx, mn = rgb.max(-1) / 255.0, rgb.min(-1) / 255.0
    d = mx - mn + 1e-9
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    return h, d / (mx + 1e-9), mx


def legs_mask(rgb):
    h, s, v = hsv(rgb.astype(np.float32))
    yellow = (h > 22) & (h < 56) & (s > 0.28) & (v > 0.33)
    red = ((h < 14) | (h > 340)) & (s > 0.45) & (v > 0.35)
    brown = (h > 8) & (h < 42) & (s > 0.3) & (v > 0.18) & (v < 0.62)
    rows = np.nonzero(yellow.sum(1) > 0.25 * yellow.sum(1).max())[0]
    top = rows.min()                                            # trousers' first wide yellow row (below the belt)
    belt = np.zeros_like(brown)
    belt[max(0, top - int(0.07 * rgb.shape[0])):top + 6] = True
    xs = np.nonzero(yellow[top:top + 30].any(0))[0]
    belt[:, :xs.min() - 8] = False
    belt[:, xs.max() + 8:] = False
    m = yellow | (red & (np.arange(rgb.shape[0])[:, None] > top)) | (brown & belt)
    m = ndi.binary_closing(m, iterations=4)
    m = ndi.binary_fill_holes(m)
    lab, n = ndi.label(m)
    sizes = ndi.sum(m, lab, range(1, n + 1))
    keep = [i + 1 for i, sz in enumerate(sizes) if sz > 0.02 * sizes.max()]
    m = np.isin(lab, keep)
    m = ndi.binary_opening(m, iterations=2)
    tail = (h > 12) & (h < 28) & (v < 0.5) & (s > 0.3)             # dark brown (tail, paws) below the belt band
    tail[: top + int(0.08 * rgb.shape[0])] = False
    m &= ~ndi.binary_dilation(tail, iterations=2)
    m = ndi.median_filter(m.astype(np.uint8), 9).astype(bool)      # smooth the ragged shaded edges
    lab, n = ndi.label(m)
    sizes = ndi.sum(m, lab, range(1, n + 1))
    m = np.isin(lab, [i + 1 for i, sz in enumerate(sizes) if sz > 0.02 * sizes.max()])
    return ndi.binary_fill_holes(m)


def metrics(m, rgb):
    """belt_top: the belt's middle (front view: the buckle) and the cut's top row; belt_w: the cut's width along
    the belt (the rows that are mostly belt brown, wherever the thighs flare); sole_y: the lowest row."""
    rows = np.nonzero(m.any(1))[0]
    y0, y1 = rows.min(), rows.max()
    h, s, v = hsv(rgb.astype(np.float32))
    brown = (h > 8) & (h < 42) & (s > 0.3) & (v > 0.18) & (v < 0.62) & m
    frac = brown.sum(1) / np.maximum(m.sum(1), 1)
    belt_rows = np.nonzero(frac[: y0 + int(0.3 * (y1 - y0))] > 0.35)[0]     # rows across the belt (mostly brown)
    yb = int(np.median(belt_rows))
    xs = np.nonzero(m[yb])[0]
    return {"belt_top": [float((xs.min() + xs.max()) / 2), float(y0)], "buckle_y": float(yb), "belt_w": float(np.ptp(xs)), "sole_y": float(y1)}


def cut(src, out, box, mirror=False):
    im = Image.open(src).convert("RGB")
    if mirror:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    x0, y0, x1, y1 = box
    rgb = np.asarray(im.crop((x0, y0, x1, y1)))
    m = ndi.binary_opening(legs_mask(rgb), iterations=3)             # no thin bits left on the edge
    yb = int(metrics(m, rgb)["buckle_y"])                             # the belt band is solid edge to edge: a notch
    for y in range(int(np.nonzero(m.any(1))[0].min()), 2 * yb + 1):  # cut into it shows the background under the hem
        xs = np.nonzero(m[y])[0]
        if len(xs):
            m[y, xs.min():xs.max() + 1] = True
    alpha = ndi.gaussian_filter(m.astype(np.float32), 1.2)
    rows, cols = np.nonzero(m.any(1))[0], np.nonzero(m.any(0))[0]
    a0, a1, b0, b1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    rgba = np.dstack([rgb, (alpha * 255).clip(0, 255).astype(np.uint8)])[a0:a1, b0:b1]
    Image.fromarray(rgba, "RGBA").save(out)
    return metrics(m[a0:a1, b0:b1], rgb[a0:a1, b0:b1])


if __name__ == "__main__":
    src, out, *box = sys.argv[1:]
    print(json.dumps(cut(src, out, [int(v) for v in box])))
