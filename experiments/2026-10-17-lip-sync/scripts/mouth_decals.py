#!/usr/bin/env python3
"""Mouth shapes as decals on the rig head's own muzzle (v2 of extract_mouths.py).

    uv run --with numpy --with pillow --with scipy --with opencv-python-headless scripts/mouth_decals.py \
        <sheet.png> --heads <face-heads dir> --out beaver/mouths [--replace H=<png> ...]

v1 swapped a muzzle-sized patch cut from each generated head. Every generation paints its own muzzle (a little
wider, taller or differently shaded), so the muzzle outline swam between shapes, the feathered border left soft
double edges, and the fade under the nose blurred the nose shadow. v2 swaps only the mouth:

1. Register each shape's head on the rig's neutral head (extract_mouths.register).
2. Mouth features of a shape: inside its own muzzle, the pixels that aren't cream (lines, lips, the dark inside,
   teeth, tongue), closed and filled. That is the decal; only the philtrum line above the mouth is left to the base.
3. The base: the rig's neutral head with its own mouth painted out (OpenCV inpainting over the cream) and its
   philtrum (nose-to-mouth line) erased, each row bridged across it.
   A mouth painted bigger than the rig muzzle is scaled about its top until it fits `--margin` px inside it.
4. Each patch = the base, with the shape's decal (colour-matched on a ring of cream around it, 2 px feather) laid
   in, snapped sideways so its philtrum meets the base's. Its alpha is the rig's muzzle: everything outside the decal
   is the rig head's own pixels, so the patch edge is invisible and the muzzle outline and nose never move.
Writes <out>/mouth_<X..H>.png, base.png, decals.json, review.png (and decal_masks.png: each decal's outline).
"""
import argparse, json, os, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, os.path.dirname(__file__))
from extract_mouths import ORDER, NAMES, cut_grid, cut_single, register   # noqa: E402


def cream(a):
    """The muzzle's cream (and the white teeth): warm and light, unlike the orange fur (G/R ~0.55) or the dark-red mouth."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (g / np.maximum(r, 1) > 0.70) & (r > 170)


def muzzle(a, H, W):
    """The muzzle region, its holes (the mouth) filled: the largest cream blob in the lower middle of the head."""
    yy, xx = np.mgrid[:H, :W]
    m = cream(a) & (a[..., 3] > 200) & (yy > H * 0.35) & (xx > W * 0.15) & (xx < W * 0.85)
    m = ndimage.binary_closing(m, iterations=3)
    lab, n = ndimage.label(m)
    m = lab == 1 + int(np.argmax(ndimage.sum(m, lab, range(1, n + 1))))
    # each row filled between its outermost cream pixels: an open mouth splits the cream ring at the lower lip,
    # so hole filling alone leaves the mouth outside the muzzle (the muzzle is convex enough for this)
    out = np.zeros_like(m)
    for y in np.where(m.any(1))[0]:
        xs = np.where(m[y])[0]
        out[y, xs.min(): xs.max() + 1] = True
    return out & (a[..., 3] > 200)


def features(a, muz, y_from):
    """Mouth pixels inside a muzzle: not plain cream (dark lines, lips, the inside, the tongue) or the white teeth."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    luma = 0.3 * r + 0.59 * g + 0.11 * b
    plain = cream(a) & (luma > 0.76 * np.median(luma[muz]))          # cream, not a line (the nose's soft shadow is cream)
    teeth = (b > 205) & (r - b < 25)
    inner = ndimage.binary_erosion(muz, iterations=6)               # not the muzzle's own outline
    f = (~plain | teeth) & inner
    f[:y_from] = False
    f = ndimage.binary_opening(f, iterations=1)                     # specks of shading
    lab, n = ndimage.label(ndimage.binary_closing(f, iterations=4))
    if n:
        sizes = ndimage.sum(f, lab, range(1, n + 1))
        f = np.isin(lab, 1 + np.where(sizes >= max(60, 0.08 * sizes.max()))[0])
    return ndimage.binary_fill_holes(f)


