#!/usr/bin/env python3
"""Mouth sheet (3x3 heads) -> one mouth patch per shape, registered on the rig's neutral head.

    uv run --with numpy --with pillow --with scipy scripts/extract_mouths.py beaver/runs/beaver-mouths/<sheet>.png \
        --head ../2026-10-15-beaver-jev-hands/beaver/face-heads/beaver_head_neutral.png --out beaver/mouths

1. Key the flat grey background, cut the nine heads from the 3x3 grid.
2. Register each head on the rig's neutral head: scale from the alpha bbox width, then translation by phase
   correlation on the upper face (eyes and nose, which the prompt holds fixed).
3. The patch mask: where the heads differ from the sheet's own rest head (union over shapes), kept to the
   muzzle around the mouth, closed, dilated and feathered. One mask for every shape, so they swap cleanly.
4. Colour: each patch is matched to the rig head on the mask's soft ring (per-channel mean/std), so the
   painted muzzle meets the rig head without a seam.
Writes <out>/mouth_<X..H>.png (head-sized, transparent outside the patch; it covers the head's own mouth),
<out>/mask.png, <out>/mouths.json and a review sheet <out>/review.png.
"""
import argparse, json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ORDER = ["X", "A", "B", "C", "D", "E", "F", "G", "H"]     # sheet order: rest, MBP, consonant, eh, ah, oh, oo, FV, L
NAMES = {"X": "rest", "A": "MBP", "B": "consonant/ee", "C": "eh", "D": "ah", "E": "oh/er", "F": "oo/w", "G": "F/V", "H": "L"}


def key(im):
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    bg = np.median(np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)]), 0)
    d = np.abs(a - bg).max(-1)
    # Colour alone can't key this: light grey shading on white teeth is as close to the backdrop as the backdrop
    # itself, and keying it punched see-through holes in the teeth. So only large non-solid regions are backdrop;
    # small enclosed ones (gaps in the teeth, a highlight) are part of the head.
    from scipy import ndimage
    soft = np.clip((d - 6) / 10, 0, 1)
    lab, n = ndimage.label(soft <= 0.5)
    sizes = ndimage.sum(np.ones_like(soft), lab, range(1, n + 1))
    big = np.zeros(n + 1, bool)
    big[1:] = sizes > 0.002 * soft.size
    alpha = np.where(big[lab], soft, 1.0)
    return a, alpha


def cut_single(path):
    """One head alone on a flat background (a re-rolled shape)."""
    a, alpha = key(Image.open(path))
    ys, xs = np.where(alpha > 0.5)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return Image.fromarray(np.dstack([a[y0:y1, x0:x1], alpha[y0:y1, x0:x1, None] * 255]).astype(np.uint8), "RGBA")


