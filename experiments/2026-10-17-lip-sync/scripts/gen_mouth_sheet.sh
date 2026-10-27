#!/bin/zsh
# Nine mouth-shape (viseme) heads for the beaver from its approved neutral head: 1 Nano Banana Pro call (--n 2 variants), then split.
cd "${0:A:h}/../beaver"
S=../../../plugin/skills/skipbo-art
export COMFY_RUNS_DIR=$PWD/runs
CH="$(grep '^CHARACTER=' ../../2026-10-15-beaver-jev-hands/prompts/beaver.env | cut -d= -f2-)"
python3 $S/scripts/comfy.py run nb-pro --prompt-file ../prompts/mouth-sheet.txt \
  --image 1=neutral_on_grey.png --image 2=face_sheet_ref.png --var CHARACTER="$CH" \
  --var ASPECT=1:1 --var TEMP=0.4 --n 2 --tag beaver-mouths \
  --criteria "nine heads, identical eyes/nose/outline, only the mouth differs, each viseme distinct"
