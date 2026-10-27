#!/bin/zsh
# Build the beaver with the garden props (can, stream, plant stages), fit the plant under the stream, rebuild, QA.
cd "${0:A:h}"
S=../../../plugin/skills/skipbo-art; B=../../2026-10-15-beaver-jev-hands/beaver
build() { rm -rf rig; uv run -q $S/scripts/spine_rig.py --master $B/beaver_master.png --annotations annotations.json --props props.json --out rig > rig_build.log 2>&1 }
build && uv run -q --with numpy --with pillow ../scripts/fit_garden.py rig/beaver.json props.json && build
grep "doubt" rig_build.log | cut -c1-200
uv run -q $S/scripts/spine_qa.py rig/beaver.json --master $B/beaver_master.png 2>&1 | cut -c1-240 | grep -v '^PASS  [a-z_]* *{"frames'
