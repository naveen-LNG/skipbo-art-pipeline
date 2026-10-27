#!/usr/bin/env python3
"""Throttled Clef judge over the rig-defect sets. Stdlib only.

  python3 run.py <set dir> <condition> [--limit N] [--model clef-flash] [--sample synthetic120]

Conditions:
  solo  one image (the frame); fan-out of 6 typed questions in one request.
  ref   two images: [approved master, frame] (setup frames only).
Safety: strictly one request at a time; waits while macOS memory pressure is elevated; 180 s timeout per call;
unloads the model (keep_alive 0) at the end. Results append to <set dir>/results_<condition>_<model>.jsonl (resumable).
"""
import base64, json, random, subprocess, sys, time, urllib.request
from pathlib import Path

args = sys.argv[1:]
SET, COND = Path(args[0]), args[1]
opt = dict(zip(args[2::2], args[3::2]))
MODEL = opt.get("--model", "clef-flash")
LIMIT = int(opt.get("--limit", 10**9))
BACKEND = opt.get("--backend", "ollama")            # ollama | cloudflare
URL, HEADERS = "http://localhost:11434/v1/systemone", {"Content-Type": "application/json"}
if BACKEND == "cloudflare":                          # creds read from a 0600 file, never printed
    env = dict(l.strip().split("=", 1) for l in open(Path.home() / ".config/clef/cloudflare.env") if "=" in l)
    URL = (f"https://api.cloudflare.com/client/v4/accounts/{env['CLOUDFLARE_ACCOUNT_ID']}"
           f"/ai/run/@cf/cloudflare/{MODEL}")
    HEADERS = dict(HEADERS, Authorization=f"Bearer {env['CLOUDFLARE_AUTH_TOKEN']}")

STATE = {
    "task": "Quality check of a 2D cutout character rig. The character was cut into separately drawn parts (head, torso, "
            "hips/trousers, sleeves, hands, feet, tail or antlers, scarf) that are re-assembled by a skeleton and "
            "composited on a flat grey background.",
    "what_correct_looks_like": "The frame reads like one seamless illustration: each hand sits in its sleeve cuff, "
            "each sleeve emerges from the armhole and tucks under the torso or vest at the shoulder, trousers meet the "
            "hips with no gap and feet sit under the trouser legs, the head sits on the neck, tail and antlers are "
            "behind the body, and hands are not mirrored.",
    "images": "The attached image is one rendered frame of the rig.",
}
STATE_REF = dict(STATE, images="Image 1 is the approved original illustration (the reference). Image 2 is the rig's "
                               "rendered rest pose, which should match the reference.")

Q = {
    "defect": {"type": "noul",
               "instructions": "Does the rendered frame show a rigging or stitching defect: a part displaced from where it "
                               "should attach, a visible gap or seam at a joint, a part drawn in front of something it "
                               "should be behind, or a mirrored part?",
               "criteria": {"true": "At least one such defect is visible.",
                            "false": "The frame looks like a clean, seamless illustration."}},
    "kind": {"type": "choice", "instructions": "What kind of defect, if any, is most visible in the rendered frame?",
             "criteria": {"none": "No defect; the frame looks like a clean illustration.",
                          "offset": "A part is shifted from its joint: it floats, leaves a gap, overlaps too far, or is misaligned.",
                          "layer_order": "A part is drawn over something it should be behind, e.g. a sleeve covering the torso edge at the shoulder, a tail in front of the legs.",
                          "mirrored": "A part is flipped or backwards, e.g. a thumb on the wrong side."}},
    "part": {"type": "choice", "instructions": "Which part of the character is faulty, if any?",
             "criteria": {"none": "No faulty part.", "head": None, "torso": "Torso, vest or overalls bib.",
                          "hips": "Hips, trousers or belt.", "arm": "Sleeve or upper arm.", "hand": "Hand or glove.",
                          "foot": "Foot, boot or hoof.", "tail": None, "antler": "Antler or ear.", "scarf": "Scarf or bell."}},
    "side": {"type": "choice", "instructions": "On which side of the image is the faulty part, as seen by the viewer?",
             "criteria": {"none": "No faulty part.", "image-left": "Left half of the image.",
                          "image-right": "Right half of the image.", "center": "On the centre line (head, torso, hips)."}},
    "direction": {"type": "choice",
                  "instructions": "If a part is displaced, in which direction (as seen in the image) has it moved away "
                                  "from where it belongs? To fix it, it would move the opposite way.",
                  "criteria": {"none": "Nothing is displaced.", "up": None, "down": None, "left": None, "right": None}},
    "magnitude": {"type": "score", "instructions": "How far is the faulty part displaced from where it belongs?",
                  "criteria": ["Not displaced at all.", "Slightly: a few pixels, only visible on close inspection.",
                               "Noticeably: a clear gap, step or overlap at the joint.",
                               "Badly: the part is obviously detached or in the wrong place."]},
}


