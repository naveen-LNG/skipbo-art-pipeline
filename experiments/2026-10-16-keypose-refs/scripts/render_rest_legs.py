"""Render the rig's own lower body at rest (trousers + boots, nothing else) as an RGBA image, and its metrics.

  uv run --with numpy --with pillow --with scipy scripts/render_rest_legs.py <rig.json> legs/rig_rest.png [px per unit]

Used twice: as `image_3` (drawing 1, exactly) for the in-between sheets, and as the first legs drawing of every
legs-swapping animation, so leaving the rig's parts for the legs slot changes nothing on screen.
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402
sys.path.insert(0, str(HERE))

src, out = Path(sys.argv[1]), Path(sys.argv[2])
ppu = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
d = json.loads(src.read_text())
keep = {"hips", "boot_l", "boot_r"}
for s in d["slots"]:
    if s["name"] not in keep:
        s.pop("attachment", None)
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / src.name
    d["skeleton"]["images"] = str((src.parent / d["skeleton"].get("images", "./images/")).resolve()) + "/"
    p.write_text(json.dumps(d))
    rig = q.Rig(p)
    H = int(rig.data["skeleton"]["height"] * 1.37 * ppu)
    cv = q.Canvas(rig, H)
    frame = q.render(rig, cv, None, 0.0, bg=(0, 0, 0, 0))[0]
a = np.asarray(frame)
ys, xs = np.nonzero(a[..., 3] > 8)
crop = frame.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
crop.save(out)
grey = Image.new("RGBA", (crop.width + 80, crop.height + 80), (214, 214, 214, 255))
grey.alpha_composite(crop, (40, 40))
grey.convert("RGB").save(out.with_name(out.stem + "_grey.png"))
# the belt in world units (cut_legs' measure on the rendered pixels): buckle row middle, belt width, buckle to soles
from cut_legs import metrics  # noqa: E402
c = np.asarray(crop)
m = metrics(c[..., 3] > 127, c[..., :3])
bx, by = (m["belt_top"][0] + xs.min()), (m["buckle_y"] + ys.min())
rec = {"ppu": cv.S, "buckle_px": [float(m["belt_top"][0]), float(m["buckle_y"])], "buckle_world": [round(bx / cv.S + cv.ox, 2), round(cv.oy - by / cv.S, 2)], "belt_w": round(m["belt_w"] / cv.S, 2),
       "height": round((m["sole_y"] - m["buckle_y"]) / cv.S, 2)}
out.with_suffix(".json").write_text(json.dumps(rec))
print(json.dumps(rec))
