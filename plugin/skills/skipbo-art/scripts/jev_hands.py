#!/usr/bin/env python3
"""jev_hands.py - what Jev is asked about hands, and the gesture-hold check built on it.

Measured on the fox and moose (experiments/2026-10-15-beaver-jev-hands): Jev reads which way the fingers point (96%
within 45°), which way the thumb points (82%), the pose (91%) and "is the thumb up" on a rendered hold (AUROC 0.99).
Asked directly it does NOT read palm vs back (AUROC 0.61) or left vs right hand (51%): palm/back comes from
jev_facing.py's visible cues, and which hand a drawing shows comes from anatomy in code (painted_side) applied to Jev's
two directions and the ANNOTATED facing.

check_holds(rig.json) crops the hand at every gesture hold (rig/annotations.resolved.json `holds`) and applies:
  thumb_up    point and thumbs_up must show the thumb up: FAIL when P(up) < 0.5. The one gate-quality Jev check
              (it catches a thumbs-up pointing down, which once passed every metric). hold_card's grip hides the
              thumb, so it is reported, not judged
  reads_as    WARN when P(the hold's variant) < 0.3: the pose does not read
  points_out  point: WARN when Jev's finger direction points across the body
  anatomy     WARN when the painted side from Jev's directions + the annotated facing is the other hand; only when
              thumb and fingers are clearly square (30-150° apart), as single frames false-alarm otherwise
Angles are degrees in the image with y up (0 = right, 90 = up).
"""
from __future__ import annotations

import io
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

import jev_client

SIDE = 448
BG = (214, 214, 214, 255)
BINS = {"right": 0, "up-right": 45, "up": 90, "up-left": 135, "left": 180, "down-left": 225, "down": 270,
        "down-right": 315}
DIRS8 = {"up": "Toward the top edge of the image.", "up-right": "Diagonally toward the top-right corner.",
         "right": "Toward the right edge of the image.", "down-right": "Diagonally toward the bottom-right corner.",
         "down": "Toward the bottom edge of the image.", "down-left": "Diagonally toward the bottom-left corner.",
         "left": "Toward the left edge of the image.", "up-left": "Diagonally toward the top-left corner."}
GESTURES = {"relaxed": "Open and relaxed, fingers loosely together, hanging at rest.",
            "open": "Open with the fingers spread wide, as in a wave.",
            "fist": "Closed into a round fist, no finger or thumb sticking out.",
            "point": "One finger stretched out straight, the others curled.",
            "thumbsup": "Closed fist with the thumb sticking straight out.",
            "grip": "Fingers curled loosely with the thumb pressed against the first finger, as when pinching "
                    "something thin."}
HAND_Q = {
    "finger_dir": {"type": "choice",
                   "instructions": "In `hand`, which way does the hand point? Follow the hand from its wrist (the end "
                                   "that joins the arm or sleeve) out to its fingertips, or to the knuckles of a closed "
                                   "fist, and give that direction as it appears in the image.",
                   "criteria": DIRS8},
    "thumb_dir": {"type": "choice",
                  "instructions": "In `hand`, which way does the thumb stick out from the rest of the hand, as it "
                                  "appears in the image? Judge the direction from the middle of the hand to the "
                                  "thumb's tip.",
                  "criteria": DIRS8},
    "gesture": {"type": "choice", "instructions": "What pose is the hand in `hand` making?", "criteria": GESTURES},
}
THUMB_UP_Q = {"thumb_up": {"type": "noul", "instructions": "In `hand`, does the thumb point upward in the image?",
                           "criteria": {"true": "The thumb points up, within about 45 degrees of straight up.",
                                        "false": "The thumb points sideways or down, or no thumb is visible."}}}
THUMB_UP_GESTURES = ("point", "thumbs_up")    # holds that FAIL without the thumb up
READS_MIN = 0.3
SQUARE = (30, 150)


def adiff(a, b):
    return abs((a - b + 180) % 360 - 180)


def circ_mean(probs: dict) -> float:
    """Angle of the probability-weighted mean of an 8-way direction answer."""
    x = sum(p * math.cos(math.radians(BINS[k])) for k, p in probs.items() if k in BINS)
    y = sum(p * math.sin(math.radians(BINS[k])) for k, p in probs.items() if k in BINS)
    return math.degrees(math.atan2(y, x)) % 360


def painted_side(finger_deg, thumb_deg, facing) -> str:
    """Which hand a drawing shows ("l" or "r"). Joint end up (fingers at 270), a left hand showing its palm has its
    thumb on the image right (rig_hands.anatomical_thumb_sign): thumb = fingers + 90, counter-clockwise. Mirroring
    flips the turn, rotating keeps it."""
    ccw = ((thumb_deg - finger_deg) % 360) < 180
    return "l" if ccw == (facing == "palm") else "r"


