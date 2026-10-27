# /// script
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""Experiment-local piece prep for the bear (writes new split-run folders under runs/, never touches the sheets):

1. runs/bear-torso-parts/torso_00.png - the body-sheet torso (bear-body-parts/09) narrowed across. Its neck-to-waist
   length sets the rig's global scale (1.079 master px per sheet px), and at that scale the sheet's shirt is ~1.25x
   the master's width: the chunky body sheet painted the torso wider for its height than the master. Arms go under the
   torso, so an over-wide torso would also swallow the sleeve tops.
2. runs/bear-trousers-parts/trousers_00.png - the lower body (red waistband + checked apron + brown trousers down to
   both hems), cut from the master and painted at the rig's scale. The body sheet's "whole lower body as ONE piece"
   came back as shorts 2/3 of the master's height (the beaver's first failure again). This piece has no joint with a
   cut edge: its top (the waistband) lies under the shirt's hem and its hems over the clogs, as in the master. In the
   master the clogs' toe caps lie over the outer half of each hem; that notch is repainted with the trouser colour of
   the rows just above, so a lifting clog never opens a hole in the hem.
3. runs/bear-arm-parts/arm_00.png, arm_01.png - the whole-arm sheet's arms with the honey-fur paw the sheet painted
   at their ends cut off at the narrowest point of the forearm (the wrist), with a rounded end. The dark mitten is
   drawn over it (master.layers.hand = over_forearm), as in the master.
Prints the measured numbers the annotations use."""
import glob
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

import geom

HERE = Path(__file__).parent
G = geom.global_scale()


def one(pattern):
    return glob.glob(str(HERE / pattern))[0]


def defringe(a, solid_thr=200):
    """Soft rim pixels hold the sheet's grey: give the rim the nearest solid colour (beaver make_trousers.py)."""
    solid = a[..., 3] >= solid_thr
    edge = ~solid & (a[..., 3] > 0)
    _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    a[edge, :3] = a[iy, ix, :3][edge]
    return a


out = {}
# ---- 1. torso ---------------------------------------------------------------------------------------------------
t = Image.open(one("runs/bear-body-parts/*_09.png")).convert("RGBA")
ta = np.asarray(t)[..., 3] > 128
row = np.nonzero(ta[int(0.88 * t.height)])[0]
w_piece = (row.max() - row.min() + 1) * G                       # master px at the rig's scale
y_master = geom.MASTER["waist"][1] - (geom.TORSO_WAIST_Y - 0.88) * t.height * G / geom.MH
# the master's shirt edge at that height (measured on the zooms: 0.25 .. 0.75 of the width just above the waistband)
TARGET = 0.50 * geom.MW
TORSO_NARROW = round(TARGET / w_piece, 3)
nt = t.resize((round(t.width * TORSO_NARROW), t.height), Image.LANCZOS)
d = HERE / "runs/bear-torso-parts"; d.mkdir(parents=True, exist_ok=True)
nt.save(d / "torso_00.png")
out["torso"] = {"narrow": TORSO_NARROW, "piece_w_master_px": round(w_piece), "at_master_y": round(y_master, 3)}

# ---- 2. trousers (master cut) -----------------------------------------------------------------------------------
m = np.asarray(Image.open(HERE / "bear_master.png").convert("RGB")).astype(np.float32)
H, W = m.shape[:2]
bg = np.median(np.concatenate([m[0], m[-1], m[:, 0], m[:, -1]]), 0)
fg = np.linalg.norm(m - bg, axis=2) > 18
R, Gc, B = m[..., 0], m[..., 1], m[..., 2]
yy, xx = np.mgrid[0:H, 0:W]
fx, fy = xx / W, yy / H
red = (R > 150) & (R - Gc > 70) & (R - B > 60)
white = (np.minimum(np.minimum(R, Gc), B) > 185) & (np.maximum(np.maximum(R, Gc), B) - np.minimum(np.minimum(R, Gc), B) < 45)
fur = (R > 170) & (Gc > 95) & (B < 110) & (R - B > 100) & (Gc / np.maximum(R, 1) > 0.52)
mask = fg & (fx > 0.205) & (fx < 0.795) & (fy > 0.495) & (fy < 0.90)
# top: below the waistband's top edge (first red pixel from the top in each column); off the band, below the shirt
band_top = np.full(W, int(0.53 * H))
for x in range(int(0.255 * W), int(0.745 * W)):
    col = np.nonzero(red[int(0.495 * H):int(0.56 * H), x])[0]
    if len(col):
        band_top[x] = int(0.495 * H) + col[0]
