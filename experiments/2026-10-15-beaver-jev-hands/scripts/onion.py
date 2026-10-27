# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Rig setup pose over the master, pixel-aligned: per region a master crop, the rig crop, and an onion skin (the master
in red channel, the rig in cyan) so any offset or size difference shows as coloured fringes.
  uv run onion.py <char> <rig dir> <annotations.json> <out.png>  [region=x0,y0,x1,y1 ...] (fractions of the master)"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parents[3] / "plugin/skills/skipbo-art/scripts"))
sys.path.insert(0, str(Path(__file__).parent))
import joint_crops as jc  # noqa: E402
import spine_qa as q  # noqa: E402
char, rigdir, annp, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
REG = {"arm_l": (0.60, 0.36, 0.95, 0.68), "arm_r": (0.05, 0.36, 0.40, 0.68), "waist": (0.25, 0.52, 0.75, 0.70),
       "legs": (0.28, 0.68, 0.72, 0.90)}
for a in sys.argv[5:]:
    k, v = a.split("="); REG[k] = tuple(float(x) for x in v.split(","))
ann = json.load(open(annp)); m = Image.open(annp.parent / ann["master"]["image"]).convert("RGB"); W, H = m.size
rig = q.Rig(rigdir / f"{char}.json"); mf = json.load(open(rigdir / "report.json"))["master_frame"]
fr, *_ = jc.render_master_frame(rig, mf, (W, H))
T = 330; rows = []
for name, (x0, y0, x1, y1) in REG.items():
    box = (int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))
    a_, b_ = m.crop(box), fr.crop(box)
    ga, gb = np.asarray(a_.convert("L")), np.asarray(b_.convert("L"))
    onion = Image.fromarray(np.stack([ga, gb, gb], -1).astype(np.uint8))
    s = T / max(a_.size); sz = (int(a_.width * s), int(a_.height * s))
    rows.append((name, [a_.resize(sz), b_.resize(sz), onion.resize(sz)]))
Wd = 3 * T + 20; Ht = sum(r[1][0].height + 18 for r in rows)
sheet = Image.new("RGB", (Wd, Ht), "white"); d = ImageDraw.Draw(sheet); y = 0
for name, ims in rows:
    d.text((3, y + 2), f"{name}: master | rig | onion (master red, rig cyan: red fringe = master only, cyan = rig only)", fill="black")
    for i, im in enumerate(ims):
        sheet.paste(im, (i * (T + 10), y + 16))
    y += ims[0].height + 18
sheet.save(out); print(out)
