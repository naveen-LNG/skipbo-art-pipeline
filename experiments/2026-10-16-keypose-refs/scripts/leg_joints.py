"""Skeleton targets from the legs drawings: per leg the hip, knee, ankle and sole, plus the belt's middle, in each
drawing's px. Only the joints are used (the bones drive the rig's own painting), not the drawings' paint.

  uv run --with numpy --with pillow --with scipy --with scikit-image scripts/leg_joints.py      -> legs/joints.json, legs/joints.png

Per side of the buckle: the boot is the largest red shape (ankle: the middle of its top, sole: the middle of its
bottom); the trouser leg is the drawing below the crotch on that side without the boot; its skeleton's path from
the crotch is ignored: seen from the front a crouch's thighs run out sideways at belt height, so the hip is fixed on
the belt (HIP_X, HIP_Y) and the knee is the leg's outer bulge (its widest point out to the side, past the hip-ankle
line), set in by half the cuff's thickness; a leg with no bulge (STRAIGHT) has its knee halfway down.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from skimage.morphology import skeletonize

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cut_legs import hsv, metrics  # noqa: E402

EXP = Path(__file__).resolve().parent.parent
HIP_X, HIP_Y = 0.24, 0.32     # the hip joint, from the belt's middle, in belt widths (rest legs: the thigh's centre, a
                              # little below the belt)
STRAIGHT = 0.06               # belt widths: a knee that sticks out less than this past the hip-ankle line is straight
STRAIGHT_LEGS = {"rig_rest", "jump_2"}   # standing and the push-off: the wide hips would read as a knee
DRAWINGS = ["rig_rest", "squat_3", "squat_34", "squat_4", "squat_45", "squat_5",
            "jump_2", "jump_23", "jump_3", "jump_34", "jump_4", "jump_5"]


def path_on(skel: np.ndarray, a, b) -> np.ndarray:
    """Shortest 8-connected path on skeleton pixels from the pixel nearest a to the one nearest b; (n, 2) as (x, y)."""
    ys, xs = np.nonzero(skel)
    idx = -np.ones(skel.shape, int)
    idx[ys, xs] = np.arange(len(xs))
    rows, cols, w = [], [], []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx or dy:
                y2, x2 = ys + dy, xs + dx
                ok = (y2 >= 0) & (y2 < skel.shape[0]) & (x2 >= 0) & (x2 < skel.shape[1])
                j = np.full(len(xs), -1)
                j[ok] = idx[y2[ok], x2[ok]]
                k = j >= 0
                rows += list(np.nonzero(k)[0]); cols += list(j[k]); w += [np.hypot(dx, dy)] * int(k.sum())
    G = coo_matrix((w, (rows, cols)), shape=(len(xs), len(xs))).tocsr()
    pts = np.stack([xs, ys], 1).astype(float)
    ia, ib = np.argmin(np.linalg.norm(pts - a, axis=1)), np.argmin(np.linalg.norm(pts - b, axis=1))
    _, pred = dijkstra(G, indices=ia, return_predecessors=True)
    out, j = [ib], ib
    while j != ia and pred[j] >= 0:
        j = pred[j]; out.append(j)
    return pts[out[::-1]]


def joints(img: Image.Image, straight: bool = False) -> dict:
    a = np.asarray(img.convert("RGBA"))
    m = a[..., 3] > 127
    rgb = a[..., :3]
    met = metrics(m, rgb)
    bx, by = met["belt_top"][0], met["buckle_y"]
    h, s, v = hsv(rgb.astype(np.float32))
    red = ((h < 14) | (h > 340)) & (s > 0.4) & m
    H, W = m.shape
    # the crotch: first row below the belt where the middle column is open
    col = m[:, int(bx) - 3:int(bx) + 4].all(1)
    below = np.nonzero(~col[int(by) + 5:])[0]
    crotch = int(by) + 5 + (int(below[0]) if len(below) else int(0.45 * (H - by)))
    out = {"belt": [float(bx), float(by)], "belt_w": met["belt_w"], "crotch_y": crotch}
    for side, sel in (("l", np.arange(W) > bx), ("r", np.arange(W) < bx)):   # the beaver's left is the picture's right
        r_ = red & sel[None, :]
        lab, n = ndi.label(r_)
        boot = lab == (np.argmax(ndi.sum(r_, lab, range(1, n + 1))) + 1)
        ys, xs = np.nonzero(boot)
        top, bot = ys.min(), ys.max()
        ank = np.array([xs[ys < top + 0.15 * (bot - top)].mean(), top + 0.08 * (bot - top)])
        sole = np.array([xs[ys > bot - 0.12 * (bot - top)].mean(), float(bot)])
        sgn = 1 if side == "l" else -1
        bw = met["belt_w"]
        hip0 = np.array([bx + sgn * HIP_X * bw, by + HIP_Y * bw])           # fixed on the belt: the hips don't bend
        cuff = float(np.ptp(xs[ys < top + 0.1 * (bot - top)]))               # the leg's thickness at the cuff
        rows = np.arange(int(hip0[1]), int(ank[1]))
        outer = []                                                           # the leg's outer edge, row by row
        for y in rows:
            xx = np.nonzero(m[y] & sel)[0]
            outer.append((xx.max() if side == "l" else xx.min()) if len(xx) else np.nan)
        outer = np.array(outer, float)
        chord_x = hip0[0] + (rows - hip0[1]) / max(ank[1] - hip0[1], 1) * (ank[0] - hip0[0])
        bulge = sgn * (outer - chord_x) - 0.5 * cuff                        # how far the knee sticks out past the chord
        i = int(np.nanargmax(bulge))
        if bulge[i] > STRAIGHT * bw and not straight:
            knee = np.array([outer[i] - sgn * 0.5 * cuff, float(rows[i])])
        else:                                                                # nearly straight: halfway down
            knee = hip0 + 0.5 * (ank - hip0)
        P = np.array([hip0, knee, ank])
        out[side] = {"hip": hip0.round(1).tolist(), "knee": np.asarray(knee).round(1).tolist(),
                     "ankle": ank.round(1).tolist(), "sole": sole.round(1).tolist(), "path": P[::6].round(1).tolist()}
    return out


if __name__ == "__main__":
    res, tiles = {}, []
    for n in DRAWINGS:
        img = Image.open(EXP / f"legs/{n}.png")
        j = joints(img, n in STRAIGHT_LEGS)
        res[n] = j
        t = Image.new("RGB", img.size, (214, 214, 214)); t.paste(img, (0, 0), img)
        d = ImageDraw.Draw(t)
        for side in ("l", "r"):
            J = j[side]
            d.line([tuple(p) for p in J["path"]], fill=(0, 160, 255), width=3)
            d.line([tuple(J["hip"]), tuple(J["knee"]), tuple(J["ankle"]), tuple(J["sole"])], fill=(0, 0, 0), width=6)
            for k, c in (("hip", (255, 0, 255)), ("knee", (0, 255, 0)), ("ankle", (255, 255, 0)), ("sole", (0, 0, 255))):
                x, y = J[k]; d.ellipse([x - 12, y - 12, x + 12, y + 12], fill=c)
        bx, by = j["belt"]; d.ellipse([bx - 10, by - 10, bx + 10, by + 10], fill=(255, 255, 255))
        d.text((8, 8), n, fill=(200, 0, 0))
        t.thumbnail((400, 400)); tiles.append(t)
    (EXP / "legs/joints.json").write_text(json.dumps(res, indent=1))
    W = 6 * 400; sheet = Image.new("RGB", (W, 2 * 400), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 6) * 400, (i // 6) * 400))
    sheet.save(EXP / "legs/joints.png")
    print("wrote legs/joints.json, legs/joints.png")
