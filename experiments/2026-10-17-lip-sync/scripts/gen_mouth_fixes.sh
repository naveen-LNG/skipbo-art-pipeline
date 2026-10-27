#!/bin/zsh
# Re-roll mouth shapes that broke continuity, each an edit of the sheet's own head for that shape (2 variants each):
# E lost the front teeth, D had stretched cracked teeth, G was a lopsided smirk. L: scripts/gen_mouth_L.sh.
cd "${0:A:h}/../beaver"
export COMFY_RUNS_DIR=$PWD/runs
ks=("$@"); (( $#ks )) || ks=(D E G)
for k in $ks; do
  python3 ../../../plugin/skills/skipbo-art/scripts/comfy.py run nb-pro --prompt-file ../prompts/mouth-$k-edit.txt \
    --image 1=head_${k}_on_grey.png --var ASPECT=1:1 --var TEMP=0.4 --n 2 --tag beaver-mouth-$k > runs/mouth-$k.log 2>&1 &
done
wait
tail -n 2 runs/mouth-*.log
