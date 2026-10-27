"""Ask Jev which way a hand points: fingers, thumb, palm or back, gesture, which hand.

  python3 run_hands.py <set dir> text|exemplar [--workers 4] [--limit N]

text      every question with text criteria only.
exemplar  facing (palm/back) and painted (left/right hand) defined by example pictures from the OTHER characters'
          confirmed pieces (leave-one-character-out), plus the same direction questions.
Pieces (set A) and render crops (set B) get the same questions; render crops add `thumb_up` and `mirrored`
and the slot's side as context. Writes <set dir>/results_<condition>.jsonl (resumable)."""
import json, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jev  # noqa: E402

MAIN = __name__ == "__main__"                         # imported by jev_annotate.py for the question wording
SET, COND = (Path(sys.argv[1]), sys.argv[2]) if MAIN else (None, "text")
opt = dict(zip(sys.argv[3::2], sys.argv[4::2])) if MAIN else {}

DIRS8 = {"up": "Toward the top edge of the image.", "up-right": "Diagonally toward the top-right corner.",
         "right": "Toward the right edge of the image.", "down-right": "Diagonally toward the bottom-right corner.",
         "down": "Toward the bottom edge of the image.", "down-left": "Diagonally toward the bottom-left corner.",
         "left": "Toward the left edge of the image.", "up-left": "Diagonally toward the top-left corner."}
GESTURES = {"relaxed": "Open and relaxed, fingers loosely together, hanging at rest.",
            "open": "Open with the fingers spread wide, as in a wave.",
            "fist": "Closed into a round fist, no finger or thumb sticking out.",
            "point": "One finger stretched out straight, the others curled.",
            "thumbsup": "Closed fist with the thumb sticking straight out.",
            "grip": "Fingers curled loosely with the thumb pressed against the first finger, as when pinching something thin."}

Q = {
    "finger_dir": {"type": "choice",
                   "instructions": "In `hand`, which way does the hand point? Follow the hand from its wrist (the end that "
                                   "joins the arm or sleeve) out to its fingertips, or to the knuckles of a closed fist, "
                                   "and give that direction as it appears in the image.",
                   "criteria": DIRS8},
    "thumb_dir": {"type": "choice",
                  "instructions": "In `hand`, which way does the thumb stick out from the rest of the hand, as it appears "
                                  "in the image? Judge the direction from the middle of the hand to the thumb's tip.",
                  "criteria": DIRS8},
    "facing": {"type": "choice",
               "instructions": "Which side of the hand in `hand` faces the viewer?",
               "criteria": {"palm": "The palm side: the soft inside of the hand or paw pad faces the viewer, and curled "
                                    "fingers curl toward the viewer so their inner sides show.",
                            "back": "The back of the hand: the outside of the hand faces the viewer, with the knuckles "
                                    "on top, and curled fingers curl away from the viewer."}},
    "gesture": {"type": "choice", "instructions": "What pose is the hand in `hand` making?", "criteria": GESTURES},
    "painted": {"type": "choice",
                "instructions": "Is the hand in `hand` drawn as a left hand or a right hand? Think of your own hands: "
                                "which of them could you hold up so it looks exactly like this, showing the same side "
                                "and with the thumb on the same side?",
                "criteria": {"left": "A left hand.", "right": "A right hand."}},
}
HOLD_Q = {
    "thumb_up": {"type": "noul", "instructions": "In `hand`, does the thumb point upward in the image?",
                 "criteria": {"true": "The thumb points up, within about 45 degrees of straight up.",
                              "false": "The thumb points sideways or down, or no thumb is visible."}},
    "mirrored": {"type": "noul",
                 "instructions": "`hand` shows the character's hand described in `which_hand`, at the end of its sleeve. "
                                 "Is the hand mirrored, i.e. drawn as the wrong hand: with the side of the hand that "
                                 "shows, its thumb is on the side a real hand on that arm could not have it?",
                 "criteria": {"true": "Mirrored: the thumb is on the anatomically impossible side for that hand.",
                              "false": "Anatomically possible: a real hand on that arm could look like this."}},
}


def exemplars(rows, char, base):
    """Two confirmed palm and two back pieces from other characters, upright and unmirrored."""
    pool = [r for r in rows if r["set"] == "pieces" and r["char"] != char and r["rot"] == 0 and not r["mirror"]
            and r.get("status") in ("confirmed", "fixed")]
    rnd = random.Random(char)
    out = {}
    for f in ("palm", "back"):
        cand = [r for r in pool if r["facing"] == f]; rnd.shuffle(cand)
        out[f] = [base / f"{r['id']}.png" for r in cand[:2]]
    left = [r for r in pool if r["painted"] == "l"]; right = [r for r in pool if r["painted"] == "r"]
    rnd.shuffle(left); rnd.shuffle(right)
    out["l"], out["r"] = [base / f"{r['id']}.png" for r in left[:2]], [base / f"{r['id']}.png" for r in right[:2]]
    return out


def build(r, rows):
    imgs = {"{hand}": SET / f"{r['id']}.png"}
    if r["set"] == "pieces":
        state = {"task": "A painted hand (or paw) of a cartoon character, cut out as one piece of a 2D animation rig and "
                         "shown on a flat grey background. The piece may be turned to any angle or mirrored.",
                 "hand": "{hand}"}
        qs = dict(Q)
    else:
        side = "left" if r["side"] == "l" else "right"
        state = {"task": "A close-up crop of one rendered frame of a 2D cartoon character rig, centred on one hand.",
                 "which_hand": f"The character's {side} hand (on the {'right' if side == 'left' else 'left'} side of the "
                               f"picture, as the character faces the viewer).",
                 "hand": "{hand}"}
        qs = {**Q, **HOLD_Q}
    if COND == "exemplar":
        ex = exemplars(rows, r["char"], EX_DIR)
        for k in ("palm", "back", "l", "r"):
            for i, p in enumerate(ex[k]):
                imgs[f"{{ex_{k}{i}}}"] = p
        qs = dict(qs)
        qs["facing"] = {**Q["facing"], "criteria": {
            "palm": {"description": Q["facing"]["criteria"]["palm"], "examples": [f"{{ex_palm{i}}}" for i in range(len(ex["palm"]))]},
            "back": {"description": Q["facing"]["criteria"]["back"], "examples": [f"{{ex_back{i}}}" for i in range(len(ex["back"]))]}}}
        qs["painted"] = {**Q["painted"], "criteria": {
            "left": {"description": "A left hand.", "examples": [f"{{ex_l{i}}}" for i in range(len(ex["l"]))]},
            "right": {"description": "A right hand.", "examples": [f"{{ex_r{i}}}" for i in range(len(ex["r"]))]}}}
    return state, qs, imgs


if MAIN:
    rows = [json.loads(l) for l in open(SET / "labels.jsonl")]
    EX_DIR = Path(opt.get("--exemplars-from", SET))     # render crops take their exemplars from the pieces set
    ref_rows = [json.loads(l) for l in open(EX_DIR / "labels.jsonl")]
    todo = rows[: int(opt.get("--limit", 10 ** 9))]
    jobs = []
    for r in todo:
        st, qs, im = build(r, ref_rows)
        jobs.append((r["id"], st, qs, im, {"set": r["set"], "char": r["char"]}))
    jev.run_many(jobs, SET / f"results_{COND}.jsonl", int(opt.get("--workers", 4)))
