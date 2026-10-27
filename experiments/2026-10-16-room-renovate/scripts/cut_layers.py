"""Cut one RGBA layer per fixable item from its in-place edit of room/base.png.

The mask is where the edit differs from the base, kept inside the item's region box, cleaned (specks out,
gaps closed, holes filled), grown a little and feathered. Edits hold the frame pixel for pixel, so the grown
margin is base-coloured and does not show. Where two masks overlap, the item whose edit moved further from
the base keeps the pixel.

Writes game/assets/{base.jpg, layers/<id>.png, thumbs/<id>.png, layout.json} and room/six-fixed.png
(every layer applied), which the finale edit starts from.
Run: uv run --with pillow --with numpy --with scipy python scripts/cut_layers.py
"""
import glob, json, os
import numpy as np
from PIL import Image
from scipy import ndimage as nd

os.chdir(os.path.join(os.path.dirname(__file__), ".."))
# region boxes as fractions of the frame (x0, y0, x1, y1), generous; anything changed outside is noise
BOXES = {"mess": (0, .50, 1, 1), "rug": (.12, .62, 1, .93), "sofa": (0, .48, .62, .78),
         "fireplace": (.60, .05, 1, .76), "window": (0, .12, .62, .56), "lamp": (.30, 0, .85, .30)}
THRESH, GROW, FEATHER = 26, 6, 2.5
# the boxes are close to the floor in tone, so the mess needs a lower threshold and wider gap closing
TUNE = {"mess": (12, 24), "lamp": (18, 12)}   # id: (threshold, closing iterations)

base = np.asarray(Image.open("room/base.png").convert("RGB")).astype(np.float32)
H, W = base.shape[:2]
edits, score, masks = {}, {}, {}
for i, box in BOXES.items():
    f = sorted(glob.glob(f"room/runs/edit-{i}/*_00.png"))[-1]
    e = np.asarray(Image.open(f).convert("RGB").resize((W, H), Image.LANCZOS)).astype(np.float32)
    d = nd.gaussian_filter(np.abs(e - base).max(2), 1.5)
    x0, y0, x1, y1 = int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)
    m = np.zeros((H, W), bool); thr, close = TUNE.get(i, (THRESH, 8))
    m[y0:y1, x0:x1] = d[y0:y1, x0:x1] > thr
    P = close + 4                              # edge padding, so a mask that reaches the frame edge stays solid there
    m = np.pad(m, P, mode="edge")
    m = nd.binary_closing(nd.binary_opening(m, iterations=2), iterations=close)[P:-P, P:-P]
    lab, n = nd.label(m)                      # drop islands under 0.1% of the item's area
    if n:
        sizes = nd.sum(m, lab, range(1, n + 1)); keep = np.isin(lab, 1 + np.flatnonzero(sizes > 0.001 * sizes.sum()))
        m = keep
    m = nd.binary_fill_holes(m)
    edits[i], score[i], masks[i] = e, d, nd.binary_dilation(m, iterations=GROW)

ids = list(BOXES)
stack = np.stack([np.where(masks[i], score[i], -1) for i in ids])
owner = stack.argmax(0)
os.makedirs("game/assets/layers", exist_ok=True); os.makedirs("game/assets/thumbs", exist_ok=True)
Image.fromarray(base.astype(np.uint8)).save("game/assets/base.jpg", quality=90)
layout, comp = {"width": W, "height": H, "items": {}}, base.copy()
for k, i in enumerate(ids):
    m = masks[i] & (owner == k)
    a = nd.gaussian_filter(m.astype(np.float32), FEATHER)
    ys, xs = np.nonzero(a > 0.01); x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    rgba = np.dstack([edits[i], a * 255])[y0:y1, x0:x1].clip(0, 255).astype(np.uint8)
    Image.fromarray(rgba).save(f"game/assets/layers/{i}.png", optimize=True)
    t = Image.fromarray(rgba); t.thumbnail((180, 180), Image.LANCZOS); t.save(f"game/assets/thumbs/{i}.png")
    comp = comp * (1 - a[..., None]) + edits[i] * a[..., None]
    layout["items"][i] = {"x": int(x0), "y": int(y0), "w": int(x1 - x0), "h": int(y1 - y0), "px": int(m.sum())}
    print(f"{i:10s} box {x0},{y0} {x1 - x0}x{y1 - y0}  mask {m.sum() / (W * H):.1%}")
Image.fromarray(comp.astype(np.uint8)).save("room/six-fixed.png")
json.dump(layout, open("game/assets/layout.json", "w"), indent=1)
