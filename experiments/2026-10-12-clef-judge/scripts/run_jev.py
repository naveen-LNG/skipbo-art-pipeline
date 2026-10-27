#!/usr/bin/env python3
"""Jev 1.14 (TypeSafe) runner for the rig-judge experiment, with Box questions. Stdlib only.

  python3 run_jev.py <set dir> <condition> [--limit N] [--model jev-1.14.0] [--sample synthetic120] [--swap 1]

Conditions mirror run.py (solo, ref, pair, joint, jref) with the same question wording, adapted to TypeSafe's image
contract: images go in `assets` under random reference strings that appear in `state`, questions refer to them by
backticked path. New Box questions:
  joint  box_render  -> the part in `render`
  jref   box_master, box_render -> code subtracts them for the offset and fix direction
  solo/ref box_defect -> the region of `frame` that looks displaced
One request at a time; stops after 3 consecutive errors; resumable.
Key: TYPESAFE_API_KEY from ~/.config/typesafe/typesafe.env (mode 600) or the environment; never printed.
"""
import base64, json, os, random, sys, time, urllib.error, urllib.request, uuid
from pathlib import Path

args = sys.argv[1:]
SET, COND = Path(args[0]), args[1]
opt = dict(zip(args[2::2], args[3::2]))
MODEL = opt.get("--model", "jev-1.14.0")
LIMIT = int(opt.get("--limit", 10**9))
URL = "https://api.typesafe.ai/v1/systemone"
envf = Path.home() / ".config/typesafe/typesafe.env"
KEY = (dict(l.strip().split("=", 1) for l in open(envf) if "=" in l).get("TYPESAFE_API_KEY") if envf.exists() else None) \
    or os.environ.get("TYPESAFE_API_KEY")
if not KEY:
    raise SystemExit("No TypeSafe key: put TYPESAFE_API_KEY=... in ~/.config/typesafe/typesafe.env")
HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}", "TypeSafe-Danger-Zone-Images": "true"}

TASK = ("Quality check of a 2D cutout character rig. The character was cut into separately drawn parts (head, torso, "
        "hips/trousers, sleeves, hands, feet, tail or antlers, scarf) that are re-assembled by a skeleton and composited on "
        "a flat grey background.")
CORRECT = ("The frame reads like one seamless illustration: each hand sits in its sleeve cuff, each sleeve emerges from "
           "the armhole and tucks under the torso or vest at the shoulder, trousers meet the hips with no gap and feet sit "
           "under the trouser legs, the head sits on the neck, tail and antlers are behind the body, and hands are not mirrored.")

FRAME_Q = {   # identical wording to run.py's Q, with the image named by path
    "defect": {"type": "noul",
               "instructions": "Does the rendered frame in `frame` show a rigging or stitching defect: a part displaced from "
                               "where it should attach, a visible gap or seam at a joint, a part drawn in front of something "
                               "it should be behind, or a mirrored part?",
               "criteria": {"true": "At least one such defect is visible.",
                            "false": "The frame looks like a clean, seamless illustration."}},
    "kind": {"type": "choice", "instructions": "What kind of defect, if any, is most visible in `frame`?",
             "criteria": {"none": "No defect; the frame looks like a clean illustration.",
                          "offset": "A part is shifted from its joint: it floats, leaves a gap, overlaps too far, or is misaligned.",
                          "layer_order": "A part is drawn over something it should be behind, e.g. a sleeve covering the torso edge at the shoulder, a tail in front of the legs.",
                          "mirrored": "A part is flipped or backwards, e.g. a thumb on the wrong side."}},
    "part": {"type": "choice", "instructions": "Which part of the character in `frame` is faulty, if any?",
             "criteria": {"none": "No faulty part.", "head": None, "torso": "Torso, vest or overalls bib.",
                          "hips": "Hips, trousers or belt.", "arm": "Sleeve or upper arm.", "hand": "Hand or glove.",
                          "foot": "Foot, boot or hoof.", "tail": None, "antler": "Antler or ear.", "scarf": "Scarf or bell."}},
    "side": {"type": "choice", "instructions": "On which side of `frame` is the faulty part, as seen by the viewer?",
             "criteria": {"none": "No faulty part.", "image-left": "Left half of the image.",
                          "image-right": "Right half of the image.", "center": "On the centre line (head, torso, hips)."}},
    "direction": {"type": "choice",
                  "instructions": "If a part in `frame` is displaced, in which direction (as seen in the image) has it moved "
                                  "away from where it belongs? To fix it, it would move the opposite way.",
                  "criteria": {"none": "Nothing is displaced.", "up": None, "down": None, "left": None, "right": None}},
    "magnitude": {"type": "score", "instructions": "How far is the faulty part in `frame` displaced from where it belongs?",
                  "criteria": ["Not displaced at all.", "Slightly: a few pixels, only visible on close inspection.",
                               "Noticeably: a clear gap, step or overlap at the joint.",
                               "Badly: the part is obviously detached or in the wrong place."]},
    "box_defect": {"type": "box",
                   "instructions": "the part of the character in `frame` that looks displaced, detached, mirrored or drawn in "
                                   "the wrong layer (if nothing looks wrong, the joint that looks least seamless)"},
}
DIR = {"type": "choice", "criteria": {"none": "It has not moved.", "up": None, "down": None, "left": None, "right": None}}
TARGET = {("fox", "head"): "the fox's head (face, cheeks and ears)", ("moose", "head"): "the moose's head (face and beard, not the cap)",
          "hand": "the hand that comes out of the sleeve cuff", ("fox", "hips"): "the blue trouser legs below the waist",
          ("moose", "hips"): "the brown trousers with the belt", "boot": "the orange boot", "tail": "the fox's tail",
          "hoof": "the brown lower trouser leg ending in the dark hoof", "antler": "the antler"}


