# /// script
# dependencies = ["pillow"]
# ///
import json, sys
from PIL import Image, ImageDraw
lab = [json.loads(l) for l in open("jref/labels_gt.jsonl")]
sc = {m: {json.loads(l)["id"]: json.loads(l)["answers"]["detached"]["noul"] for l in open(f"jref/results_jref_{p}.jsonl")}
      for m, p in [("F", "cloudflare_clef-flash"), ("C", "cloudflare_clef"), ("J", "typesafe_jev-1.14.0")]}
ids = [r["id"] for r in lab if r["id"].split("__")[0].endswith("_clean")]
T = 260; tiles = []
for i in ids:
    m, r = Image.open(f"jref/{i}__ref.jpg").resize((T, T)), Image.open(f"jref/{i}.jpg").resize((T, T))
    t = Image.new("RGB", (2 * T + 6, T + 26), "white"); t.paste(m, (0, 26)); t.paste(r, (T + 6, 26))
    ImageDraw.Draw(t).text((4, 6), f"{i.replace('_clean__', ' ')}   master | render   Flash {sc['F'][i]:.2f}  27B {sc['C'][i]:.2f}  Jev {sc['J'][i]:.2f}", fill=(0, 0, 0))
    tiles.append(t)
cols = 3; W = tiles[0].width; Hh = tiles[0].height
s = Image.new("RGB", (cols * W + 10 * (cols - 1), ((len(tiles) + cols - 1) // cols) * (Hh + 10)), "white")
for k, t in enumerate(tiles): s.paste(t, ((k % cols) * (W + 10), (k // cols) * (Hh + 10)))
s.save("audit_clean.png"); print(len(tiles))
