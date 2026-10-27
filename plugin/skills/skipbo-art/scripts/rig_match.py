"""rig_match.py - find where the generated parts sit on the master by colour (spine_rig.py stages 1-2).

Masked colour matching (FFT SSD) over scale and rotation at WORK_H, each part searched in a band of the body
(BANDS); pairs are tried on both halves and get the cheaper left/right assignment. Also matches the expression heads
and drops the ear pieces they already include. rig_place uses the matcher as a second opinion on annotated
placements.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from rig_image import load_rgba
from rig_roles import LIMBS, is_role, role

WORK_H = 640  # matching resolution (master height in px)


def master_mask(rgb: np.ndarray) -> np.ndarray:
    """Foreground of a flat-background master: distance from the median border colour."""
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    return (np.linalg.norm(rgb - bg, axis=2) > 0.06).astype(np.float32)


def transform(part: np.ndarray, scale: float, angle: float) -> np.ndarray:
    im = Image.fromarray((part * 255).astype(np.uint8), "RGBA")
    w, h = max(1, round(im.width * scale)), max(1, round(im.height * scale))
    im = im.resize((w, h), Image.LANCZOS)
    if angle:
        im = im.rotate(angle, resample=Image.BICUBIC, expand=True)
    return np.asarray(im, dtype=np.float32) / 255.0


BG_WEIGHT = 0.3  # cost per unit fraction of the part landing on master background

# Where a part's centre may sit, as fractions of the character's silhouette height (0 = top of the
# antlers/hat, 1 = the ground) and of its half-width from the centre line. Front-view rest pose.
BANDS = {  # layer: (y_from, y_to, min |x| from centre, max |x|)
    "hat": (0.0, 0.3, 0.0, 0.6), "back": (0.0, 0.45, 0.0, 1.0), "head": (0.05, 0.5, 0.0, 0.3),
    "neckwear": (0.25, 0.6, 0.0, 0.5), "front": (0.25, 0.95, 0.0, 1.0), "torso": (0.3, 0.8, 0.0, 0.2),
    "hips": (0.5, 0.85, 0.0, 0.2), "arm": (0.28, 0.75, 0.25, 1.0), "forearm": (0.3, 0.85, 0.3, 1.0),
    "hand": (0.35, 0.95, 0.4, 1.0), "leg": (0.55, 1.0, 0.0, 0.6), "foot": (0.78, 1.0, 0.0, 0.8),
    "tail": (0.4, 1.0, 0.15, 1.0),
}


def masked_ssd(img: np.ndarray, img_sq: np.ndarray, tpl: np.ndarray, region: tuple | None, penalties=()):
    """Mean squared colour error of tpl (RGBA) placed at every valid offset of img (RGB). FFT based."""
    H, W, _ = img.shape
    h, w = tpl.shape[:2]
    if h >= H or w >= W:
        return None
    m = tpl[..., 3]
    m = (m > 0.5).astype(np.float32)
    msum = m.sum()
    if msum < 20:
        return None
    shape = (H, W)
    fm = np.fft.rfft2(m, shape)
    total = np.zeros(shape, np.float32)
    const = 0.0
    for c in range(3):
        t = tpl[..., c] * m
        fi = np.fft.rfft2(img[..., c])
        fi2 = img_sq[c]
        a = np.fft.irfft2(fi2 * np.conj(fm), shape)
        b = np.fft.irfft2(fi * np.conj(np.fft.rfft2(t, shape)), shape)
        total += a - 2 * b
        const += float((t * tpl[..., c]).sum())
    ssd = (total + const) / msum
    for f_pen, weight in penalties:
        if not weight:
            continue
        ssd += weight * np.fft.irfft2(f_pen * np.conj(fm), shape) / msum
    valid = ssd[: H - h + 1, : W - w + 1]
    if isinstance(region, np.ndarray):  # allowed top-left offsets, the shape of `valid` (rig_place.match_headgear)
        if not region.any():
            return None
        valid = np.where(region, valid, np.inf)
    elif region is not None:  # (x0, x1, y0, y1) bounds for the template centre, work px
        x0, x1, y0, y1 = region
        cx = np.arange(valid.shape[1]) + w / 2
        cy = np.arange(valid.shape[0]) + h / 2
        ok = ((cy >= y0) & (cy <= y1))[:, None] & ((cx >= x0) & (cx <= x1))[None, :]
        if not ok.any():
            return None
        valid = np.where(ok, valid, np.inf)
    idx = np.unravel_index(np.argmin(valid), valid.shape)
    return float(valid[idx]), int(idx[1]), int(idx[0])


class Matcher:
    def __init__(self, master_rgb: np.ndarray, fg: np.ndarray):
        self.img = master_rgb
        self.img_sq = [np.fft.rfft2(master_rgb[..., c] ** 2) for c in range(3)]
        self.f_bg = np.fft.rfft2(1.0 - fg)

    def best(self, part: np.ndarray, scales, angles, region=None):
        best = None
        for s in scales:
            for a in angles:
                tpl = transform(part, s, a)
                r = masked_ssd(self.img, self.img_sq, tpl, region,
                               [(self.f_bg, BG_WEIGHT)])
                if r and (best is None or r[0] < best["err"]):
                    h, w = tpl.shape[:2]
                    best = {"err": r[0], "x": r[1], "y": r[2], "w": w, "h": h, "scale": s, "angle": a,
                            "cx": r[1] + w / 2, "cy": r[2] + h / 2, "tpl": tpl}
        return best


def placed_points(m: dict) -> np.ndarray:
    """Opaque pixel coordinates of a placed part, in work-space (x, y)."""
    ys, xs = np.nonzero(m["tpl"][..., 3] > 0.5)
    return np.stack([xs + m["x"], ys + m["y"]], 1).astype(np.float32)


@dataclass
class MasterFrame:
    """The master at working resolution, with the body frame the part bands are measured against."""
    work: np.ndarray       # master RGB at WORK_H, float 0..1
    fg: np.ndarray         # foreground mask of `work`
    k: float               # work px per master px
    ground_y: float
    top: float
    mid_x: float
    half_w: float


def load_master(path: Path) -> MasterFrame:
    master = load_rgba(path)[..., :3]
    k = WORK_H / master.shape[0]
    work = np.asarray(Image.fromarray((master * 255).astype(np.uint8)).resize(
        (round(master.shape[1] * k), WORK_H), Image.LANCZOS), dtype=np.float32) / 255.0
    fg = master_mask(work)
    ys, xs = np.nonzero(fg)
    ground_y = float(np.percentile(ys, 99.5))
    top = float(np.percentile(ys, 0.5))
    mid_x = float(np.median(xs[ys < top + 0.55 * (ground_y - top)]))   # head + torso: a tail can't drag it
    half_w = float(max(mid_x - np.percentile(xs, 0.5), np.percentile(xs, 99.5) - mid_x))
    return MasterFrame(work, fg, k, ground_y, top, mid_x, half_w)


def make_band(frame: MasterFrame):
    """band(layer, side) -> search box (x0, x1, y0, y1) in work px for a part layer."""
    top, ground_y, mid_x, half_w = frame.top, frame.ground_y, frame.mid_x, frame.half_w

    def band(layer: str, side: str = ""):
        y0, y1, ax0, ax1 = BANDS.get(layer, (0.0, 1.0, 0.0, 1.0))
        Y0, Y1 = top + y0 * (ground_y - top), top + y1 * (ground_y - top)
        if side == "r":  # character's right = picture's left
            return (mid_x - ax1 * half_w, mid_x - ax0 * half_w, Y0, Y1)
        if side == "l":
            return (mid_x + ax0 * half_w, mid_x + ax1 * half_w, Y0, Y1)
        return (mid_x - ax1 * half_w, mid_x + ax1 * half_w, Y0, Y1)
    return band


def match_parts(frame: MasterFrame, parts: dict, cut_from_master: bool, g: float | None = None,
                layer_angles: dict | None = None, roles: dict | None = None):
    """Stages 1-2 of main(): the global scale (unless g is given), then every body part's place on the master.
    layer_angles overrides the rotations searched for a draw layer (e.g. {"back": range(-90, 91, 10)}).
    roles: the annotated roles (ann_roles; None: guessed from the names), which set each part's layer.
    Returns (placed, renames, g): placed parts by (corrected) name, left/right renames, work px per part px."""
    work, fg, k = frame.work, frame.fg, frame.k
    ground_y, top, mid_x, half_w = frame.ground_y, frame.top, frame.mid_x, frame.half_w
    matcher = Matcher(work, fg)

    # 1. global scale: parts are painted at one scale; find it on the biggest, most distinctive part
    if g is None:
        anchor = "torso" if "torso" in parts else "head_base"
        coarse = matcher.best(parts[anchor][1], [k * s for s in np.geomspace(0.8, 2.4, 18)], [0])
        fine = matcher.best(parts[anchor][1], [coarse["scale"] * s for s in np.linspace(0.92, 1.08, 9)], [0])
        g = fine["scale"]  # work px per part px
        print(f"global scale: {g / k:.3f} master px per part px (anchor {anchor}, err {fine['err']:.4f})")

    # 2. place parts one group at a time, most reliable first; each placed part claims its pixels.
    #    Pairs are tried on both halves and get the cheaper left/right assignment.
    placed, renames = {}, {}
    scales = [g * s for s in (0.9, 0.95, 1.0, 1.05, 1.1)]
    band = make_band(frame)

    groups: dict[str, dict] = {}
    for name in parts:
        m = re.match(r"(.+)_(l|r)$", name)
        groups.setdefault(m.group(1) if m else name, {})[m.group(2) if m else ""] = name
    priority = ["hips", "torso", "head", "hat", "neckwear", "front", "leg", "foot", "back", "arm", "hand", "forearm"]

    def between(side: str, a_role: str, b_role: str):
        """Search box for a middle limb piece: between the placed pieces on either side of it."""
        pa = next((m for n, m in placed.items() if n == f"{a_role}_{side}"), None)
        pb = next((m for n, m in placed.items() if n == f"{b_role}_{side}"), None)
        if not pa or not pb:
            return None
        pad = 0.12 * half_w
        return (min(pa["cx"], pb["cx"]) - pad, max(pa["cx"], pb["cx"]) + pad, min(pa["cy"], pb["cy"]) - pad, max(pa["cy"], pb["cy"]) + pad)
    for base in sorted(groups, key=lambda b: priority.index(role(b, roles)[1])):
        members = groups[base]
        layer = role(base, roles)[1]
        angles = list(range(-45, 46, 9)) if layer in ("arm", "forearm", "hand") else (list(range(-30, 31, 10)) if layer in LIMBS else [0])
        angles = (layer_angles or {}).get(layer, angles)
        if set(members) == {"l", "r"}:
            lay = "tail" if is_role(base, roles, "tail", ("tail",)) else layer
            sc = ([g * s for s in (0.8, 0.85, 0.9, 0.95, 1.0)] if layer == "forearm" else
                  [g * s for s in (0.9, 1.0, 1.1, 1.2, 1.3, 1.4)] if layer in ("hand", "foot") and not cut_from_master else scales)
            def near_arm_end(side_: str):
                """Search box for a hand: around the far end of that side's placed upper arm (or forearm)."""
                arm = placed.get(f"forearm_{side_}") or placed.get(f"upperarm_{side_}")
                if arm is None:
                    return None
                pts_ = placed_points(arm)
                body_pt = np.array([mid_x, top + 0.35 * (ground_y - top)])
                far_ = pts_[np.argmax(np.linalg.norm(pts_ - body_pt, axis=1))]
                r_ = 0.32 * half_w
                return (far_[0] - r_, far_[0] + r_, far_[1] - r_, far_[1] + r_)
            regions = {half: (between(half, "upperarm", "hand") if layer == "forearm" else
                              near_arm_end(half) if layer == "hand" else None) or band(lay, half) for half in ("l", "r")}
            cand = {(pn, half): matcher.best(parts[pn][1], sc, angles, regions[half])
                    for pn in members.values() for half in ("l", "r")}
            a_, b_ = members["l"], members["r"]
            keep = cand[(a_, "l")]["err"] + cand[(b_, "r")]["err"] <= cand[(a_, "r")]["err"] + cand[(b_, "l")]["err"]
            assign = {a_: "l", b_: "r"} if keep else {a_: "r", b_: "l"}
            for pn, half in assign.items():
                new = f"{base}_{half}"
                placed[new] = cand[(pn, half)] | {"src": parts[pn][0]}
                if new != pn:
                    renames[pn] = new
        else:
            for pn in members.values():
                lay = "tail" if is_role(pn, roles, "tail", ("tail",)) else layer
                region = band(lay)
                hangs_on = [m_ for n_, m_ in placed.items() if role(n_, roles)[1] == role(pn, roles)[0]] if role(pn, roles)[0] == "neckwear" else []
                if hangs_on:                                  # a bell or medal hangs from its scarf: search the
                    m_ = hangs_on[0]                          # scarf's lower part (its box's top overlaps the chin)
                    pad = 0.1 * half_w
                    region = (m_["x"] - pad, m_["x"] + m_["w"] + pad, m_["y"] + 0.4 * m_["h"], m_["y"] + m_["h"] + pad)
                placed[pn] = matcher.best(parts[pn][1], scales, angles, region) | {"src": parts[pn][0]}
    for name in sorted(placed):
        print(f"  {name:14s} err {placed[name]['err']:.4f}  scale {placed[name]['scale'] / g:.2f}  angle {placed[name]['angle']}")
    if renames:
        print("left/right corrected:", renames)
    return placed, renames, g