# round 2: the shirt's rounded hem met the waistband's curved top edge to edge (torso overlap 0 px, a background
# hairline at the waist): carry the master's shirt UNDER_PX up above the band, hidden under the torso at rest
UNDER_PX = 60
inband = np.zeros(W, bool); inband[int(0.262 * W):int(0.738 * W)] = True
top = np.where(inband, np.minimum(band_top - UNDER_PX, int(0.497 * H)), band_top)   # red detection misses the band's dark middle
mask &= yy >= top[None, :]
mask &= ~(white & (fy < 0.535) & ~inband[None, :])     # the shirt above the band stays (hidden under the torso)
mask &= ~(fur & (fy < 0.60))
# the shirt's shaded hem is within 18 RGB of the grey background: take it by position, not colour
mask |= inband[None, :] & (yy >= top[None, :]) & (yy <= band_top[None, :] + 5) & (fx > 0.27) & (fx < 0.73)


def hem_y(x, pts):
    xs, ys = zip(*pts)
    return np.interp(x, xs, ys)


HEMS = {"r": [(0.213, 0.856), (0.30, 0.879), (0.40, 0.884), (0.470, 0.870)],
        "l": [(0.530, 0.870), (0.60, 0.884), (0.70, 0.879), (0.787, 0.856)]}
NOTCH = {"r": (0.213, 0.352), "l": (0.648, 0.787)}            # where the clog's toe cap lies over the hem
paint = m.copy()
for s, pts in HEMS.items():
    x0, x1 = int(pts[0][0] * W), int(pts[-1][0] * W)
    for x in range(x0, x1 + 1):
        yb = int(hem_y(x / W, pts) * H)
        mask[yb + 1:int(0.90 * H), x] = False
        n0, n1 = NOTCH[s]
        if n0 * W <= x <= n1 * W:
            # round 8: repaint the notch with the hem's own vertical profile, copied from the nearest clear column
            # (aligned on the hem's bottom edge) and blended in over the top RAMP rows; a flat colour from the rows
            # above showed as a lighter block with a seam (joints sheet)
            xr = int((n1 + 0.012) * W) if s == "r" else int((n0 - 0.012) * W)
            ybr = int(hem_y(xr / W, pts) * H)
            ys0, RAMP = int(0.838 * H), int(0.012 * H)
            for y in range(ys0, yb + 1):
                src = m[min(H - 1, ybr - (yb - y)), xr]
                wgt = min(1.0, (y - ys0) / RAMP)
                paint[y, x] = src * wgt + m[y, x] * (1 - wgt)
                mask[y, x] = True
lab, n = ndimage.label(mask)
mask = lab == (1 + np.argmax(ndimage.sum(mask, lab, range(1, n + 1))))
mask = ndimage.binary_fill_holes(mask)
mask = ndimage.binary_opening(mask, iterations=2)
# round 2: the master's outline pixels blend into the grey background, a pale hairline where the hems lie over the
# clogs (seams 0.07): the outer 3 px take the colour of the nearest pixel 3 px inside
inner = ndimage.binary_erosion(mask, iterations=3)
_, (iy, ix) = ndimage.distance_transform_edt(~inner, return_indices=True)
rim = mask & ~inner
paint[rim] = paint[iy[rim], ix[rim]]
ys, xs = np.nonzero(mask)
y0, y1, x0, x1 = ys.min() - 4, ys.max() + 5, xs.min() - 4, xs.max() + 5
alpha = ndimage.gaussian_filter(mask.astype(np.float32), 0.8)[y0:y1, x0:x1]
alpha = np.where(mask[y0:y1, x0:x1], np.maximum(alpha, 0.5), alpha)
rgba = np.dstack([paint[y0:y1, x0:x1], 255 * np.clip((alpha - 0.25) / 0.5, 0, 1)]).astype(np.uint8)
rgba = defringe(rgba)
cut = Image.fromarray(rgba, "RGBA")
k = 1 / G                                                      # paint at the body sheet's scale
cut = cut.resize((round(cut.width * k), round(cut.height * k)), Image.LANCZOS)
d = HERE / "runs/bear-trousers-parts"; d.mkdir(parents=True, exist_ok=True)
cut.save(d / "trousers_00.png")


def to_cut(p):
    return [round((p[0] * W - x0) / (x1 - x0), 3), round((p[1] * H - y0) / (y1 - y0), 3)]


mp = geom.MASTER
out["trousers"] = {"box_master": [round(x0 / W, 3), round(y0 / H, 3), round(x1 / W, 3), round(y1 / H, 3)],
                   "size": cut.size, "waist": to_cut(mp["waist"]), "hip_l": to_cut(mp["hip_l"]),
                   "hip_r": to_cut(mp["hip_r"])}

