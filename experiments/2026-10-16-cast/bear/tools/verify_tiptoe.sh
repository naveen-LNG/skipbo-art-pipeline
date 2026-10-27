#!/bin/zsh
# Pipeline-fix check (experiments/2026-10-16-cast/PIPELINE_FIXES.md): rebuild the bear in a temporary copy with the
# tiptoe clog restored (stubbed by make_tiptoe.py), then spine_qa. The committed rig/ is not touched.
# Usage: tools/verify_tiptoe.sh [out dir]      (default: a new temp dir; prints it)
set -e
BEAR="${0:A:h:h}"
S="${BEAR:h:h:h}/plugin/skills/skipbo-art/scripts"
W="${1:-$(mktemp -d)}"
rsync -a --exclude rig --exclude rig_pro "$BEAR/" "$W/"
cd "$W"
uv run -q tools/make_tiptoe.py .
python3 - <<'PY'
from pathlib import Path
p = Path("draft_annotations.py"); s = p.read_text()
i = s.index('    f"{P}/02": ignored('); j = s.index('"foot"),\n', i) + len('"foot"),\n')
s = s[:i] + '''    f"{P}/02": ignored("tiptoe clog; stubbed copy in bear-tiptoe-parts", "foot"),
    "bear-tiptoe-parts/00": piece("foot", "either", {"ankle": (0.36, 0.155), "ground": (0.66, 0.988)}, name="clog",
                                  variant="tiptoe", painted_as="l", note="restored: tiptoe clog with the ankle stub"),
''' + s[j:]
p.write_text(s)
PY
python3 draft_annotations.py > /dev/null
python3 - <<'PY'
import json
p = 'annotations.json'; a = json.load(open(p))
fixed = {"bear-trousers-parts/00", "bear-clog-parts/00", "bear-clog-parts/01", "bear-point-palm-parts/00"}
for k, v in a['pieces'].items():
    if v['status'] == 'proposed':
        v['status'] = 'fixed' if k in fixed else 'confirmed'
a['master']['status'] = 'confirmed'
json.dump(a, open(p, 'w'), indent=2, sort_keys=True)
PY
for k in body hands poses face torso trousers arm clog point-palm tiptoe; do
  uv run -q $S/rig_annotations.py check annotations.json --sheet bear-$k-parts > /dev/null 2>&1
done
uv run -q $S/spine_rig.py --master bear_master.png --annotations annotations.json --props props.json --out rig > rig_build.log 2>&1
grep "tiptoe" rig_build.log | cut -c1-220
uv run -q $S/spine_qa.py rig/bear.json --master bear_master.png > qa.log 2>&1 || true
cut -c1-200 qa.log | grep -v '^PASS  [a-z_]* *{"frames'
echo "work dir: $W"
