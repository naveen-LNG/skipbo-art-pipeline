#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow>=10.1"]
# ///
"""rig_overlay.py - the pictures the user looks at before confirming annotations at each checkpoint.

  render_master_overlay  the master with its labelled points, thumb arrows and layer hints
  render_sheet_overlay   every piece of one split sheet in a numbered cell with its points drawn on
  render_worn_strip      each hand / foot / upper-arm / whole-sleeve output as it will be worn: on a stub forearm at the
                         pose its gesture will use (rig_hands.hold_pose), labelled with the painted side,
                         with a tick or cross for the thumb direction

Marks: hollow circle = rough point, filled circle = snapped point, ellipse = snapped opening,
orange arrow = thumb, red frame = a doubt question for the piece (rig_annotations.doubts; a failed snap alone is
only a red "(snap failed)" label). In the worn strip the thumb is judged, and drawn, across the hand's axis
(rig_hands.thumb_vector), never as the raw wrist -> thumb tip vector.
`_l` is the character's left = the picture's right, in the worn strip as everywhere else.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import rig_annotations as ra
import rig_hands as rh

BG = (205, 208, 214)           # behind pieces: far from white hands, dark boots and the marks
PAPER = (250, 250, 250)
INK = (30, 30, 36)
ROUGH = (0, 90, 220)           # hollow circles
SNAPPED = (0, 150, 70)         # filled circles and opening ellipses
FAILED = (220, 30, 30)
THUMB = (255, 120, 0)
TARGET = (130, 40, 200)
OK, BAD = (0, 150, 70), (220, 30, 30)
MARK_SIDE = {"l": (220, 80, 0), "r": (0, 110, 200), "": (170, 0, 150)}

WORN_ROLES = ("hand", "foot", "upperarm", "arm")   # a whole sleeve (arm) hangs from its shoulder like an upper arm
WORN_PER_ROW = 3               # pairs (character's right | left) per row of the worn strip
SHEET_COLS = 4
HEADER_H = 56                  # three lines of cell label above each sheet cell
LEGEND_PAD = 8

_FONTS: dict = {}


def font(size: int):
    """The default font at a readable size (Pillow >= 10.1 can scale it), else Pillow's bitmap default."""
    if size not in _FONTS:
        try:
            _FONTS[size] = ImageFont.load_default(size=size)
        except TypeError:
            _FONTS[size] = ImageFont.load_default()
    return _FONTS[size]


# ------------------------------------------------------------------ drawing helpers

def _text_w(draw, text, fnt) -> float:
    return draw.textlength(text, font=fnt)