def png(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def on_grey(im: Image.Image, pad: float = 0.18) -> Image.Image:
    """RGBA piece -> square flat-grey RGB, SIDE px, the piece centred with a margin."""
    bb = im.getbbox()
    im = im.crop(bb) if bb else im
    s = int(max(im.size) * (1 + 2 * pad)) or 1
    c = Image.new("RGBA", (s, s), BG)
    c.alpha_composite(im, ((s - im.size[0]) // 2, (s - im.size[1]) // 2))
    return c.convert("RGB").resize((SIDE, SIDE), Image.LANCZOS)


def facings(ann_path: Path) -> dict:
    """{attachment name: facing} from the annotations' hand outputs (variants/<char>_hand_l_point.png ->
    <char>_hand_l_point), plus {variant: facing} as a fallback."""
    out = {}
    if not Path(ann_path).is_file():
        return out
    ann = json.loads(Path(ann_path).read_text(encoding="utf-8"))
    for p in ann.get("pieces", {}).values():
        if p.get("role") != "hand" or p.get("status") == "ignored" or p.get("facing") not in ("palm", "back"):
            continue
        for o in p.get("outputs", []):
            out[Path(o["file"]).stem] = p["facing"]
        out.setdefault(f"variant:{p.get('variant') or 'relaxed'}", p["facing"])
    return out


def hold_crops(rig_json: Path, ann_path: Path, out: Path) -> list:
    """One hand crop per gesture hold: [{"anim", "slot", "side", "variant", "attachment", "facing", "path"}]."""
    import spine_qa as q
    rig_json = Path(rig_json)
    res_path = rig_json.parent / "annotations.resolved.json"
    if not res_path.is_file():
        return []
    res = json.loads(res_path.read_text(encoding="utf-8"))
    fac = facings(ann_path)
    rig = q.Rig(rig_json)
    cv = q.Canvas(rig, 1400)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for anim, h in res.get("holds", {}).items():
        if anim not in rig.data["animations"]:
            continue
        slot, att = h["slot"], h["attachment"]
        fr, _, _, alph = q.render(rig, cv, anim, h["time"], override={slot: att})
        ys, xs = np.nonzero(alph.get(slot, np.zeros((1, 1), bool)))
        if len(xs) == 0:
            continue
        cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
        half = max(120, max(xs.max() - xs.min(), ys.max() - ys.min()) * 1.3)
        crop = fr.convert("RGB").crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half)))
        p = out / f"{rig_json.stem}__{anim}_{slot}.png"
        crop.resize((SIDE, SIDE), Image.LANCZOS).save(p)
        var = h.get("variant") or "relaxed"
        rows.append({"anim": anim, "slot": slot, "side": h.get("side") or slot[-1], "variant": var,
                     "attachment": att, "facing": fac.get(att, fac.get(f"variant:{var}")), "path": str(p)})
    return rows


def hold_state(side: str) -> dict:
    name = "left" if side == "l" else "right"
    return {"task": "A close-up crop of one rendered frame of a 2D cartoon character rig, centred on one hand.",
            "which_hand": f"The character's {name} hand (on the {'right' if side == 'l' else 'left'} side of the "
                          "picture).",
            "hand": "{hand}"}


def judge_hold(row: dict, a: dict) -> dict:
    """The rules above on one hold's answers -> {"reads_as", "p_variant", "p_thumb_up", "finger_deg", "thumb_deg",
    "issues": ["FAIL ..." | "WARN ..."]}."""
    v = row["variant"]
    f_deg, t_deg = circ_mean(a["finger_dir"]["probabilities"]), circ_mean(a["thumb_dir"]["probabilities"])
    p_v = a["gesture"]["probabilities"].get(v, 0.0)
    p_up = a["thumb_up"]["noul"]
    issues = []
    if p_v < READS_MIN:
        issues.append(f"WARN reads as '{a['gesture']['choice']}', not {v}")
    if row["anim"] in THUMB_UP_GESTURES and p_up < 0.5:
        issues.append("FAIL thumb not up")
    if row["anim"] == "point":
        outward = 0 if row["side"] == "l" else 180          # the character's left hand points to the picture's right
        if adiff(f_deg, outward) > 90:
            issues.append("WARN points across the body")
    turn = (t_deg - f_deg) % 360
    square = SQUARE[0] <= turn <= SQUARE[1] or 360 - SQUARE[1] <= turn <= 360 - SQUARE[0]
    if row.get("facing") and square and painted_side(f_deg, t_deg, row["facing"]) != row["side"]:
        issues.append("WARN may be drawn as the other hand (mirrored): look at it")
    return {"reads_as": a["gesture"]["choice"], "p_variant": round(p_v, 2), "p_thumb_up": round(p_up, 2),
            "finger_deg": round(f_deg), "thumb_deg": round(t_deg), "issues": issues}


def check_holds(rig_json: Path, ann_path: Path, out: Path, cache=None) -> dict:
    """{"<anim>/<slot>": judge_hold(...)} for every hold Jev answered."""
    rows = hold_crops(rig_json, ann_path, out)
    qs = {**HAND_Q, **THUMB_UP_Q}
    ans = jev_client.run([(f"{r['anim']}/{r['slot']}", hold_state(r["side"]), qs, {"{hand}": r["path"]})
                          for r in rows], cache=cache)
    return {f"{r['anim']}/{r['slot']}": {**judge_hold(r, ans[f"{r['anim']}/{r['slot']}"]), "crop": r["path"]}
            for r in rows if f"{r['anim']}/{r['slot']}" in ans}
