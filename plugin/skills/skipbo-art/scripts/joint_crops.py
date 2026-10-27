#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""joint_crops.py - the rig's setup pose and the master, pixel-aligned and cropped at every joint.

  uv run scripts/joint_crops.py <char>/rig/<char>.json [--annotations <char>/annotations.json] [--out DIR]

The setup pose is rendered straight into the master's own pixel frame (rig/report.json `master_frame`: master px ->
skeleton units), so one box cuts the same place out of both pictures. One square per joint, centred on the master's
annotated point and sized by the body: shoulders, elbows, wrists, neck, waist, ankles and the tail root. Needs no Jev:
the contact sheet is the quickest way to see a sleeve stuck on, a neck gap or a boot off centre (the beaver review
found every one of its round-2 defects on it).

Writes <out>/<char>__<joint>__master.png and __render.png (448 px), <out>/labels.jsonl, and the contact sheet
<rig>/qa/joints.png (master | rig, side by side, per joint; --sheet moves it). --out defaults to <rig>/qa/joints.
Two more review sheets next to it (--no-review skips them):
  <rig>/qa/onion.png   arms, waist and legs: master | rig | onion (master in red, rig in cyan, so a part that is too
                       wide, too thin or a few px off shows as a coloured fringe; the beaver's wide trousers, thin
                       sleeves and outward boots were all plain here and invisible in the 0.88 silhouette IoU)
  <rig>/qa/motion.png  wrists, waist and ankles followed through idle, wave, cheer_jump and point (the crop moves with
                       the joint's bone), beside the master's rest crop: gaps and peeking parts that only show in motion
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import spine_qa as q

SIDE = 448            # crop side in px: Jev needs at least 320
BG = (214, 214, 214, 255)
# joint -> (master point(s) to centre on, crop side as a share of body height, what meets there: Jev's wording)
JOINTS = {
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


def kind(joint: str) -> str:
    """shoulder_l -> shoulder: the joint type approved rigs are compared by."""
    return joint.split("_")[0]


def default_annotations(rig_json: Path) -> Path:
    return Path(rig_json).parent.parent / "annotations.json"


def master_canvas(rig: q.Rig, mf: dict, w: int, h: int) -> q.Canvas:
    cv = q.Canvas(rig, 400)
    k = mf["units_per_px"]
    cv.S, cv.ox, cv.oy, cv.W, cv.H = 1 / k, -mf["mid_x"] * k, mf["ground_y"] * k, w, h
    return cv


class Aligned:
    """A rig and its master in one pixel frame: .master and .render (RGB, master size), .alphas (slot masks of the
    render), .points (master points in px), .body_h (px)."""

    def __init__(self, rig_json, ann_path=None, anim=None, t=0.0):
        rig_json = Path(rig_json)
        ann_path = Path(ann_path) if ann_path else default_annotations(rig_json)
        self.char = rig_json.stem
        self.rig = q.Rig(rig_json)
        rdir = rig_json.parent
        mf = json.loads((rdir / "report.json").read_text(encoding="utf-8"))["master_frame"]
        ann = json.loads(ann_path.read_text(encoding="utf-8"))
        self.master = Image.open(ann_path.parent / ann["master"]["image"]).convert("RGB")
        w, h = self.master.size
        fr, _, _, self.alphas = q.render(self.rig, master_canvas(self.rig, mf, w, h), anim, t, bg=BG)
        self.render = fr.convert("RGB")
        self.points = {k: (v[0] * w, v[1] * h) for k, v in ann["master"]["points"].items()}
        res = rdir / "annotations.resolved.json"
        bh = json.loads(res.read_text(encoding="utf-8")).get("body_height_units") if res.is_file() else None
        self.body_h = bh / mf["units_per_px"] if bh else (ann["master"]["points"]["ground"][1] - 0.08) * h

    def boxes(self) -> dict:
        """{joint: (box, what)}; a joint whose master points (or, for the tail, whose tail slot) are missing is left
        out."""
        out = {}
        for j, (pts, share, what) in JOINTS.items():
            if pts is None:              # the tail: centred on its rendered mass
                if "tail" not in self.alphas or not self.alphas["tail"].any():
                    continue
                ys, xs = np.nonzero(self.alphas["tail"])
                c = (xs.mean(), ys.mean())
            else:
                if any(p not in self.points for p in pts):
                    continue
                c = tuple(np.mean([self.points[p] for p in pts], 0))
            r = share * self.body_h / 2
            out[j] = ((int(c[0] - r), int(c[1] - r), int(c[0] + r), int(c[1] + r)), what)
        return out


def cut(img: Image.Image, box) -> Image.Image:
    return img.crop(box).resize((SIDE, SIDE), Image.LANCZOS)


def crops(al: Aligned, out: Path, tag: str = None, boxes: dict = None) -> list:
    """Write <tag>__<joint>__render.png and __master.png per joint (boxes: another build's, to compare the same
    place). Returns the label rows."""
    tag = tag or al.char
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for j, (box, what) in (boxes or al.boxes()).items():
        iid = f"{tag}__{j}"
        cut(al.render, box).save(out / f"{iid}__render.png")
        cut(al.master, box).save(out / f"{iid}__master.png")
        rows.append({"id": iid, "char": al.char, "joint": j, "what": what, "box": list(box),
                     "render": str(out / f"{iid}__render.png"), "master": str(out / f"{iid}__master.png")})
    return rows


def sheet(rows: list, path: Path, notes: dict = None) -> Path:
    """Contact sheet: per joint, master | rig, four joints a row; notes[joint] is added to its label."""
    t, cols, lab = 260, 4, 20
    nrow = max(1, -(-len(rows) // cols))
    im = Image.new("RGB", (cols * (2 * t + 10), nrow * (t + lab + 6)), "white")
    d = ImageDraw.Draw(im)
    for i, r in enumerate(rows):
        x, y = (i % cols) * (2 * t + 10), (i // cols) * (t + lab + 6)
        im.paste(Image.open(r["master"]).resize((t, t)), (x, y + lab))
        im.paste(Image.open(r["render"]).resize((t, t)), (x + t, y + lab))
        label = f"{r['joint']}: master | rig" + (f"  {notes[r['joint']]}" if notes and r["joint"] in notes else "")
        d.text((x + 3, y + 4), label, fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def onion_sheet(al: Aligned, path: Path) -> Path:
    """Arms, waist and legs regions (from the master's points): master | rig | onion, one row each."""
    P, w, h = al.points, *al.master.size
    def span(names, pad):
        xs = [P[n][0] for n in names if n in P]; ys = [P[n][1] for n in names if n in P]
        return (int(min(xs) - pad), int(min(ys) - pad), int(max(xs) + pad), int(max(ys) + pad)) if xs else None
    pad = 0.06 * al.body_h
    regions = {"arm_l": span(["shoulder_l", "elbow_l", "wrist_l", "fingertip_l"], pad),
               "arm_r": span(["shoulder_r", "elbow_r", "wrist_r", "fingertip_r"], pad),
               "waist": span(["waist", "hip_l", "hip_r", "shoulder_l", "shoulder_r"], 0.02 * al.body_h),
               "legs": span(["hip_l", "hip_r", "ankle_l", "ankle_r", "ground"], pad)}
    t, rows = 330, []
    for name, box in regions.items():
        if box is None:
            continue
        box = (max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3]))
        a_, b_ = al.master.crop(box), al.render.crop(box)
        ga, gb = np.asarray(a_.convert("L")), np.asarray(b_.convert("L"))
        onion = Image.fromarray(np.stack([ga, gb, gb], -1).astype(np.uint8))
        k = t / max(a_.size)
        rows.append((name, [im.resize((max(1, int(a_.width * k)), max(1, int(a_.height * k)))) for im in (a_, b_, onion)]))
    im = Image.new("RGB", (3 * (t + 10), sum(r[1][0].height + 20 for r in rows) or 1), "white")
    d, y = ImageDraw.Draw(im), 0
    for name, ims in rows:
        d.text((3, y + 3), f"{name}: master | rig | onion (master red, rig cyan)", fill="black")
        for i, x in enumerate(ims):
            im.paste(x, (i * (t + 10), y + 18))
        y += ims[0].height + 20
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


MOTION_JOINTS = {"wrist_l": "hand_l", "wrist_r": "hand_r", "waist": "torso", "ankle_l": None, "ankle_r": None}


def motion_sheet(rig_json: Path, ann_path, path: Path, anims=("idle", "wave", "cheer_jump", "point"), per: int = 3) -> Path:
    """Each joint (a row) through the setup pose and `per` times of each animation, the crop centred on the master
    point carried by the joint's bone (feet: by the bone of the slot drawn there), master's rest crop first."""
    base = Aligned(rig_json, ann_path)
    rig, P = base.rig, base.points
    mf = json.loads((Path(rig_json).parent / "report.json").read_text(encoding="utf-8"))["master_frame"]
    k = mf["units_per_px"]
    slot_bone = {s["name"]: s["bone"] for s in rig.slots}
    bones = {j: b or next((slot_bone[s] for s in slot_bone if s.startswith(("boot", "hoof", "foot", "shoe")) and s.endswith(j[-2:])), None)
             for j, b in MOTION_JOINTS.items()}
    joints = [j for j in MOTION_JOINTS if (j if j in P else None) and bones[j]]
    frames = [(None, 0.0)] + [(a, round(rig.duration(a) * (i + 0.5) / per, 3)) for a in anims if a in rig.data["animations"]
                              for i in range(per)]
    t, lab = 150, 14
    im = Image.new("RGB", (t * (len(frames) + 1), (t + lab) * len(joints) + lab), "white")
    d = ImageDraw.Draw(im)
    d.text((2, 1), "master", fill="black")
    w0, _ = rig.pose(None, 0)

    def mat(wb):
        return np.array([[wb[0], wb[1], wb[4]], [wb[2], wb[3], wb[5]], [0, 0, 1]])
    for c, (an, tt) in enumerate(frames):
        d.text(((c + 1) * t + 2, 1), f"{an or 'setup'} {tt:.2f}"[:22], fill="black")
        al = base if an is None else Aligned(rig_json, ann_path, an, tt)
        world, _ = rig.pose(an, tt)
        for r, j in enumerate(joints):
            share = 0.22 if j == "waist" else 0.14
            hh = share * base.body_h / 2
            b = bones[j]
            pu = np.array([(P[j][0] - mf["mid_x"]) * k, (mf["ground_y"] - P[j][1]) * k, 1.0])
            pw = mat(world[b]) @ np.linalg.inv(mat(w0[b])) @ pu
            cx, cy = pw[0] / k + mf["mid_x"], mf["ground_y"] - pw[1] / k
            y = lab + r * (t + lab)
            im.paste(al.render.crop((int(cx - hh), int(cy - hh), int(cx + hh), int(cy + hh))).resize((t, t)), ((c + 1) * t, y))
            if c == 0:
                im.paste(base.master.crop((int(P[j][0] - hh), int(P[j][1] - hh), int(P[j][0] + hh), int(P[j][1] + hh))).resize((t, t)), (0, y))
                d.text((2, y + t), j, fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rig", type=Path, help="<char>/rig/<char>.json")
    ap.add_argument("--annotations", type=Path, help="default: <char>/annotations.json next to the rig folder")
    ap.add_argument("--out", type=Path, help="crop folder (default <rig>/qa/joints)")
    ap.add_argument("--sheet", type=Path, help="contact sheet path (default <rig>/qa/joints.png)")
    ap.add_argument("--no-review", action="store_true", help="skip the onion and motion sheets")
    a = ap.parse_args(argv)
    out = a.out or a.rig.parent / "qa" / "joints"
    al = Aligned(a.rig, a.annotations)
    rows = crops(al, out)
    al.render.save(out / f"{al.char}__setup_in_master_frame.png")
    (out / "labels.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} joints -> {out}")
    print(f"sheet: {sheet(rows, a.sheet or a.rig.parent / 'qa' / 'joints.png')}")
    if not a.no_review:
        qa = (a.sheet.parent if a.sheet else a.rig.parent / "qa")
        print(f"onion: {onion_sheet(al, qa / 'onion.png')}")
        print(f"motion: {motion_sheet(a.rig, a.annotations, qa / 'motion.png')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
