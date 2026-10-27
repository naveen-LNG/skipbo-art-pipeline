"""Place the plant under the watering can's stream and end the stream on the soil, from the built rig's own pose.

  uv run --with numpy --with pillow scripts/fit_garden.py garden/rig/beaver.json garden/props.json

At the middle of `water` (the can tipped, pouring) it reads where the spout's stream starts, sets the plant's `x` so
the stream lands a little left of the stem (on the mound, clear of the leaves), and the stream's `fall` so it ends on
the mound's top. Rebuild the rig afterwards (rebuild.sh does both)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "plugin/skills/skipbo-art/scripts"))
import spine_qa as q  # noqa: E402

rig_path, props_path = Path(sys.argv[1]), Path(sys.argv[2])
rig, props = q.Rig(rig_path), json.loads(props_path.read_text())
world, _ = rig.pose("water", 1.8)
body_h = rig.data["skeleton"]["height"]
sx, sy = world["prop_stream"][4], world["prop_stream"][5]
import numpy as np  # noqa: E402
mound = rig.skin["prop_plant"]["beaver_prop_plant"]                     # stage 0: the mound with its seed
alpha = np.asarray(rig.images["beaver_prop_plant"])[..., 3] > 128
widths = alpha.sum(1)
top_row = int(np.argmax(widths > 0.6 * widths.max()))                    # the mound's shoulder, below the seed
bottom_row = int(np.nonzero(widths)[0].max())
mound_top = world["prop_plant"][5] + 0.75 * (bottom_row - top_row) * mound["scaleY"]
st = rig.skin["prop_stream"]["beaver_prop_stream"]
fall = (sy - mound_top) / (st["height"] * st["scaleY"])
sa = np.asarray(rig.images["beaver_prop_stream"])[..., 3] > 128
cols = np.nonzero(sa[int(0.9 * sa.shape[0])])[0]                         # the stream's lower end, across
lean = ((cols.min() + cols.max()) / 2 / sa.shape[1] - props["stream"]["top"][0]) * st["width"] * st["scaleX"]
land_x = sx + lean * fall                                                # it leans right as it falls
props["plant"]["x"] = round(land_x / body_h + 0.075, 3)                    # the stem 7.5% of body height right: it lands on the mound
props["stream"]["fall"] = round(fall, 3)
props_path.write_text(json.dumps(props, indent=1))
print(f"stream top ({sx:.0f}, {sy:.0f}); plant x {props['plant']['x']}; stream fall {props['stream']['fall']}")
