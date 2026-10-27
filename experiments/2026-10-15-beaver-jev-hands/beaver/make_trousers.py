# /// script
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""Round 3: one trousers piece = the belt-to-crotch hips (beaver-lower-parts/06) over the two cuffed legs
(beaver-lower-parts/04, 05), legs placed under the hips' leg openings and long enough that the cuffs end where the
master's do. Why a composite: with separate leg pieces the rig always draws the boots over the legs (leg, foot, hips),
but the master has the trouser cuff over the boot; leg-less hips put the boots under the trousers (foot: under_hips).
Proportions from the master (measured by colour): belt top 0.600, crotch 0.740, cuff hem 0.807, trouser width at
0.68 = 0.371 of the master's width. Writes runs/beaver-trousers-parts/trousers_00.png and prints the opening points."""
import glob
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def defringe(im):
    """Soft rim pixels hold the sheet's grey: give the rim (under alpha 200, within 3 px of the solid body) the nearest solid colour,
    so the hips' leg openings lying over the legs leave no pale hairline (round 5, seen at the ankles). Hips only: the
    legs' cuffs hold large semi-transparent areas that a full fill turned into blocky patches."""
    a = np.asarray(im).copy()
    solid = a[..., 3] >= 200
    edge = ~solid & (a[..., 3] > 0) & ndimage.binary_dilation(solid, iterations=3)   # the rim only
    _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    a[edge, :3] = a[iy, ix, :3][edge]
    return Image.fromarray(a, "RGBA")

HERE = Path(__file__).parent
MW, MH = 1792, 2400
BELT, CROTCH, HEM, WIDTH = 0.600, 0.740, 0.807, 0.371

hips = defringe(Image.open(glob.glob(str(HERE / "runs/beaver-lower-parts/*_06.png"))[0]).convert("RGBA"))
legs = [(Image.open(glob.glob(str(HERE / f"runs/beaver-lower-parts/*_{n}.png"))[0]).convert("RGBA")) for n in ("04", "05")]
a = np.asarray(hips)[..., 3] > 128
ys, xs = np.nonzero(a)
top, bot = ys.min(), ys.max()
mid = int(top + 0.45 * (bot - top))
row = np.nonzero(a[mid])[0]
s = WIDTH * MW / (row.max() - row.min() + 1)                  # master px per part px
# leg openings: the two runs of opaque pixels in the hips' bottom rows
for yy in range(bot - 3, mid, -1):                            # scan up to the first row with two openings
    low = np.nonzero(a[yy])[0]
    runs = sorted([r for r in np.split(low, np.nonzero(np.diff(low) > 3)[0] + 1) if len(r) > 5], key=lambda r: r[0])
    if len(runs) >= 2:
        break
centres = [(r[0] + r[-1]) / 2 for r in (runs[0], runs[-1])]
hem_y = top + (HEM - BELT) * MH / s                           # part px below the belt top
W = hips.width
H = int(hem_y + 8)
out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
LEG_NARROW = 0.85     # round 5: the sheet's legs came out ~1.2x the master's leg width (Jev: ankles worse than approved)
for leg, cx in zip(sorted(legs, key=lambda im: 0), centres):
    leg = leg.resize((round(leg.width * LEG_NARROW), leg.height), Image.LANCZOS)
    la = np.asarray(leg)[..., 3] > 128
    lys, lxs = np.nonzero(la)
    lw = lxs.max() - lxs.min() + 1
    x = int(round(cx - (lxs.min() + lw / 2)))
    y = int(round(hem_y - lys.max()))
    out.alpha_composite(leg, (x, y))
# round 6: the upper trousers were 10-13% wider than the master's, so the belt's corners stuck out past the sweater hem
# with background between (rig 0.282-0.717 vs master 0.312-0.693 at the belt). Narrow the hips only, about their
# centre; the cuffed legs keep their place (their cuffs already sit within 1% of the master's).
HIPS_NARROW = 0.88
nh = hips.resize((round(hips.width * HIPS_NARROW), hips.height), Image.LANCZOS)
legs_only = out.copy()
out.alpha_composite(nh, ((W - nh.width) // 2, 0))
# round 7: the shorts' painted bottom edge left a pale seam across each leg above the cuff (motion sheet, every frame).
# Where the hips' outline lies over a leg, hand the last few px back to the leg underneath, feathered.
ha = np.zeros((H, W), bool); ha[:nh.height, (W - nh.width) // 2:(W - nh.width) // 2 + nh.width] = np.asarray(nh)[..., 3] > 128
la = np.asarray(legs_only)[..., 3] > 128
SEAM = 6
inner = ndimage.binary_erosion(ha, iterations=SEAM)
band = ha & ~inner & la
band[: int(0.5 * nh.height)] = False                            # the leg openings only, not the belt
dist = ndimage.distance_transform_edt(ha)                       # 1 at the outline .. SEAM inside
wgt = np.where(band, np.clip((SEAM + 0.5 - dist) / SEAM, 0, 1), 0.0)[..., None]
o, l_ = np.asarray(out).astype(float), np.asarray(legs_only).astype(float)
o[..., :3] = o[..., :3] * (1 - wgt) + l_[..., :3] * wgt
out = Image.fromarray(o.clip(0, 255).astype(np.uint8), "RGBA")
# the rig scales every piece by one global factor (the body sheet's: 1.268 master px per part px) and only stretches a
# two-point part by 15%, so paint this one at that scale: else the trousers came out 25% too long (hips stretch 0.75)
RIG_SCALE = 1.268
k = s / RIG_SCALE
out = out.resize((round(out.width * k), round(out.height * k)), Image.LANCZOS)
W, H, hem_y, top, centres = out.width, out.height, hem_y * k, top * k, [c * k for c in centres]
s = RIG_SCALE
d = HERE / "runs/beaver-trousers-parts"; d.mkdir(parents=True, exist_ok=True)
out.save(d / "trousers_00.png")
print(f"scale {s:.3f} master px/part px; size {W}x{H}")
print(f"waist [0.5, {(top + 0.035 * MH / s) / H:.3f}]  hip_r [{centres[0] / W:.3f}, {(hem_y - 2) / H:.3f}]  "
      f"hip_l [{centres[1] / W:.3f}, {(hem_y - 2) / H:.3f}]")
