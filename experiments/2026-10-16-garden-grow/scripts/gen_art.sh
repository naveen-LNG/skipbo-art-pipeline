#!/bin/zsh
# Garden art: watering can + water stream (props pair), five plant stages (one sheet), the lawn scene (LR render).
# 3 Nano Banana Pro calls in parallel, then the two sheets are split into pieces.
cd "${0:A:h}/../garden"
S=../../../plugin/skills/skipbo-art; P=$S/references/prompts/spine
MASTER=../../2026-10-15-beaver-jev-hands/beaver/beaver_master.png
HIPPO=$S/references/styles/blocks-characters/refs/shipped-hippo-atlas-small.jpg
LR=$S/references/styles/lr-render/refs
export COMFY_RUNS_DIR=$PWD/runs
v() { grep "^$1=" ../prompts/garden.env | cut -d= -f2-; }
sheet() { tag=$1; shift; python3 $S/scripts/comfy.py run nb-pro --image 1=$MASTER --image 2=$HIPPO --var CHARACTER="$(v CHARACTER)" --var TEMP=0.4 --tag $tag "$@" > runs/$tag.log 2>&1
          python3 $S/scripts/comfy.py run parts-split --image 1=$(ls -t runs/$tag/*_00.png | head -1) --tag $tag-parts >> runs/$tag.log 2>&1 }
mkdir -p runs
sheet garden-props --prompt-file $P/props-pair.txt --var PROPS="$(v PROPS)" --var ASPECT=4:3 \
  --criteria "blue watering can side view, spout right" --criteria "one connected water stream" &
sheet garden-stages --prompt-file ../prompts/plant-stages.txt --var STAGES="$(v STAGES)" --var ASPECT=16:9 \
  --criteria "five stages seed to flower" --criteria "identical soil mound, same baseline" &
python3 $S/scripts/comfy.py run nb-pro --prompt-file ../prompts/lawn-full.txt --image 1=$LR/EXAMPLE_LR_block_01.png --image 2=$LR/EXAMPLE_LR_block_02.png \
  --var ASPECT=9:16 --var SIZE=2K --var TEMP=1.0 --tag garden-lawn --criteria "open empty lawn middle" --criteria "no characters, no text" > runs/garden-lawn.log 2>&1 &
wait
for t in props stages lawn; do echo "== $t"; tail -2 runs/garden-$t.log; done
