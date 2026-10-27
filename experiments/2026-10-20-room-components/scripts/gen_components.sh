#!/bin/sh
# One standalone component per fixable item, painted alone from the room's camera and cut to a transparent PNG.
# Seven Nano Banana Pro calls, run in parallel like v1's gen_edits.sh.
#
#   scripts/gen_components.sh                 # all seven
#   scripts/gen_components.sh sofa tv         # just these
#
# The room (image_1) is v1's before-room; the two LR style refs are image_2 and image_3. Per-item text comes from
# prompts/items.tsv (id, component, perspective, placement, check) and the room paragraph from prompts/room.txt,
# which is the same for every component. Outputs land in room/runs/<tag>/ and are collected into room/components/.
set -e
cd "$(dirname "$0")/.."
S=../../plugin/skills/skipbo-art
LR=$S/references/styles/lr-render/refs
ROOM=$(cat prompts/room.txt)
export COMFY_RUNS_DIR="$PWD/room/runs"
mkdir -p room/runs room/components

# aspect = the shape of the item's box in layout.json, so the object is painted into a frame of its own proportions
aspect() {
  case "$1" in
    window) echo 3:4 ;; lamp) echo 1:1 ;; fireplace) echo 9:16 ;; sofa) echo 3:2 ;;
    rug) echo 16:9 ;; mess) echo 4:3 ;; tv) echo 4:3 ;; *) echo 1:1 ;;
  esac
}

while IFS="$(printf '\t')" read -r id component perspective placement check; do
  [ -z "$id" ] && continue
  if [ $# -gt 0 ]; then
    case " $* " in *" $id "*) ;; *) continue ;; esac
  fi
  py -3 $S/scripts/comfy.py run components \
    --image 1=game/assets/base.jpg --image 2=$LR/EXAMPLE_LR_block_01.png --image 3=$LR/EXAMPLE_LR_block_02.png \
    --var ROOM="$ROOM" --var COMPONENT="$component" --var PERSPECTIVE="$perspective" \
    --var PLACEMENT="$placement" --var CHECK="$check" \
    --var ASPECT="$(aspect "$id")" --var SIZE=2K --var MODE=BEN2 \
    --tag "comp-$id" \
    --criteria "one object only, whole, on flat grey, nothing else in frame" \
    --criteria "same eye level and light direction as the room" \
    --criteria "colour and saturation inside the room's palette" \
    > "room/runs/comp-$id.log" 2>&1 &
done < prompts/items.tsv
wait

for f in room/runs/comp-*.log; do printf '== %s\n' "$f"; tail -2 "$f"; done
# the cut-out is the second SaveImage of each run; collect it under its plain id
for d in room/runs/comp-*/; do
  id=$(basename "$d" | sed 's/^comp-//')
  last=$(ls -1 "$d" 2>/dev/null | grep -v '_flat' | grep -E '\.png$' | tail -1) || true
  [ -n "$last" ] && cp "$d$last" "room/components/$id.png" && echo "collected $id.png <- $last"
done
