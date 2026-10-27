#!/bin/zsh
# Mouth decals on the rig muzzle (sheet _00 + the re-rolled shapes; v1 muzzle patches: extract_mouths.py), Spine rig copy, review videos and sync check, from the existing audio/cues.
cd "${0:A:h}/.."
uv run -q --with numpy --with pillow --with scipy --with opencv-python-headless python scripts/mouth_decals.py beaver/runs/beaver-mouths/1017_130218_s1783308165_n2_00.png \
  --heads ../2026-10-15-beaver-jev-hands/beaver/face-heads --out beaver/mouths \
  --replace H=beaver/runs/beaver-mouth-L/1017_132458_s120575337_n2_00.png \
  --replace D=beaver/runs/beaver-mouth-D/1017_132658_s2029136600_n2_00.png \
  --replace E=beaver/runs/beaver-mouth-E/1017_132842_s2142203522_n2_01.png \
  --replace G=beaver/runs/beaver-mouth-G/1017_132750_s2084108946_n2_01.png
uv run -q --with pillow python scripts/spine_talk.py ../2026-10-15-beaver-jev-hands/beaver/rig beaver/rig_talk --mouths beaver/mouths --line results/line1 --line results/line2
for l in line1 line2; do
  uv run -q --with numpy --with pillow --with imageio-ffmpeg python scripts/render.py results/$l --heads ../2026-10-15-beaver-jev-hands/beaver/face-heads --mouths beaver/mouths
done
uv run -q --with pillow python scripts/expr_grid.py ../2026-10-15-beaver-jev-hands/beaver/face-heads beaver/mouths results/expressions_x_mouths.png