def _wrap(draw, text, fnt, width) -> list:
    """Greedy word wrap into lines no wider than `width` px."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and _text_w(draw, trial, fnt) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def _legend_height(width, text, size=14) -> int:
    d = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    return len(_wrap(d, text, font(size), width - 2 * LEGEND_PAD)) * (size + 4) + 2 * LEGEND_PAD


def _draw_legend(img, y, text, size=14) -> None:
    d = ImageDraw.Draw(img)
    fnt = font(size)
    h = _legend_height(img.width, text, size)
    d.rectangle([0, y, img.width, y + h], fill=PAPER)
    for i, line in enumerate(_wrap(d, text, fnt, img.width - 2 * LEGEND_PAD)):
        d.text((LEGEND_PAD, y + LEGEND_PAD + i * (size + 4)), line, fill=INK, font=fnt)


def _label(draw, xy, text, size=12, fill=INK, halo=(255, 255, 255)) -> None:
    """Text with a thin halo so it stays readable on any piece colour."""
    fnt = font(size)
    x, y = xy
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.text((x + dx, y + dy), text, fill=halo, font=fnt)
    draw.text((x, y), text, fill=fill, font=fnt)


def _circle(draw, c, r, colour, filled, width=3) -> None:
    x, y = c
    box = [x - r, y - r, x + r, y + r]
    draw.ellipse([box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2], outline=(255, 255, 255), width=width + 2)
    if filled:
        draw.ellipse(box, fill=colour, outline=INK)
    else:
        draw.ellipse(box, outline=colour, width=width)


def _arrow(draw, a, b, colour, width=3, head=10) -> None:
    ax, ay = a
    bx, by = b
    ang = math.atan2(by - ay, bx - ax)
    draw.line([a, b], fill=(255, 255, 255), width=width + 3)
    draw.line([a, b], fill=colour, width=width)
    pts = [b, (bx - head * math.cos(ang - 0.45), by - head * math.sin(ang - 0.45)),
           (bx - head * math.cos(ang + 0.45), by - head * math.sin(ang + 0.45))]
    draw.polygon(pts, fill=colour, outline=(255, 255, 255))


def _tick(draw, x, y, s, colour, ok) -> None:
    """A vector tick or cross (the default font has no such glyphs), s px tall, left edge at x, top at y."""
    w = max(3, s // 5)
    if ok:
        draw.line([(x, y + s * 0.55), (x + s * 0.35, y + s * 0.9), (x + s * 0.95, y + s * 0.1)],
                  fill=colour, width=w, joint="curve")
    else:
        draw.line([(x + s * 0.1, y + s * 0.1), (x + s * 0.9, y + s * 0.9)], fill=colour, width=w)
        draw.line([(x + s * 0.9, y + s * 0.1), (x + s * 0.1, y + s * 0.9)], fill=colour, width=w)


def _on_bg(rgba, bg=BG) -> Image.Image:
    base = Image.new("RGBA", rgba.size, bg + (255,))
    return Image.alpha_composite(base, rgba).convert("RGB")


def _alpha_centroid(img):
    """Centre of mass of the opaque pixels (x, y), or the image centre when nothing is opaque."""
    ys, xs = np.nonzero(np.asarray(img.getchannel("A")) > 127)
    if xs.size == 0:
        return (img.width / 2, img.height / 2)
    return (float(xs.mean()), float(ys.mean()))


# ------------------------------------------------------------------ piece facts

def _is_doubt(piece) -> bool:
    """The piece's own confidence makes it a doubt. A failed snap alone does not (it is labelled, not framed)."""
    return piece.status != "ignored" and piece.confidence < ra.CONFIDENCE_DOUBT


def _out_side(piece, out) -> str:
    """'l' or 'r' for an output: the side token in its name, else the piece's side."""
    toks = out.name.split("_")
    for t in toks[1:]:
        if t in ("l", "r"):
            return t
    return piece.side if piece.side in ("l", "r") else ""


def _thumb_vec(out):
    """The output's thumb direction across the hand's axis (rig_hands.thumb_vector), or None without one."""
    w, t = out.points.get("wrist"), out.points.get("thumb_tip")
    return None if w is None or t is None else rh.thumb_vector(w, t, out.points.get("fingertip"))


def _painted_thumb_dx(piece) -> float:
    """Which way the thumb sticks out across the hand as painted, joint end up: > 0 image-right, < 0 image-left.

    From an output when there is one (undoing its mirror), else from the raw points: the sign of the cross
    product of the hand's axis and the thumb does not change when the piece is turned joint end up."""
    for o in piece.outputs:
        v = _thumb_vec(o)
        if v is not None:
            return -v[0] if o.mirrored else v[0]
    pt = {n: (p.snapped or p.at) for n, p in piece.points.items()}
    if "wrist" not in pt or "thumb_tip" not in pt:
        return 0.0
    (wx, wy), (tx, ty) = pt["wrist"], pt["thumb_tip"]
    ax, ay = (0.0, 1.0)
    if "fingertip" in pt:
        ax, ay = pt["fingertip"][0] - wx, pt["fingertip"][1] - wy
    return -(ax * (ty - wy) - ay * (tx - wx))         # axis (0, 1), thumb (1, 0): cross -1, image-right


def _thumb_side_label(piece) -> str:
    """What the thumb does, or '' when unknown.

    side "either": the piece is mirrored per hand, so lateral/medial would flip with the mirror; say where the
    thumb is painted ("thumb image-left" / "image-right", joint end up). side l/r: from the outputs, the thumb
    side with the arm hanging ("thumb lateral at rest").
    """
    if piece.role != "hand":
        return ""
    if piece.side == "either":
        dx = _painted_thumb_dx(piece)
        return "" if abs(dx) < 1e-6 else "thumb image-left" if dx < 0 else "thumb image-right"
    cands = sorted((o for o in piece.outputs if _thumb_vec(o) is not None),
                   key=lambda o: 0 if _out_side(piece, o) == "l" else 1)
    if not cands:
        return ""
    o = cands[0]
    side = _out_side(piece, o) or "l"
    world = rh.thumb_world_deg(_thumb_vec(o), rh.side_deg(rh.HOLD_FOREARM_DEG["rest"], side))
    outward = math.cos(math.radians(world)) * (1 if side == "l" else -1)
    return "thumb lateral at rest" if outward >= 0 else "thumb medial at rest"


