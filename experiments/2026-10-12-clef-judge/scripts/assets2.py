# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Extra page assets for the rebuilt report: disputed clean joints, previous-render pairs with Jev boxes, rig
generations, two-pass Box. Adds keys to assets.json."""
import base64, io, json
from pathlib import Path
from PIL import Image, ImageDraw

H = Path(__file__).parent
A = json.load(open(H / "assets.json"))


def uri(im, w=260, q=80):
    im = im.convert("RGB"); im.thumbnail((w, w * 2)); b = io.BytesIO(); im.save(b, "JPEG", quality=q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def draw(im, jb=None, gb=None, color=(230, 40, 120)):
    im = im.convert("RGB").copy(); d = ImageDraw.Draw(im); W, Hh = im.size
    px = lambda b: (b["left"] * W, b["top"] * Hh, b["right"] * W, b["bottom"] * Hh)
    if gb:
        x0, y0, x1, y1 = px(gb)
        for x in range(int(x0), int(x1), 14):
            d.line([(x, y0), (min(x + 7, x1), y0)], fill=(0, 150, 140), width=3); d.line([(x, y1), (min(x + 7, x1), y1)], fill=(0, 150, 140), width=3)
        for y in range(int(y0), int(y1), 14):
            d.line([(x0, y), (x0, min(y + 7, y1))], fill=(0, 150, 140), width=3); d.line([(x1, y), (x1, min(y + 7, y1))], fill=(0, 150, 140), width=3)
    if jb: d.rectangle(px(jb), outline=color, width=4)
    return im


J = H / "jref"
G = {r["id"]: r for r in map(json.loads, open(J / "labels_gt.jsonl"))}
for c, s in [("fox", "hand_l"), ("fox", "hand_r"), ("moose", "hand_l"), ("moose", "hand_r"), ("fox", "boot_l"), ("moose", "hips")]:
    i = f"{c}_clean__{s}"
    A[f"aud_{i}__ref"] = uri(Image.open(J / f"{i}__ref.jpg"), 200); A[f"aud_{i}"] = uri(Image.open(J / f"{i}.jpg"), 200)

C = {json.loads(l)["id"]: json.loads(l)["answers"] for l in open(J / "results_cref_typesafe_jev-1.14.0.jsonl")}
for i in ["fox_shift_hand_l_down_24__hand_l", "fox_shift_boot_r_right_16__boot_r", "moose_shift_head_up_24__head", "moose_shift_hand_r_left_8__hand_r"]:
    if i not in C: continue
    cid = f"{G[i]['char']}_clean__{G[i]['slot']}"
    A[f"cref_{i}__before"] = uri(draw(Image.open(J / f"{cid}.jpg"), C[i]["box_before"]["box"], G[cid]["gt_box"]), 220)
    A[f"cref_{i}__after"] = uri(draw(Image.open(J / f"{i}.jpg"), C[i]["box_after"]["box"], G[i]["gt_box"]), 220)

R = H / "rounds"
for c, pose in [("fox", "setup_0.0"), ("moose", "wave_1.2"), ("fox", "cheer_jump_0.6")]:
    for g in ("g1", "g2", "g3"):
        p = R / f"{c}_{g}_{pose}.png"
        if p.exists(): A[f"rd_{c}_{g}_{pose}"] = uri(Image.open(p), 220)

Z = H / "zoom"
ZL = {r["id"]: r for r in map(json.loads, open(Z / "labels.jsonl"))}
ZR = {json.loads(l)["id"]: json.loads(l)["answers"] for l in open(Z / "results_zoom_typesafe_jev-1.14.0.jsonl")} if (Z / "results_zoom_typesafe_jev-1.14.0.jsonl").exists() else {}
k = "fox_shift_hand_l_right_24__hand_l"
if k in ZR:
    L = ZL[k]; w = L["zoom_window"]
    big = Image.open(J / f"{k}.jpg"); A["zoom_first"] = uri(draw(big, L["first_box"], G[k]["gt_box"]), 220)
    W_, H_ = w[2] - w[0], w[3] - w[1]; gb = G[k]["gt_box"]
    gz = dict(left=(gb["left"] - w[0]) / W_, right=(gb["right"] - w[0]) / W_, top=(gb["top"] - w[1]) / H_, bottom=(gb["bottom"] - w[1]) / H_)
    gz = {kk: min(1, max(0, v)) for kk, v in gz.items()}
    A["zoom_second"] = uri(draw(Image.open(Z / f"{k}.jpg"), ZR[k]["box_render"]["box"], gz), 220)
json.dump(A, open(H / "assets.json", "w"))
print(len(A), "assets", sum(len(v) for v in A.values()) // 1024, "KB")