# ---- 3. arms: cut the sheet's fur paw off at the wrist ---------------------------------------------------------
d = HERE / "runs/bear-arm-parts"; d.mkdir(parents=True, exist_ok=True)
out["arms"] = {}
for nn in ("00", "01"):
    a = np.asarray(Image.open(one(f"runs/bear-arms-parts/*_{nn}.png")).convert("RGBA")).copy()
    h, w = a.shape[:2]
    op = a[..., 3] > 128
    widths = [(np.ptp(np.nonzero(op[y])[0]) if op[y].any() else 0) for y in range(h)]
    lo, hi = int(0.66 * h), int(0.80 * h)
    yc = lo + int(np.argmin(widths[lo:hi]))                    # the narrowest row of the forearm: the wrist
    r = np.nonzero(op[yc])[0]
    cx, half = (r.min() + r.max()) / 2, (r.max() - r.min()) / 2
    depth = 0.35 * half                                          # a rounded end, like a sausage
    yy2, xx2 = np.mgrid[0:h, 0:w]
    keep = (yy2 < yc - depth) | (((xx2 - cx) / max(half, 1)) ** 2 + ((yy2 - (yc - depth)) / depth) ** 2 <= 1)
    a[..., 3] = np.where(keep, a[..., 3], 0)
    a = a[: yc + 4]
    Image.fromarray(a, "RGBA").save(d / f"arm_{nn}.png")
    out["arms"][nn] = {"wrist_row": yc, "orig_h": h, "new_h": a.shape[0], "wrist_x": round(cx / w, 3),
                       "wrist_w_px": int(2 * half)}
# ---- 4. clogs: the body sheet's side-view clogs are ~0.9x the master's clog length at the rig's scale ------------
CLOG_WIDEN = 1.10
d = HERE / "runs/bear-clog-parts"; d.mkdir(parents=True, exist_ok=True)
# round 4: the clog tops sat only ~50 px under the hems, so when walk/run bob the hips up the overlap fell to a quarter
# (unstitched) and jump_hurdle's crouch quadrupled it. Paint the hidden part: a honey-fur ankle stub rising from
# the heel opening, under the clog's rim. Below a lifted hem it reads as the bear's ankle, not a gap.
STUB_UP, STUB_W = 0.55, 0.42                  # stub height and width as shares of the clog's height and width
FUR = np.array([214, 138, 62], np.float32)    # the master's honey forearm fur, mid tone
out["clogs"] = {"widen": CLOG_WIDEN}
for nn, ax in (("00", 0.77), ("01", 0.23)):   # ankle x of each clog (heel opening), as annotated
    c = Image.open(one(f"runs/bear-body-parts/*_{nn}.png")).convert("RGBA")
    c = c.resize((round(c.width * CLOG_WIDEN), c.height), Image.LANCZOS)
    w, h = c.size; ext = round(STUB_UP * h)
    canvas = np.zeros((h + ext, w, 4), np.float32)
    sw = STUB_W * w; cx = ax * w; ay = ext + 0.18 * h
    yy2, xx2 = np.mgrid[0:h + ext, 0:w]
    u = (xx2 - cx) / (sw / 2)
    top_r = sw / 2
    inside = (np.abs(u) <= 1) & (yy2 <= ay + 0.05 * h) & ((yy2 >= top_r) | ((u ** 2 + ((yy2 - top_r) / top_r) ** 2) <= 1))
    shade = (1.08 - 0.25 * (u + 1) / 2)[..., None]               # lit left, shaded right, as the master's forearms
    canvas[..., :3] = np.clip(FUR * shade, 0, 255)
    canvas[..., 3] = 255 * np.clip(ndimage.gaussian_filter(inside.astype(np.float32), 1.0) * 2 - 0.5, 0, 1)
    stub = Image.fromarray(canvas.astype(np.uint8), "RGBA")
    stub.alpha_composite(c, (0, ext))
    stub.save(d / f"clog_{nn}.png")
    # round 6: the pivot sits up in the stub (0.17 of the piece above the heel opening), so the joint disk spline
    # QA measures lies under the hem and jump_hurdle's tuck can't more than double the overlap; the master's ankles
    # moved up by the same 0.026
    ay = ay - 0.171 * (h + ext)
    out["clogs"][nn] = {"ankle": [ax, round(ay / (h + ext), 3)], "ground": [None, round((ext + 0.98 * h) / (h + ext), 3)]}
# ---- 5. props: the split's soft rim holds the sheet's grey, a pale hairline where the hurdle lies over the trousers in
# jump_hurdle (seams 0.11): rim pixels take the nearest solid colour, and the faintest rim is dropped
(HERE / "props").mkdir(exist_ok=True)
for name, nn in (("flag", "01"), ("hurdle", "00")):
    a = np.asarray(Image.open(one(f"runs/bear-props-parts/*_{nn}.png")).convert("RGBA")).copy()
    a[..., 3] = np.where(a[..., 3] < 60, 0, a[..., 3])
    solid = ndimage.binary_erosion(a[..., 3] >= 250, iterations=2)
    _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    rim = (a[..., 3] > 0) & ~solid
    a[rim, :3] = a[iy[rim], ix[rim], :3]
    Image.fromarray(a, "RGBA").save(HERE / "props" / f"{name}.png")
res = {"global_scale": round(G, 4), **out}
(HERE / "parts.json").write_text(json.dumps(res, indent=1) + "\n")
print(json.dumps(res, indent=1))
