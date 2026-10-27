# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Jev reads every gesture hold of a rig the way a viewer would: which pose, which way the finger and thumb point.

  uv run jev_rig_check.py <char>=<rig dir> [--out <dir>]

Per hold (the frames annotations.resolved.json names), crop the hand, ask Jev, and apply rules in code:
  reads_as     P(the hold's variant) from the gesture question; WARN under 0.3 (the pose does not read)
  thumb_up     point and thumbs_up must show the thumb up: FAIL when P(up) < 0.5 (thumbs-up pointing down, a
               mirrored hand). hold_card's grip hides the thumb, so it is reported, not judged
  points_out   point: the finger should point away from the body (outward half-plane for the side); WARN when
               Jev's finger direction points across the body
  anatomy      the painted side from Jev's finger and thumb directions plus the ANNOTATED facing
               (rig_hands' anatomy rule) should be the slot's side: WARN when it is the other hand (mirrored), only
               when thumb and fingers are clearly square (30-150 deg apart either way). A WARN, not a FAIL: on single
               approved frames Jev's thumb direction is off often enough (fox and moose wave) to false-alarm
Jev's own palm/back answer is not used: it was at chance on the fox, moose and beaver hands.
Prints one line per hold and a JSON summary; exit code 1 on any FAIL."""
import json, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import hands_set  # noqa: E402
import jev  # noqa: E402
import run_hands  # noqa: E402
from score_hands import circ_mean, painted_side, adiff  # noqa: E402

spec = sys.argv[1]; char = spec.split("=", 1)[0]
out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else Path(tempfile.mkdtemp(prefix=f"jev_{char}_"))
out.mkdir(parents=True, exist_ok=True)
rows = [r for r in hands_set.holds(out, [spec]) if r["is_hold"] and not r["planted_mirror"]]
qs = {**{k: run_hands.Q[k] for k in ("finger_dir", "thumb_dir", "gesture")}, "thumb_up": run_hands.HOLD_Q["thumb_up"]}
jobs = []
for r in rows:
    side = "left" if r["side"] == "l" else "right"
    state = {"task": "A close-up crop of one rendered frame of a 2D cartoon character rig, centred on one hand.",
             "which_hand": f"The character's {side} hand (on the {'right' if side == 'left' else 'left'} side of the picture).",
             "hand": "{hand}"}
    jobs.append((r["id"], state, qs, {"{hand}": out / f"{r['id']}.png"}, {}))
res_path = out / "jev_rig_check.jsonl"
if res_path.exists():
    res_path.unlink()
jev.run_many(jobs, res_path, 4)
ans = {json.loads(l)["id"]: json.loads(l)["answers"] for l in open(res_path)}

summary, failed = {}, False
for r in rows:
    a = ans[r["id"]]; v = r["variant"]
    f_deg = circ_mean(a["finger_dir"]["probabilities"])[0]; t_deg = circ_mean(a["thumb_dir"]["probabilities"])[0]
    p_v = a["gesture"]["probabilities"].get(v, 0.0); p_up = a["thumb_up"]["noul"]
    verdict = {"reads_as": a["gesture"]["choice"], "p_variant": round(p_v, 2), "p_thumb_up": round(p_up, 2),
               "finger_deg": round(f_deg), "thumb_deg": round(t_deg), "issues": []}
    if p_v < 0.3:
        verdict["issues"].append(f"WARN reads as '{a['gesture']['choice']}', not {v}")
    if r["anim"] in ("point", "thumbs_up") and p_up < 0.5:
        verdict["issues"].append("FAIL thumb not up")
    if r["anim"] == "point":
        outward = 0 if r["side"] == "l" else 180              # the character's left hand points to the picture's right
        if adiff(f_deg, outward) > 90:
            verdict["issues"].append("WARN points across the body")
    turn = (t_deg - f_deg) % 360
    square = 30 <= turn <= 150 or 210 <= turn <= 330
    if r.get("facing") and square and painted_side(f_deg, t_deg, r["facing"]) != r["side"]:
        verdict["issues"].append("WARN may be drawn as the other hand (mirrored): look at it")
    failed |= any(i.startswith("FAIL") for i in verdict["issues"])
    summary[f"{r['anim']}/{r['slot']}"] = verdict
    print(f"{r['anim']:10s} {r['slot']} {v:9s} reads={verdict['reads_as']:9s} P={p_v:.2f} P(up)={p_up:.2f} "
          f"finger={f_deg:4.0f} thumb={t_deg:4.0f}  {'; '.join(verdict['issues']) or 'ok'}")
json.dump(summary, open(out / "jev_rig_check.json", "w"), indent=1)
print(json.dumps({"char": char, "fail": failed, "crops": str(out)}))
sys.exit(1 if failed else 0)