def ears_in_heads(masks: dict, head_mask: np.ndarray, roles: dict | None = None) -> list:
    """Separate ear pieces the expression heads already include: ears (annotated role ear, else named ear/ears) whose
    placed mask lies over 40% under the head."""
    return [n for n, m in masks.items()
            if is_role(n, roles, "ear", ("ear", "ears")) and (m & head_mask).sum() > 0.4 * m.sum()]


def drop_ears(masks: dict, head_mask: np.ndarray, roles: dict | None, *records: dict):
    """Drop the ear pieces the expression heads already include (ears_in_heads over masks) from every dict in
    records."""
    for n_ in ears_in_heads(masks, head_mask, roles):
        print(f"  dropping {n_}: the expression heads already include the ears")
        for d_ in records:
            d_.pop(n_, None)


def match_heads(heads: list, matcher: Matcher, band, g: float, ff) -> tuple:
    """Where the expression heads (PNG paths; they share one placement) sit: the neutral one (else the first)
    matched in the head band, coarse then fine. Returns (head_pc, head_mask): the placement as a piece record
    (centre in full-res px, unit, angle) and its full-res mask. ff: rig_frame.FullFrame."""
    U = ff.U
    ref = next((f for f in heads if f.stem.endswith("_neutral")), heads[0])
    rgba = load_rgba(ref)
    coarse_h = matcher.best(rgba, [g * s_ for s_ in np.geomspace(0.6, 1.6, 12)], [0], band("head"))
    mh = matcher.best(rgba, [coarse_h["scale"] * s_ for s_ in np.linspace(0.94, 1.06, 7)], [0], band("head"))
    head_pc = {"cx": mh["cx"] * U, "cy": mh["cy"] * U, "unit": mh["scale"] / g, "angle": 0.0}
    head_mask = ff.full_mask(mh)
    print(f"  expression heads matched: err {mh['err']:.4f}, scale {mh['scale'] / g:.2f}")
    return head_pc, head_mask
