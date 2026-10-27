# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Slice the human-reviewed before/after sheets into labelled tiles (text labels cropped away).
Tiles sit on grey 214; labels sit on white strips above them, so cropping each tile to its grey area drops the text."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image

EXP = Path("/work/comfy/experiments/2026-10-11-rig-annotations")
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
# sheet, columns per row, label per row (True = defect the reviewer rejected), kind of the defect
SHEETS = [("before_after_fox.png", 6, [True, False], "reviewer_rejected"),
          ("before_after_moose.png", 5, [True, False], "reviewer_rejected"),
          ("shoulders_ab_fox.png", 4, [True, False], "layer_order"),
          ("shoulders_ab_moose.png", 4, [True, False], "layer_order")]


def runs(b):
    out, start = [], None
    for i, v in enumerate(list(b) + [False]):
        if v and start is None: start = i
        if not v and start is not None: out.append((start, i)); start = None
    return out


rows_out = []
for name, ncol, labels, kind in SHEETS:
    a = np.asarray(Image.open(EXP / name).convert("RGB")).astype(int)
    white = (a > 245).all(-1)
    band_rows = runs(~(white.mean(1) > 0.97))               # vertical bands that are not all white
    bands = [(y0, y1) for y0, y1 in band_rows if y1 - y0 > 150]
    assert len(bands) == len(labels), (name, band_rows)
    for r, ((y0, y1), lab) in enumerate(zip(bands, labels)):
        sub = a[y0:y1]
        grey_cols = (np.abs(sub - 214) <= 3).all(-1).any(0)
        cols = [c for c in runs(grey_cols) if c[1] - c[0] > 100]
        if len(cols) != ncol:                               # tiles abut: split the grey extent evenly
            x0, x1 = cols[0][0], cols[-1][1]; w = (x1 - x0) / ncol
            cols = [(int(x0 + i * w), int(x0 + (i + 1) * w)) for i in range(ncol)]
        for c, (x0, x1) in enumerate(cols):
            tile = sub[:, x0:x1]
            g = (np.abs(tile - 214) <= 3).all(-1)
            ys = np.nonzero(g.any(1))[0]
            tile = tile[ys.min():ys.max() + 1]               # grey area only: drops the white label strip
            g = (np.abs(tile - 214) <= 6).all(-1)
            ys, xs = np.nonzero(~g)
            m = 25
            tile = tile[max(0, ys.min() - m):ys.max() + m, max(0, xs.min() - m):xs.max() + m]
            im = Image.fromarray(tile.astype(np.uint8)); im.thumbnail((768, 768))
            tid = f"real_{Path(name).stem}_r{r}_c{c}"
            im.save(OUT / f"{tid}.png")
            rows_out.append(dict(id=tid, sheet=name, row=r, col=c, defect=lab, kind=kind if lab else "none",
                                 char="fox" if "fox" in name else "moose", pair=f"{Path(name).stem}_c{c}"))
with open(OUT / "labels.jsonl", "w") as f:
    for r in rows_out: f.write(json.dumps(r) + "\n")
print(len(rows_out), "tiles", sum(r["defect"] for r in rows_out), "defects")
