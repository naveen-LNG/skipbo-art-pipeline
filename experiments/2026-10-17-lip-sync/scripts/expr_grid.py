#!/usr/bin/env python3
"""Can one mouth set talk over every expression head? Grid: expression heads (rows) x mouth shapes (columns).
    uv run --with pillow scripts/expr_grid.py <face-heads dir> <mouths dir> <out.png>"""
import sys
from PIL import Image, ImageDraw
heads, mouths, out = sys.argv[1:4]
rows, cols = ["neutral", "happy", "sad", "angry", "surprised", "laugh"], ["none", "X", "A", "C", "D", "F", "G"]
cell = None
tiles = []
for r in rows:
    h = Image.open(f"{heads}/beaver_head_{r}.png").convert("RGBA")
    for c in cols:
        t = Image.new("RGBA", h.size, (214, 214, 214, 255)); t.alpha_composite(h)
        if c != "none":
            t.alpha_composite(Image.open(f"{mouths}/mouth_{c}.png").convert("RGBA").resize(h.size))
        t = t.crop((40, 60, h.width - 40, h.height)).convert("RGB").resize((240, 200))
        ImageDraw.Draw(t).text((4, 2), f"{r} / {c}", fill=(120, 0, 0))
        tiles.append(t)
g = Image.new("RGB", (240 * len(cols), 200 * len(rows)))
for i, t in enumerate(tiles):
    g.paste(t, ((i % len(cols)) * 240, (i // len(cols)) * 200))
g.save(out)
