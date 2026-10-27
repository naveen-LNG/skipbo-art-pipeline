#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""Legacy vs pro frames, one column per (animation, time), legacy on top, pro below; plus onion-skin strips.

  uv run side_by_side.py legacy/beaver.json pro/beaver.json out.png [--height 300]

Columns: the setup pose, then for each animation both rigs share the middle frame (or the jump's apex), and the
pro-only animations (look_around, talk) show the pro rig twice. Rendered with spine_qa's renderer (checked against
the Spine 4.2 web player by runtime_check/).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugin" / "skills" / "skipbo-art" / "scripts"))
import spine_qa as q  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("legacy", type=Path)
ap.add_argument("pro", type=Path)
ap.add_argument("out", type=Path)
ap.add_argument("--height", type=int, default=300)
a = ap.parse_args()
L, P = q.Rig(a.legacy), q.Rig(a.pro)
cl = q.Canvas(L, a.height)
cp = q.Canvas(L, a.height)          # same framing for both


def frame(rig, canvas, anim, t):
    f, *_ = q.render(rig, canvas, anim, t)
    return f.convert("RGB")


def picks(rig, anim):
    d = rig.duration(anim)
    if "jump" in anim or anim == "cheer_jump":
        ys = [rig.pose(anim, t)[0]["hips"][5] for t in np.linspace(0, d, 31)]
        return [float(np.linspace(0, d, 31)[int(np.argmax(ys))])]
    return [round(d * 0.35, 3), round(d * 0.7, 3)]


cols = [("setup", None, 0.0)]
for anim in P.data["animations"]:
    if anim in ("blink",):
        continue
    for t in picks(P, anim):
        cols.append((f"{anim} {t:.2f}s", anim, t))
tiles = []
for label, anim, t in cols:
    top = frame(L, cl, anim, t) if (anim is None or anim in L.data["animations"]) else None
    bot = frame(P, cp, anim, t)
    if top is None:
        top = Image.new("RGB", bot.size, (235, 235, 235))
        ImageDraw.Draw(top).text((8, bot.height // 2), "(pro only)", fill=(120, 120, 120))
    tiles.append((label, top, bot))
w, h = tiles[0][2].size
per_row = 8
rows = (len(tiles) + per_row - 1) // per_row
sheet = Image.new("RGB", (w * min(per_row, len(tiles)), rows * (2 * h + 18)), (255, 255, 255))
d = ImageDraw.Draw(sheet)
for i, (label, top, bot) in enumerate(tiles):
    x, y = (i % per_row) * w, (i // per_row) * (2 * h + 18)
    d.text((x + 4, y + 3), label, fill=(0, 0, 0))
    sheet.paste(top, (x, y + 16))
    sheet.paste(bot, (x, y + 16 + h))
    d.text((x + 4, y + 20), "legacy", fill=(160, 0, 0))
    d.text((x + 4, y + 20 + h), "pro", fill=(0, 110, 0))
sheet.save(a.out)
print(a.out, f"{len(tiles)} columns")

# onion skins: the average of 10 frames across each animation (what moves blurs), legacy above pro
onion = []
for anim in ("idle", "walk", "cheer_jump", "wave", "squat", "look_around", "talk"):
    if anim not in P.data["animations"]:
        continue
    row = []
    for rig, canvas in ((L, cl), (P, cp)):
        if anim not in rig.data["animations"]:
            row.append(None)
            continue
        d = rig.duration(anim)
        acc = None
        for t in np.linspace(0, d, 10, endpoint=False):
            f = np.asarray(frame(rig, canvas, anim, float(t)), dtype=np.float32)
            acc = f if acc is None else acc + f
        row.append(Image.fromarray((acc / 10).astype(np.uint8)))
    onion.append((anim, row))
sheet = Image.new("RGB", (w * len(onion), 2 * h + 18), (255, 255, 255))
d = ImageDraw.Draw(sheet)
for i, (anim, (top, bot)) in enumerate(onion):
    d.text((i * w + 4, 3), f"{anim} (onion, 10 frames)", fill=(0, 0, 0))
    if top is None:
        top = Image.new("RGB", (w, h), (235, 235, 235))
        ImageDraw.Draw(top).text((8, h // 2), "(pro only)", fill=(120, 120, 120))
    sheet.paste(top, (i * w, 16))
    sheet.paste(bot, (i * w, 16 + h))
    d.text((i * w + 4, 20), "legacy", fill=(160, 0, 0))
    d.text((i * w + 4, 20 + h), "pro", fill=(0, 110, 0))
onion_path = a.out.with_name(a.out.stem + "_onion.png")
sheet.save(onion_path)
print(onion_path)
