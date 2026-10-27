#!/bin/zsh
# Re-draft the annotations (self-reviewed at each checkpoint; pieces changed after a fix round are `fixed`), check every
# sheet, build the rig from scratch and run spine_qa. Usage: ./rebuild.sh
cd "${0:A:h}"
S=../../../plugin/skills/skipbo-art
uv run -q make_master_bg.py > /dev/null
python3 draft_annotations.py > /dev/null
python3 - <<'PY'
import json
p = 'annotations.json'; a = json.load(open(p))
fixed = set(json.load(open('fixed.json'))) if __import__('os').path.exists('fixed.json') else set()
for k, v in a['pieces'].items():
    if v['status'] == 'proposed':
        v['status'] = 'fixed' if k in fixed else 'confirmed'
a['master']['status'] = 'fixed' if 'master' in fixed else 'confirmed'
json.dump(a, open(p, 'w'), indent=2, sort_keys=True)
PY
uv run -q make_sleeve_wide.py > /dev/null; uv run -q make_torso.py > /dev/null; uv run -q make_trousers.py > /dev/null; uv run -q make_ears.py > /dev/null
for k in body hands face sleeves point-palm sleeves-wide torso trousers ears; do
  [ -d runs/rabbit-$k-parts ] && uv run -q $S/scripts/rig_annotations.py check annotations.json --sheet rabbit-$k-parts > /dev/null 2>&1
done
rm -rf rig
uv run -q tools/spine_rig_local.py --master rabbit_master.png --annotations annotations.json --props props.json --out rig > rig_build.log 2>&1
python3 tools/fix_draworder.py rig/rabbit.json >> rig_build.log
grep "doubt" rig_build.log | cut -c1-240
uv run -q $S/scripts/spine_qa.py rig/rabbit.json --master rabbit_master.png > rig_qa.log 2>&1
grep -c "^PASS" rig_qa.log; grep -v "^PASS" rig_qa.log | cut -c1-260
uv run -q $S/scripts/joint_crops.py rig/rabbit.json --annotations annotations.json > /dev/null 2>&1
