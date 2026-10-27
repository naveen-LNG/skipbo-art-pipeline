# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Score Jev's Box answers: localisation, confidence calibration, box-derived fix direction, defect pointing."""
import json, math, statistics, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

H = Path(__file__).parent
M = sys.argv[1] if len(sys.argv) > 1 else "jev-1.14.0"
J = H / "jref"
lab = {r["id"]: r for r in map(json.loads, open(J / "labels_gt.jsonl"))}
base = lambda s: s[:-2] if s[-2:] in ("_l", "_r") else s
out = {}


def load(p): return {r["id"]: r["answers"] for r in map(json.loads, open(p)) if r.get("answers")} if p.exists() else {}


def iou(a, b):
    ix = max(0, min(a["right"], b["right"]) - max(a["left"], b["left"])); iy = max(0, min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]))
    u = (a["right"] - a["left"]) * (a["bottom"] - a["top"]) + (b["right"] - b["left"]) * (b["bottom"] - b["top"]) - ix * iy
    return ix * iy / u if u > 0 else 0.0


def auroc(p, n): return sum((a > b) + .5 * (a == b) for a in p for b in n) / (len(p) * len(n)) if p and n else float("nan")


def spearman(x, y):
    rk = lambda v: {i: r for r, i in enumerate(sorted(range(len(v)), key=lambda i: v[i]))}
    rx, ry = rk(x), rk(y); n = len(x)
    return 1 - 6 * sum((rx[i] - ry[i]) ** 2 for i in range(n)) / (n * (n * n - 1))


def calibration(conf, hit, bins=5):
    """Reliability: confidence as the predicted chance the box is right (IoU >= 0.5)."""
    order = sorted(range(len(conf)), key=lambda i: conf[i]); k = len(order) // bins; rows = []; ece = 0
    for b in range(bins):
        idx = order[b * k:(b + 1) * k] if b < bins - 1 else order[b * k:]
        c, h = statistics.mean(conf[i] for i in idx), statistics.mean(hit[i] for i in idx)
        rows.append((c, h, len(idx))); ece += len(idx) / len(conf) * abs(c - h)
    return rows, ece


# ---------- 1. localisation + calibration of box_render (both joint conditions)
for cond in ("joint", "jref"):
    A = load(J / f"results_{cond}_typesafe_{M}.jsonl")
    if not A: continue
    ids = [i for i in lab if i in A]
    ious = [iou(A[i]["box_render"]["box"], lab[i]["gt_box"]) for i in ids]
    conf = [A[i]["box_render"]["confidence"] for i in ids]
    hit = [v >= .5 for v in ious]
    rows, ece = calibration(conf, hit)
    print(f"\n== box_render localisation [{cond}] n={len(ids)}: mean IoU {statistics.mean(ious):.2f}, IoU>=0.5 on "
          f"{sum(hit)/len(hit):.0%} | confidence mean {statistics.mean(conf):.2f}, Spearman(conf, IoU) {spearman(conf, ious):.2f}, ECE {ece:.2f}")
    print("   reliability (conf -> share with IoU>=0.5): " + "  ".join(f"{c:.2f}->{h:.0%}(n{n})" for c, h, n in rows))
    bj = defaultdict(list)
    for i, v in zip(ids, ious): bj[base(lab[i]["slot"])].append(v)
    print("   IoU by joint: " + "  ".join(f"{k} {statistics.mean(v):.2f}" for k, v in sorted(bj.items())))
    full = [v for i, v in zip(ids, ious) if lab[i]["gt_visible"] >= .9]
    print(f"   parts fully inside the crop (n={len(full)}): mean IoU {statistics.mean(full):.2f}")
    out[f"loc_{cond}"] = dict(n=len(ids), miou=statistics.mean(ious), hit=sum(hit) / len(hit), rho=spearman(conf, ious), ece=ece,
                              rel=rows, by_joint={k: statistics.mean(v) for k, v in bj.items()})


# ---------- 2. fix direction and detection from box_master vs box_render (jref)
def delta(m, r, lb):
    """Per-axis movement of render box vs master box, from edges the crop cuts in neither image (true edges away from 0/1)."""
    ok = lambda e: all(0.02 < g[e] < 0.98 for g in (lb["gt_box"], lb["gt_box_master"]))
    dx = [r[e] - m[e] for e in ("left", "right") if ok(e)]; dy = [r[e] - m[e] for e in ("top", "bottom") if ok(e)]
    return (statistics.mean(dx) if dx else 0.0), (statistics.mean(dy) if dy else 0.0)


def d4(dx, dy): return ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else ("down" if dy > 0 else "up")


