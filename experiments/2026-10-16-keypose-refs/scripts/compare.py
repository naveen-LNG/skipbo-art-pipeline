"""Reference key frame | old rig at that moment | new rig at that moment, one row per key pose.

  uv run --with numpy --with pillow scripts/compare.py <old rig.json> <new rig.json> out.png
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402
sys.path.insert(0, str(HERE))
from render_alpha import render as render_alpha  # noqa: E402

EXP = HERE.parent
ROWS = [  # reference, mirror, old anim/time, new anim/time
    ("half_crouch", False, ("squat", 0.45), ("squat", 0.45)),
    ("hurdle_crouch", False, ("squat", 1.0), ("squat", 1.0)),
    ("plant_low", False, ("squat", 1.0), ("plant_seed", 1.3)),
    ("hurdle_crouch", False, ("jump_hurdle", 0.34), ("jump_hurdle", 0.5)),
    ("hurdle_air", False, ("jump_hurdle", 0.8), ("jump_hurdle", 1.1)),
    ("hurdle_land", False, ("jump_hurdle", 1.46), ("jump_hurdle", 1.72)),
    ("flag_out", True, ("wave_flag", 1.05), ("wave_flag", 1.03)),
    ("flag_in", True, ("wave_flag", 1.55), ("wave_flag", 1.58)),
]
H = 420
old, new = q.Rig(Path(sys.argv[1])), q.Rig(Path(sys.argv[2]))
cv_o, cv_n = q.Canvas(old, H), q.Canvas(new, H)
tiles = []
for ref, mir, (ao, to), (an, tn) in ROWS:
    r = Image.open(EXP / f"refs/{ref}.png").convert("RGB")
    if mir:
        r = ImageOps.mirror(r)
    r = r.resize((int(r.width * H / r.height), H))
    fo = render_alpha(old, cv_o, ao, to)[0].convert("RGB")
    fn = render_alpha(new, cv_n, an, tn)[0].convert("RGB")
    row = Image.new("RGB", (r.width + fo.width + fn.width + 20, H), "white")
    for i, (im, lab) in enumerate([(r, f"ref {ref}{' (mirrored)' if mir else ''}"), (fo, f"before {ao} {to}s"), (fn, f"after {an} {tn}s")]):
        x = [0, r.width + 10, r.width + fo.width + 20][i]
        row.paste(im, (x, 0))
        ImageDraw.Draw(row).text((x + 6, 6), lab, fill=(180, 0, 0))
    tiles.append(row)
W = max(t.width for t in tiles)
out = Image.new("RGB", (W * 2 + 10, (H + 10) * ((len(tiles) + 1) // 2)), "white")
for i, t in enumerate(tiles):
    out.paste(t, ((i % 2) * (W + 10), (i // 2) * (H + 10)))
out.save(sys.argv[3])
print(sys.argv[3], out.size)
