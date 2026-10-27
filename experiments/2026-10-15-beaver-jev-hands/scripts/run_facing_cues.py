"""Palm or back from observable cues instead of the abstract question (which is at chance).

  python3 run_facing_cues.py <pieces set dir> [--upright]   -> results_cues.jsonl, then prints AUROC per cue

Each cue is something visible in the drawing; code combines them. palm_score = mean of the palm-side cues minus the
mean of the back-side cues. --upright: only unturned, unmirrored items (one per piece)."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jev  # noqa: E402
from score_hands import auroc  # noqa: E402

CUES = {
    "pads": ("palm", "In `hand`, can you see the soft inner side of the hand: a palm pad, the pads of the fingers, or the "
                     "fingertips folded in toward the viewer?"),
    "creases": ("palm", "In `hand`, are the curled fingers seen from the inside, so the creases between the folded fingers "
                        "and their tips face the viewer, like looking into a loosely closed hand?"),
    "thumb_front": ("palm", "In `hand`, does the thumb lie across the front of the curled fingers or the palm, on the side "
                            "facing the viewer?"),
    "knuckles": ("back", "In `hand`, do you see the back of the hand: a smooth broad surface with the knuckles along its "
                         "edge, the fingers bending away from the viewer?"),
    "smooth_top": ("back", "In `hand`, is the biggest visible area of the hand a smooth, rounded surface with no finger tips "
                           "or palm pad on it, like the back of a mitten?"),
}
Q = {k: {"type": "noul", "instructions": txt, "criteria": {"true": "Yes, clearly visible.", "false": "No."}}
     for k, (_, txt) in CUES.items()}
Q["curl"] = {"type": "choice", "instructions": "In `hand`, which way do the bent fingers curl?",
             "criteria": {"toward": "Toward the viewer: the fingertips come forward, out of the picture.",
                          "away": "Away from the viewer: the fingertips go behind the hand.",
                          "flat": "The fingers are not bent."}}
def palm_score(a):
    pal = [a[k]["noul"] for k, (side, _) in CUES.items() if side == "palm"]
    bak = [a[k]["noul"] for k, (side, _) in CUES.items() if side == "back"]
    return sum(pal) / len(pal) - sum(bak) / len(bak) + 0.5 * (a["curl"]["probabilities"]["toward"] - a["curl"]["probabilities"]["away"])



if __name__ == "__main__":
    D = Path(sys.argv[1]); upright = "--upright" in sys.argv
    rows = [json.loads(l) for l in open(D / "labels.jsonl")]
    if upright:
        rows = [r for r in rows if r["rot"] == 0 and not r["mirror"]]
    state = {"task": "A painted hand (or paw) of a cartoon character, cut out as one piece of a 2D animation rig and shown on a "
                     "flat grey background. The piece may be turned to any angle or mirrored.", "hand": "{hand}"}
    out = D / "results_cues.jsonl"
    jev.run_many([(r["id"], state, Q, {"{hand}": D / f"{r['id']}.png"}, {}) for r in rows], out, 4)
    res = {json.loads(l)["id"]: json.loads(l)["answers"] for l in open(out)}
    rows = [r for r in rows if r["id"] in res]


    report = {}
    for name, f in [*[(k, (lambda a, k=k, s=s: a[k]["noul"] if s == "palm" else -a[k]["noul"])) for k, (s, _) in CUES.items()],
                    ("curl", lambda a: a["curl"]["probabilities"]["toward"] - a["curl"]["probabilities"]["away"]),
                    ("combined", palm_score)]:
        sc = {"all": auroc([f(res[r["id"]]) for r in rows if r["facing"] == "palm"], [f(res[r["id"]]) for r in rows if r["facing"] == "back"])}
        for c in sorted({r["char"] for r in rows}):
            sc[c] = auroc([f(res[r["id"]]) for r in rows if r["facing"] == "palm" and r["char"] == c],
                          [f(res[r["id"]]) for r in rows if r["facing"] == "back" and r["char"] == c])
        report[name] = sc
        print(f"{name:12s}", "  ".join(f"{k}={v}" for k, v in sc.items()))
    json.dump(report, open(D / "scores_cues.json", "w"), indent=1)
