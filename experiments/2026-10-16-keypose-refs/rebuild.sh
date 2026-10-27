#!/bin/zsh
# Cut the legs drawings from the in-between sheets, build rig_kp/ from the beaver rig, QA it, render the comparisons.
cd "${0:A:h}"
S=../../plugin/skills/skipbo-art; B=../2026-10-15-beaver-jev-hands/beaver
R() { uv run -q --with numpy --with pillow --with scipy python scripts/cut_legs.py "$@"; }
: > legs/metrics.jsonl
uv run -q --with numpy --with pillow --with scipy python scripts/render_rest_legs.py $B/rig/beaver.json legs/rig_rest.png 1.5
for s in squat jump; do
  uv run -q --with numpy --with pillow --with scipy python scripts/cut_sheet.py refs/legs_sheet_$s.png $s $B/rig/images
done
for m in "s34 squat_3 squat_4 squat_34" "s45 squat_4 squat_5 squat_45" "j23 jump_2 jump_3 jump_23" "j34 jump_3 jump_4 jump_34"; do
  set -- ${=m}; uv run -q --with numpy --with pillow --with scipy python scripts/cut_mid.py refs/legs_mid_$1.png $2 $3 $4 $B/rig/images
done
uv run -q --with numpy --with pillow --with scipy --with scikit-image python scripts/leg_joints.py
KP_LEGS=bones uv run -q --with numpy --with pillow --with scipy python scripts/kp_rig.py $B/rig rig_bones > /dev/null   # skeleton-driven legs
KP_LEGS=bones KP_HYBRID=1 uv run -q --with numpy --with pillow --with scipy python scripts/kp_rig.py $B/rig rig_hybrid > /dev/null   # + paintings at the holds
rm -rf rig_hybrid2 && cp -r rig_hybrid rig_hybrid2 && uv run -q --with numpy --with pillow python scripts/match_handover.py rig_hybrid2/beaver.json   # box-matched hand-overs
KP_SKIN=1 KP_LEGS=bones KP_HYBRID=1 uv run -q --with numpy --with pillow --with scipy python scripts/kp_rig.py $B/rig rig_hybrid3 > /dev/null   # paintings skinned to the bones
KP_MORPH=1 KP_LEGS=bones KP_HYBRID=1 uv run -q --with numpy --with pillow --with scipy python scripts/kp_rig.py $B/rig rig_morph > /dev/null   # + per-vertex morph at the hand-overs
for r in rig_hybrid rig_hybrid2 rig_hybrid3 rig_morph; do uv run -q --with numpy --with pillow python scripts/halo.py $r/beaver.json squat jump_hurdle; done
KP_PREV=1 uv run -q --with numpy --with pillow --with scipy python scripts/kp_rig.py $B/rig rig_prev > /dev/null   # the previous pass, to compare
uv run -q --with numpy --with pillow --with scipy python scripts/kp_rig.py $B/rig rig_kp
uv run -q $S/scripts/spine_qa.py rig_kp/beaver.json --master $B/beaver_master.png 2>&1 | cut -c1-160
uv run -q --with numpy --with pillow python scripts/compare.py $B/rig/beaver.json rig_kp/beaver.json results/keyposes_vs_rig.png
for a in squat jump_hurdle wave_flag; do uv run -q --with numpy --with pillow python scripts/before_after.py $B/rig/beaver.json rig_kp/beaver.json $a results; done
uv run -q --with numpy --with pillow python scripts/before_after.py $B/rig/beaver.json rig_kp/beaver.json plant_seed squat results
uv run -q --with numpy --with pillow python scripts/jerk.py rig_kp/beaver.json jump_hurdle torso hand_l
for r in rig_prev rig_kp; do echo "== $r"; uv run -q --with numpy --with pillow python scripts/pops.py $r/beaver.json squat plant_seed jump_hurdle; done
