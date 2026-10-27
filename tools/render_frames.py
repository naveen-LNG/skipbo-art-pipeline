#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""Render chosen frames of generated Spine rigs into one labelled grid, for looking at poses by eye.

  uv run tools/render_frames.py out.png 600 rig/fox.json:setup:0 rig/fox.json:cheer_jump:0.83 old/fox.json:cheer_jump:0.83

Each spec is <skeleton.json>:<animation or setup>:<seconds>; 600 is the frame height in px. Uses the renderer in
spine_qa.py, which matches the Spine 4.2 web player for the features spine_rig.py writes.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "skills" / "skipbo-art" / "scripts"))
import spine_qa as q  # noqa: E402

if len(sys.argv) < 4:
    raise SystemExit(__doc__)
out, H, specs = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
tiles, rigs = [], {}
for sp in specs:
    path, anim, t = sp.rsplit(":", 2)
    rig = rigs.setdefault(path, q.Rig(Path(path)))
    frame, *_ = q.render(rig, q.Canvas(rig, H), None if anim == "setup" else anim, float(t))
    frame = frame.convert("RGB")
    ImageDraw.Draw(frame).text((6, 6), f"{Path(path).parent.parent.name[:18]} {anim} {t}s", fill=(160, 0, 0))
    tiles.append(frame)
cols = min(4, len(tiles))
w, h = max(t.width for t in tiles), max(t.height for t in tiles)
grid = Image.new("RGB", (w * cols, h * ((len(tiles) + cols - 1) // cols)), (255, 255, 255))
for i, t in enumerate(tiles):
    grid.paste(t, ((i % cols) * w, (i // cols) * h))
grid.save(out)
print(out)