def base(s): return s[:-2] if s[-2:] in ("_l", "_r") else s


def target(r): return TARGET.get((r["char"], base(r["slot"]))) or TARGET[base(r["slot"])]


class Req:
    def __init__(self): self.state, self.assets = {}, {}

    def img(self, path):
        ref = f"img-{uuid.uuid4()}"
        fmt = "png" if path.suffix == ".png" else "jpg"
        self.assets[ref] = {"type": "image", "format": fmt, "data_base64": base64.b64encode(path.read_bytes()).decode()}
        return ref


def build(r):
    q = Req(); s = {"task": TASK, "what_correct_looks_like": CORRECT}
    img = SET / f"{r['id']}.png" if (SET / f"{r['id']}.png").exists() else SET / f"{r['id']}.jpg"
    if COND in ("solo", "ref"):
        if COND == "ref":
            s["master"] = q.img(SET / f"{r['char']}__master.png")
            s["images"] = "`master` is the approved original illustration. `frame` is the rig's rendered rest pose, which should match it."
        else:
            s["images"] = "`frame` is one rendered frame of the rig."
        s["frame"] = q.img(img)
        return s, q.assets, FRAME_Q, r
    joint = f"The {base(r['slot'])} joint: {r['joint']}." if "slot" in r else ""
    if COND == "joint":
        s.update(images="`render` is a close-up crop of one joint of a rendered frame.", focus=joint, render=q.img(img))
        return s, q.assets, {
            "detached": {"type": "noul",
                         "instructions": "Look at the joint described in `focus`, in `render`. Is the part displaced from its "
                                         "joint: a visible gap, a step, a doubled edge, an overlap, or a misalignment where it "
                                         "meets the neighbouring part?",
                         "criteria": {"true": "The part is displaced; the join does not look like one seamless drawing.",
                                      "false": "The part joins its neighbour seamlessly, as in a single hand-drawn illustration."}},
            "direction": dict(DIR, instructions="If a part in `render` is displaced, in which direction (as seen in the image) "
                                                "has it moved away from where it belongs? To fix it, it would move the opposite way."),
            "box_render": {"type": "box", "instructions": f"{target(r)} in `render`"},
        }, r
    if COND == "jref":
        s.update(images="Two close-up crops of the same joint: `master` from the approved original illustration, `render` "
                        "from the rig render, cropped at exactly the same place.", focus=joint,
                 master=q.img(SET / f"{r['id']}__ref.jpg"), render=q.img(img))
        return s, q.assets, {
            "detached": {"type": "noul",
                         "instructions": "Is the part described in `focus` displaced in `render` compared with where `master` "
                                         "has it: shifted, with a gap, a step, a doubled edge or an overlap at the joint? Ignore "
                                         "small differences in how the parts are drawn or shaded.",
                         "criteria": {"true": "The part in `render` sits in a different place than in `master`.",
                                      "false": "The part in `render` sits where `master` has it."}},
            "direction": dict(DIR, instructions="Compared with `master`, which way has the part in `render` moved? To fix it, "
                                                "it would move the opposite way."),
            "box_master": {"type": "box", "instructions": f"{target(r)} in `master`"},
            "box_render": {"type": "box", "instructions": f"{target(r)} in `render`"},
        }, r
    if COND == "zoom":
        s.update(images="`render` is a close-up of one part of a rendered character rig.", render=q.img(img))
        return s, q.assets, {"box_render": {"type": "box", "instructions": f"{target(r)} in `render`"}}, r
    if COND == "cref":
        clean_id = f"{r['char']}_clean__{r['slot']}"
        s.update(images="Two close-up crops of the same joint: `before` from the previous approved render, `after` from the "
                        "new render, cropped at exactly the same place.", focus=joint,
                 before=q.img(SET / f"{clean_id}.jpg"), after=q.img(img))
        return s, q.assets, {
            "detached": {"type": "noul",
                         "instructions": "Has the part described in `focus` moved between `before` and `after`: shifted, "
                                         "opening a gap, a step or an overlap at the joint?",
                         "criteria": {"true": "The part in `after` sits in a different place than in `before`.",
                                      "false": "The part in `after` sits where `before` has it."}},
            "direction": dict(DIR, instructions="Compared with `before`, which way has the part in `after` moved? To fix it, "
                                                "it would move the opposite way."),
            "box_before": {"type": "box", "instructions": f"{target(r)} in `before`"},
            "box_after": {"type": "box", "instructions": f"{target(r)} in `after`"},
        }, r
    if COND == "pair":
        other = next(o for o in all_labels if o.get("pair") == r["pair"] and not o["defect"])
        first_bad = (random.Random(r["id"]).random() < 0.5) != ("--swap" in opt)
        a, b = (img, SET / f"{other['id']}.png") if first_bad else (SET / f"{other['id']}.png", img)
        s.update(images="`image_1` and `image_2` are two renders of the same pose of the rig.", image_1=q.img(a), image_2=q.img(b))
        return s, q.assets, {"worse": {"type": "choice",
            "instructions": "`image_1` and `image_2` are two renders of the same rig pose. Which one shows a rigging or "
                            "stitching defect (a displaced part, a gap or seam at a joint, a part drawn in front of something "
                            "it should be behind, a stiff or broken-looking pose)?",
            "criteria": {"image_1": "`image_1` has the defect.", "image_2": "`image_2` has the defect."}}}, \
            dict(r, truth="image_1" if first_bad else "image_2")
    raise SystemExit(f"unknown condition {COND}")


