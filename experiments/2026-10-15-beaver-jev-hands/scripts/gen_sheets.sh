#!/bin/zsh
# Body, hands, poses and face sheets for the beaver from the approved master (4 Nano Banana Pro calls, run in parallel).
cd "${0:A:h}/../beaver"
S=../../../plugin/skills/skipbo-art; P=$S/references/prompts/spine; HIPPO=$S/references/styles/blocks-characters/refs/shipped-hippo-atlas-small.jpg
export COMFY_RUNS_DIR=$PWD/runs
v() { grep "^$1=" ../prompts/beaver.env | cut -d= -f2-; }
CH="$(v CHARACTER)"
run() { python3 $S/scripts/comfy.py run nb-pro --image 1=beaver_master.png --image 2=$HIPPO --var CHARACTER="$CH" "$@" > runs/$(echo "$@" | grep -o 'beaver-[a-z]*' | head -1).log 2>&1 }
mkdir -p runs
run --prompt-file $P/body-sheet.txt --var PIECES="$(v PIECES)" --var ASPECT=1:1 --var TEMP=0.4 --tag beaver-body &
run --prompt-file $P/hands-sheet.txt --var HANDS="$(v HANDS)" --var ASPECT=3:2 --var TEMP=0.4 --tag beaver-hands &
run --prompt-file $P/poses-sheet.txt --var POSES="$(v POSES)" --var ASPECT=1:1 --var TEMP=0.4 --tag beaver-poses &
run --prompt-file $P/face-sheet.txt --var ASPECT=1:1 --var TEMP=0.4 --tag beaver-face &
wait
tail -3 runs/*.log
