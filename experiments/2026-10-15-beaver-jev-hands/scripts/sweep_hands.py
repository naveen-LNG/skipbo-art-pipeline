# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Sweep the master's fingertip points (hand size and hang angle) and keep the one whose hands stay inside their
cuffs (spine_qa sockets) in every animation. The rig sizes a hand by the master's wrist->fingertip and turns it to
that direction; the beaver's whole sleeves are slimmer at the cuff than the two-piece arms were, so the master's
more upright mitten swings its top corner out beside the cuff.

  uv run sweep_hands.py <scratch dir>     (each candidate: annotations copy -> spine_rig -> check_sockets)"""
import copy, json, math, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent; B = HERE.parent / "beaver"
S = HERE.parents[2] / "plugin/skills/skipbo-art/scripts"
sys.path.insert(0, str(S))
import spine_qa as q  # noqa: E402

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
ann0 = json.load(open(B / "annotations.json"))
M = ann0["master"]["points"]
W, H = 1792, 2400
res = []
for size in (1.0, 1.1, 1.2):
    for blend in (0.0, 0.35, 0.7):          # 0 = the master's mitten direction, 1 = straight along the sleeve
        ann = copy.deepcopy(ann0)
        for s, sg in (("l", 1), ("r", -1)):
            w = (M[f"wrist_{s}"][0] * W, M[f"wrist_{s}"][1] * H); e = (M[f"elbow_{s}"][0] * W, M[f"elbow_{s}"][1] * H)
            hand_deg = math.atan2(0.078 * H, sg * 0.046 * W)               # the master's own mitten (round 1 points)
            arm_deg = math.atan2(w[1] - e[1], w[0] - e[0])
            d = hand_deg + blend * ((arm_deg - hand_deg + math.pi) % (2 * math.pi) - math.pi)
            L = size * math.hypot(0.046 * W, 0.078 * H)
            ann["master"]["points"][f"fingertip_{s}"] = [round((w[0] + L * math.cos(d)) / W, 4), round((w[1] + L * math.sin(d)) / H, 4)]
        tag = f"s{size}_b{blend}"
        d_ = out / tag; d_.mkdir(exist_ok=True)
        (d_ / "annotations.json").write_text(json.dumps(ann))
        for f in ("beaver_master.png",):
            (d_ / f).unlink(missing_ok=True); (d_ / f).symlink_to(B / f)
        (d_ / "runs").unlink(missing_ok=True); (d_ / "runs").symlink_to(B / "runs")
        for sub in ("body", "variants", "face-heads"):
            (d_ / sub).unlink(missing_ok=True); (d_ / sub).symlink_to(B / sub)
        r = subprocess.run(["uv", "run", "-q", str(S / "spine_rig.py"), "--master", str(d_ / "beaver_master.png"), "--annotations",
                            str(d_ / "annotations.json"), "--out", str(d_ / "rig")], capture_output=True, text=True)
        rig = q.Rig(d_ / "rig/beaver.json"); cv = q.Canvas(rig, q.CHECK_H)
        resolved = json.load(open(d_ / "rig/annotations.resolved.json"))
        so = q.check_sockets(rig, cv, resolved, list(rig.data["animations"]))
        sp = {k.split("/")[0][-6:]: v["spill"] for k, v in so["sockets"].items()}
        row = {"size": size, "blend": blend, "pass": so["pass"], "spill": sp, "fingertips": {s: ann["master"]["points"][f"fingertip_{s}"] for s in "lr"}}
        res.append(row); print(json.dumps(row), flush=True)
json.dump(res, open(out / "sweep.json", "w"), indent=1)
