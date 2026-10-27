#!/bin/zsh
# Key-pose reference frames of the approved beaver master (Nano Banana Pro, keypose.txt), one call per frame, in parallel.
#   scripts/gen_keyposes.sh [name ...]     default: every frame below
cd "${0:A:h}/.."
S=../../plugin/skills/skipbo-art
MASTER=../2026-10-15-beaver-jev-hands/beaver/beaver_master.png
SOIL=../2026-10-16-garden-grow/garden/props/plant_0.png
HURDLE=../2026-10-15-beaver-jev-hands/beaver/props/hurdle.png
FLAG=../2026-10-15-beaver-jev-hands/beaver/props/flag.png
export COMFY_RUNS_DIR=$PWD/runs
v() { grep "^$1=" prompts/keyposes.env | cut -d= -f2-; }
# name  prop-image  story  role  pose  placement  check
typeset -A F
F[half_crouch]="- SQUAT NONE HALF GROUND SQUAT"
F[plant_mid]="$SOIL PLANT SOIL PLANT_MID GROUND PLANT"
F[plant_low]="$SOIL PLANT SOIL PLANT_LOW GROUND PLANT"
F[hurdle_crouch]="$HURDLE HURDLE HURDLE HURDLE_CROUCH GROUND HURDLE"
F[hurdle_air]="$HURDLE HURDLE HURDLE HURDLE_AIR AIR HURDLE"
F[hurdle_land]="$HURDLE HURDLE HURDLE HURDLE_LAND GROUND HURDLE"
F[flag_out]="$FLAG FLAG FLAG FLAG_OUT AIR FLAG"
F[flag_in]="$FLAG FLAG FLAG FLAG_IN AIR FLAG"
names=(${@:-${(k)F}})
mkdir -p runs
for n in $names; do
  read img story role pose place check <<< "${F[$n]}"
  python3 $S/scripts/comfy.py run nb-pro --prompt-file $S/references/prompts/spine/keypose.txt \
    --image 1=$MASTER ${${img:#-}:+--image 2=$img} \
    --var PROP_ROLE="$(v ROLE_$role)" --var STORY="$(v STORY_$story)" --var POSE="$(v POSE_$pose)" \
    --var PLACEMENT="$(v PLACE_$place)" --var CHECK="$(v CHECK_$check)" --var CHARACTER="$(v CHARACTER)" \
    --var ASPECT=3:4 --var SIZE=2K --var TEMP=0.5 --tag kp-$n \
    --criteria "front view, no body turn" --criteria "same beaver, same scale as master" --criteria "$(v CHECK_$check)" \
    > runs/kp-$n.log 2>&1 &
done
wait
for n in $names; do echo "== $n"; tail -2 runs/kp-$n.log; done
