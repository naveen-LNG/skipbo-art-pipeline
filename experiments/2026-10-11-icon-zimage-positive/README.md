# Experiment 2026-10-11: positive-only icon block on Z-Image

The original Icon - Skip-Bo block feeds `--avoid …`/`NOT …` to Z-Image at cfg 1, where negations act as positive conditioning. This experiment rewrote it positively (`plugin/skills/skipbo-art/references/styles/icon/block-zimage.md`) and ran it once, 2 seeds, on the local GPU at no API cost.

- Prompt: [`prompt.txt`](prompt.txt) (subject 70 words + block). `comfy.py lint --engine zimage` passes.
- Result: [`runs/honey-dew-pot/`](runs/honey-dew-pot/). Both seeds are on-model for the house icon look (chunky painted pot, hue-shifted shading, coloured outlines, no text). Both have a soft ground shadow.
- About 95 s per image.
