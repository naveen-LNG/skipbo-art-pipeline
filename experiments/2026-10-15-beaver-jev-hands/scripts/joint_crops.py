# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Rig render and master, pixel-aligned, cropped at every joint: what Jev and a reviewer compare.

  uv run joint_crops.py <char> <rig dir> <annotations.json> <out dir> [--sheet out.png]

The setup pose is rendered straight into the master's pixel frame (report.json master_frame: master px -> skeleton
units), so the same box cuts the same place out of both. One square per joint, centred on the master's annotated
point and sized by the body (shoulders, elbows, wrists, waist, hips/ankles, neck, tail root). Writes
<id>__render.png, <id>__master.png and labels.jsonl; --sheet writes a side-by-side contact sheet for people."""
import json, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402

SIDE = 448
JOINTS = {   # joint -> (master point(s) to centre on, crop size as a share of body height, what meets there)
    "shoulder_l": (["shoulder_l"], 0.20, "the sleeve meeting the torso at the character's left shoulder"),
    "shoulder_r": (["shoulder_r"], 0.20, "the sleeve meeting the torso at the character's right shoulder"),
    "elbow_l": (["elbow_l"], 0.16, "the upper sleeve meeting the lower sleeve at the left elbow"),
    "elbow_r": (["elbow_r"], 0.16, "the upper sleeve meeting the lower sleeve at the right elbow"),
    "wrist_l": (["wrist_l", "fingertip_l"], 0.16, "the left hand coming out of its sleeve cuff"),
    "wrist_r": (["wrist_r", "fingertip_r"], 0.16, "the right hand coming out of its sleeve cuff"),
    "neck": (["neck"], 0.22, "the head sitting on the neck and collar"),
    "waist": (["waist"], 0.22, "the top (sweater or bib) meeting the trousers at the waist"),
    "ankle_l": (["ankle_l"], 0.16, "the left boot meeting the trouser leg"),
    "ankle_r": (["ankle_r"], 0.16, "the right boot meeting the trouser leg"),
    "tail": (None, 0.30, "the tail attaching behind the hips"),
}


def master_canvas(rig, mf, W, H):
    cv = q.Canvas(rig, 400)
    k = mf["units_per_px"]
    cv.S, cv.ox, cv.oy, cv.W, cv.H = 1 / k, -mf["mid_x"] * k, mf["ground_y"] * k, W, H
    return cv


def render_master_frame(rig, mf, size, anim=None, t=0.0, bg=(214, 214, 214, 255)):
    cv = master_canvas(rig, mf, *size)
    fr, world, active, alphas = q.render(rig, cv, anim, t, bg=bg)
    return fr.convert("RGB"), alphas, cv, world


def crops(char, rigdir, ann_path, out, anim=None, t=0.0, tag="setup"):
    rig = q.Rig(rigdir / f"{char}.json")
    mf = json.load(open(rigdir / "report.json"))["master_frame"]
    ann = json.load(open(ann_path))
    master = Image.open(ann_path.parent / ann["master"]["image"]).convert("RGB")
    W, H = master.size
    fr, alphas, cv, world = render_master_frame(rig, mf, (W, H), anim, t)
    P = {k: (v[0] * W, v[1] * H) for k, v in ann["master"]["points"].items()}
    body_h = (ann["master"]["points"]["ground"][1] - 0.08) * H     # roughly head top to ground
    rows = []
    for j, (pts, share, what) in JOINTS.items():
        if pts is None:                                       # tail: centre between its root and the master's tail mass
            if "tail" not in alphas:
                continue
            ys, xs = np.nonzero(alphas["tail"])
            c = (xs.mean(), ys.mean())
        else:
            if any(p not in P for p in pts):
                continue
            c = tuple(np.mean([P[p] for p in pts], 0))
        h = share * body_h / 2
        box = (int(c[0] - h), int(c[1] - h), int(c[0] + h), int(c[1] + h))
        iid = f"{char}__{tag}__{j}"
        fr.crop(box).resize((SIDE, SIDE), Image.LANCZOS).save(out / f"{iid}__render.png")
        master.crop(box).resize((SIDE, SIDE), Image.LANCZOS).save(out / f"{iid}__master.png")
        rows.append({"id": iid, "char": char, "pose": tag, "joint": j, "what": what, "box": box})
    return rows, fr, master


def sheet(rows, out, path):
    T = 260
    im = Image.new("RGB", (T * 2 * 4 + 30, ((len(rows) + 3) // 4) * (T + 22)), "white")
    for i, r in enumerate(rows):
        x, y = (i % 4) * (2 * T + 8), (i // 4) * (T + 22)
        im.paste(Image.open(out / f"{r['id']}__master.png").resize((T, T)), (x, y + 18))
        im.paste(Image.open(out / f"{r['id']}__render.png").resize((T, T)), (x + T, y + 18))
        ImageDraw.Draw(im).text((x + 3, y + 3), f"{r['joint']}: master | rig", fill="black")
    im.save(path)


if __name__ == "__main__":
    char, rigdir, ann_path, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    out.mkdir(parents=True, exist_ok=True)
    rows, fr, master = crops(char, rigdir, ann_path, out)
    fr.save(out / f"{char}__setup_full.png")
    with open(out / "labels.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    if "--sheet" in sys.argv:
        sheet(rows, out, sys.argv[sys.argv.index("--sheet") + 1])
    print(len(rows), "joints ->", out)
