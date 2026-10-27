#!/bin/zsh
# One command: a built legacy rig -> pro rig + spine_qa + runtime-check data + legacy-vs-pro sheets.
#   build_pro.sh <char_dir_with_rig> <out>
#   e.g. build_pro.sh ../2026-10-16-cast/rabbit ../2026-10-16-cast/rabbit/rig_pro
# <char_dir> holds rig/<name>.json (spine_rig.py output); its master is <char_dir>/*master*.png if there is one.
# Writes <out>/ (json, atlas, images, preview.html, pro_report.json, qa/, qa_summary.txt, runtime_expected.json) and
# <out>/legacy_vs_pro.png, <out>/legacy_vs_pro_onion.png. Exit code = spine_qa's (1 if any check fails).
set -e
HERE="${0:A:h}"
S="$HERE/../../plugin/skills/skipbo-art/scripts"
CHAR="${1:?usage: build_pro.sh <char_dir_with_rig> <out>}"
OUT="${2:?usage: build_pro.sh <char_dir_with_rig> <out>}"
RIG=$(ls "$CHAR"/rig/*.json | grep -v -e report.json -e annotations.resolved.json -e runtime_expected.json | head -1)
[[ -f "$RIG" ]] || { echo "no rig json in $CHAR/rig"; exit 2; }
NAME="${RIG:t:r}"
MASTER=$(ls "$CHAR"/*master*.png 2>/dev/null | head -1 || true)
uv run -q "$S/spine_pro.py" "$RIG" --out "$OUT" ${=SKIP:+--skip $SKIP}
set +e
if [[ -n "$MASTER" ]]; then
  uv run -q "$S/spine_qa.py" "$OUT/$NAME.json" --master "$MASTER" > "$OUT/qa_summary.txt" 2>&1
else
  uv run -q "$S/spine_qa.py" "$OUT/$NAME.json" > "$OUT/qa_summary.txt" 2>&1
fi
QA=$?
set -e
uv run -q "$HERE/runtime_check/expected.py" "$OUT/$NAME.json" > /dev/null
uv run -q "$HERE/side_by_side.py" "$RIG" "$OUT/$NAME.json" "$OUT/legacy_vs_pro.png" --height 260 > /dev/null
grep -v '^PASS' "$OUT/qa_summary.txt" | cut -c1-200 || true
echo "$NAME: pro rig in $OUT, spine_qa $([[ $QA == 0 ]] && echo PASS || echo FAIL)"
exit $QA