def mouth_top(f):
    """Top row of the mouth itself: thin vertical lines (the philtrum, pucker creases) are opened away first."""
    body = ndimage.binary_opening(f, structure=np.ones((1, 11), bool))
    lab, n = ndimage.label(body)
    if not n:
        return int(np.argmax(f.sum(1) > 24))
    big = lab == 1 + int(np.argmax(ndimage.sum(body, lab, range(1, n + 1))))
    return int(np.where(big)[0].min())


def philtrum_x(a, y, x0, x1):
    """x of the philtrum line at row y: the darkest pixel of that row near the middle, or None without a clear line."""
    luma = a[y, x0:x1, :3].mean(-1)
    i = int(np.argmin(luma))
    return x0 + i if luma[i] < np.median(luma) - 25 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--heads", required=True, help="the rig's face-heads dir (neutral is the base)")
    ap.add_argument("--char", default="beaver")
    ap.add_argument("--out", required=True)
    ap.add_argument("--replace", action="append", default=[], metavar="SHAPE=PNG")
    ap.add_argument("--grow", type=int, default=5, help="px of cream kept around each decal's features")
    ap.add_argument("--margin", type=int, default=6, help="px a decal keeps inside the rig muzzle's outline")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ref_im = Image.open(f"{a.heads}/{a.char}_head_neutral.png").convert("RGBA")
    ref = np.asarray(ref_im).astype(np.float32)
    H, W = ref.shape[:2]
    heads = cut_grid(a.sheet)
    for r in a.replace:
        k, path = r.split("=", 1)
        heads[ORDER.index(k)] = cut_single(path)
    regs = {}
    for k, h in zip(ORDER, heads):
        im, _ = register(h, ref_im)
        regs[k] = np.asarray(im).astype(np.float32)

    # the nose (dark blob, middle of the face): features start below it
    luma = ref[..., :3].mean(-1)
    yy, xx = np.mgrid[:H, :W]
    dark = (luma < 90) & (ref[..., 3] > 200) & (xx > W * 0.3) & (xx < W * 0.7) & (yy > H * 0.2) & (yy < H * 0.65)
    lab, n = ndimage.label(dark)
    nose = lab == 1 + int(np.argmax(ndimage.sum(dark, lab, range(1, n + 1))))
    nose_bottom = int(np.where(nose)[0].max())
    cx = int(np.where(nose)[1].mean())

    import cv2
    rmuz = muzzle(ref, H, W)
    inside = ndimage.binary_erosion(rmuz, iterations=a.margin)
    feats, fit = {}, {}
    for k, v in regs.items():
        f = features(v, muzzle(v, H, W), nose_bottom + 10)
        top = mouth_top(f)
        # a mouth painted bigger than the rig muzzle (D's dropped jaw) is scaled about its top until it fits inside;
        # otherwise its lower lip lands on the fur and the mouth reads as sliding off the face
        s = 1.0
        while s > 0.6:
            M = np.float32([[s, 0, cx * (1 - s)], [0, s, top * (1 - s)]])
            fw = cv2.warpAffine(f.astype(np.uint8), M, (W, H), flags=cv2.INTER_NEAREST) > 0
            if (ndimage.binary_dilation(fw, iterations=a.grow) & ~inside).sum() <= 20:
                break
            s -= 0.02
        if s < 1.0:
            regs[k] = cv2.warpAffine(v, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            f = fw
        feats[k], fit[k] = f & rmuz, round(s, 2)
    tops = {k: mouth_top(f) for k, f in feats.items()}
    # The philtrum (nose-to-mouth line) is drawn once, from the rig head's own line: each generated shape painted its
    # own, and where two different lines met there was a visible break. The base has the rig's line erased; each patch
    # gets one continuous line from the nose to its mouth's top, re-drawn from the rig line's cross-section.
    y0 = nose_bottom + 1
    rig_top = mouth_top(features(ref, rmuz, nose_bottom + 10))
    found = {}                                      # rig line x per row where a clear line is seen
    for y in range(y0, rig_top + 3):
        x = philtrum_x(ref, y, cx - 30, cx + 30)
        if x is not None:
            found[y] = x
    fy = np.array(sorted(found))
    kx, cx0 = np.polyfit(fy, [found[y] for y in fy], 1)
    # one straight fitted line for every row: per-row detection jitters and skips rows, and erasing along it left
    # remnants of the old line that showed as a ladder of ticks
    line = {y: int(round(kx * y + cx0)) for y in range(y0, rig_top + 3)}
    HALF = 7
    def strip_dev(img, y, x):
        """the line's cross-section at (y, x): pixels minus the straight ramp between the strip's two ends"""
        seg = img[y, x - HALF - 1: x + HALF + 2, :3]
        ramp = np.linspace(seg[0], seg[-1], len(seg))
        return (seg - ramp)[1:-1]
    rows = [y for y in found if nose_bottom + 6 <= y <= min(nose_bottom + 22, rig_top - 4)]
    dev = np.mean([strip_dev(ref, y, found[y]) for y in rows], 0)          # (2*HALF+1, 3): the rig's line, darkening
    # the base: the rig head with its own philtrum erased (each row bridged across the line) ...
    base_rgb = ref[..., :3].copy()
    E = HALF + 3                                    # erase a little wider than the line
    for y, x in line.items():
        seg = base_rgb[y, x - E - 1: x + E + 2]
        base_rgb[y, x - E - 1: x + E + 2] = np.linspace(seg[0], seg[-1], len(seg))
    # ... and its mouth inpainted (Telea, then a soft blur inside the hole)
    own = features(ref, rmuz, rig_top - 2)
    hole = ndimage.binary_dilation(own, iterations=4) & rmuz & (yy >= rig_top - 6)
    bgr = cv2.cvtColor(base_rgb.astype(np.uint8), cv2.COLOR_RGB2BGR)
    base_rgb = cv2.cvtColor(cv2.inpaint(bgr, hole.astype(np.uint8) * 255, 9, cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB).astype(np.float32)
    blur = cv2.GaussianBlur(base_rgb, (0, 0), 6)
    hw = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 3)[..., None]
    base_rgb = base_rgb * (1 - hw) + blur * hw
    base = np.dstack([base_rgb, ref[..., 3]])
    Image.fromarray(base.astype(np.uint8), "RGBA").save(f"{a.out}/base.png")
    # the patch's alpha: the rig muzzle (pixels there equal the rig head's except the line and the mouth), grown a little
    alpha = ndimage.binary_dilation(rmuz, iterations=3).astype(np.float32)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 2) * (ref[..., 3] / 255)
    bx = line[min(line)]
    info = {"nose_bottom": nose_bottom, "rig_mouth_top": rig_top, "mouth_tops": tops, "fit_scale": fit,
            "philtrum_x_at_nose": bx, "shapes": {}}
    out, decals = {}, {}
    xs_dev = np.arange(-HALF, HALF + 1, dtype=np.float32)
    def line_meets_mouth(f, x_at, body_top):
        """first row where the shape's pixels around the line run wider than a line: its upper lip. Searched from just
        above the mouth body, so cheek creases near the nose (the "oo" pucker, F/V) aren't taken for the lip."""
        for y in range(max(nose_bottom + 10, body_top - 20), H):
            x = int(x_at(y))
            if not f[y, x - 2: x + 3].any():
                continue
            l = r = x
            while l > 0 and f[y, l - 1]:
                l -= 1
            while r < W - 1 and f[y, r + 1]:
                r += 1
            if r - l + 1 > 12:
                return y
        return None
    for k, v in regs.items():
        m_ = line_meets_mouth(feats[k], lambda y: kx * y + cx0, tops[k])
        top = m_ if m_ is not None else tops[k]
        tops[k] = top
        d = feats[k].copy()
        d[: top - 3] = False                         # the decal is the mouth only; the line above it is drawn below
        d = ndimage.binary_dilation(d, iterations=a.grow) & rmuz & (yy >= top - 3 - a.grow)
        mx = philtrum_x(v, top - 3, cx - 30, cx + 30)
        mx = bx if mx is None or abs(mx - bx) > 12 else mx
        decals[k] = d
        ring = ndimage.binary_dilation(d, iterations=6) & ~ndimage.binary_erosion(d, iterations=2) & rmuz & ~hole
        rgb = v[..., :3].copy()
        if ring.sum() > 50:
            for c in range(3):                                     # cream around the decal -> the base's cream
                m1, s1 = v[..., c][ring].mean(), v[..., c][ring].std() + 1e-6
                m2, s2 = base[..., c][ring].mean(), base[..., c][ring].std()
                # the cream ring's mean, contrast barely touched: scaling by the ring's std washed the dark mouths out
                rgb[..., c] = (rgb[..., c] - m1) * float(np.clip(s2 / s1, 0.9, 1.1)) + m2
        w = cv2.GaussianBlur(d.astype(np.float32), (0, 0), 1.5)[..., None]
        comp = base[..., :3] * (1 - w) + np.clip(rgb, 0, 255) * w
        # one continuous philtrum, nose to this mouth's top, slanting from the rig line's x to where this mouth's starts
        for y in range(y0, top + 2):
            t = (y - y0) / max(1, top + 1 - y0)
            x = bx + (mx - bx) * t
            xi = int(np.floor(x))
            shifted = np.stack([np.interp(xs_dev, xs_dev + (x - xi), dev[:, c]) for c in range(3)], -1)
            keep = 1 - w[y, xi - HALF: xi + HALF + 1]    # never over the mouth: the decal carries its own line there
            comp[y, xi - HALF: xi + HALF + 1] += shifted * keep
        p = np.dstack([comp, alpha * 255]).astype(np.uint8)
        Image.fromarray(p, "RGBA").save(f"{a.out}/mouth_{k}.png")
        out[k] = Image.fromarray(p, "RGBA")
        ys, xs = np.where(d)
        info["shapes"][k] = {"line_end_x": int(mx), "decal_bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                             "decal_px": int(d.sum()), "outside_muzzle_px": int((feats[k] & ~rmuz).sum())}
    bb = Image.fromarray(((alpha > 0.02) * 255).astype(np.uint8)).getbbox()
    info.update({"order": ORDER, "names": NAMES, "mask_bbox": list(bb), "head_size": [W, H]})
    json.dump(info, open(f"{a.out}/mouths.json", "w"), indent=1)
    # review: each patch on the rig head, the decal outlined in a second copy
    crop = (int(W * 0.15), int(H * 0.38), int(W * 0.85), H)
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    sheet = Image.new("RGB", (cw * 9, (ch + 24) * 2), (214, 214, 214))
    dr = ImageDraw.Draw(sheet)
    for i, k in enumerate(ORDER):
        t = Image.new("RGBA", (W, H), (214, 214, 214, 255))
        t.alpha_composite(ref_im)
        t.alpha_composite(out[k])
        sheet.paste(t.crop(crop).convert("RGB"), (i * cw, 24))
        o = np.asarray(t).copy()
        edge = decals[k] & ~ndimage.binary_erosion(decals[k])
        edge |= rmuz & ~ndimage.binary_erosion(rmuz)
        o[ndimage.binary_dilation(edge)] = (255, 0, 255, 255)
        sheet.paste(Image.fromarray(o).crop(crop).convert("RGB"), (i * cw, ch + 48))
        dr.text((i * cw + 6, 6), f"{k}  {NAMES[k]}", fill=(20, 20, 20))
    sheet.save(f"{a.out}/review.png")
    print(json.dumps({k: info[k] for k in ("nose_bottom", "rig_mouth_top", "mouth_tops", "fit_scale", "philtrum_x_at_nose")} |
                     {"line_end_x": {k: s["line_end_x"] for k, s in info["shapes"].items()},
                      "outside_muzzle": {k: s["outside_muzzle_px"] for k, s in info["shapes"].items()}}))


if __name__ == "__main__":
    main()
