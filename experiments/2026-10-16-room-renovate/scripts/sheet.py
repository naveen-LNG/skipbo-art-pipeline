"""Contact sheet: base + every edit, each with its diff heat map against the base (for checking edits stay in place)."""
import sys, glob, numpy as np
from PIL import Image
out = sys.argv[1]; ids = "window lamp fireplace sofa rug mess walls".split()
base = np.asarray(Image.open("room/base.png").convert("RGB")).astype(np.int16)
tiles = [("base", Image.fromarray(base.astype(np.uint8)))]
for i in ids:
    f = sorted(glob.glob(f"room/runs/edit-{i}/*_00.png"))[-1]
    e = np.asarray(Image.open(f).convert("RGB").resize(base.shape[1::-1])).astype(np.int16)
    d = np.abs(e - base).sum(2).clip(0, 255).astype(np.uint8)
    tiles += [(i, Image.fromarray(e.astype(np.uint8))), (i + " diff", Image.fromarray(d).convert("RGB"))]
s = 0.18; w, h = int(1536 * s), int(2752 * s); cols = 5
sheet = Image.new("RGB", (cols * (w + 8), ((len(tiles) + cols - 1) // cols) * (h + 8)), "white")
for k, (n, im) in enumerate(tiles):
    sheet.paste(im.resize((w, h)), ((k % cols) * (w + 8), (k // cols) * (h + 8)))
sheet.save(out); print(sheet.size)
