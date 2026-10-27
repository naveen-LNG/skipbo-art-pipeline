"""Cut an in-between legs sheet (prompts/legs-inbetweens.txt) into its drawings, colour-matched to the rig's own
trousers and boots, so a swap from the rig's parts to the first drawing (and between drawings) keeps its colours.

  uv run --with numpy --with pillow --with scipy scripts/cut_sheet.py refs/legs_sheet_squat.png squat <rig images dir>

Writes legs/<name>_<i>.png (1-based, left to right) and appends their cut_legs metrics to legs/metrics.jsonl.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cut_legs import cut, hsv  # noqa: E402

EXP = Path(__file__).resolve().parent.parent


def classes(rgb, alpha):
    h, s, v = hsv(rgb.astype(np.float32))
    on = alpha > 200
    red = ((h < 14) | (h > 340)) & (s > 0.4) & on
    belt = (h > 8) & (h < 36) & (v < 0.62) & (s > 0.3) & on & ~red
    yellow = on & ~red & ~belt
    return {"yellow": yellow, "red": red, "belt": belt}


def stats(imgs):
    """Per colour class: mean and std of RGB over the opaque pixels of the given RGBA images."""
    acc = {}
    for im in imgs:
        a = np.asarray(im.convert("RGBA")).astype(np.float32)
        for k, m in classes(a[..., :3], a[..., 3]).items():
            acc.setdefault(k, []).append(a[..., :3][m])
    return {k: (np.concatenate(v).mean(0), np.concatenate(v).std(0) + 1e-3) for k, v in acc.items()}


def match(im: Image.Image, target: dict) -> Image.Image:
    """Shift each colour class's mean and spread to the target's, blended across class edges."""
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    rgb, al = a[..., :3], a[..., 3]
    src = stats([im])
    out = rgb.copy()
    cls = classes(rgb, np.full_like(al, 255) * (al > 0))
    weight = sum(ndi.gaussian_filter(m.astype(np.float32), 2) for m in cls.values()) + 1e-6
    acc = np.zeros_like(rgb)
    for k, m in cls.items():
        mu_s, sd_s = src[k]
        mu_t, sd_t = target[k]
        w = ndi.gaussian_filter(m.astype(np.float32), 2)[..., None]
        acc += w * ((rgb - mu_s) * (sd_t / sd_s) + mu_t)
    out = acc / weight[..., None]
    return Image.fromarray(np.dstack([out.clip(0, 255), al]).astype(np.uint8), "RGBA")


def main(sheet: Path, name: str, rig_images: Path):
    im = Image.open(sheet).convert("RGB")
    rgb = np.asarray(im).astype(np.float32)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    fg = np.linalg.norm(rgb - np.median(border, 0), axis=2) > 40
    fg = ndi.binary_opening(fg, iterations=3)
    h, sat, val = hsv(rgb)
    boots = ((h < 14) | (h > 340)) & (sat > 0.45) & (val > 0.35)
    lab, n = ndi.label(fg)
    counts = np.bincount(lab[boots], minlength=n + 1)
    keep = [i for i in range(1, n + 1) if counts[i] > 0.0015 * fg.size]   # the drawings: shapes with boots (ghosts have none)
    boxes = []
    for i in keep:
        ys, xs = np.nonzero(lab == i)
        if len(xs) > 0.002 * fg.size:
            boxes.append([max(0, xs.min() - 6), max(0, ys.min() - 6), min(im.width, xs.max() + 7), min(im.height, ys.max() + 7)])
    boxes.sort()
    target = stats([Image.open(rig_images / f"beaver_{p}.png") for p in ("hips", "boot_l", "boot_r")])
    with open(EXP / "legs/metrics.jsonl", "a") as f:
        for i, box in enumerate(boxes, 1):
            out = EXP / f"legs/{name}_{i}.png"
            m = cut(sheet, out, box)
            match(Image.open(out), target).save(out)
            f.write(json.dumps(dict(m, name=f"{name}_{i}")) + "\n")
            print(out.name, json.dumps(m))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
