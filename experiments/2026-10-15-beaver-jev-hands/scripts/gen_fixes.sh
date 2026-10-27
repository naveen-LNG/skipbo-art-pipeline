#!/bin/zsh
# Round 3 art: whole sleeves (one bending mesh per arm), a palm-facing fist, hips + cuffed legs + a tail as the master
# holds it. 3 Nano Banana Pro calls in parallel, then split.
cd "${0:A:h}/../beaver"
S=../../../plugin/skills/skipbo-art; P=$S/references/prompts/spine; HIPPO=$S/references/styles/blocks-characters/refs/shipped-hippo-atlas-small.jpg
export COMFY_RUNS_DIR=$PWD/runs
v() { grep "^$1=" ../prompts/beaver.env | cut -d= -f2-; }
CH="$(v CHARACTER)"
run() { tag=$1; shift; python3 $S/scripts/comfy.py run nb-pro --image 1=beaver_master.png --image 2=$HIPPO --var CHARACTER="$CH" --tag $tag "$@" > runs/$tag.log 2>&1
        python3 $S/scripts/comfy.py run parts-split --image 1=$(ls runs/$tag/*_00.png) --tag $tag-parts >> runs/$tag.log 2>&1 }
run beaver-sleeves --prompt-file $P/poses-sheet.txt --var POSES="$(v SLEEVES)" --var ASPECT=1:1 --var TEMP=0.4 &
run beaver-fist-palm --prompt-file ../prompts/hands-fist-palm.txt --var HANDS="$(v FIST)" --var ASPECT=4:3 --var TEMP=0.4 &
run beaver-lower --prompt-file $P/body-sheet.txt --var PIECES="$(v LOWER)" --var ASPECT=1:1 --var TEMP=0.4 &
wait
for t in sleeves fist-palm lower; do echo "$t: $(ls runs/beaver-$t-parts/*_[0-9][0-9].png 2>/dev/null | wc -l) pieces"; tail -1 runs/beaver-$t.log; done
