"""Hairline seams where one piece overlaps another (hips over legs, torso over hips, vest over trousers).

Diagnosis (2026-10-11, probes on experiments/2026-10-11-part-variants/{fox,moose}/rig, setup pose at 1400 px):
- Leading hypothesis REFUTED for our renderer: alpha-0 pixels do keep the sheet's pale grey RGB (lum ~0.86 next to a
  body of ~0.4), but Pillow's RGBA `transform` premultiplies before resampling, so bleeding the part colour into
  them changed 0 composite pixels (test_renderer_ignores_alpha0_rgb). The Spine web player samples straight alpha
  (premultipliedAlpha: false, Linear filter), so there those pixels do matter; the fix bleeds them as well.
- Root cause: `spine_rig.solidify`. The generated parts carry a 5-7 px anti-aliased ramp whose RGB still has the grey
  sheet mixed in (moose hips: alpha 178 at lum 0.62 on a 0.33 body; fox torso: alpha 177 at 0.46 on 0.36).
  solidify's "fill enclosed semi-transparent pixels" step treats every ramp pixel more than 3 px from an alpha<=8
  pixel as enclosed and makes it opaque, so the inner ramp pixels (contaminated) become solid; its edge
  decontamination then copies "the nearest solid pixel" (that contaminated pixel) across the rest of the ramp.
  Result: an opaque pale (sometimes dark) 1-3 px band plus a fading rim of the same colour along every outer edge.
  Over the grey background it barely shows; over another piece it is the hairline. At QA scale (~0.35 canvas px per
  native px) it is a 1 px line that is greyer than both sides.
- Fix (alpha untouched, so placement and the skeleton json stay byte-identical): ramp pixels below TRUST_ALPHA in
  the source, and transparent pixels within BLEED_PX, take the colour of the nearest trusted pixel (source alpha >=
  TRUST_ALPHA or solid off the ramp). Paint on nearly opaque edge pixels is kept: a first version that recoloured
  the whole ramp turned the fox boot's painted light lip into a stippled line (test_fix_keeps_painted_lip).
- Check: the spec's rule alone (edge luminance outside the inside/outside range by 0.04) also fires on painted
  rims along piece edges (fox boot lip 0.58, moose bell lip 0.56, chin fur 0.18 after the fix). Profiles across
  the edge separate them: the matting hairline is confined to the edge pixel (1 px further in is back to the
  piece's colour) and greyer than both sides (it is the sheet's grey), while painted rims run inward or keep their
  colour. check_seams counts only confined, greyer pixels. Calibration (worst pair, setup + middle frames):
  unfixed fox 0.375 (hips/leg 0.156-0.184, torso/hips 0.135), unfixed moose 0.417 (hips/leg 0.207-0.233,
  torso/hips 0.211); fixed fox 0.070, fixed moose 0.034. SEAM_MAX = 0.10.

The synthetic layers render at 0.4 canvas px per native px, like the real rigs at spine_qa.CHECK_H.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

import spine_qa
import spine_rig

SHEET = (218, 218, 218)
BODY = (70, 130, 190)
SCALE = 0.4


def disc_layer(size=420, radius=150, ramp=6, band=0, band_rgb=None, freeze=False, contaminate=None,
               alpha0_rgb=(0, 0, 0)) -> Image.Image:
    """A BODY-coloured opaque disc with an anti-aliased ramp `ramp` px wide (alpha 250 -> 0).
    contaminate: premix this colour into the ramp the way background removal leaves it.
    band_rgb: colour of the ramp plus the outermost `band` px of the opaque body (a painted lip, or a leftover).
    freeze: make the inner half of the ramp opaque, as the old solidify did (pixels > 3 px from alpha <= 8)."""
    yy, xx = np.mgrid[:size, :size]
    d = np.hypot(xx - size / 2 + 0.5, yy - size / 2 + 0.5)
    alpha = np.where(d < radius - ramp, 1.0, np.clip((radius - d) / ramp, 0, 1) * 250 / 255)
    rgb = np.empty((size, size, 3))
    rgb[:] = BODY
    soft = (alpha > 0) & (alpha < 1)
    if contaminate is not None:
        rgb[soft] = np.array(BODY) * alpha[soft, None] + np.array(contaminate) * (1 - alpha[soft, None])
    if band_rgb is not None:
        rgb[(d >= radius - ramp - band) & (alpha > 0)] = band_rgb
    if freeze:
        alpha[(d >= radius - ramp) & (d < radius - ramp / 2)] = 1.0
    rgb[alpha == 0] = alpha0_rgb
    arr = np.dstack([rgb, alpha * 255]).round().clip(0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def two_layer_rig(tmp_path: Path, upper: Image.Image) -> tuple:
    """lower: a flat opaque square; upper: the given image drawn over its middle, at SCALE canvas px per image px."""
    (tmp_path / "images").mkdir(parents=True)
    lower = Image.new("RGBA", (560, 560), (40, 120, 215, 255))
    lower.save(tmp_path / "images" / "lower.png")
    upper.save(tmp_path / "images" / "upper.png")
    att = lambda im: {"x": 350, "y": 350, "width": im.width, "height": im.height}
    data = {
        "skeleton": {"x": 0, "y": 0, "width": 700, "height": 700, "images": "./images/"},
        "bones": [{"name": "root"}],
        "slots": [{"name": "lower", "bone": "root", "attachment": "lower"},
                  {"name": "upper", "bone": "root", "attachment": "upper"}],
        "skins": [{"name": "default", "attachments": {"lower": {"lower": att(lower)}, "upper": {"upper": att(upper)}}}],
        "animations": {},
    }
    (tmp_path / "t.json").write_text(json.dumps(data))
    rig = spine_qa.Rig(tmp_path / "t.json")
    return rig, spine_qa.Canvas(rig, round(700 * 1.37 * SCALE))


def score(tmp_path, upper):
    rig, canvas = two_layer_rig(tmp_path, upper)
    res = spine_qa.check_seams(rig, canvas, [(None, 0.0)])
    return res["seams"]["upper/lower"], res


def pale(k=0.6):
    return tuple(round(b * (1 - k) + s * k) for b, s in zip(BODY, SHEET))


def test_renderer_ignores_alpha0_rgb(tmp_path):
    """Evidence for the refuted hypothesis: our renderer premultiplies, so the RGB of alpha-0 pixels never shows."""
    frames = []
    for name, rgb in (("black", (0, 0, 0)), ("white", (255, 255, 255))):
        rig, canvas = two_layer_rig(tmp_path / name, disc_layer(alpha0_rgb=rgb))
        frames.append(np.asarray(spine_qa.render(rig, canvas, None, 0)[0]).astype(int))
    assert np.abs(frames[0] - frames[1]).max() <= 1


def test_seam_score_detects_dark_rim(tmp_path):
    """The old solidify's frozen band, from a black sheet: a dark, grey-ish hairline."""
    dark = tuple(round(c * 0.35) for c in BODY)
    s, res = score(tmp_path, disc_layer(band_rgb=dark, freeze=True, alpha0_rgb=(0, 0, 0)))
    assert s > spine_qa.SEAM_MAX
    assert res["pass"] is False


