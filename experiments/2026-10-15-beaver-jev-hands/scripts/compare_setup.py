# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Setup render beside the master, both in the master's frame, plus close-ups of named regions (0..1 of the master).
  uv run compare_setup.py <char> <rig dir> <master.png> <out.png> [anim:t ...]"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw
REPO = Path(__file__).resolve().parents[3]; sys.path.insert(0, str(REPO / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q
char, rigdir, master, out = sys.argv[1], Path(sys.argv[2]), Image.open(sys.argv[3]).convert("RGB"), sys.argv[4]
rig = q.Rig(rigdir / f"{char}.json"); mf = json.load(open(rigdir / "report.json"))["master_frame"]
def in_master(anim, t):
    """Render a frame and map it into master px (the frame spine_qa's setup check uses)."""
    cv = q.Canvas(rig, 1600); fr, *_ = q.render(rig, cv, anim, t)
    k = mf["units_per_px"]; W, H = master.size
    # master px (x, y) -> skeleton units -> canvas px
    import numpy as np
    def m2c(x, y):
        ux = mf["origin_units"][0] + x * k if "origin_units" in mf else None
        return ux
    return fr, cv
print(json.dumps(mf)[:400])
