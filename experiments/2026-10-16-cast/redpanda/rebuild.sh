#!/bin/zsh
# Rebuild rig/ from scratch: local art fixes, annotations (decisions recorded from the self-reviewed checkpoints:
# pieces changed after a review round are `fixed`, the rest `confirmed`), check every sheet, build, spine_qa, review sheets.
# Usage: ./rebuild.sh [--no-qa]
cd "${0:A:h}"
S=../../../plugin/skills/skipbo-art
for m in make_ears make_props make_sleeve_wide make_boots make_trousers make_paws; do uv run -q scripts/$m.py > /dev/null; done
python3 draft_annotations.py > /dev/null
python3 - <<'PY'
import json
p = 'annotations.json'; a = json.load(open(p))
fixed = {"redpanda-trousers-parts/00", "redpanda-boots-parts/00", "redpanda-boots-parts/01", "redpanda-sleeves-wide-parts/00",
         "redpanda-sleeves-wide-parts/01", "redpanda-point-palm2-parts/00", "redpanda-body-parts/10",
         "redpanda-paws-parts/00", "redpanda-paws-parts/01", "redpanda-paws-parts/02", "redpanda-paws-parts/03",
         "redpanda-paws-parts/04", "redpanda-paws-parts/05",
         "redpanda-boots-parts/03", "redpanda-boots-parts/04"}
for k, v in a['pieces'].items():
    if v['status'] == 'proposed':
        v['status'] = 'fixed' if k in fixed else 'confirmed'
a['master']['status'] = 'fixed'
json.dump(a, open(p, 'w'), indent=2, sort_keys=True)
PY
rm -rf body variants face-heads
for k in body hands poses face ears sleeves-wide boots trousers point-palm2 paws; do
  uv run -q $S/scripts/rig_annotations.py check annotations.json --sheet redpanda-$k-parts > /dev/null 2>&1
done
rm -rf rig
uv run -q $S/scripts/spine_rig.py --master redpanda_master.png --annotations annotations.json --props props.json --out rig > rig_build.log 2>&1
grep "doubt" rig_build.log | cut -c1-200
[[ "$1" == "--no-qa" ]] && exit 0
uv run -q $S/scripts/joint_crops.py rig/redpanda.json --annotations annotations.json > rig/joint_crops.log 2>&1
uv run -q $S/scripts/spine_qa.py rig/redpanda.json --master redpanda_master.png 2>&1 | cut -c1-400 | tee rig/spine_qa.txt | grep -v '^PASS  [a-z_]* *{"frames'