def test_seam_score_detects_pale_rim(tmp_path):
    """What the old solidify produced from our grey sheet: a frozen pale band."""
    s, _ = score(tmp_path, disc_layer(band_rgb=pale(), freeze=True, alpha0_rgb=SHEET))
    assert s > spine_qa.SEAM_MAX


def test_seam_score_clean(tmp_path):
    s, res = score(tmp_path, disc_layer())           # ramp carries the disc colour (bled)
    assert s <= spine_qa.SEAM_MAX
    assert res["pass"] is True


def test_seam_score_ignores_painted_lip(tmp_path):
    """A light, saturated lip painted along the edge (the fox boot's cuff) is art, not a seam."""
    s, _ = score(tmp_path, disc_layer(band=4, band_rgb=(130, 200, 255), alpha0_rgb=SHEET))
    assert s <= spine_qa.SEAM_MAX


def test_fix_removes_rim(tmp_path):
    """The real input: a ramp with the sheet grey premixed. solidify must not freeze it into a hairline."""
    fixed = spine_rig.solidify(disc_layer(contaminate=SHEET, alpha0_rgb=SHEET))
    s, _ = score(tmp_path, fixed)
    assert s <= spine_qa.SEAM_MAX


def test_fix_recolours_ramp_bleeds_alpha0_keeps_alpha():
    src = disc_layer(contaminate=SHEET, alpha0_rgb=SHEET)
    out = np.asarray(spine_rig.solidify(src)).astype(int)
    a_src = np.asarray(src)[..., 3].astype(int)
    low = (a_src > 0) & (a_src < spine_rig.TRUST_ALPHA)
    near = (a_src == 0) & spine_qa.dilate(a_src > 0, 4)             # alpha-0 pixels next to the part (Spine runtime)
    # they carry the colour of the trusted edge pixels, which hold at most (255 - TRUST_ALPHA)/255 of the sheet
    tol = (255 - spine_rig.TRUST_ALPHA) / 255 * np.abs(np.array(SHEET) - BODY).max() + 2
    assert np.abs(out[..., :3][near | low] - np.array(BODY)).max() <= tol
    before = np.abs(np.asarray(src)[..., :3].astype(int)[low] - np.array(BODY)).max()
    assert before > 4 * tol                                         # the input really was contaminated
    # alpha is what the colour-blind solidify gives (placement reads it): same result on a recoloured copy
    flat = np.asarray(src).copy()
    flat[..., :3] = 0
    assert np.array_equal(out[..., 3], np.asarray(spine_rig.solidify(Image.fromarray(flat, "RGBA")))[..., 3])


