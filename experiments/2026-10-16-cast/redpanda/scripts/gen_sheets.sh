#!/bin/zsh
# Body, hands, poses, face, sleeves and props sheets from the approved master (6 Nano Banana Pro calls in parallel),
# each split into pieces. Usage: scripts/gen_sheets.sh [tag ...]   (default: all six)
cd "${0:A:h}/.."
S=../../../plugin/skills/skipbo-art; P=$S/references/prompts/spine; HIPPO=$S/references/styles/blocks-characters/refs/shipped-hippo-atlas-small.jpg
export COMFY_RUNS_DIR=$PWD/runs
v() { grep "^$1=" prompts/redpanda.env | cut -d= -f2-; }
CH="$(v CHARACTER)"
run() { tag=$1; shift; python3 $S/scripts/comfy.py run nb-pro --image 1=redpanda_master.png --image 2=$HIPPO --var CHARACTER="$CH" --var TEMP=0.4 --tag redpanda-$tag "$@" > runs/redpanda-$tag.log 2>&1
        python3 $S/scripts/comfy.py run parts-split --image 1=$(ls runs/redpanda-$tag/*_00.png | head -1) --tag redpanda-$tag-parts >> runs/redpanda-$tag.log 2>&1 }
want() { [[ $# -eq 0 ]] && return 0; (( ${ALL[(Ie)$1]} )) }
ALL=("$@"); [[ ${#ALL} -eq 0 ]] && ALL=(body hands poses face sleeves props)
mkdir -p runs
(( ${ALL[(Ie)body]} ))    && run body    --prompt-file $P/body-sheet.txt  --var PIECES="$(v PIECES)" --var ASPECT=1:1 &
(( ${ALL[(Ie)hands]} ))   && run hands   --prompt-file $P/hands-sheet.txt --var HANDS="$(v HANDS)"   --var ASPECT=3:2 &
(( ${ALL[(Ie)poses]} ))   && run poses   --prompt-file $P/poses-sheet.txt --var POSES="$(v POSES)"   --var ASPECT=1:1 &
(( ${ALL[(Ie)face]} ))    && run face    --prompt-file $P/face-sheet.txt  --var ASPECT=1:1 &
(( ${ALL[(Ie)sleeves]} )) && run sleeves --prompt-file $P/sleeves-pair.txt --var SLEEVE="$(v SLEEVE)" --var ASPECT=4:3 &
(( ${ALL[(Ie)props]} ))   && run props   --prompt-file $P/props-pair.txt  --var PROPS="$(v PROPS)"   --var ASPECT=4:3 &
wait
for t in $ALL; do echo "$t: $(ls runs/redpanda-$t-parts/*_[0-9][0-9].png 2>/dev/null | wc -l) pieces"; tail -1 runs/redpanda-$t.log; done
