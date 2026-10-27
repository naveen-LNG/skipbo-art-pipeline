#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""jev_facing.py - palm or back for hand pieces, from five things Jev can see, averaged over 16 turns.

  uv run scripts/jev_facing.py <char>/annotations.json [--sheet <split-run>]    every hand piece, against its facing
  uv run scripts/jev_facing.py --piece <name>=<piece.png> ...                   loose pieces

Asked "palm or back?" Jev is at chance (AUROC 0.61 on the fox and moose). Asked what it sees - finger pads, the
creases of curled fingers, the thumb across the front, knuckles, a smooth mitten back, which way the fingers curl -
and combined in code (palm_score), it reaches AUROC 0.89. Each piece is scored at 8 turns x mirrored (16 calls) and
the mean is read through a band set on the user-confirmed fox and moose pieces (12 of 13 confident calls right):

  score >= -0.05  palm        score <= -0.20  back        in between: ask (no call)

`rig_annotations.py check --jev` uses facing_doubt(): a confident call that disagrees with a hand's annotated facing
becomes a checkpoint question. It checks the label only: the beaver's back-facing cheer fist was labelled back,
and Jev agreed (-0.40), so it raised nothing; whether a pose shows the right side is a separate question. The upright piece also
gets Jev's finger and thumb direction and pose reading, printed to help place thumb_tip and fingertip.
Without a TypeSafe key it prints SKIP and exits 0. Cost: about $0.001 per piece; answers are cached.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

from PIL import Image

import jev_client
import jev_hands as jh

PALM, BACK = -0.05, -0.20
TURNS = [(m, rot) for m in (0, 1) for rot in range(0, 360, 45)]
STATE = {"task": "A painted hand (or paw) of a cartoon character, cut out as one piece of a 2D animation rig and "
                 "shown on a flat grey background. The piece may be turned to any angle or mirrored.",
         "hand": "{hand}"}
CUES = {   # cue -> (the side it argues for, the question)
    "pads": ("palm", "In `hand`, can you see the soft inner side of the hand: a palm pad, the pads of the fingers, "
                     "or the fingertips folded in toward the viewer?"),
    "creases": ("palm", "In `hand`, are the curled fingers seen from the inside, so the creases between the folded "
                        "fingers and their tips face the viewer, like looking into a loosely closed hand?"),
    "thumb_front": ("palm", "In `hand`, does the thumb lie across the front of the curled fingers or the palm, on the "
                            "side facing the viewer?"),
    "knuckles": ("back", "In `hand`, do you see the back of the hand: a smooth broad surface with the knuckles along "
                         "its edge, the fingers bending away from the viewer?"),
    "smooth_top": ("back", "In `hand`, is the biggest visible area of the hand a smooth, rounded surface with no finger "
                           "tips or palm pad on it, like the back of a mitten?"),
}
CUE_Q = {k: {"type": "noul", "instructions": txt, "criteria": {"true": "Yes, clearly visible.", "false": "No."}}
         for k, (_, txt) in CUES.items()}
CUE_Q["curl"] = {"type": "choice", "instructions": "In `hand`, which way do the bent fingers curl?",
                 "criteria": {"toward": "Toward the viewer: the fingertips come forward, out of the picture.",
                              "away": "Away from the viewer: the fingertips go behind the hand.",
                              "flat": "The fingers are not bent."}}


def palm_score(a: dict) -> float:
    """Mean of the palm cues minus mean of the back cues, plus half the curl's toward-minus-away: > 0 palm-ish."""
    pal = [a[k]["noul"] for k, (side, _) in CUES.items() if side == "palm"]
    bak = [a[k]["noul"] for k, (side, _) in CUES.items() if side == "back"]
    curl = a["curl"]["probabilities"]
    return sum(pal) / len(pal) - sum(bak) / len(bak) + 0.5 * (curl.get("toward", 0) - curl.get("away", 0))


def band(score: float) -> str:
    return "palm" if score >= PALM else "back" if score <= BACK else "ask"


def turned(im: Image.Image) -> dict:
    """{(mirror, rot): PNG bytes} of the 16 turns, each on flat grey."""
    out = {}
    for m, rot in TURNS:
        base = im.transpose(Image.FLIP_LEFT_RIGHT) if m else im
        out[(m, rot)] = jh.png(jh.on_grey(base.rotate(rot, expand=True, resample=Image.BICUBIC)))
    return out