labels = [json.loads(l) for l in open(SET / ("labels_gt.jsonl" if (SET / "labels_gt.jsonl").exists() else "labels.jsonl"))]
all_labels = labels
if COND == "ref": labels = [r for r in labels if r.get("anim") == "setup"]
if COND == "pair": labels = [r for r in labels if r["defect"] and "pair" in r]
if COND == "cref": labels = [r for r in labels if r["defect"] or r["id"].split("__")[0].endswith("_clean")]
if opt.get("--sample") == "synthetic120":              # same sampler and seed as run.py -> same items
    rnd = random.Random(1)
    clean = [r for r in labels if not r["defect"]]; strata = {}
    for r in [r for r in labels if r["defect"]]:
        strata.setdefault((r["char"], r["kind"], r.get("mag", 0)), []).append(r)
    pick = []
    while len(pick) < 120 - len(clean) and any(strata.values()):
        for k in sorted(strata):
            if strata[k]: pick.append(strata[k].pop(rnd.randrange(len(strata[k]))))
    labels = clean + pick[: 120 - len(clean)]; rnd.shuffle(labels)

out_path = SET / f"results_{COND}{'_swap' if '--swap' in opt else ''}_typesafe_{MODEL}.jsonl"
done = {json.loads(l)["id"] for l in open(out_path)} if out_path.exists() else set()
todo = [r for r in labels if r["id"] not in done][:LIMIT]
print(f"{len(todo)} to run ({len(done)} done) -> {out_path}", flush=True)
errs = 0
with open(out_path, "a") as f:
    for i, r in enumerate(todo):
        state, assets, qs, r = build(r)
        body = json.dumps({"model": MODEL, "state": state, "assets": assets, "questions": qs}).encode()
        t0 = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(URL, body, HEADERS), timeout=180) as resp:
                res = json.load(resp)
            errs = 0
        except Exception as e:
            detail = e.read().decode()[:400] if hasattr(e, "read") else ""
            print(r["id"], "ERROR", e, detail, flush=True); errs += 1
            if errs >= 3: print("3 errors in a row; stopping. Re-run to resume.", flush=True); break
            time.sleep(10); continue
        dt = time.time() - t0
        f.write(json.dumps({"id": r["id"], "truth": r.get("truth"), "model": res.get("model"), "latency_s": round(dt, 2),
                            "usage": res.get("usage"), "answers": res.get("answers")}) + "\n"); f.flush()
        a = res.get("answers", {})
        brief = " ".join(f"{k}={v.get('noul', v.get('choice', ''))}" if v.get("type") != "box" else
                         f"{k}=[{v['box']['left']:.2f},{v['box']['top']:.2f},{v['box']['right']:.2f},{v['box']['bottom']:.2f}]c{v['confidence']:.2f}"
                         for k, v in a.items() if k in ("defect", "detached", "worse", "box_render", "box_after", "box_defect"))
        print(f"[{i+1}/{len(todo)}] {r['id'][:52]:52s} {brief} {dt:.1f}s tok={res.get('usage', {}).get('input_tokens')}", flush=True)
print("done", flush=True)
