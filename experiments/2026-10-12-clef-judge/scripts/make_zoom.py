# /// script
# dependencies = ["pillow"]
# ///
"""Two-pass Box: crop each joint crop tightly around Jev's first box (padded 35%) and upscale it, so the part fills
the image. zoom/labels.jsonl keeps the window (fractions of the joint crop) to map the second box back."""
import json
from pathlib import Path
from PIL import Image
H = Path(__file__).parent; J = H / "jref"; Z = H / "zoom"; Z.mkdir(exist_ok=True)
lab = [json.loads(l) for l in open(J / "labels_gt.jsonl")]
first = {json.loads(l)["id"]: json.loads(l)["answers"]["box_render"] for l in open(J / "results_joint_typesafe_jev-1.14.0.jsonl")}
rows = []
for r in lab:
    if not (r["defect"] or r["id"].split("__")[0].endswith("_clean")): continue
    b = first[r["id"]]["box"]; w, h = b["right"] - b["left"], b["bottom"] - b["top"]; p = 0.35
    w2, h2 = max(w * (1 + 2 * p), 0.5 * h * (1 + 2 * p)), max(h * (1 + 2 * p), 0.5 * w * (1 + 2 * p))   # aspect at most 2:1
    cx, cy = (b["left"] + b["right"]) / 2, (b["top"] + b["bottom"]) / 2
    win = [max(0, cx - w2 / 2), max(0, cy - h2 / 2), min(1, cx + w2 / 2), min(1, cy + h2 / 2)]
    im = Image.open(J / f"{r['id']}.jpg"); W, Hh = im.size
    c = im.crop((round(win[0] * W), round(win[1] * Hh), round(win[2] * W), round(win[3] * Hh)))
    k = min(max(448 / max(c.size), 320 / min(c.size), (80000 / (c.width * c.height)) ** 0.5), 1568 / max(c.size))
    c = c.resize((min(1568, max(320, round(c.width * k))), min(1568, max(320, round(c.height * k)))), Image.LANCZOS)
    c.save(Z / f"{r['id']}.jpg", quality=92)
    rows.append(dict(r, zoom_window=[round(v, 5) for v in win], first_box=b))
with open(Z / "labels.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
print(len(rows), "zoom crops")
