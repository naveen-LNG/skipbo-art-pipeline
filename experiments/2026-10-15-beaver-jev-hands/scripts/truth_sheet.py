# /// script
# dependencies = ["pillow"]
# ///
"""Contact sheet of a test set with the ground-truth arrows drawn: green = fingers, red = thumb. For checking labels by eye.
  uv run truth_sheet.py <set dir> <out.png> [filter substring] [max]"""
import json, math, sys
from pathlib import Path
from PIL import Image, ImageDraw
d = Path(sys.argv[1]); flt = sys.argv[3] if len(sys.argv) > 3 else ""; mx = int(sys.argv[4]) if len(sys.argv) > 4 else 48
rows = [json.loads(l) for l in open(d / "labels.jsonl") if flt in l][:mx]
T = 224; cols = 8
sheet = Image.new("RGB", (cols * T, ((len(rows) + cols - 1) // cols) * (T + 28)), "white")
for i, r in enumerate(rows):
    im = Image.open(d / f"{r['id']}.png").convert("RGB").resize((T, T)); dr = ImageDraw.Draw(im)
    c = T / 2
    for k, col in (("finger_deg", (0, 160, 0)), ("thumb_deg", (220, 0, 0))):
        a = math.radians(r[k]); dr.line([c, c, c + 80 * math.cos(a), c - 80 * math.sin(a)], fill=col, width=4)
    x, y = (i % cols) * T, (i // cols) * (T + 28)
    sheet.paste(im, (x, y))
    ImageDraw.Draw(sheet).text((x + 3, y + T + 2), f"{r['variant']} {r['facing']} {r.get('painted', r.get('side'))}\n{r['id'].split('__', 1)[1][:34]}", fill="black")
sheet.save(sys.argv[2]); print(sys.argv[2])
