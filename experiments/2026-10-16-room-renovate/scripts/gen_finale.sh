#!/bin/zsh
# Finale: new wallpaper, clean ceiling, polished floor, straight picture, warm light, edited from the six-fixed composite (1 Nano Banana Pro call). Run cut_layers.py first.
cd "${0:A:h}/../room"
S=../../../plugin/skills/skipbo-art
export COMFY_RUNS_DIR=$PWD/runs
python3 $S/scripts/comfy.py run nb-pro --prompt-file ../prompts/finale.txt --image 1=six-fixed.png \
  --var ASPECT=9:16 --var SIZE=2K --var TEMP=0.4 --tag edit-finale2 --n 2 \
  --criteria "new wallpaper, clean ceiling, polished floor, picture level" --criteria "same camera and framing" > runs/edit-finale2.log 2>&1
tail -1 runs/edit-finale2.log
# Touch-up pass on the chosen finale (copied to finale-pass1.png): level the picture, polish the floor (2 calls)
python3 $S/scripts/comfy.py run nb-pro --prompt-file ../prompts/finale-touchup.txt --image 1=finale-pass1.png \
  --var ASPECT=9:16 --var SIZE=2K --var TEMP=0.35 --n 2 --tag edit-finale-touchup \
  --criteria "picture frame level" --criteria "floor clean, no scratches" > runs/edit-finale-touchup.log 2>&1
tail -2 runs/edit-finale-touchup.log
