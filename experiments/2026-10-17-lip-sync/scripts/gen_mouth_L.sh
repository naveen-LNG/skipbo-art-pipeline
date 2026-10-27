#!/bin/zsh
# Re-roll the "L" mouth shape (sheet _00 drew a tongue-out "blep"): an edit of the sheet's own "eh" head. 1 Nano Banana Pro call, 2 variants.
cd "${0:A:h}/../beaver"
export COMFY_RUNS_DIR=$PWD/runs
python3 ../../../plugin/skills/skipbo-art/scripts/comfy.py run nb-pro --prompt-file ../prompts/mouth-L-edit.txt \
  --image 1=head_C_on_grey.png --var ASPECT=1:1 --var TEMP=0.4 --n 2 --tag beaver-mouth-L \
  --criteria "tongue tip behind the front teeth, inside the mouth; everything else unchanged"
