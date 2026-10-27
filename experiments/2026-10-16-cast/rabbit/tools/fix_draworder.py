"""Pipeline workaround (round 8): in hold_card the drawOrder key that lifts the left sleeve and paw over the torso
fires "on the last frame before the forearm reaches the torso" (rig_anim). The rabbit's paw is longer than its
sleeve's forearm half, so the paw reaches the bib first and slid behind it for ~0.15 s (spine_qa `occluded` hand_l,
39% visible at 0.33 s; seen in the frames). Move the lift key LEAD s earlier and the drop key LEAD s later, in place.
  python3 tools/fix_draworder.py rig/rabbit.json"""
import json
import sys
LEAD = 0.15
p = sys.argv[1]; r = json.load(open(p))
keys = r["animations"]["hold_card"]["drawOrder"]
lift = [k for k in keys if k.get("offsets")]; drop = [k for k in keys if not k.get("offsets")]
assert len(lift) == 1 and len(drop) == 1, keys
lift[0]["time"] = round(lift[0]["time"] - LEAD, 4); drop[0]["time"] = round(drop[0]["time"] + LEAD, 4)
json.dump(r, open(p, "w"), indent=1)
print("hold_card drawOrder:", [k["time"] for k in keys])
