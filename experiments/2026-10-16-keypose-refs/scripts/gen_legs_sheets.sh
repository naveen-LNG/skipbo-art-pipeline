#!/bin/zsh
# In-between legs sheets (prompts/legs-inbetweens.txt): squat and jump, eight drawings each in two rows of four.
cd "${0:A:h}/.."
S=../../plugin/skills/skipbo-art; M=../2026-10-15-beaver-jev-hands/beaver/beaver_master.png
export COMFY_RUNS_DIR=$PWD/runs
v() { grep "^$1=" prompts/keyposes.env | cut -d= -f2-; }
L="in two rows of four, read like text: drawings 1 to 4 in the top row from left to right, drawings 5 to 8 in the bottom row from left to right"
sheet() {  # tag target steps rest move
  python3 $S/scripts/comfy.py run nb-pro --prompt-file prompts/legs-inbetweens.txt --image 1=$M --image 2=refs/$2.png --image 3=legs/rig_rest_grey.png \
    --var COUNT=eight --var LAYOUT="$L" --var MOVE="$5" --var STEPS="$(v $3)" --var REST_USE="$(v $4)" --var CHARACTER="$(v CHARACTER)" \
    --var ASPECT=16:9 --var SIZE=4K --var TEMP=0.4 --tag $1 --criteria "8 lower bodies in 2 rows of 4, even small steps" --criteria "chunky like image_3, same painting" > runs/$1.log 2>&1
}
sheet legs8b-squat hurdle_crouch STEPS_SQUAT8 REST_SQUAT "$(v MOVE_SQUAT)" &
sheet legs8b-jump hurdle_air STEPS_JUMP8 REST_JUMP "The movement: from standing as in image_3 the legs push off the ground, straight and stretched on their toes, then fold up under the belt into the tucked jump of image_2." &
wait; tail -1 runs/legs8b-*.log