def cut_grid(path):
    im = Image.open(path)
    a, alpha = key(im)
    H, W = alpha.shape
    heads = []
    for k in range(9):
        r, c = divmod(k, 3)
        sl = (slice(r * H // 3, (r + 1) * H // 3), slice(c * W // 3, (c + 1) * W // 3))
        al = alpha[sl]
        ys, xs = np.where(al > 0.5)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        rgba = np.dstack([a[sl][y0:y1, x0:x1], al[y0:y1, x0:x1, None] * 255]).astype(np.uint8)
        heads.append(Image.fromarray(rgba, "RGBA"))
    return heads


def phase_shift(a, b):
    """Translation (dy, dx) that moves b onto a."""
    A, B = np.fft.fft2(a), np.fft.fft2(b)
    R = A * np.conj(B)
    r = np.fft.ifft2(R / (np.abs(R) + 1e-6)).real
    dy, dx = np.unravel_index(np.argmax(r), r.shape)
    h, w = a.shape
    return (dy - h if dy > h // 2 else dy), (dx - w if dx > w // 2 else dx)


def register(head, ref):
    """head (RGBA) resized and placed on ref's canvas so eyes and nose line up."""
    rb = ref.getbbox()
    hb = head.getbbox()
    s = (rb[2] - rb[0]) / (hb[2] - hb[0])
    h = head.resize((round(head.width * s), round(head.height * s)), Image.LANCZOS)
    canvas = Image.new("RGBA", ref.size)
    canvas.alpha_composite(h, (rb[0] - round(hb[0] * s), rb[1] - round(hb[1] * s)))
    g = lambda im: np.asarray(im.convert("L"), np.float32)[: int(ref.height * 0.55)]   # upper face: eyes, nose
    dy, dx = phase_shift(g(ref), g(canvas))
    out = Image.new("RGBA", ref.size)
    out.alpha_composite(canvas, (0, 0)) if (dx, dy) == (0, 0) else out.paste(canvas, (int(dx), int(dy)), canvas)
    return out, {"scale": round(s, 4), "dx": int(dx), "dy": int(dy)}


def colour_match(src, ref, w):
    """Per-channel mean/std of src -> ref, weighted by w."""
    out = src.copy()
    for c in range(3):
        m1, m2 = np.average(src[..., c], weights=w), np.average(ref[..., c], weights=w)
        s1 = np.sqrt(np.average((src[..., c] - m1) ** 2, weights=w)) + 1e-6
        s2 = np.sqrt(np.average((ref[..., c] - m2) ** 2, weights=w))
        out[..., c] = (src[..., c] - m1) * (s2 / s1) + m2
    return np.clip(out, 0, 255)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--head", required=True, help="the rig's neutral head (the patches are registered on it)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--grow", type=int, default=14, help="px the changed region is grown by")
    ap.add_argument("--feather", type=float, default=6)
    ap.add_argument("--inset", type=int, default=10, help="px the patch keeps inside the rig head's outline")
    ap.add_argument("--replace", action="append", default=[], metavar="SHAPE=PNG",
                    help="take one shape from a single-head image instead of the sheet (a re-roll)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ref = Image.open(a.head).convert("RGBA")
    heads = cut_grid(a.sheet)
    for r in a.replace:
        k, path = r.split("=", 1)
        heads[ORDER.index(k)] = cut_single(path)
    regs, info = [], {}
    for k, h in zip(ORDER, heads):
        r, inf = register(h, ref)
        regs.append(r)
        info[k] = inf
    arr = [np.asarray(r).astype(np.float32) for r in regs]
    rest = arr[0]
    H, W = ref.height, ref.width
    yy, xx = np.mgrid[:H, :W]
    # the mouth lives below the nose: search the lower 60% of the head, middle 60% of its width
    roi = (yy > H * 0.45) & (xx > W * 0.2) & (xx < W * 0.8)
    diff = np.zeros((H, W), bool)
    for x in arr[1:]:
        d = np.abs(x[..., :3] - rest[..., :3]).max(-1)
        diff |= (d > 40) & roi & (x[..., 3] > 200)
    # the rig head's own mouth must be covered too: where the rig head differs from the sheet's rest head
    refa = np.asarray(ref).astype(np.float32)
    d0 = np.abs(refa[..., :3] - rest[..., :3]).max(-1)
    own = (d0 > 50) & roi & (refa[..., 3] > 200)
    m = Image.fromarray(((diff | own) * 255).astype(np.uint8))
    # close small holes, then one solid blob (filled bbox-hull by a big max/min filter)
    m = m.filter(ImageFilter.MaxFilter(31)).filter(ImageFilter.MinFilter(31))
    m = m.filter(ImageFilter.MaxFilter(2 * a.grow + 1)).filter(ImageFilter.GaussianBlur(a.feather))
    mask = np.asarray(m).astype(np.float32) / 255 * (refa[..., 3] / 255)
    # the patch starts just below the nose, so the nose always comes from the rig head: a patch that covers it
    # makes the nose twitch by its few pixels of registration error on every swap
    from scipy import ndimage
    luma = refa[..., :3].mean(-1)
    dark = (luma < 90) & (refa[..., 3] > 200) & (xx > W * 0.3) & (xx < W * 0.7) & (yy > H * 0.2) & (yy < H * 0.65)
    lab, n = ndimage.label(dark)
    nose = lab == (1 + int(np.argmax(ndimage.sum(dark, lab, range(1, n + 1)))))
    nose_bottom = int(np.where(nose)[0].max())
    mask *= np.clip((yy - nose_bottom - 3) / 8, 0, 1)
    # and stays inside the rig head's own outline: the head's silhouette never changes, and a patch reaching the
    # chin edge met the sweater collar (spine_qa seams, mouth_patch/torso)
    inside = Image.fromarray(((refa[..., 3] > 200) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(2 * a.inset + 1))
    mask *= np.asarray(inside.filter(ImageFilter.GaussianBlur(3))).astype(np.float32) / 255
    Image.fromarray((mask * 255).astype(np.uint8)).save(f"{a.out}/mask.png")
    ring = (mask > 0.05) & (mask < 0.6)
    out = {}
    for k, x in zip(ORDER, arr):
        rgb = colour_match(x[..., :3], refa[..., :3], ring.astype(np.float32) + 1e-6)
        alpha = mask * (x[..., 3] / 255)
        p = np.dstack([rgb, alpha * 255]).astype(np.uint8)
        Image.fromarray(p, "RGBA").save(f"{a.out}/mouth_{k}.png")
        out[k] = Image.fromarray(p, "RGBA")
    bb = Image.fromarray((mask > 0.02).astype(np.uint8) * 255).getbbox()
    json.dump({"nose_bottom": nose_bottom, "order": ORDER, "names": NAMES, "registration": info, "mask_bbox": bb, "head_size": ref.size},
              open(f"{a.out}/mouths.json", "w"), indent=1)
    # review: rig head + each patch, cropped around the face, labelled
    from PIL import ImageDraw
    crop = (0, int(H * 0.25), W, H)
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    sheet = Image.new("RGB", (cw * 5, (ch + 30) * 2), (214, 214, 214))
    dr = ImageDraw.Draw(sheet)
    for i, k in enumerate(ORDER + ["mask"]):
        if k == "mask":
            t = Image.new("RGBA", ref.size, (214, 214, 214, 255))
            t.alpha_composite(ref)
            tint = np.zeros((H, W, 4), np.uint8)
            tint[..., 0], tint[..., 2], tint[..., 3] = 255, 255, (mask * 160).astype(np.uint8)
            t.alpha_composite(Image.fromarray(tint, "RGBA"))
        else:
            t = Image.new("RGBA", ref.size, (214, 214, 214, 255))
            t.alpha_composite(ref)
            t.alpha_composite(out[k])
        x0, y0 = (i % 5) * cw, (i // 5) * (ch + 30)
        sheet.paste(t.crop(crop).convert("RGB"), (x0, y0 + 30))
        dr.text((x0 + 10, y0 + 8), f"{k}  {NAMES.get(k, 'patch mask')}", fill=(20, 20, 20))
    sheet.save(f"{a.out}/review.png")
    print(json.dumps({"registration": info, "mask_bbox": bb}))


if __name__ == "__main__":
    main()
