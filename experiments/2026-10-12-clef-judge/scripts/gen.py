# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Build a labelled rig-defect test set from the approved fox/moose rigs, without touching repo code.

Each slot is rendered as its own layer (spine_qa's renderer), then composited here so one layer can be shifted by an
exact screen-space offset, moved in draw order, or mirrored. Ground truth is known by construction.
Writes <out>/<id>.png (body crop, long side <= 768) and <out>/labels.jsonl.
"""
import json, random, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

REPO = Path("/work/comfy")
sys.path.insert(0, str(REPO / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402

EXP = REPO / "experiments/2026-10-11-rig-annotations"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
H = 800
BG = (214, 214, 214, 255)
random.seed(7)

# slot -> semantic part name (side is decided per frame from screen position)
PARTS = {
    "fox": {"head": "head", "torso": "torso", "hips": "hips", "hand_l": "hand", "hand_r": "hand",
            "boot_l": "foot", "boot_r": "foot", "tail": "tail", "upperarm_l": "arm", "upperarm_r": "arm"},
    "moose": {"head": "head", "torso": "torso", "hips": "hips", "hand_l": "hand", "hand_r": "hand",
              "hoof_l": "foot", "hoof_r": "foot", "antler_l": "antler", "antler_r": "antler",
              "upperarm_l": "arm", "upperarm_r": "arm", "scarf": "scarf"},
}
LINKED = {"boot_l": ["boot_l_back"], "boot_r": ["boot_r_back"]}   # worn backs move with their shell
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def layers(rig, canvas, anim, t):
    world, active = rig.pose(anim, t)
    by_name = {s["name"]: s for s in rig.slots}
    out = []
    for n in rig.draw_order(anim, t):
        att = active.get(n)
        if att:
            out.append((n, canvas.layer(rig, n, att, world)))
    return out


def composite(lays, shift=None, dxy=(0, 0), order=None, mirror=None):
    W, Hh = lays[0][1].size
    frame = Image.new("RGBA", (W, Hh), BG)
    names = [n for n, _ in lays]
    if order:
        names = order(names)
    d = dict(lays)
    moved = set([shift] + LINKED.get(shift, [])) if shift else set()
    for n in names:
        lay = d[n]
        if n in moved:
            lay = Image.new("RGBA", lay.size, (0, 0, 0, 0)); lay.paste(d[n], dxy, d[n])
        if n == mirror:
            bb = d[n].getbbox(); cx = (bb[0] + bb[2]) / 2
            fl = ImageOps.mirror(d[n]); lay = Image.new("RGBA", fl.size, (0, 0, 0, 0))
            lay.paste(fl, (int(round(2 * cx - fl.width)), 0), fl)
        frame.alpha_composite(lay)
    return frame


def side(lays, slot):
    bb = dict(lays)[slot].getbbox()
    tb = dict(lays)["torso"].getbbox()
    return "image-left" if (bb[0] + bb[2]) / 2 < (tb[0] + tb[2]) / 2 else "image-right"


def crop_save(frame, lays, name, crop_box=None):
    if crop_box is None:
        bb = None
        for _, l in lays:
            b = l.getbbox()
            bb = b if bb is None else (min(bb[0], b[0]), min(bb[1], b[1]), max(bb[2], b[2]), max(bb[3], b[3]))
        m = 30
        crop_box = (max(0, bb[0] - m), max(0, bb[1] - m), min(frame.width, bb[2] + m), min(frame.height, bb[3] + m))
    im = frame.convert("RGB").crop(crop_box)
    im.thumbnail((768, 768))
    im.save(OUT / f"{name}.png")
    return crop_box


labels = []
for char in ["fox", "moose"]:
    rig = q.Rig(EXP / char / "rig" / f"{char}.json")
    canvas = q.Canvas(rig, H)
    body_px = rig.data["skeleton"]["height"] * canvas.S
    frames = [(None, 0.0)] + [(a, t) for a in ["idle", "wave", "point", "thumbs_up", "hold_card", "cheer_jump"]
                                for t in (0.5, 1.2, 1.8)]
    for anim, t in frames:
        lays = layers(rig, canvas, anim, t)
        tag = f"{char}_{anim or 'setup'}_{t:.1f}"
        box = crop_save(composite(lays), lays, f"{tag}__clean")
        base = dict(char=char, anim=anim or "setup", t=t, body_px=round(body_px), crop=box)
        labels.append(dict(base, id=f"{tag}__clean", defect=False, kind="none", part="none", direction="none", mag=0))
        present = [n for n, _ in lays]
        # offsets: setup gets the full grid, animation frames a random sample
        slots = [s for s in PARTS[char] if s in present and s not in ("upperarm_l", "upperarm_r")]
        grid = [(s, d, m) for s in slots for d in DIRS for m in (3, 8, 16, 24)]
        pick = grid if anim is None else random.sample(grid, 4)
        for s, dname, m in pick:
            dx, dy = DIRS[dname]
            fr = composite(lays, shift=s, dxy=(dx * m, dy * m))
            sd = side(lays, s) if PARTS[char][s] in ("hand", "foot", "antler") else ""
            pid = f"{tag}__shift_{s}_{dname}_{m}"
            crop_save(fr, lays, pid, box)
            labels.append(dict(base, id=pid, defect=True, kind="offset", slot=s, part=PARTS[char][s], side=sd,
                               direction=dname, mag=m, mag_pct=round(100 * m / body_px, 2)))
        # draw-order faults: sleeve over torso (documented failure), hand under sleeve, tail/antler in front
        for arm in ("upperarm_l", "upperarm_r"):
            if arm in present and "torso" in present:
                def o(ns, arm=arm):
                    ns = [n for n in ns if n != arm]; i = ns.index("torso"); return ns[:i + 1] + [arm] + ns[i + 1:]
                if o(present) != present:
                    pid = f"{tag}__layer_{arm}_over_torso"
                    crop_save(composite(lays, order=o), lays, pid, box)
                    labels.append(dict(base, id=pid, defect=True, kind="layer_order", slot=arm, part="arm",
                                       side=side(lays, arm), direction="none", mag=0))
        if anim is None:
            for back in ("tail", "antler_l"):
                if back in present:
                    o = lambda ns, b=back: [n for n in ns if n != b] + [b]
                    pid = f"{tag}__layer_{back}_front"
                    crop_save(composite(lays, order=o), lays, pid, box)
                    labels.append(dict(base, id=pid, defect=True, kind="layer_order", slot=back,
                                       part=PARTS[char][back], direction="none", mag=0))
            for h in ("hand_l", "hand_r"):
                pid = f"{tag}__mirror_{h}"
                crop_save(composite(lays, mirror=h), lays, pid, box)
                labels.append(dict(base, id=pid, defect=True, kind="mirrored", slot=h, part="hand",
                                   side=side(lays, h), direction="none", mag=0))
        print(tag, len(labels), flush=True)

with open(OUT / "labels.jsonl", "w") as f:
    for r in labels:
        f.write(json.dumps(r) + "\n")
# master reference, same long-side budget
for char in ["fox", "moose"]:
    m = Image.open(EXP / char / "master.png").convert("RGB"); m.thumbnail((768, 768)); m.save(OUT / f"{char}__master.png")
print("total", len(labels), "defects", sum(r["defect"] for r in labels))
