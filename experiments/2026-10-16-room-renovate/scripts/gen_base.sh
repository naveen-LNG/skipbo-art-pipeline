#!/bin/zsh
# The "before" room: LR style block + room scene, two variants to pick from (2 Nano Banana Pro calls).
cd "${0:A:h}/../room"
S=../../../plugin/skills/skipbo-art; LR=$S/references/styles/lr-render/refs
export COMFY_RUNS_DIR=$PWD/runs; mkdir -p runs
cat ../prompts/lr-block.txt ../prompts/room-scene.txt > ../prompts/room-full.txt
python3 $S/scripts/comfy.py run nb-pro --prompt-file ../prompts/room-full.txt \
  --image 1=$LR/EXAMPLE_LR_block_01.png --image 2=$LR/EXAMPLE_LR_block_02.png \
  --var ASPECT=9:16 --var SIZE=2K --var TEMP=1.0 --n 2 --tag room-base \
  --criteria "six fixable items in their own places, none overlapping" --criteria "open rug in the middle, no characters, no text"
