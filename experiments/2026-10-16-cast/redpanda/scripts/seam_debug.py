# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Which frame makes spine_qa's `seams` score for one pair: check_seams per frame (the setup pose and each animation's
midpoint, as spine_qa samples). uv run seam_debug.py <rig.json> <up/lo>"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q
rig = q.Rig(Path(sys.argv[1])); canvas = q.Canvas(rig, q.CHECK_H)
frames = [(None, 0.0)] + [(n, rig.duration(n) / 2) for n in rig.data["animations"]]
for f in frames:
    r = q.check_seams(rig, canvas, [f])["seams"].get(sys.argv[2])
    if r: print(f, r)