def pressure() -> int:
    return int(subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True,
                              text=True).stdout.strip() or 1)


def b64(p: Path) -> str:                             # Ollama: raw base64; Cloudflare: data URI
    raw = base64.b64encode(p.read_bytes()).decode()
    mime = "image/jpeg" if p.suffix == ".jpg" else "image/png"
    return f"data:{mime};base64,{raw}" if BACKEND == "cloudflare" else raw


def call(state, images, qs, keep="3m"):
    payload = {"model": MODEL, "state": state, "images": images, "questions": qs}
    if BACKEND == "ollama":
        payload["keep_alive"] = keep
    req = urllib.request.Request(URL, json.dumps(payload).encode(), HEADERS)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.load(r)
    return out.get("result", out), time.time() - t0


JOINT_Q = {
    "detached": {"type": "noul",
                 "instructions": "Look at the joint described in `focus`. Is the part displaced from its joint: a visible "
                                 "gap, a step, a doubled edge, an overlap, or a misalignment where it meets the neighbouring part?",
                 "criteria": {"true": "The part is displaced; the join does not look like one seamless drawing.",
                              "false": "The part joins its neighbour seamlessly, as in a single hand-drawn illustration."}},
    "direction": Q["direction"],
}
JREF_Q = {
    "detached": {"type": "noul",
                 "instructions": "Image 1 is the approved original illustration, cropped around the joint described in "
                                 "`focus`. Image 2 is the rig render, cropped at exactly the same place. Is the part in "
                                 "image 2 displaced from where image 1 has it: shifted, with a gap, a step, a doubled edge or "
                                 "an overlap at the joint? Ignore small differences in how the parts are drawn or shaded.",
                 "criteria": {"true": "The part in image 2 sits in a different place than in image 1.",
                              "false": "The part in image 2 sits where image 1 has it."}},
    "direction": {"type": "choice",
                  "instructions": "Compared with image 1, which way has the part in image 2 moved? To fix it, it would "
                                  "move the opposite way.",
                  "criteria": {"none": "It has not moved.", "up": None, "down": None, "left": None, "right": None}},
}
CREF_Q = {
    "detached": {"type": "noul",
                 "instructions": "Image 1 is the previous, approved render of the rig cropped around the joint described in "
                                 "`focus`. Image 2 is the new render, cropped at exactly the same place. Has the part moved "
                                 "between image 1 and image 2: shifted, opening a gap, a step or an overlap at the joint?",
                 "criteria": {"true": "The part in image 2 sits in a different place than in image 1.",
                              "false": "The part in image 2 sits where image 1 has it."}},
    "direction": {"type": "choice",
                  "instructions": "Compared with image 1, which way has the part in image 2 moved? To fix it, it would "
                                  "move the opposite way.",
                  "criteria": {"none": "It has not moved.", "up": None, "down": None, "left": None, "right": None}},
}
PAIR_Q = {
    "worse": {"type": "choice",
              "instructions": "Images 1 and 2 are two renders of the same rig pose. Which one shows a rigging or stitching "
                              "defect (a displaced part, a gap or seam at a joint, a part drawn in front of something it "
                              "should be behind, a stiff or broken-looking pose)?",
              "criteria": {"image_1": "Image 1 has the defect.", "image_2": "Image 2 has the defect."}},
}
labels = [json.loads(l) for l in open(SET / "labels.jsonl")]
all_labels = labels
if COND == "ref":
    labels = [r for r in labels if r.get("anim") == "setup"]
if COND == "pair":
    labels = [r for r in labels if r["defect"] and "pair" in r]
if COND == "cref":                                     # shifted joints, plus each clean joint against itself
    labels = [r for r in labels if r["defect"] or r["id"].split("__")[0].endswith("_clean")]
if opt.get("--sample") == "synthetic120":            # all clean + a stratified spread of defects
    rnd = random.Random(1)
    clean = [r for r in labels if not r["defect"]]
    rest = [r for r in labels if r["defect"]]
    strata = {}
    for r in rest:
        strata.setdefault((r["char"], r["kind"], r.get("mag", 0)), []).append(r)
    pick = []
    while len(pick) < 120 - len(clean) and any(strata.values()):
        for k in sorted(strata):
            if strata[k]:
                pick.append(strata[k].pop(rnd.randrange(len(strata[k]))))
    labels = clean + pick[: 120 - len(clean)]
    rnd.shuffle(labels)

