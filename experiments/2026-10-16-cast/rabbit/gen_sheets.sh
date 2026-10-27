#!/bin/zsh
# Body, hands, face, sleeves and props sheets for the rabbit from the approved master (5 Nano Banana Pro calls, parallel).
cd "${0:A:h}"
S=../../../plugin/skills/skipbo-art; P=$S/references/prompts/spine; HIPPO=$S/references/styles/blocks-characters/refs/shipped-hippo-atlas-small.jpg
export COMFY_RUNS_DIR=$PWD/runs
v() { grep "^$1=" prompts/rabbit.env | cut -d= -f2-; }
CH="$(v CHARACTER)"
run() { local tag=$1; shift; python3 $S/scripts/comfy.py run nb-pro --image 1=rabbit_master.png --image 2=$HIPPO --var CHARACTER="$CH" --var TEMP=0.4 --tag $tag "$@" > runs/$tag.log 2>&1 }
mkdir -p runs
run rabbit-body    --prompt-file $P/body-sheet.txt    --var PIECES="$(v PIECES)" --var ASPECT=1:1 &
run rabbit-hands   --prompt-file $P/hands-sheet.txt   --var HANDS="$(v HANDS)"   --var ASPECT=3:2 &
run rabbit-face    --prompt-file $P/face-sheet.txt    --var ASPECT=1:1 &
run rabbit-sleeves --prompt-file $P/sleeves-pair.txt  --var SLEEVE="$(v SLEEVE)" --var ASPECT=4:3 &
run rabbit-props   --prompt-file $P/props-pair.txt    --var PROPS="$(v PROPS)"   --var ASPECT=4:3 &
wait
tail -2 runs/rabbit-{body,hands,face,sleeves,props}.log
