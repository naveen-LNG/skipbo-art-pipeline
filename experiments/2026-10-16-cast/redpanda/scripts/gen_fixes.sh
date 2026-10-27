#!/bin/zsh
# Fix calls after the sheet checkpoints. Usage: scripts/gen_fixes.sh point-palm
cd "${0:A:h}/.."
S=../../../plugin/skills/skipbo-art; P=$S/references/prompts/spine; HIPPO=$S/references/styles/blocks-characters/refs/shipped-hippo-atlas-small.jpg
export COMFY_RUNS_DIR=$PWD/runs
v() { grep "^$1=" prompts/redpanda.env | cut -d= -f2-; }
CH="$(v CHARACTER)"
run() { tag=$1; shift; python3 $S/scripts/comfy.py run nb-pro --image 1=redpanda_master.png --image 2=$HIPPO --var CHARACTER="$CH" --var TEMP=0.4 --tag redpanda-$tag "$@" > runs/redpanda-$tag.log 2>&1
        python3 $S/scripts/comfy.py run parts-split --image 1=$(ls runs/redpanda-$tag/*_00.png | head -1) --tag redpanda-$tag-parts >> runs/redpanda-$tag.log 2>&1 }
for t in "$@"; do case $t in
  point-palm2) run point-palm2 --prompt-file $P/hands-point-palm.txt --var HANDS="$(v POINT2)" --var ASPECT=4:3 & ;;
  point-palm) run point-palm --prompt-file $P/hands-point-palm.txt --var HANDS="$(v POINT)" --var ASPECT=4:3 & ;;
esac; done
wait
for t in "$@"; do echo "$t: $(ls runs/redpanda-$t-parts/*_[0-9][0-9].png 2>/dev/null | wc -l) pieces"; done
