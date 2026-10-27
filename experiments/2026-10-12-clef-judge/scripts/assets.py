# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Encode the example images for the report page as JPEG data URIs (assets.json).
Defective synthetic frames get a second copy with a dashed box around the changed pixels (diff vs the clean frame)."""
import base64, io, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

H = Path(__file__).parent


def uri(im, w=460, q=80):
    im = im.convert("RGB"); im.thumbnail((w, w * 2))
    b = io.BytesIO(); im.save(b, "JPEG", quality=q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def marked(bad, clean):
    a, c = np.asarray(bad.convert("RGB")).astype(int), np.asarray(clean.convert("RGB")).astype(int)
    if a.shape != c.shape: return bad
    ys, xs = np.nonzero(np.abs(a - c).sum(-1) > 30)
    im = bad.convert("RGB").copy()
    if len(ys):
        d = ImageDraw.Draw(im); x0, y0, x1, y1 = xs.min() - 8, ys.min() - 8, xs.max() + 8, ys.max() + 8
        for i in range(0, 4):
            d.rectangle([x0 - i, y0 - i, x1 + i, y1 + i], outline=(230, 40, 120) if i < 3 else (255, 255, 255))
    return im


out = {}
D, R, J = H / "data", H / "real", H / "data/joints"
out["master_fox"] = uri(Image.open(H.parent / "clef" / "data" / "fox__master.png"), 300)
out["master_moose"] = uri(Image.open(D / "moose__master.png"), 300)
syn = ["fox_setup_0.0__clean", "fox_setup_0.0__shift_hand_l_right_24", "fox_setup_0.0__shift_head_down_24",
       "moose_setup_0.0__layer_upperarm_l_over_torso", "moose_setup_0.0__mirror_hand_l",
       "moose_thumbs_up_0.5__shift_hips_down_16", "fox_setup_0.0__shift_head_left_24", "moose_setup_0.0__clean"]
for k in syn:
    im = Image.open(D / f"{k}.png"); out[k] = uri(im)
    if "__clean" not in k:
        clean = Image.open(D / f"{k.split('__')[0]}__clean.png")
        out[k + "__marked"] = uri(marked(im, clean))
for k in ["fox_setup_0.0__shift_hand_l_right_24__hand_l", "fox_setup_0.0__clean__hand_r",
          "moose_setup_0.0__shift_hand_l_left_24__hand_l", "fox_idle_1.8__clean__hand_l"]:
    out["j_" + k] = uri(Image.open(J / f"{k}.png"), 300)
for k in ["real_before_after_fox_r0_c0", "real_before_after_fox_r1_c0", "real_before_after_moose_r0_c2",
          "real_before_after_moose_r1_c2", "real_shoulders_ab_moose_r0_c1", "real_shoulders_ab_moose_r1_c1",
          "real_shoulders_ab_fox_r0_c0", "real_shoulders_ab_fox_r1_c0"]:
    out[k] = uri(Image.open(R / f"{k}.png"), 380)
json.dump(out, open(H / "assets.json", "w"))
print(len(out), "assets", sum(len(v) for v in out.values()) // 1024, "KB")

# round 2: master crop + render crop pairs
JR = H / "jref"
for k in ["fox_shift_hand_l_down_24__hand_l", "fox_shift_boot_l_right_24__boot_l", "fox_shift_hand_l_up_24__hand_l",
          "fox_clean__hand_l"]:
    out["r2_" + k + "__ref"] = uri(Image.open(JR / f"{k}__ref.jpg"), 260)
    out["r2_" + k] = uri(Image.open(JR / f"{k}.jpg"), 260)
json.dump(out, open(H / "assets.json", "w"))
print("with round 2:", len(out), "assets", sum(len(v) for v in out.values()) // 1024, "KB")

# round 4: Jev boxes drawn on what it saw (magenta = Jev's box, dashed teal = true box)
def draw_box(im, jb, gb=None, w=4):
    im = im.convert("RGB").copy(); d = ImageDraw.Draw(im); W, Hh = im.size
    px = lambda b: (b["left"] * W, b["top"] * Hh, b["right"] * W, b["bottom"] * Hh)
    if gb:
        x0, y0, x1, y1 = px(gb); step = 14
        for x in range(int(x0), int(x1), step):
            d.line([(x, y0), (min(x + 7, x1), y0)], fill=(0, 150, 140), width=3); d.line([(x, y1), (min(x + 7, x1), y1)], fill=(0, 150, 140), width=3)
        for y in range(int(y0), int(y1), step):
            d.line([(x0, y), (x0, min(y + 7, y1))], fill=(0, 150, 140), width=3); d.line([(x1, y), (x1, min(y + 7, y1))], fill=(0, 150, 140), width=3)
    d.rectangle(px(jb), outline=(230, 40, 120), width=w)
    return im


JG = {r["id"]: r for r in map(json.loads, open(JR / "labels_gt.jsonl"))}
JA = {r["id"]: r["answers"] for r in map(json.loads, open(JR / "results_jref_typesafe_jev-1.14.0.jsonl"))}
for k in ["fox_shift_hand_l_right_24__hand_l", "fox_shift_hand_r_left_24__hand_r", "moose_shift_hand_r_down_24__hand_r",
          "fox_shift_boot_l_left_24__boot_l"]:
    out["r4m_" + k] = uri(draw_box(Image.open(JR / f"{k}__ref.jpg"), JA[k]["box_master"]["box"], JG[k]["gt_box_master"]), 260)
    out["r4r_" + k] = uri(draw_box(Image.open(JR / f"{k}.jpg"), JA[k]["box_render"]["box"], JG[k]["gt_box"]), 260)

# full-frame box_defect: one that lands, one that doesn't (true region = diff vs clean)
import numpy as np
FA = {r["id"]: r["answers"] for r in map(json.loads, open(D / "results_solo_typesafe_jev-1.14.0.jsonl"))}
picked = {}
for k, a in FA.items():
    if "__clean" in k or not (D / f"{k}.png").exists(): continue
    x = np.asarray(Image.open(D / f"{k}.png").convert("RGB"), int); c = np.asarray(Image.open(D / f"{k.split('__')[0]}__clean.png").convert("RGB"), int)
    ys, xs = np.nonzero(np.abs(x - c).sum(-1) > 30)
    if not len(ys): continue
    h, w = x.shape[:2]; g = dict(left=(xs.min() - 10) / w, right=(xs.max() + 10) / w, top=(ys.min() - 10) / h, bottom=(ys.max() + 10) / h)
    b = a["box_defect"]["box"]; cx, cy = (b["left"] + b["right"]) / 2, (b["top"] + b["bottom"]) / 2
    hit = g["left"] <= cx <= g["right"] and g["top"] <= cy <= g["bottom"]
    key = "hit" if hit else "miss"
    if key not in picked and "shift" in k and ("_24" in k or "_16" in k):
        picked[key] = k; out["r4f_" + key] = uri(draw_box(Image.open(D / f"{k}.png"), b, g), 340); out["r4f_" + key + "_id"] = k
json.dump(out, open(H / "assets.json", "w"))
print("with round 4:", len(out), "assets", sum(len(v) for v in out.values()) // 1024, "KB", picked)
