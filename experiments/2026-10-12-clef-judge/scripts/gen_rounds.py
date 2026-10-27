# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Real rounds: render three generations of each rig (g1, g2 rejected builds; g3 approved) in the same poses.
Writes rounds/<char>_<gen>_<pose>.png (character crop, long side <= 768) and rounds/labels.jsonl.
Rejected rows carry pair=<char>_<pose>, shared with the approved frame of that pose."""
import json, sys
from pathlib import Path
from PIL import Image

REPO = Path("/work/comfy")
sys.path.insert(0, str(REPO / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402

H = Path(__file__).parent
OUT = H / "rounds"; OUT.mkdir(exist_ok=True)
POSES = [(None, 0.0)] + [(a, t) for a in ("idle", "wave", "cheer_jump", "point", "thumbs_up", "hold_card") for t in (0.6, 1.2, 1.8)]
rows = []
for char in ("fox", "moose"):
    rigs = {g: q.Rig(H / "gens" / f"{char}_{g}" / f"{char}.json") for g in ("g1", "g2", "g3")}
    for anim, t in POSES:
        pose = f"{anim or 'setup'}_{t:.1f}"
        for g, rig in rigs.items():
            if anim and anim not in rig.data.get("animations", {}):
                continue
            if anim and anim not in rigs["g3"].data["animations"]:
                continue
            fr, *_ = q.render(rig, q.Canvas(rig, 800), anim, t)
            bg = Image.new("RGBA", fr.size, (214, 214, 214, 255))
            alpha_src, *_ = q.render(rig, q.Canvas(rig, 800), anim, t, bg=(0, 0, 0, 0))
            bb = alpha_src.getbbox(); m = 30
            im = fr.convert("RGB").crop((max(0, bb[0] - m), max(0, bb[1] - m), min(fr.width, bb[2] + m), min(fr.height, bb[3] + m)))
            im.thumbnail((768, 768))
            if min(im.size) < 256:                         # TypeSafe minimum side
                k = 256 / min(im.size); im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
            rid = f"{char}_{g}_{pose}"
            im.save(OUT / f"{rid}.png")
            rows.append(dict(id=rid, char=char, gen=g, anim=anim or "setup", t=t, pose=pose, defect=(g != "g3"),
                             kind="old_rig" if g != "g3" else "none", pair=f"{char}_{pose}"))
        print(char, pose, flush=True)
with open(OUT / "labels.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
print(len(rows), "frames,", sum(r["defect"] for r in rows), "from rejected builds")
