# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Close-ups that follow a joint through the animations, beside the master's rest-pose crop: what a viewer sees
in motion (joint_crops.py only shows the setup pose).

  uv run motion_crops.py <char> <rig dir> <annotations.json> <out.png> [--joints wrist_l,waist,ankle_l] [--anims idle,wave]

Each row is one joint: the master crop (rest pose), then the rig at the setup pose and at 5 times through each
animation, the box centred on that joint's bone in that frame (so the crop moves with the arm)."""
import argparse, json, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import joint_crops as jc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("char"); ap.add_argument("rigdir", type=Path); ap.add_argument("ann", type=Path); ap.add_argument("out")
ap.add_argument("--joints", default="wrist_l,wrist_r,waist,ankle_l,ankle_r")
ap.add_argument("--anims", default="idle,wave,cheer_jump,point,hold_card")
ap.add_argument("--per", type=int, default=4)
a = ap.parse_args()
import spine_qa as q  # noqa: E402  (path set by joint_crops)

rig = q.Rig(a.rigdir / f"{a.char}.json"); mf = json.load(open(a.rigdir / "report.json"))["master_frame"]
ann = json.load(open(a.ann)); master = Image.open(a.ann.parent / ann["master"]["image"]).convert("RGB"); W, H = master.size
P = {k: (v[0] * W, v[1] * H) for k, v in ann["master"]["points"].items()}
body_h = (ann["master"]["points"]["ground"][1] - 0.08) * H
BONE = {"wrist_l": "hand_l", "wrist_r": "hand_r", "waist": "torso", "ankle_l": "boot_l", "ankle_r": "boot_r",
        "elbow_l": "forearm_l", "elbow_r": "forearm_r", "shoulder_l": "upperarm_l", "shoulder_r": "upperarm_r", "neck": "head_base"}
SHARE = {"wrist": 0.14, "waist": 0.22, "ankle": 0.14, "elbow": 0.16, "shoulder": 0.2, "neck": 0.22}
joints = a.joints.split(","); anims = [x for x in a.anims.split(",") if x in rig.data["animations"]]
frames = [(None, 0.0)] + [(an, round(rig.duration(an) * (i + 0.5) / a.per, 3)) for an in anims for i in range(a.per)]
T = 150
sheet = Image.new("RGB", (T * (len(frames) + 1), (T + 14) * len(joints) + 14), "white")
d = ImageDraw.Draw(sheet)
for c, (an, t) in enumerate(frames):
    d.text(((c + 1) * T + 2, 1), f"{an or 'setup'} {t:.2f}"[:24], fill="black")
d.text((2, 1), "master", fill="black")
rendered = {}
for c, (an, t) in enumerate(frames):
    fr, al, cv, world = jc.render_master_frame(rig, mf, (W, H), an, t)
    for r, j in enumerate(joints):
        h = SHARE[j.split("_")[0]] * body_h / 2
        b = BONE[j]
        if b in world:
            # the joint point of this frame: the master point carried by its bone (setup -> this frame)
            w0, _ = rig.pose(None, 0)
            M0 = np.array([[w0[b][0], w0[b][1], w0[b][4]], [w0[b][2], w0[b][3], w0[b][5]], [0, 0, 1]])
            M1 = np.array([[world[b][0], world[b][1], world[b][4]], [world[b][2], world[b][3], world[b][5]], [0, 0, 1]])
            k = mf["units_per_px"]
            pu = np.array([(P[j][0] - mf["mid_x"]) * k, (mf["ground_y"] - P[j][1]) * k, 1.0])
            pw = M1 @ np.linalg.inv(M0) @ pu
            cx, cy = pw[0] / k + mf["mid_x"], mf["ground_y"] - pw[1] / k
        else:
            cx, cy = P[j]
        crop = fr.crop((int(cx - h), int(cy - h), int(cx + h), int(cy + h))).resize((T, T))
        sheet.paste(crop, ((c + 1) * T, 14 + r * (T + 14)))
        if c == 0:
            mc = master.crop((int(P[j][0] - h), int(P[j][1] - h), int(P[j][0] + h), int(P[j][1] + h))).resize((T, T))
            sheet.paste(mc, (0, 14 + r * (T + 14)))
            d.text((2, 14 + r * (T + 14) + T), j, fill="black")
sheet.save(a.out); print(a.out)