def score_pieces(pieces: dict, cache=None) -> dict:
    """pieces {name: RGBA piece path} -> {name: {"score", "facing" (palm|back|ask), "n", and from the upright
    piece: "finger_dir", "thumb_dir", "thumb_deg", "reads_as"}}. A piece Jev answered no turn of is left out."""
    jobs = []
    for name, path in pieces.items():
        for (m, rot), data in turned(Image.open(path).convert("RGBA")).items():
            qs = {**CUE_Q, **jh.HAND_Q} if (m, rot) == (0, 0) else CUE_Q
            jobs.append((f"{name}__m{m}_r{rot:03d}", STATE, qs, {"{hand}": data}))
    ans = jev_client.run(jobs, cache=cache)
    out = {}
    for name in pieces:
        sc = [palm_score(a) for k, a in ans.items() if k.rsplit("__", 1)[0] == name]
        if not sc:
            continue
        s = st.mean(sc)
        r = {"score": round(s, 3), "facing": band(s), "n": len(sc)}
        up = ans.get(f"{name}__m0_r000")
        if up and "thumb_dir" in up:
            r.update(finger_dir=up["finger_dir"]["choice"], thumb_dir=up["thumb_dir"]["choice"],
                     thumb_deg=round(jh.circ_mean(up["thumb_dir"]["probabilities"])), reads_as=up["gesture"]["choice"])
        out[name] = r
    return out


def facing_doubt(annotated, result) -> str | None:
    """The question text when Jev's confident call disagrees with the annotated facing, else None. An "ask" call or
    a hand without a facing (already a doubt of its own) raises nothing."""
    if not result or result["facing"] == "ask" or annotated not in ("palm", "back") or result["facing"] == annotated:
        return None
    return (f"annotated {annotated}, but Jev reads the {result['facing']} from visible cues (score "
            f"{result['score']:+.2f}; palm >= {PALM}, back <= {BACK}); this hand shows its")


def annotation_hands(ann_path: Path, sheet=None) -> dict:
    """{piece key: (piece image path, annotated facing)} for every hand piece in use (in one split run with
    sheet)."""
    ann = json.loads(Path(ann_path).read_text(encoding="utf-8"))
    root = Path(ann_path).parent / "runs"
    out = {}
    for key, p in sorted(ann.get("pieces", {}).items()):
        run, _, nn = key.rpartition("/")
        if p.get("role") != "hand" or p.get("status") == "ignored" or (sheet and run != sheet):
            continue
        f = next(iter(sorted((root / run).glob(f"*_{nn}.png"))), None)
        if f:
            out[key] = (f, p.get("facing"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("annotations", nargs="?", type=Path)
    ap.add_argument("--sheet", help="only this split run's hands")
    ap.add_argument("--piece", action="append", default=[], help="<name>=<piece.png>, repeatable")
    ap.add_argument("--cache", type=Path, help="answer cache (default <char>/annotations/jev_cache.jsonl)")
    a = ap.parse_args(argv)
    if not a.annotations and not a.piece:
        ap.error("give an annotations file or --piece")
    if not jev_client.available():
        print(jev_client.SKIP)
        return 0
    hands = annotation_hands(a.annotations, a.sheet) if a.annotations else {}
    hands.update({n: (Path(p), None) for n, p in (s.split("=", 1) for s in a.piece)})
    cache = a.cache or ((a.annotations.parent / "annotations" / "jev_cache.jsonl") if a.annotations else None)
    res = score_pieces({k: v[0] for k, v in hands.items()}, cache=cache)
    for k, (_, annotated) in hands.items():
        r = res.get(k)
        if not r:
            print(f"{k:28s} no answer")
            continue
        d = facing_doubt(annotated, r)
        print(f"{k:28s} score={r['score']:+.3f} -> {r['facing']:4s} annotated={annotated or '-':4s} "
              f"thumb={r.get('thumb_dir', '-'):10s} fingers={r.get('finger_dir', '-'):10s} "
              f"reads={r.get('reads_as', '-'):9s}{'  DOUBT' if d else ''}")
    print(json.dumps({"facing": res, "jev": dict(jev_client.USAGE)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
