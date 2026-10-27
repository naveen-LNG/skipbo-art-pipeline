"""rig_image.py - load part images and clean them for the rig (solidify).

Generated parts come out of background removal with thinned interiors and a soft rim still carrying the sheet's
colour; solidify closes the interior and recolours the rim from the part's own paint, so no hairline shows where one
part lies over another.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def load_rgba(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32) / 255.0


RIM_PX = 8     # deepest outer anti-aliasing ramp solidify recolours from the part's interior
BLEED_PX = 4   # transparent pixels this close to a part get the part's colour (straight-alpha bilinear sampling)
TRUST_ALPHA = 230  # edge pixels at least this opaque carry <= ~10% sheet colour: their own paint is kept
# --annotations: edge pixels must be this opaque to be trusted. The real fox's cuffs end in a 1 px row at alpha ~231,
# ~14% darker than the paint inside it (a background-removal halo, not paint: the raw split piece has it too); kept
# and carried outwards it made a dark line wherever a cuff crossed the belly (hold_card seam 0.103 -> 0.047 at 240).
# The fox's laugh head (T18) ends in a 1-2 px ring at alpha 238-249 carrying ~10% sheet colour (G/B +15 over the fur
# inside): trusted at 240, it made a pale hairline where the head lies over the raised sleeve (cheer_jump seam 0.14).
# So annotated pieces trust only the opaque body (>= 250); a lip painted there is still carried outwards.
TRUST_ALPHA_ANNOTATED = 250


def solidify(img: Image.Image, trust: int | None = None) -> Image.Image:
    """Make semi-transparent pixels enclosed by the part opaque. Background removal sometimes thins pale interior
    areas (eye whites, highlights), which would let the scene show through; true gaps (alpha ~0) stay open.
    trust: the TRUST_ALPHA to use (default TRUST_ALPHA; colour only - the alpha never depends on it)."""
    trust = TRUST_ALPHA if trust is None else trust
    arr = np.asarray(img.convert("RGBA")).copy()
    a8 = arr[..., 3].copy()                                     # the source alpha (arr is edited below)
    outside = np.pad(a8 <= 8, 1, constant_values=True)
    im = Image.fromarray(np.where(outside, 255, 0).astype(np.uint8)).copy()
    ImageDraw.floodfill(im, (0, 0), 128)                       # everything reachable from the border through gaps
    reach = (np.asarray(im) == 128)[1:-1, 1:-1]
    weak = (a8 > 8) & (a8 < 250)
    inner = weak & ~reach

    def grow(m: np.ndarray, steps: int, within: np.ndarray | None = None, square: bool = False) -> np.ndarray:
        for _ in range(steps):
            g = m | np.roll(m, 1, 0) | np.roll(m, -1, 0)
            g = g | np.roll(g, 1, 1) | np.roll(g, -1, 1) if square else g | np.roll(m, 1, 1) | np.roll(m, -1, 1)
            m = g if within is None else m | (g & within)
        return m
    arr[..., 3] = np.where(inner & ~grow(reach, 3), 255, a8)  # keep the soft anti-aliased rim: only pixels > 3 px
    # from anything reachable get fixed. Placement reads this alpha, so the colour pass below never changes it.
    # Edge decontamination: the outer anti-aliasing ramp (weak pixels joined to the outside through weak pixels, up
    # to RIM_PX deep; generated parts have 5-7 px ramps) still carries the sheet's grey mixed in, and its inner half
    # was just made opaque above. Copying "the nearest solid pixel" spread that contaminated colour along the rim: a
    # pale or dark hairline wherever the part lies over another. So the ramp pixels below TRUST_ALPHA in the source
    # take the colour of the nearest trusted pixel (source alpha >= TRUST_ALPHA, or solid off the ramp), and so do
    # the transparent pixels within BLEED_PX of the part (the Spine runtime samples straight alpha bilinearly, so
    # those show there). Paint on nearly opaque edge pixels (a boot's light lip) is kept and carried outwards.
    ramp = grow(reach, RIM_PX, within=weak)
    known = (a8 >= trust) | ((arr[..., 3] >= 250) & ~ramp)
    todo = ~known & grow(arr[..., 3] > 0, BLEED_PX, square=True)
    rgb = arr[..., :3].astype(np.float32)
    for _ in range(2 * (RIM_PX + BLEED_PX) + 2):               # 4-neighbour steps: diagonals need ~1.4x
        todo &= ~known
        if not todo.any():
            break
        acc, cnt = np.zeros_like(rgb), np.zeros(known.shape, np.float32)
        for ax, k in ((0, 1), (0, -1), (1, 1), (1, -1)):        # mean of the known 4-neighbours
            kn = np.roll(known, k, ax)
            acc += np.roll(rgb, k, ax) * kn[..., None]
            cnt += kn
        new = todo & (cnt > 0)
        rgb[new] = acc[new] / cnt[new][:, None]
        known |= new
    arr[..., :3] = np.round(rgb).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")
