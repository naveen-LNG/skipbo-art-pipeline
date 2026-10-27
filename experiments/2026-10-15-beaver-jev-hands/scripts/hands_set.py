# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Hand-direction test sets with exact ground truth.

  uv run hands_set.py pieces <out> <char>=<annotations.json> ...   # set A: every annotated hand piece, 8 turns x mirror
  uv run hands_set.py holds  <out> <char>=<rig dir> ...            # set B: rendered gesture frames, hand crops, planted mirrors

Angles are degrees in the image with y UP (0 = right, 90 = up). Per item:
  finger_deg  wrist -> fingertip (or wrist -> the hand's centroid for a fist / thumbs-up)
  thumb_deg   rig_hands.thumb_vector: the part of wrist -> thumb_tip across that axis
  facing      palm | back (from the confirmed annotation)
  painted     l | r: which hand the drawing shows, from anatomy (rig_hands.anatomical_thumb_sign): a left hand seen from
              the palm has its thumb counter-clockwise of wrist->fingers in y-up terms... see painted_side()
Writes <out>/<id>.png (448 px, flat grey) and <out>/labels.jsonl."""
import json, math, random, sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "plugin/skills/skipbo-art/scripts"))
import rig_hands  # noqa: E402

BG = (214, 214, 214, 255)
SIDE = 448


def deg(v):                       # image vector (y down) -> y-up degrees
    return math.degrees(math.atan2(-v[1], v[0])) % 360


def painted_side(finger_deg, thumb_deg, facing):
    """Which hand a drawing shows. Joint end up (fingers at 270), a left hand showing its palm has its thumb on the
    image right (0 deg): thumb = finger + 90 (counter-clockwise). Mirroring flips the turn, rotating keeps it."""
    ccw = ((thumb_deg - finger_deg) % 360) < 180
    return "l" if ccw == (facing == "palm") else "r"


def centroid(im):
    a = np.asarray(im)[..., 3].astype(float)
    ys, xs = np.nonzero(a > 127)
    return float(xs.mean()), float(ys.mean())


def on_grey(im, pad=0.18):
    """RGBA piece -> square flat-grey RGB, SIDE px, piece centred with a margin."""
    bb = im.getbbox(); im = im.crop(bb)
    s = int(max(im.size) * (1 + 2 * pad))
    c = Image.new("RGBA", (s, s), BG)
    c.alpha_composite(im, ((s - im.size[0]) // 2, (s - im.size[1]) // 2))
    return c.convert("RGB").resize((SIDE, SIDE), Image.LANCZOS)


def piece_truth(ann_piece, im):
    W, H = im.size
    P = {k: (v["at"][0] * W, v["at"][1] * H) for k, v in ann_piece["points"].items()}
    w = P["wrist"]
    tip = P.get("fingertip") or centroid(im)
    tv = rig_hands.thumb_vector(w, P["thumb_tip"], P.get("fingertip"))
    if P.get("fingertip") is None:             # thumb_vector assumes image-down without a fingertip; use the centroid axis
        ax = (tip[0] - w[0], tip[1] - w[1]); n = math.hypot(*ax); ax = (ax[0] / n, ax[1] / n)
        t = (P["thumb_tip"][0] - w[0], P["thumb_tip"][1] - w[1]); along = t[0] * ax[0] + t[1] * ax[1]
        tv = (t[0] - along * ax[0], t[1] - along * ax[1])
    return deg((tip[0] - w[0], tip[1] - w[1])), deg(tv), math.hypot(*tv) / max(1e-9, math.hypot(P["thumb_tip"][0] - w[0], P["thumb_tip"][1] - w[1]))


def pieces(out, specs):
    rows = []
    for spec in specs:
        char, ann_path = spec.split("=", 1); ann_path = Path(ann_path)
        ann = json.load(open(ann_path))
        for key, p in sorted(ann["pieces"].items()):
            if p.get("role") != "hand" or not p.get("facing") or "thumb_tip" not in p.get("points", {}):
                continue
            run, nn = key.split("/")
            f = next((ann_path.parent / "runs" / run).glob(f"*_{nn}.png"))
            im = Image.open(f).convert("RGBA")
            f_deg, t_deg, t_side_share = piece_truth(p, im)
            for mirror in (False, True):
                base = im.transpose(Image.FLIP_LEFT_RIGHT) if mirror else im
                fd0, td0 = ((180 - f_deg) % 360, (180 - t_deg) % 360) if mirror else (f_deg, t_deg)
                for rot in range(0, 360, 45):
                    img = on_grey(base.rotate(rot, expand=True, resample=Image.BICUBIC))
                    fd, td = (fd0 + rot) % 360, (td0 + rot) % 360
                    iid = f"{char}__{run}_{nn}__m{int(mirror)}_r{rot:03d}"
                    img.save(out / f"{iid}.png")
                    rows.append({"id": iid, "set": "pieces", "char": char, "piece": key, "variant": p.get("variant") or "relaxed",
                                 "facing": p["facing"], "status": p.get("status"), "mirror": mirror, "rot": rot,
                                 "finger_deg": round(fd, 1), "thumb_deg": round(td, 1), "thumb_side_share": round(t_side_share, 2),
                                 "painted": painted_side(fd, td, p["facing"])})
    return rows


def holds(out, specs):
    import spine_qa as q
    rows = []
    for spec in specs:
        char, rigdir = spec.split("=", 1); rigdir = Path(rigdir)
        rig = q.Rig(rigdir / f"{char}.json"); cv = q.Canvas(rig, 1400)
        res = json.load(open(rigdir / "annotations.resolved.json"))
        ann = json.load(open(rigdir.parent / "annotations.json"))
        facing_of = {}
        for p in ann["pieces"].values():
            if p.get("role") == "hand" and p.get("status") in ("confirmed", "fixed"):
                facing_of[p.get("variant") or "relaxed"] = p.get("facing")
        anims = [a for a in ("wave", "point", "thumbs_up", "hold_card", "cheer_jump") if a in rig.data["animations"]]
        frames = []
        for a in anims:
            T = rig.duration(a)
            ts = sorted({round(T * k / 6, 3) for k in range(1, 6)} | ({res["holds"][a]["time"]} if a in res["holds"] else set()))
            frames += [(a, t) for t in ts]
        frames.append((None, 0.0))
        for a, t in frames:
            world, active = rig.pose(a, t)
            for slot in ("hand_l", "hand_r"):
                att = active.get(slot)
                info = res["attachments"].get(att)
                if not att or not info or "thumb_tip" not in info["points"]:
                    continue
                var = info.get("variant") or "relaxed"
                is_hold = bool(a in res["holds"] and abs(res["holds"][a]["time"] - t) < 1e-3)
                if var == "relaxed" and a is not None and not is_hold:
                    continue                  # a resting hand looks the same in every frame: setup and holds only
                pts = info["points"]
                tip = pts.get("fingertip") or centroid(rig.images[att])
                u = np.subtract(tip, pts["wrist"]); u = u / np.linalg.norm(u)
                R2 = 2 * np.outer(u, u) - np.eye(2)               # reflection across the hand's own axis
                Rfl = np.eye(3); Rfl[:2, :2] = R2; Rfl[:2, 2] = np.asarray(pts["wrist"]) - R2 @ np.asarray(pts["wrist"])
                for planted in (False, True):
                    if planted and (a is None or var == "relaxed"):
                        continue              # plant mirrors only on gesture variants
                    fr, _, _, alph = render_mirrored(q, rig, cv, a, t, slot, att, Rfl) if planted else q.render(rig, cv, a, t)
                    # world point of what is drawn at image px p: M @ p, or M @ Rfl @ p for the mirrored drawing
                    M = rig.att_affine_at(slot, att, world, pts["wrist"])
                    if planted:
                        M = M @ Rfl
                    def W(p): return q._xy(M, p)
                    w0 = W(pts["wrist"])
                    tv = rig_hands.thumb_vector(pts["wrist"], pts["thumb_tip"], pts.get("fingertip"))
                    if pts.get("fingertip") is None:   # thumb across the centroid axis (thumb_vector assumes image-down)
                        tt = np.subtract(pts["thumb_tip"], pts["wrist"]); tv = tuple(tt - (tt @ u) * u)
                    f1, t1 = W(tip), W((pts["wrist"][0] + tv[0], pts["wrist"][1] + tv[1]))
                    f_deg = math.degrees(math.atan2(f1[1] - w0[1], f1[0] - w0[0])) % 360   # world is y up
                    t_deg = math.degrees(math.atan2(t1[1] - w0[1], t1[0] - w0[0])) % 360
                    lay = alph[slot]; ys, xs = np.nonzero(lay)
                    if len(xs) == 0:
                        continue
                    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
                    half = max(xs.max() - xs.min(), ys.max() - ys.min()) * 1.3
                    half = max(half, 120)
                    crop = fr.convert("RGB").crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half))).resize((SIDE, SIDE), Image.LANCZOS)
                    iid = f"{char}__{a or 'setup'}_{t:.2f}_{slot}{'__mirrored' if planted else ''}"
                    crop.save(out / f"{iid}.png")
                    fr.convert("RGB").resize((fr.size[0] * 520 // fr.size[1], 520)).save(out / f"{iid}__frame.jpg", quality=88)
                    rows.append({"id": iid, "set": "holds", "char": char, "anim": a or "setup", "t": t, "slot": slot,
                                 "side": slot[-1], "attachment": att, "variant": var, "facing": facing_of.get(var),
                                 "planted_mirror": planted, "is_hold": is_hold and res["holds"][a]["slot"] == slot,
                                 "finger_deg": round(f_deg, 1), "thumb_deg": round(t_deg, 1)})
    return rows


def render_mirrored(q, rig, cv, a, t, slot, att, Rfl):
    """q.render with the hand attachment drawn reflected across its own axis through the wrist (a mirrored hand: the
    wrist and the finger direction stay, the thumb changes side). Done on the matrix, so nothing is clipped."""
    orig = rig.att_matrix
    rig.att_matrix = lambda s_, a_, w_: orig(s_, a_, w_) @ Rfl if (s_, a_) == (slot, att) else orig(s_, a_, w_)
    try:
        return q.render(rig, cv, a, t)
    finally:
        del rig.att_matrix


if __name__ == "__main__":
    mode, out = sys.argv[1], Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    rows = (pieces if mode == "pieces" else holds)(out, sys.argv[3:])
    with open(out / "labels.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(len(rows), "items ->", out)
