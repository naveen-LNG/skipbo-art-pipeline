#!/bin/zsh
# Body, hands, poses (tiptoe clogs), face, whole-arm and props sheets for the bear from the approved master
# (6 Nano Banana Pro calls, run in parallel). Usage: ./gen_sheets.sh [tag ...]  (no args = all six)
cd "${0:A:h}"
S=../../../plugin/skills/skipbo-art; P=$S/references/prompts/spine; HIPPO=$S/references/styles/blocks-characters/refs/shipped-hippo-atlas-small.jpg
export COMFY_RUNS_DIR=$PWD/runs
v() { grep "^$1=" prompts/bear.env | cut -d= -f2-; }
CH="$(v CHARACTER)"
run() { local tag=$1; shift; python3 $S/scripts/comfy.py run nb-pro --image 1=bear_master.png --image 2=$HIPPO --var CHARACTER="$CH" --tag $tag "$@" > runs/$tag.log 2>&1 }
mkdir -p runs
ARGS=("$@")
w() { [[ ${#ARGS} -eq 0 ]] || (( ${ARGS[(Ie)$1]} )) }
w bear-body  && run bear-body  --prompt-file $P/body-sheet.txt  --var PIECES="$(v PIECES)" --var ASPECT=1:1  --var TEMP=0.4 &
w bear-hands && run bear-hands --prompt-file $P/hands-sheet.txt --var HANDS="$(v HANDS)"   --var ASPECT=3:2  --var TEMP=0.4 &
w bear-poses && run bear-poses --prompt-file $P/poses-sheet.txt --var POSES="$(v POSES)"   --var ASPECT=16:9 --var TEMP=0.4 &
w bear-face  && run bear-face  --prompt-file $P/face-sheet.txt  --var ASPECT=1:1  --var TEMP=0.4 &
w bear-arms  && run bear-arms  --prompt-file prompts/arms-pair.txt --var SLEEVE="$(v SLEEVE)" --var ASPECT=4:3 --var TEMP=0.4 &
w bear-props && run bear-props --prompt-file $P/props-pair.txt  --var PROPS="$(v PROPS)"   --var ASPECT=4:3  --var TEMP=0.4 &
wait
tail -n 2 runs/*.log
