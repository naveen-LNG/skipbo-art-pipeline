# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Setup-pose joint crops paired with the same region of the approved master.

For each joint slot, the box comes from the clean setup render (what pipeline code knows). The same box is mapped
canvas px -> skeleton units -> master px (rig/report.json master_frame, as spine_qa.check_setup does), so the master
crop shows what that joint should look like. Rendered at 1600 px with doubled shifts: defect sizes equal the earlier
800 px run (8/16/24 px) and render crops are as sharp as master crops.
Writes <out>/<id>.jpg (render crop), <out>/<id>__ref.jpg (master crop), <out>/labels.jsonl."""
import json, random, sys
from pathlib import Path
from PIL import Image

REPO = Path("/work/comfy")
sys.path.insert(0, str(REPO / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402

EXP = Path(__file__).parent / "rigs"   # snapshot of both rigs (T20), so concurrent rebuilds cannot change the test
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SCALE = 2                                   # canvas 1600 = 2 x the earlier 800
BG = (214, 214, 214, 255)
JOINTS = {"fox": ["head", "hand_l", "hand_r", "hips", "boot_l", "boot_r", "tail"],
          "moose": ["head", "hand_l", "hand_r", "hips", "hoof_l", "hoof_r", "antler_l", "antler_r"]}
LINKED = {"boot_l": ["boot_l_back"], "boot_r": ["boot_r_back"]}
DESC = {"head": "the head where it sits on the neck and collar", "hand": "the hand where it enters the sleeve cuff",
        "hips": "the waist where the trousers meet the torso", "boot": "the boot where it meets the trouser leg",
        "hoof": "the hoof where it meets the trouser leg", "tail": "the tail where it attaches behind the hips",
        "antler": "the antler where it attaches to the head"}
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
MAGS = (8, 16, 24)                          # in 800-canvas px
rnd = random.Random(11)


def base(s): return s[:-2] if s[-2:] in ("_l", "_r") else s


rows = []
for char in ("fox", "moose"):
    rig = q.Rig(EXP / char / "rig" / f"{char}.json"); cv = q.Canvas(rig, 800 * SCALE)
    mf = json.load(open(EXP / char / "rig" / "report.json"))["master_frame"]; k = mf["units_per_px"]
    master = Image.open(EXP / char / "master.png").convert("RGB")
    world, active = rig.pose(None, 0)
    lays = [(n, cv.layer(rig, n, active[n], world)) for n in rig.draw_order(None, 0) if active.get(n)]
    names = [n for n, _ in lays]; d = dict(lays)
    boxes = {s: d[s].getbbox() for s in JOINTS[char] if s in d}

    # joint point = where the slot's bone attaches (hips: the torso bone, i.e. the waist), in canvas px
    bone = {sl["name"]: sl["bone"] for sl in rig.slots}

    def jpoint(s):
        b = "torso" if s == "hips" else bone[s]
        return cv.point(world[b][4], world[b][5])

    def cbox(s):                                          # square around the joint, sized by the part
        x0, y0, x1, y1 = boxes[s]; cx, cy = jpoint(s)
        h = min(max(0.8 * max(x1 - x0, y1 - y0), 140 * SCALE), 260 * SCALE) / 2
        return cx - h, cy - h, cx + h, cy + h

    def overlaps(a, s):                                   # a's crop vs s's part box grown by the largest shift
        A, (x0, y0, x1, y1) = cbox(a), boxes[s]; g = max(MAGS) * SCALE
        return not (A[2] < x0 - g or A[0] > x1 + g or A[3] < y0 - g or A[1] > y1 + g)

    def compose(shift=None, dxy=(0, 0)):
        fr = Image.new("RGBA", lays[0][1].size, BG)
        moved = {shift, *LINKED.get(shift, [])} if shift else set()
        for n in names:
            lay = d[n]
            if n in moved:
                lay = Image.new("RGBA", lay.size, (0, 0, 0, 0)); lay.paste(d[n], dxy, d[n])
            fr.alpha_composite(lay)
        return fr.convert("RGB")

    mbg = tuple(int(v) for v in __import__("numpy").median(__import__("numpy").concatenate(
        [__import__("numpy").asarray(master)[0], __import__("numpy").asarray(master)[:, 0]]), 0))

    def padded_crop(img, box, fill):                      # crop that may run past the image edge
        box = tuple(int(round(v)) for v in box)
        out = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), fill)
        out.paste(img.crop((max(0, box[0]), max(0, box[1]), min(img.width, box[2]), min(img.height, box[3]))),
                  (max(0, -box[0]), max(0, -box[1])))
        return out

    def crops(frame, s):
        b = cbox(s)
        rc = padded_crop(frame, b, BG[:3])
        to_m = lambda cx, cy: ((cx / cv.S + cv.ox) / k + mf["mid_x"], mf["ground_y"] - (cv.oy - cy / cv.S) / k)
        (u0, v0), (u1, v1) = to_m(b[0], b[1]), to_m(b[2], b[3])
        mc = padded_crop(master, (u0, v0, u1, v1), mbg)
        size = (448, 448)
        return rc.resize(size, Image.LANCZOS), mc.resize(size, Image.LANCZOS)

    import numpy as _np
    tight = {}                                            # part box from alpha > 127 (what a person would box)
    for s_ in boxes:
        ys, xs = _np.nonzero(_np.asarray(d[s_])[..., 3] > 127)
        tight[s_] = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)

    def gt_box(s, off):                                   # part box in crop fractions (clipped) + visible share
        x0, y0, x1, y1 = tight[s]; x0, x1, y0, y1 = x0 + off[0], x1 + off[0], y0 + off[1], y1 + off[1]
        b = cbox(s); W, Hc = b[2] - b[0], b[3] - b[1]
        cl = lambda v: min(1.0, max(0.0, v))
        f = dict(left=cl((x0 - b[0]) / W), right=cl((x1 - b[0]) / W), top=cl((y0 - b[1]) / Hc), bottom=cl((y1 - b[1]) / Hc))
        vis = ((f["right"] - f["left"]) * W * (f["bottom"] - f["top"]) * Hc) / ((x1 - x0) * (y1 - y0))
        return {k: round(v, 4) for k, v in f.items()}, round(vis, 3)

    def save(frame, s, rid, off=(0, 0), **lab):
        if "--noimg" not in sys.argv:
            rc, mc = crops(frame, s)
            rc.save(OUT / f"{rid}.jpg", quality=92); mc.save(OUT / f"{rid}__ref.jpg", quality=92)
        gb, vis = gt_box(s, off)                          # render: the part where it was drawn (shifted or not)
        mb, _ = gt_box(s, (0, 0))                         # master: approximated by the clean rig's part box
        b_ = cbox(s)
        to_m = lambda cx, cy: ((cx / cv.S + cv.ox) / k + mf["mid_x"], mf["ground_y"] - (cv.oy - cy / cv.S) / k)
        (u0, v0), (u1, v1) = to_m(b_[0], b_[1]), to_m(b_[2], b_[3])
        lab["master_crop"] = [round(u0 / master.width, 5), round(v0 / master.height, 5), round(u1 / master.width, 5), round(v1 / master.height, 5)]
        rows.append(dict(id=rid, char=char, slot=s, joint=DESC[base(s)], gt_box=gb, gt_visible=vis, gt_box_master=mb, **lab))

    clean = compose()
    for s in boxes:                                       # every joint of the clean render: negatives
        save(clean, s, f"{char}_clean__{s}", defect=False, direction="none", mag=0, shifted="none")
    for s in boxes:
        for dn, (dx, dy) in DIRS.items():
            for m in MAGS:
                fr = compose(s, (dx * m * SCALE, dy * m * SCALE))
                tag = f"{char}_shift_{s}_{dn}_{m}"
                save(fr, s, f"{tag}__{s}", off=(dx * m * SCALE, dy * m * SCALE), defect=True, direction=dn, mag=m, shifted=s)
                far = [x for x in boxes if x != s and not overlaps(x, s)]  # untouched joint, crop clear of the moved part
                if not far: continue
                o = rnd.choice(far)
                save(fr, o, f"{tag}__{o}", defect=False, direction="none", mag=0, shifted=s)
    print(char, len(rows), flush=True)

with open(OUT / ("labels_gt.jsonl" if "--noimg" in sys.argv else "labels.jsonl"), "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
print(len(rows), "crops,", sum(r["defect"] for r in rows), "positive")
