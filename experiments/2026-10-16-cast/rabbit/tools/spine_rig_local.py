# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""spine_rig.py with one local override (pipeline workaround, not a change to the skill): the matcher's tail band.
rig_match.BANDS["tail"] is 0.40-1.00 of the silhouette height (0 = top of the ears). The rabbit's long ears push the
white muzzle down to 0.41 of that height, and the white cotton tail, mostly hidden behind the paw at 0.71, matched
onto the cheek (err 0.064), then onto the right paw. Narrowed here to 0.60-0.85 of the height and the inner half of the half-width.
  uv run tools/spine_rig_local.py <spine_rig.py args>"""
import runpy
import sys
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parents[4] / "plugin/skills/skipbo-art/scripts"
sys.path.insert(0, str(SCRIPTS))
import rig_match  # noqa: E402
rig_match.BANDS["tail"] = (0.60, 0.85, 0.0, 0.5)
sys.argv[0] = str(SCRIPTS / "spine_rig.py")
runpy.run_path(str(SCRIPTS / "spine_rig.py"), run_name="__main__")