def test_fix_keeps_painted_lip():
    """Paint on nearly opaque edge pixels survives and is carried outwards over the ramp."""
    lip = (255, 160, 40)
    src = disc_layer(ramp=6, band=3, band_rgb=lip, alpha0_rgb=SHEET)
    arr = np.asarray(src).copy()
    soft = (arr[..., 3] > 0) & (arr[..., 3] < 250)
    arr[..., :3][soft & (arr[..., 3] < 200)] = SHEET                 # the faint outer ramp: mostly sheet grey
    out = np.asarray(spine_rig.solidify(Image.fromarray(arr, "RGBA"))).astype(int)
    a = arr[..., 3].astype(int)
    kept = (a >= spine_rig.TRUST_ALPHA) & spine_qa.dilate(a < 250, 1)  # edge pixels carrying the lip
    assert np.abs(out[..., :3][kept] - np.array(lip)).max() <= 3
    assert np.abs(out[..., :3][(a > 0) & (a < 200)] - np.array(lip)).max() <= 3


def test_annotated_trust_drops_a_halo_ring():
    """T18: the real fox's laugh head ends in a 1-2 px ring at alpha 238-249 holding ~10% of the sheet (G/B +15 over
    the fur inside); trusted at 240 its pale paint was carried over the ramp and showed as a hairline where the head
    lies over the raised sleeve (cheer_jump seam 0.14). Annotated pieces trust only alpha >= 250: the ring takes the
    colour inside it, while a lip painted on the opaque body is still carried outwards."""
    src = disc_layer(ramp=6)
    arr = np.asarray(src).copy()
    a = arr[..., 3].astype(int)
    ring = (a >= 236) & (a < 250)
    arr[..., :3][ring] = pale(0.12)
    out = np.asarray(spine_rig.solidify(Image.fromarray(arr, "RGBA"), spine_rig.TRUST_ALPHA_ANNOTATED)).astype(int)
    assert np.abs(out[..., :3][ring] - np.array(BODY)).max() <= 3
    old = np.asarray(spine_rig.solidify(Image.fromarray(arr, "RGBA"), 240)).astype(int)
    assert np.abs(old[..., :3][ring & (a >= 240)] - np.array(BODY)).max() > 10       # the old trust kept the halo
    lip = (255, 160, 40)
    arr = np.asarray(disc_layer(ramp=6, band=3, band_rgb=lip, alpha0_rgb=SHEET)).copy()
    out = np.asarray(spine_rig.solidify(Image.fromarray(arr, "RGBA"), spine_rig.TRUST_ALPHA_ANNOTATED)).astype(int)
    a = arr[..., 3].astype(int)
    assert np.abs(out[..., :3][(a > 0) & (a < 255)] - np.array(lip)).max() <= 3


def test_fix_still_fills_enclosed_thin_pixels():
    """solidify's original job: a thinned pale area enclosed by the part becomes opaque."""
    arr = np.asarray(disc_layer()).copy()
    arr[200:220, 200:220, 3] = 120
    out = np.asarray(spine_rig.solidify(Image.fromarray(arr, "RGBA")))
    assert (out[204:216, 204:216, 3] == 255).all()


def test_check_seams_report_shape(tmp_path):
    rig, canvas = two_layer_rig(tmp_path, disc_layer())
    res = spine_qa.check_seams(rig, canvas, [(None, 0.0), (None, 0.0)])
    assert set(res) == {"pass", "seams"}
    assert set(res["seams"]) == {"upper/lower"}
