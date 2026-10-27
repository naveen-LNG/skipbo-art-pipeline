"""Before | after GIF of one animation (old rig, new rig), plus a still strip of both.

  uv run --with numpy --with pillow scripts/before_after.py <old rig.json> <new rig.json> <anim> [<old anim>] out_dir
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402
sys.path.insert(0, str(HERE))
from render_alpha import render as render_alpha  # noqa: E402

old_p, new_p, anim, *rest = sys.argv[1:]
old_anim, out = (rest[0], Path(rest[1])) if len(rest) == 2 else (anim, Path(rest[0]))
out.mkdir(parents=True, exist_ok=True)
old, new = q.Rig(Path(old_p)), q.Rig(Path(new_p))
H = 360
co, cn = q.Canvas(old, H), q.Canvas(new, H)
do, dn = old.duration(old_anim) if old_anim in old.data["animations"] else 0, new.duration(anim)
T = max(do, dn)
frames = []
for i in range(int(T * 30) + 1):
    t = i / 30
    fn = render_alpha(new, cn, anim, min(t, dn))[0].convert("RGB")
    if do:
        fo = render_alpha(old, co, old_anim, min(t, do))[0].convert("RGB")
        f = Image.new("RGB", (fo.width + fn.width, H), "white")
        f.paste(fo, (0, 0)); f.paste(fn, (fo.width, 0))
        d = ImageDraw.Draw(f); lo, ln = (os.environ.get("BA_LABELS") or "before,after").split(",")
        d.text((8, 8), f"{lo} {old_anim}", fill=(160, 0, 0)); d.text((fo.width + 8, 8), f"{ln} {anim}", fill=(0, 110, 0))
    else:
        f = fn; ImageDraw.Draw(f).text((8, 8), f"new {anim}", fill=(0, 110, 0))
    frames.append(f)
frames[0].save(out / f"{anim}.gif", save_all=True, append_images=frames[1:], duration=33, loop=0)
print(out / f"{anim}.gif", len(frames))