A = load(J / f"results_jref_typesafe_{M}.jsonl")
if A:
    ids = [i for i in lab if i in A]
    for name, get in [("Jev boxes", lambda i: (A[i]["box_master"]["box"], A[i]["box_render"]["box"])),
                      ("true boxes (sanity)", lambda i: (lab[i]["gt_box_master"], lab[i]["gt_box"]))]:
        D = {i: delta(*get(i), lab[i]) for i in ids}
        P_all = [i for i in ids if lab[i]["defect"]]
        vis = {i for i in P_all if any(all(0.02 < g[e] < 0.98 for g in (lab[i]["gt_box"], lab[i]["gt_box_master"]))
                                       for e in (("left", "right") if lab[i]["direction"] in ("left", "right") else ("top", "bottom")))}
        P = [i for i in ids if lab[i]["defect"]]; N = [i for i in ids if not lab[i]["defect"]]
        acc = sum(d4(*D[i]) == lab[i]["direction"] for i in P) / len(P)
        accv = sum(d4(*D[i]) == lab[i]["direction"] for i in P if i in vis) / max(1, len(vis))
        mag = lambda i: math.hypot(*D[i])
        bym = {m_: sum(d4(*D[i]) == lab[i]["direction"] for i in P if lab[i]["mag"] == m_) / sum(lab[i]["mag"] == m_ for i in P) for m_ in (8, 16, 24)}
        print(f"\n== fix direction from {name}: {acc:.0%} right (chance 25%); {accv:.0%} on the {len(vis)} shifts a box can show | by shift 8/16/24: "
              + " / ".join(f"{v:.0%}" for v in bym.values())
              + f" | detection AUROC from box movement {auroc([mag(i) for i in P], [mag(i) for i in N]):.2f}")
        bj = defaultdict(list)
        for i in P: bj[base(lab[i]["slot"])].append(d4(*D[i]) == lab[i]["direction"])
        print("   direction by joint: " + "  ".join(f"{k} {sum(v)/len(v):.0%}" for k, v in sorted(bj.items())))
        if name == "Jev boxes":
            out["dir_box"] = dict(acc=acc, acc_visible=accv, n_visible=len(vis), by_mag=bym, by_joint={k: sum(v) / len(v) for k, v in bj.items()},
                                  auroc=auroc([mag(i) for i in P], [mag(i) for i in N]))
            # does box confidence tell when the direction is right?
            cf = [min(A[i]["box_master"]["confidence"], A[i]["box_render"]["confidence"]) for i in P]
            ok = [d4(*D[i]) == lab[i]["direction"] for i in P]
            hi = [o for c, o in zip(cf, ok) if c >= statistics.median(cf)]; lo = [o for c, o in zip(cf, ok) if c < statistics.median(cf)]
            print(f"   direction right when both box confidences are above the median: {sum(hi)/len(hi):.0%}, below: {sum(lo)/len(lo):.0%}")
            out["dir_box"].update(conf_hi=sum(hi) / len(hi), conf_lo=sum(lo) / len(lo))

# ---------- 3. full-frame box_defect: does it point at what changed?
dl = {r["id"]: r for r in map(json.loads, open(H / "data/labels.jsonl"))}
for cond in ("solo", "ref"):
    A = load(H / f"data/results_{cond}_typesafe_{M}.jsonl")
    if not A: continue
    hits, ious_, n = [], [], 0
    for i, a in A.items():
        L = dl[i]
        if not L["defect"]: continue
        clean = H / "data" / f"{i.split('__')[0]}__clean.png"
        if not clean.exists() or not (H / "data" / f"{i}.png").exists(): continue
        x, c = np.asarray(Image.open(H / "data" / f"{i}.png").convert("RGB"), int), np.asarray(Image.open(clean).convert("RGB"), int)
        if x.shape != c.shape: continue
        ys, xs = np.nonzero(np.abs(x - c).sum(-1) > 30)
        if not len(ys): continue
        h, w = x.shape[:2]; pad = 10
        g = dict(left=(xs.min() - pad) / w, right=(xs.max() + pad) / w, top=(ys.min() - pad) / h, bottom=(ys.max() + pad) / h)
        b = a["box_defect"]["box"]; cx, cy = (b["left"] + b["right"]) / 2, (b["top"] + b["bottom"]) / 2
        hits.append(g["left"] <= cx <= g["right"] and g["top"] <= cy <= g["bottom"]); ious_.append(iou(b, g))
    if hits:
        # chance: how often a random point lands in the changed region = mean changed-area share; approximate with box areas
        print(f"\n== box_defect on full frames [{cond}] n={len(hits)} defective frames: box centre inside the changed region "
              f"{sum(hits)/len(hits):.0%}, mean IoU {statistics.mean(ious_):.2f}")
        out[f"point_{cond}"] = dict(n=len(hits), hit=sum(hits) / len(hits), miou=statistics.mean(ious_))
json.dump(out, open(J / f"box_summary_{M}.json", "w"), indent=1, default=float)