out_path = SET / f"results_{COND}{'_swap' if '--swap' in opt else ''}_{BACKEND}_{MODEL.replace(':', '_')}.jsonl"
done = {json.loads(l)["id"] for l in open(out_path)} if out_path.exists() else set()
todo = [r for r in labels if r["id"] not in done][:LIMIT]
print(f"{len(todo)} to run ({len(done)} done) -> {out_path}", flush=True)
with open(out_path, "a") as f:
    for i, r in enumerate(todo):
        waited = 0
        while BACKEND == "ollama" and pressure() >= 2 and waited < 120:          # back off while macOS reports memory pressure
            time.sleep(5); waited += 5
        if pressure() >= 4:
            print("critical memory pressure; stopping", flush=True); break
        img = SET / f"{r['id']}.png" if (SET / f"{r['id']}.png").exists() else SET / f"{r['id']}.jpg"
        if COND == "cref":
            clean_id = f"{r['char']}_clean__{r['slot']}"
            state = dict(STATE, images="Two close-up crops of the same joint: image 1 from the previous approved render, "
                         "image 2 from the new render.",
                         focus=f"The {r['slot'].replace('_l', '').replace('_r', '')} joint: {r['joint']}.")
            images, QQ = [b64(SET / f"{clean_id}.jpg"), b64(SET / f"{r['id']}.jpg")], CREF_Q
        elif COND == "jref":
            state = dict(STATE, images="Two close-up crops of the same joint: image 1 from the approved original "
                         "illustration, image 2 from the rig render.",
                         focus=f"The {r['slot'].replace('_l', '').replace('_r', '')} joint: {r['joint']}.")
            images, QQ = [b64(SET / f"{r['id']}__ref.jpg"), b64(SET / f"{r['id']}.jpg")], JREF_Q
        elif COND == "joint":
            state = dict(STATE, images="The attached image is a close-up crop of one joint of a rendered frame.",
                         focus=f"The {r['slot'].replace('_l', '').replace('_r', '')} joint: {r['joint']}.")
            images, QQ = [b64(img)], JOINT_Q
        elif COND == "pair":
            other = next(o for o in all_labels if o.get("pair") == r["pair"] and not o["defect"])
            first_bad = (random.Random(r["id"]).random() < 0.5) != ("--swap" in opt)
            ims = [img, SET / f"{other['id']}.png"] if first_bad else [SET / f"{other['id']}.png", img]
            state = dict(STATE, images="Two images: image 1 and image 2, two renders of the same pose of the rig.")
            images, QQ = [b64(x) for x in ims], PAIR_Q
            r = dict(r, truth="image_1" if first_bad else "image_2")
        elif COND == "ref":
            state, images, QQ = STATE_REF, [b64(SET / f"{r['char']}__master.png"), b64(img)], Q
        else:
            state, images, QQ = STATE, [b64(img)], Q
        try:
            res, dt = call(state, images, QQ)
            errs = 0
        except Exception as e:                            # record and carry on; never retry in a tight loop
            body = e.read().decode()[:300] if hasattr(e, "read") else ""
            print(r["id"], "ERROR", e, body, flush=True)
            errs = locals().get("errs", 0) + 1
            if errs >= 3:
                print("3 errors in a row (quota or outage?); stopping. Re-run to resume.", flush=True); break
            time.sleep(10); continue
        rec = {"id": r["id"], "truth": r.get("truth"), "latency_s": round(dt, 2), "usage": res.get("usage"), "answers": res.get("answers"),
               "pressure_after": pressure()}
        f.write(json.dumps(rec) + "\n"); f.flush()
        a = res.get("answers", {})
        print(f"[{i+1}/{len(todo)}] {r['id'][:60]:60s} " + " ".join(
              f"{k}={v.get('noul', v.get('choice'))}" for k, v in a.items() if k in ("defect", "kind", "detached", "worse"))
              + f" {dt:.1f}s tok={res.get('usage',{}).get('input_tokens')}", flush=True)
# unload so the Mac gets its memory back
if BACKEND == "ollama":
    subprocess.run(["ollama", "stop", MODEL], capture_output=True)
try:
    urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/generate",
                           json.dumps({"model": MODEL, "keep_alive": 0}).encode()), timeout=30)
except Exception:
    pass
print("done; model unloaded", flush=True)
