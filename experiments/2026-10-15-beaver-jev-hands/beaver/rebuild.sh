#!/bin/zsh
# Re-draft the annotations (approved at checkpoint; pieces changed after a review round are `fixed`), check every
# sheet, build the rig from scratch and run spine_qa. Usage: beaver/rebuild.sh
cd "${0:A:h}"
S=../../../plugin/skills/skipbo-art
python3 draft_annotations.py > /dev/null
python3 - <<'PY'
import json
p = 'annotations.json'; a = json.load(open(p))
fixed = {"beaver-body-parts/12", "beaver-trousers-parts/00", "beaver-sleeves3-parts/01",
         "beaver-tail-parts/16", "beaver-fist-palm-parts/00", "beaver-point-palm-parts/02"
}
for k, v in a['pieces'].items():
    if v['status'] == 'proposed':
        v['status'] = 'fixed' if k in fixed else 'confirmed'
a['master']['status'] = 'fixed'
json.dump(a, open(p, 'w'), indent=2, sort_keys=True)
PY
for k in body hands poses face point-palm sleeves2 fist-palm trousers tail sleeves3; do
  uv run -q $S/scripts/rig_annotations.py check annotations.json --sheet beaver-$k-parts > /dev/null 2>&1
done
rm -rf rig
uv run -q $S/scripts/spine_rig.py --master beaver_master.png --annotations annotations.json --props props.json --out rig > rig_build.log 2>&1
grep "doubt" rig_build.log | cut -c1-200
uv run -q $S/scripts/spine_qa.py rig/beaver.json --master beaver_master.png 2>&1 | cut -c1-240 | grep -v '^PASS  [a-z_]* *{"frames'
