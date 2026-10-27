# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Print each bone's setup origin in master fractions (via rig/report.json master_frame). uv run tools/bones.py rig/bear.json"""
import json, sys
from pathlib import Path
sys.path.insert(0, "../../../plugin/skills/skipbo-art/scripts")
import spine_qa as q
rig = q.Rig(Path(sys.argv[1])); canvas = q.Canvas(rig, 1000)
frame, world, active, sa = q.render(rig, canvas, None, 0)
mf = json.loads((Path(sys.argv[1]).parent / "report.json").read_text())["master_frame"]
print(json.dumps(mf)[:300])
for b, w in world.items():
    print(b, round(w[4], 1), round(w[5], 1), "canvas", [round(v) for v in canvas.point(w[4], w[5])])
