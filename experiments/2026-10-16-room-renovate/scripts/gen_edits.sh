#!/bin/zsh
# One in-place edit of the "before" room per fixable item, all from room/base.png (7 Nano Banana Pro calls in parallel).
# Usage: gen_edits.sh [item ...]   (default: every item in prompts/items.tsv)
cd "${0:A:h}/../room"
S=../../../plugin/skills/skipbo-art
export COMFY_RUNS_DIR=$PWD/runs; mkdir -p runs
while IFS=$'\t' read -r id target new; do
  (( $# )) && [[ " $* " != *" $id "* ]] && continue
  python3 $S/scripts/comfy.py run nb-pro --prompt-file ../prompts/edit.txt --image 1=base.png \
    --var TARGET="$target" --var NEW="$new" --var ASPECT=9:16 --var SIZE=2K --var TEMP=0.4 \
    --tag edit-$id --criteria "only the $id changed" --criteria "same camera and framing as base" > runs/edit-$id.log 2>&1 &
done < ../prompts/items.tsv
wait
for f in runs/edit-*.log; do echo "== $f"; tail -1 $f; done
