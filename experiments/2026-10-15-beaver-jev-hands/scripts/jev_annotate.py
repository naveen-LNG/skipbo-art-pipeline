# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Jev second opinion on every annotated hand piece, before its checkpoint.

  uv run jev_annotate.py <annotations.json> --exemplars <pieces set dir> [--all-hands]

For each hand piece (as painted, on flat grey) Jev answers gesture, finger and thumb direction and palm/back (with
palm/back example pictures from the exemplar set: other characters' confirmed pieces). Code then compares:
  gesture        Jev's choice vs the annotated variant
  thumb_side     which hand the drawing shows by anatomy, from the ANNOTATED facing and (a) the annotated points
                 (b) Jev's two directions; a mismatch means the thumb_tip / fingertip points or the piece reading is off
  facing         Jev's P(palm) vs the annotated facing; a hint only (AUROC ~0.8 on fox/moose), raised when Jev is
                 confident (P <= 0.2 or >= 0.8) and disagrees
Writes <annotations dir>/annotations/jev_hands.json and prints the doubts as JSON (key, reason, options)."""
import json, math, sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import jev  # noqa: E402
from hands_set import on_grey, painted_side, piece_truth  # noqa: E402
from score_hands import circ_mean  # noqa: E402

import argparse  # noqa: E402
ap = argparse.ArgumentParser(); ap.add_argument("annotations"); ap.add_argument("--exemplars", required=True)
ap.add_argument("--all-hands", action="store_true"); args = ap.parse_args()
ann_path = Path(args.annotations); opt = {"--exemplars": args.exemplars}
ann = json.load(open(ann_path)); root = ann_path.parent
out_dir = root / "annotations" / "jev"; out_dir.mkdir(parents=True, exist_ok=True)
EX = Path(opt["--exemplars"])
ex_rows = [json.loads(l) for l in open(EX / "labels.jsonl")]


def examples(facing, n=3):
    rows = [r for r in ex_rows if r["rot"] == 0 and not r["mirror"] and r["facing"] == facing and r.get("status") in ("confirmed", "fixed")]
    seen, out = set(), []
    for r in rows:                         # one per variant first: the examples should span poses, not repeat one
        if r["variant"] not in seen:
            seen.add(r["variant"]); out.append(EX / f"{r['id']}.png")
    return out[:n]


import run_hands  # noqa: E402  (question wording shared with the experiment)  # pylint: disable=wrong-import-position

Q = {k: run_hands.Q[k] for k in ("finger_dir", "thumb_dir", "gesture")}
EXP, EXB = examples("palm"), examples("back")
Q["facing"] = {**run_hands.Q["facing"], "criteria": {
    "palm": {"description": run_hands.Q["facing"]["criteria"]["palm"], "examples": [f"{{p{i}}}" for i in range(len(EXP))]},
    "back": {"description": run_hands.Q["facing"]["criteria"]["back"], "examples": [f"{{b{i}}}" for i in range(len(EXB))]}}}

keys = [k for k, p in sorted(ann["pieces"].items()) if p.get("role") == "hand" and p.get("status") != "ignored"]
if args.all_hands:              # spare hands too (the experiment's held-out set), if they carry a facing
    keys = [k for k, p in sorted(ann["pieces"].items()) if p.get("role") == "hand" and p.get("facing")]
jobs, meta = [], {}
for k in keys:
    p = ann["pieces"][k]; run, nn = k.split("/")
    f = next((root / "runs" / run).glob(f"*_{nn}.png")); im = Image.open(f).convert("RGBA")
    img = out_dir / f"{run}_{nn}.png"; on_grey(im).save(img)
    f_deg, t_deg, _ = piece_truth(p, im)
    meta[k] = {"variant": p.get("variant") or "relaxed", "facing": p["facing"], "finger_deg": round(f_deg, 1), "thumb_deg": round(t_deg, 1)}
    imgs = {"{hand}": img, **{f"{{p{i}}}": x for i, x in enumerate(EXP)}, **{f"{{b{i}}}": x for i, x in enumerate(EXB)}}
    state = {"task": "A painted hand (or paw) of a cartoon character, cut out as one piece of a 2D animation rig and shown "
                     "on a flat grey background.", "hand": "{hand}"}
    jobs.append((k, state, Q, imgs, {}))
res_path = out_dir / "results.jsonl"
jev.run_many(jobs, res_path, 4)
res = {json.loads(l)["id"]: json.loads(l)["answers"] for l in open(res_path)}

report, doubts = {}, []
for k in keys:
    a, m = res[k], meta[k]
    jf = circ_mean(a["finger_dir"]["probabilities"])[0]; jt = circ_mean(a["thumb_dir"]["probabilities"])[0]
    ann_side = painted_side(m["finger_deg"], m["thumb_deg"], m["facing"])
    jev_side = painted_side(jf, jt, m["facing"])
    p_palm = a["facing"]["probabilities"]["palm"]
    r = {**m, "jev_gesture": a["gesture"]["choice"], "jev_gesture_p": a["gesture"]["probabilities"].get(m["variant"]),
         "jev_finger_deg": round(jf, 1), "jev_thumb_deg": round(jt, 1), "painted_from_points": ann_side,
         "painted_from_jev": jev_side, "jev_p_palm": p_palm}
    report[k] = r
    if a["gesture"]["choice"] != m["variant"]:
        doubts.append({"key": k, "reason": f"Jev reads the {m['variant']} hand as '{a['gesture']['choice']}' "
                                           f"(P({m['variant']})={r['jev_gesture_p']:.2f})", "options": ["variant is right", "needs a fix"]})
    if ann_side != jev_side:
        doubts.append({"key": k, "reason": f"thumb side: with facing={m['facing']} the annotated points make it a "
                                           f"{'left' if ann_side == 'l' else 'right'} hand, Jev's directions (fingers "
                                           f"{jf:.0f} deg, thumb {jt:.0f} deg) a {'left' if jev_side == 'l' else 'right'} one",
                       "options": ["points are right", "move thumb_tip / fingertip"]})
    if (p_palm >= 0.8 and m["facing"] == "back") or (p_palm <= 0.2 and m["facing"] == "palm"):
        doubts.append({"key": k, "reason": f"Jev says {'palm' if p_palm >= 0.5 else 'back'} (P(palm)={p_palm:.2f}) where the "
                                           f"annotation says {m['facing']}", "options": [f"{m['facing']} is right", "switch facing"]})
json.dump(report, open(out_dir / "jev_hands.json", "w"), indent=1)
print(json.dumps({"hands": report, "doubts": doubts}, indent=1))
