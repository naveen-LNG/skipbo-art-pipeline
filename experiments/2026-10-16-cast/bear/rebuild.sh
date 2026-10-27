#!/bin/zsh
# Rebuild rig/ from scratch: re-make the experiment-local pieces, re-draft the annotations (self-approved at each
# checkpoint, see README; pieces changed after a review round are `fixed`), check every sheet, build, run spine_qa.
# Usage: ./rebuild.sh
cd "${0:A:h}"
S=../../../plugin/skills/skipbo-art
uv run -q make_parts.py > make_parts.log
python3 draft_annotations.py > /dev/null
python3 - <<'PY'
import json
p = 'annotations.json'; a = json.load(open(p))
fixed = {"bear-trousers-parts/00", "bear-clog-parts/00", "bear-clog-parts/01", "bear-point-palm-parts/00"}   # changed after a review round
for k, v in a['pieces'].items():
    if v['status'] == 'proposed':
        v['status'] = 'fixed' if k in fixed else 'confirmed'
a['master']['status'] = 'confirmed'
json.dump(a, open(p, 'w'), indent=2, sort_keys=True)
PY
for k in body hands poses face torso trousers arm clog point-palm; do
  uv run -q $S/scripts/rig_annotations.py check annotations.json --sheet bear-$k-parts > /dev/null 2>&1
done
rm -rf rig
uv run -q $S/scripts/spine_rig.py --master bear_master.png --annotations annotations.json --props props.json --out rig > rig_build.log 2>&1
grep "doubt" rig_build.log | cut -c1-220
uv run -q $S/scripts/spine_qa.py rig/bear.json --master bear_master.png > qa.log 2>&1
cut -c1-240 qa.log | grep -v '^PASS  [a-z_]* *{"frames'
