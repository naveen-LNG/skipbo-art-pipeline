# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Per-joint crops for the synthetic set. Joint boxes come from the CLEAN render's slot layers (what pipeline code
would know), so the same box is cropped from clean and defective images alike.
Writes <set>/joints/<image id>__<slot>.png (long side 448) and <set>/joints/labels.jsonl:
one row per (image, joint); positive iff that joint's slot was the shifted one (offset defects only)."""
import json, random, sys
from pathlib import Path
from PIL import Image

REPO = Path("/work/comfy")
sys.path.insert(0, str(REPO / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402

SET = Path(sys.argv[1]); OUT = SET / "joints"; OUT.mkdir(exist_ok=True)
EXP = REPO / "experiments/2026-10-11-rig-annotations"
JOINTS = {"fox": ["head", "hand_l", "hand_r", "hips", "boot_l", "boot_r", "tail"],
          "moose": ["head", "hand_l", "hand_r", "hips", "hoof_l", "hoof_r", "antler_l", "antler_r"]}
DESC = {"head": "the head where it sits on the neck and collar", "hand": "the hand where it enters the sleeve cuff",
        "hips": "the waist where the trousers meet the torso", "boot": "the boot where it meets the trouser leg",
        "hoof": "the hoof where it meets the trouser leg", "tail": "the tail where it attaches behind the hips",
        "antler": "the antler where it attaches to the head"}
labels = [json.loads(l) for l in open(SET / "labels.jsonl")]
# frames used by the evaluated sample, plus every clean frame
want = {r["id"] for r in map(json.loads, open(SET / "results_solo_cloudflare_clef-flash.jsonl"))} \
    if (SET / "results_solo_cloudflare_clef-flash.jsonl").exists() else set()
items = [r for r in labels if r["id"] in want and r["kind"] in ("offset", "none")]
rnd = random.Random(3)
out = []
for char in ("fox", "moose"):
    rig = q.Rig(EXP / char / "rig" / f"{char}.json"); cv = q.Canvas(rig, 800)
    frames = {(r["anim"], r["t"]) for r in items if r["char"] == char}
    for anim, t in sorted(frames):
        world, active = rig.pose(None if anim == "setup" else anim, t)
        boxes = {}
        for s in JOINTS[char]:
            if active.get(s):
                boxes[s] = cv.layer(rig, s, active[s], world).getbbox()
        for r in [r for r in items if r["char"] == char and (r["anim"], r["t"]) == (anim, t)]:
            cx0, cy0, cx1, cy1 = r["crop"]; sc = min(1.0, 768 / max(cx1 - cx0, cy1 - cy0))
            im = Image.open(SET / f"{r['id']}.png")
            # positives: the shifted joint; negatives: up to 2 other joints of the same image
            cand = [s for s in boxes if s == r.get("slot")] + rnd.sample([s for s in boxes if s != r.get("slot")], 2)
            for s in cand:
                x0, y0, x1, y1 = boxes[s]; w, h = x1 - x0, y1 - y0; m = max(w, h) * 0.45 + 12
                b = [int((x0 - m - cx0) * sc), int((y0 - m - cy0) * sc), int((x1 + m - cx0) * sc), int((y1 + m - cy0) * sc)]
                b = [max(0, b[0]), max(0, b[1]), min(im.width, b[2]), min(im.height, b[3])]
                c = im.crop(b); k = 448 / max(c.size); c = c.resize((max(1, int(c.width * k)), max(1, int(c.height * k))), Image.LANCZOS)
                jid = f"{r['id']}__{s}"; c.save(OUT / f"{jid}.png")
                kind = (s[:-2] if s[-2:] in ("_l", "_r") else s)
                out.append(dict(id=jid, image=r["id"], char=char, slot=s, joint=DESC[kind], defect=(s == r.get("slot")),
                                kind="offset" if s == r.get("slot") else "none",
                                direction=r["direction"] if s == r.get("slot") else "none",
                                mag=r.get("mag", 0) if s == r.get("slot") else 0))
with open(OUT / "labels.jsonl", "w") as f:
    for r in out: f.write(json.dumps(r) + "\n")
print(len(out), "joint crops,", sum(r["defect"] for r in out), "positive")