def _piece_label(piece) -> str:
    if piece.status == "ignored":
        return " · ".join(b for b in ("ignored", piece.role) if b)
    bits = [b for b in (piece.role or "?", piece.variant, piece.side, piece.facing, _thumb_side_label(piece)) if b]
    return " · ".join(bits)


def _header_lines(draw, text, width, max_lines=3):
    """Wrap a cell label into at most max_lines lines, shrinking the font before ever cutting text."""
    for size in (13, 12, 11, 10):
        lines = _wrap(draw, text, font(size), width)
        if len(lines) <= max_lines:
            return lines, size
    lines = lines[:max_lines]
    lines[-1] = lines[-1].rstrip() + " ..."
    return lines, size


# ------------------------------------------------------------------ sheet overlay

def layout_size(n: int, cell: int = 260, cols: int = SHEET_COLS) -> tuple:
    """(columns, rows, width, height-without-legend) of a sheet overlay with n cells."""
    cols = max(1, min(cols, n))
    rows = max(1, -(-n // cols))
    return cols, rows, cols * cell, rows * (cell + HEADER_H)


def _inward(img, p):
    """Unit vector from point p toward the piece's centre of mass (where an opening's hollow runs)."""
    cx, cy = _alpha_centroid(img)
    dx, dy = cx - p[0], cy - p[1]
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-6 else (0.0, 1.0)


def _ellipse_poly(c, a, b, ux, uy, n=40) -> list:
    """Ellipse centred at c, semi-axis a along (ux, uy) and b across it."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = a * math.cos(t), b * math.sin(t)
        pts.append((c[0] + x * ux - y * uy, c[1] + x * uy + y * ux))
    return pts


def _draw_piece_cell(canvas, ox, oy, cell, piece, src: Image.Image) -> None:
    pad = 22
    s = (cell - 2 * pad) / max(src.width, src.height)
    w, h = max(1, round(src.width * s)), max(1, round(src.height * s))
    left, top = ox + (cell - w) // 2, oy + (cell - h) // 2
    canvas.paste(_on_bg(src.resize((w, h), Image.LANCZOS)), (left, top))
    d = ImageDraw.Draw(canvas)

    def px(xy):
        return (left + xy[0] * w, top + xy[1] * h)

    if piece.status == "ignored":          # a spare piece: no joints to show
        return

    # openings first, so the dots sit on top of them
    for pt in piece.points.values():
        if pt.kind == "opening" and pt.width and pt.snapped is not None:
            c = px(pt.snapped)
            ux, uy = _inward(src, (pt.snapped[0] * src.width, pt.snapped[1] * src.height))
            half_w = max(3.0, pt.width * s / 2)
            half_d = max(3.0, (pt.depth or pt.width * 0.3) * s / 2)
            # the hollow runs along (ux, uy); the rim (the width) runs across it
            poly = _ellipse_poly(c, half_d, half_w, ux, uy)
            d.line(poly + [poly[0]], fill=SNAPPED, width=2)

    for name, pt in piece.points.items():
        failed = pt.snap == "failed"
        if pt.snapped is not None:
            c = px(pt.snapped)
            if math.hypot(*(a - b for a, b in zip(px(pt.at), c))) > 3:
                _circle(d, px(pt.at), 4, ROUGH, filled=False, width=2)
                d.line([px(pt.at), c], fill=ROUGH, width=1)
            _circle(d, c, 5, SNAPPED, filled=True)
        else:
            c = px(pt.at)
            _circle(d, c, 6, FAILED if failed else ROUGH, filled=False)
        text = name + (" (snap failed)" if failed else "")
        tx = c[0] + 8
        if tx + _text_w(d, text, font(12)) > ox + cell - 2:     # keep the label inside its cell
            tx = c[0] - 8 - _text_w(d, text, font(12))
        _label(d, (tx, c[1] - 7), text, size=12, fill=FAILED if failed else INK)

    thumb, wrist = piece.points.get("thumb_tip"), piece.points.get("wrist")
    if thumb is not None and wrist is not None:
        _arrow(d, px(wrist.snapped or wrist.at), px(thumb.snapped or thumb.at), THUMB)


LEGEND_SHEET = ("hollow circle = rough point, filled circle = snapped point, green ellipse = snapped opening "
                "(width x depth), orange arrow = wrist to thumb tip, red label = a point that did not snap (its "
                "rough point is kept), red frame = a doubt question for the piece (e.g. confidence under 0.7).")


def render_sheet_overlay(ann: ra.Annotations, run_dir: str, out: Path, cell: int = 260) -> Path:
    """One numbered cell per piece of `run_dir`, with its points, openings and thumb arrow drawn on.
    A piece with a doubt question (rig_annotations.doubts, which reads the outputs) gets a red frame."""
    out = Path(out)
    keys = sorted(k for k in ann.pieces if k.startswith(run_dir + "/"))
    doubted = {x["key"] for x in ra.doubts(ann) if ra._in_run(x["key"], run_dir)}
    cols, rows, w, h = layout_size(len(keys), cell)
    w = max(w, 640)
    legend_h = _legend_height(w, LEGEND_SHEET)
    canvas = Image.new("RGB", (w, h + legend_h), PAPER)
    d = ImageDraw.Draw(canvas)
    for i, key in enumerate(keys):
        piece = ann.pieces[key]
        ox, oy = (i % cols) * cell, (i // cols) * (cell + HEADER_H)
        src = Image.open(ra.piece_image(ann, key)).convert("RGBA")
        d.rectangle([ox, oy, ox + cell - 1, oy + HEADER_H - 1], fill=PAPER)
        lines, hs = _header_lines(d, f"{key.rpartition('/')[2]}  {_piece_label(piece)}", cell - 8)
        for j, line in enumerate(lines):
            d.text((ox + 4, oy + 2 + j * (hs + 4)), line, fill=INK, font=font(hs))
        _draw_piece_cell(canvas, ox, oy + HEADER_H, cell, piece, src)
        d = ImageDraw.Draw(canvas)
        d.rectangle([ox, oy + HEADER_H, ox + cell - 1, oy + HEADER_H + cell - 1], outline=(150, 150, 156), width=1)
        if _is_doubt(piece) or key in doubted:
            d.rectangle([ox, oy, ox + cell - 1, oy + HEADER_H + cell - 1], outline=FAILED, width=4)
    _draw_legend(canvas, h, LEGEND_SHEET)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


# ------------------------------------------------------------------ master overlay

LEGEND_MASTER = ("hollow circle = point as annotated (orange = character's left, blue = right, magenta = centre), "
                 "orange arrow = which way the thumb points (lateral = away from the body, medial = toward it), "
                 "corner text = layer overrides, red frame = a question about the master (doubts keyed \"master\").")


def render_master_overlay(ann: ra.Annotations, out: Path) -> Path:
    """The master image with every labelled point, a thumb arrow at each wrist and the layer overrides."""
    out = Path(out)
    src = Image.open(ann.path.parent / ann.master.image).convert("RGBA")
    base = _on_bg(src, (214, 214, 214))
    scale = max(1.0, 900 / max(base.size))
    if scale > 1.0:
        base = base.resize((round(base.width * scale), round(base.height * scale)), Image.LANCZOS)
    w, h = base.size
    legend_w = max(w, 640)
    legend_h = _legend_height(legend_w, LEGEND_MASTER)
    canvas = Image.new("RGB", (legend_w, h + legend_h), PAPER)
    canvas.paste(base, ((legend_w - w) // 2, 0))
    ox = (legend_w - w) // 2
    d = ImageDraw.Draw(canvas)

    def px(xy):
        return (ox + xy[0] * w, xy[1] * h)

    for name, xy in ann.master.points.items():
        side = name[-1] if name[-2:] in ("_l", "_r") else ""
        c = px(xy)
        _circle(d, c, 6, MARK_SIDE[side], filled=False)
        # the character's left sits on the picture's right, so its labels go right, the other side's left
        label = name
        tx = c[0] + 10 if side != "r" else c[0] - 10 - _text_w(d, label, font(13))
        ty = c[1] - 8 - (22 if name.startswith("wrist") else 0)    # clear of the thumb arrow
        _label(d, (tx, ty), label, size=13)

    for side in ("l", "r"):
        hand = ann.master.hands.get(side)
        wrist = ann.master.points.get(f"wrist_{side}")
        if not hand or wrist is None:
            continue
        ts = hand.get("thumb_side")
        if ts not in ("lateral", "medial"):
            continue
        ang = math.radians(rh.target_deg(ts, side))
        a = px(wrist)
        b = (a[0] + 46 * math.cos(ang), a[1] - 46 * math.sin(ang))
        _arrow(d, a, b, THUMB, width=4, head=12)
        info = f"{side}: thumb {ts}" + (f", {hand['facing']}" if hand.get("facing") else "")
        _label(d, (min(a[0], b[0]) - (0 if side == "l" else 40), a[1] + 10), info, size=13, fill=THUMB)

    layers = ann.master.layers
    text = "layers: " + (", ".join(f"{k}={v}" for k, v in sorted(layers.items())) if layers else "default order")
    _label(d, (ox + 8, 8), text, size=15)
    if [x for x in ra.doubts(ann) if x["key"] == "master"]:    # a master question (e.g. thumb_side vs facing)
        d.rectangle([ox, 0, ox + w - 1, h - 1], outline=FAILED, width=6)
    _draw_legend(canvas, h, LEGEND_MASTER)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


# ------------------------------------------------------------------ worn strip

LEGEND_WORN = ("grey bar = the forearm, held at the pose its gesture will use (point / thumbs up: outward, or across "
               "the body when only that shows the thumb up); the picture's right is the character's left. Label: the "
               "painted side (palm / back), the pose, the thumb's target (anatomy = where that side puts it). "
               "Orange line and dot = the thumb's side: how far the thumb tip sticks out across the hand's axis "
               "(wrist to fingertip), purple arrow = where it should point. "
               "Green tick = within 45 degrees of the target, red cross = further off or the thumb on the wrong side "
               "for the painted side (hands only; feet, upper arms and sleeves are shown for shape), orange ? = cannot be "
               "checked.")


def _worn_anchor(role, out, img):
    """The joint of the output (output px) that sits on the stub's end."""
    name = {"hand": "wrist", "foot": "ankle"}.get(role, "shoulder")
    return out.points.get(name, (img.width / 2, 0.0))


def _hand_target(ann, piece, side):
    """Name of the thumb target for a hand output, or None when it cannot be known."""
    if piece.variant in (None, "rest"):
        return (ann.master.hands.get(side) or {}).get("thumb_side")
    return rh.THUMB_TARGET.get(piece.variant)


def _hand_hold(ann, piece, out, side):
    """(forearm world deg, thumb target world deg or None, label bits, anatomy ok) for a hand output as worn.

    With a `facing`: a gesture hand (point, thumbsup, grip) is drawn at the pose rig_hands.hold_pose picks for it
    (point/thumbsup: outward or across) with the thumb's target up; open and fist hands at their hold with the
    target anatomy gives (rig_hands.anatomical_thumb_deg); the rest hand against the master's thumb_side. anatomy
    ok is False when the worn thumb is on the other image side than anatomy puts it for that facing (a wrong
    mirror). Without a facing: the legacy hold angle and THUMB_TARGET, and anatomy ok None."""
    variant = piece.variant if piece.variant in rh.HOLD_FOREARM_DEG else "rest"
    forearm = rh.side_deg(rh.HOLD_FOREARM_DEG[variant], side)
    thumb = _thumb_vec(out)
    if piece.facing not in ra.FACINGS:
        name = _hand_target(ann, piece, side)
        return forearm, (rh.target_deg(name, side) if name else None), [name] if name else [], None
    bits, target, anatomy = [piece.facing], None, None
    if thumb is not None and thumb != (0.0, 0.0):
        anatomy = (thumb[0] > 0) == (rh.anatomical_thumb_sign(side, piece.facing) > 0)
    hold = rh.hold_pose(piece.variant, thumb or (0.0, 0.0), side)
    if hold is not None:
        forearm, target = hold["forearm_deg"], rh.target_deg("up", side)
        bits += ([hold["pose"]] if hold["pose"] != "hold_card" else []) + ["up"]
    elif variant == "rest":
        name = (ann.master.hands.get(side) or {}).get("thumb_side")
        if name:
            target = rh.target_deg(name, side)
            bits.append(name)
    else:
        target = rh.anatomical_thumb_deg(forearm, side, piece.facing)
        bits.append("anatomy")
    if anatomy is False:
        bits.append("thumb on the wrong side")
    return forearm, target, bits, anatomy


def _worn_item(ann, piece, out):
    """Render one output on its stub; returns (RGBA content, label lines, ok, geometry).

    geometry holds "wrist" (the anchor) and, for a hand with a thumb, "thumb_dot", in content px."""
    img = Image.open(ann.path.parent / out.file).convert("RGBA")
    side = _out_side(piece, out) or "l"
    forearm = rh.side_deg(rh.HOLD_FOREARM_DEG["rest"], side)
    if piece.role == "hand":
        forearm, target, bits, anatomy = _hand_hold(ann, piece, out, side)
    anchor = _worn_anchor(piece.role, out, img)
    # One angle drives the stub, the pasted image, the orange dot and the verdict: outputs are joint end up, so
    # image-down (world -90) is laid along the stub (world `forearm`), as rig_hands.thumb_world_deg assumes.
    # The dot and the verdict share one thumb vector: rig_hands.thumb_vector, across the hand's own axis.
    phi = forearm + 90.0

    R = int(math.ceil(max(math.hypot(x - anchor[0], y - anchor[1])
                          for x in (0, img.width) for y in (0, img.height)))) + 2
    length = max(img.width, img.height)
    half = R + length + 4
    stub_w = max(12, int(0.28 * min(img.width, img.height) + 6))
    ca, sa = math.cos(math.radians(forearm)), math.sin(math.radians(forearm))

    layer = Image.new("RGBA", (2 * half, 2 * half), (0, 0, 0, 0))
    c = (half, half)
    d = ImageDraw.Draw(layer)
    elbow = (c[0] - length * ca, c[1] + length * sa)             # image y is down, world y is up
    if piece.role not in ("upperarm", "arm"):                    # (whole) upper arms hang from the torso, not a forearm
        d.line([elbow, c], fill=(120, 120, 126, 255), width=stub_w)
        for e in (elbow, c):
            d.ellipse([e[0] - stub_w / 2, e[1] - stub_w / 2, e[0] + stub_w / 2, e[1] + stub_w / 2],
                      fill=(120, 120, 126, 255))

    pad = Image.new("RGBA", (2 * R, 2 * R), (0, 0, 0, 0))
    pad.paste(img, (round(R - anchor[0]), round(R - anchor[1])))
    rot = pad.rotate(phi, resample=Image.BICUBIC)
    layer.alpha_composite(rot, (half - R, half - R))

    ok, extra, geom = True, "", {"wrist": c}
    if piece.role == "hand":
        thumb = _thumb_vec(out)
        d = ImageDraw.Draw(layer)
        ok = None
        extra = " · ".join(bits + ([] if target is not None else ["no thumb_tip" if thumb is None else "no target"]))
        if target is not None:
            ta = math.radians(target)
            _arrow(d, c, (c[0] + 0.6 * R * math.cos(ta), c[1] - 0.6 * R * math.sin(ta)), TARGET, width=3, head=12)
        if thumb is not None:
            # the thumb across the hand's axis (what the verdict judges), not the raw wrist -> thumb tip
            u = (thumb[0], -thumb[1])                            # image px (y down) -> world (y up), then rotate
            cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
            tp = (c[0] + u[0] * cp - u[1] * sp, c[1] - (u[0] * sp + u[1] * cp))
            r = 7
            d.line([c, tp], fill=(255, 255, 255, 255), width=6)
            d.line([c, tp], fill=THUMB, width=3)
            d.ellipse([tp[0] - r, tp[1] - r, tp[0] + r, tp[1] + r], fill=THUMB, outline=(255, 255, 255), width=2)
            geom["thumb_dot"] = tp
            if thumb == (0.0, 0.0):                              # the tip lies on the hand's axis: no side
                ok, extra = None, " · ".join(bits[:1] + ["thumb on the hand's axis"])
            elif target is not None:
                ok = rh.ang_diff(rh.thumb_world_deg(thumb, forearm), target) <= rh.THUMB_TOL and anatomy is not False
    lines = [out.name, extra]
    box = layer.getbbox() or (0, 0, 1, 1)
    geom = {k: (x - box[0], y - box[1]) for k, (x, y) in geom.items()}
    return layer.crop(box), lines, ok, geom


def _group_key(out):
    return "_".join(t for t in out.name.split("_") if t not in ("l", "r"))


def worn_cells(ann: ra.Annotations, run_dir: str) -> list:
    """[(piece, output, row, col)] for the worn strip. A pair (same part, same variant) shares two columns,
    the character's right on the picture's left; WORN_PER_ROW pairs per row."""
    found, order = [], {}
    for key in sorted(k for k in ann.pieces if k.startswith(run_dir + "/")):
        piece = ann.pieces[key]
        if piece.role not in WORN_ROLES:
            continue
        for o in piece.outputs:
            g = (piece.role, piece.variant or "", _group_key(o))
            order.setdefault(g, len(order))
            found.append((piece, o, order[g], 1 if _out_side(piece, o) == "l" else 0))
    return [(p, o, g // WORN_PER_ROW, (g % WORN_PER_ROW) * 2 + side) for p, o, g, side in found]


def render_worn_strip(ann: ra.Annotations, run_dir: str, out: Path, h: int = 300) -> tuple:
    """Hands, feet, upper arms and whole sleeves of `run_dir` as worn. Returns (path, [(output name, thumb ok)]).

    ok is None when a hand cannot be checked (no thumb_tip or no target).
    The character's right output of each pair is on the picture's left. Non-hand outputs are True (shape only).
    """
    out = Path(out)
    items = []                                               # (row, col, content, lines, ok, name)
    for piece, o, row, col in worn_cells(ann, run_dir):
        content, lines, ok, _ = _worn_item(ann, piece, o)
        items.append((row, col, content, lines, ok, o.name))
    verdicts = [(it[5], it[4]) for it in items]

    label_h = 2 * 18 + 6
    pad = 10
    avail = max(20, h - label_h - 2 * pad)
    scale = min([avail / it[2].height for it in items] or [1.0])
    scale = min(scale, 3.0)
    cell_w = max([round(it[2].width * scale) for it in items] or [100]) + 2 * pad
    cell_w = max(cell_w, 200)

    n_rows = max([it[0] for it in items] + [0]) + 1
    n_cols = max([it[1] for it in items] + [1]) + 1
    width = max(n_cols * cell_w, 640)
    legend_h = _legend_height(width, LEGEND_WORN)
    canvas = Image.new("RGB", (width, n_rows * h + legend_h), PAPER)
    d = ImageDraw.Draw(canvas)
    fnt = font(15)
    for row, col, content, lines, ok, name in items:
        ox, oy = col * cell_w, row * h
        cw, ch = max(1, round(content.width * scale)), max(1, round(content.height * scale))
        tile = _on_bg(content.resize((cw, ch), Image.LANCZOS))
        d.rectangle([ox + 2, oy + 2, ox + cell_w - 3, oy + h - label_h - 1], fill=BG)
        canvas.paste(tile, (ox + (cell_w - cw) // 2, oy + 2 + (h - label_h - 2 - ch) // 2))
        ly = oy + h - label_h + 2
        d.text((ox + 6, ly), lines[0], fill=INK, font=fnt)
        if lines[1]:
            d.text((ox + 6, ly + 18), lines[1], fill=INK, font=fnt)
            mx = ox + 6 + _text_w(d, lines[1], fnt) + 8
            if ok is None:
                d.text((mx, ly + 17), "?", fill=(200, 120, 0), font=font(18))
            else:
                _tick(d, mx, ly + 19, 15, OK if ok else BAD, ok)
        if ok is False:
            d.rectangle([ox + 1, oy + 1, ox + cell_w - 2, oy + h - 1], outline=FAILED, width=4)
    _draw_legend(canvas, n_rows * h, LEGEND_WORN)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out, verdicts
