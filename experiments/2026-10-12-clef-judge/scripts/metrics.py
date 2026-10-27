#!/usr/bin/env python3
"""One scoring pass for every test x model, on identical items -> metrics.json (the page reads only this).

Label variants for joint crops: 'original', and 'audited' = the four approved hand joints that don't match the master
(fox hand_l/hand_r off-centre in the cuff, moose hand_l/hand_r with a furry wrist band) dropped from the clean set.
They stay as positives when shifted."""
import json, math, random, statistics
from collections import defaultdict
from pathlib import Path

H = Path(__file__).parent
MODELS = [("clef-flash", "cloudflare", "Clef Flash"), ("clef", "cloudflare", "Clef 27B"), ("jev-1.14.0", "typesafe", "Jev 1.14")]
DISPUTED = {("fox", "hand_l"), ("fox", "hand_r"), ("moose", "hand_l"), ("moose", "hand_r")}
base = lambda s: s[:-2] if s[-2:] in ("_l", "_r") else s


def jl(p): return [json.loads(l) for l in open(H / p)] if (H / p).exists() else []
def res(d, cond, m, p, swap=False):
    return {r["id"]: r for r in jl(f"{d}/results_{cond}{'_swap' if swap else ''}_{p}_{m}.jsonl") if r.get("answers")}
def auroc(P, N):
    return sum((a > b) + .5 * (a == b) for a in P for b in N) / (len(P) * len(N)) if P and N else None
def ci(P, N, n=500):
    if not P or not N: return None
    rnd = random.Random(0); v = sorted(auroc([rnd.choice(P) for _ in P], [rnd.choice(N) for _ in N]) for _ in range(n))
    return [v[int(.025 * n)], v[int(.975 * n)]]
def catch10(P, N):
    if len(N) < 10: return None
    th = sorted(N)[int(.9 * len(N)) - 1]; return sum(p > th for p in P) / len(P)
def bacc(P, N, th=.5):
    return (sum(p > th for p in P) / len(P) + sum(n <= th for n in N) / len(N)) / 2 if P and N else None
def d4(probs):
    p = {k: v for k, v in probs.items() if k != "none"}; return max(p, key=p.get)
def detect_block(P, N):
    return dict(auroc=auroc(P, N), ci=ci(P, N), catch10=catch10(P, N), bacc50=bacc(P, N), nP=len(P), nN=len(N),
                meanP=statistics.mean(P) if P else None, meanN=statistics.mean(N) if N else None)


OUT = {"models": [m[2] for m in MODELS]}

# ---------- full frames, planted defects (120) and with master (60, positives only)
dl = {r["id"]: r for r in jl("data/labels.jsonl")}
for cond, key in (("solo", "frames"), ("ref", "frames_master")):
    sec = {}
    for m, p, name in MODELS:
        R = res("data", cond, m, p)
        if not R: continue
        ids = [i for i in R]
        P = [R[i]["answers"]["defect"]["noul"] for i in ids if dl[i]["defect"]]
        N = [R[i]["answers"]["defect"]["noul"] for i in ids if not dl[i]["defect"]]
        off = [i for i in ids if dl[i]["kind"] == "offset"]
        b = detect_block(P, N)
        b["dir"] = sum(d4(R[i]["answers"]["direction"]["probabilities"]) == dl[i]["direction"] for i in off) / len(off)
        b["part"] = sum(d4(R[i]["answers"]["part"]["probabilities"]) == dl[i]["part"] for i in off) / len(off)
        b["kind_none"] = sum(R[i]["answers"]["kind"]["choice"] == "none" for i in ids if dl[i]["defect"]) / max(1, len(P))
        bym = defaultdict(list)
        for i in ids:
            if dl[i]["kind"] in ("offset", "none"): bym[dl[i].get("mag", 0)].append(R[i]["answers"]["defect"]["noul"])
        b["by_mag"] = {str(k): statistics.mean(v) for k, v in sorted(bym.items())}
        byk = defaultdict(list)
        for i in ids: byk[dl[i]["kind"]].append(R[i]["answers"]["defect"]["noul"])
        b["by_kind"] = {k: statistics.mean(v) for k, v in byk.items()}
        b["n"] = len(ids)
        sec[name] = b
    OUT[key] = sec

# ---------- joint crops: render only / with master crop / vs previous render
J = {r["id"]: r for r in jl("jref/labels_gt.jsonl")}
for cond, key in (("joint", "joint_render"), ("jref", "joint_master"), ("cref", "joint_prev")):
    sec = {}
    for m, p, name in MODELS:
        R = res("jref", cond, m, p)
        if not R: continue
        out = {}
        for variant in ("original", "audited"):
            ids = [i for i in R if not (variant == "audited" and not J[i]["defect"] and (J[i]["char"], J[i]["slot"]) in DISPUTED)]
            P = [R[i]["answers"]["detached"]["noul"] for i in ids if J[i]["defect"]]
            N = [R[i]["answers"]["detached"]["noul"] for i in ids if not J[i]["defect"]]
            b = detect_block(P, N)
            b["unique_clean"] = len({(J[i]["char"], J[i]["slot"]) for i in ids if not J[i]["defect"]})
            out[variant] = b
        D = [i for i in R if J[i]["defect"]]
        if not D: continue
        out["dir"] = sum(d4(R[i]["answers"]["direction"]["probabilities"]) == J[i]["direction"] for i in D) / len(D)
        out["dir_by_mag"] = {str(mg): sum(d4(R[i]["answers"]["direction"]["probabilities"]) == J[i]["direction"] for i in D if J[i]["mag"] == mg)
                             / sum(J[i]["mag"] == mg for i in D) for mg in (8, 16, 24)}
        cnt = defaultdict(int)
        for i in D: cnt[d4(R[i]["answers"]["direction"]["probabilities"])] += 1
        out["dir_answers"] = dict(cnt)
        clean = {(J[i]["char"], J[i]["slot"]): R[i]["answers"]["detached"]["noul"] for i in R if J[i]["id"].split("__")[0].endswith("_clean")}
        w = [R[i]["answers"]["detached"]["noul"] > clean[(J[i]["char"], J[i]["slot"])] for i in D if (J[i]["char"], J[i]["slot"]) in clean]
        out["same_joint"] = sum(w) / len(w) if w else None
        bym = defaultdict(list)
        for i in D: bym[J[i]["mag"]].append(R[i]["answers"]["detached"]["noul"])
        out["by_mag"] = {str(k): statistics.mean(v) for k, v in sorted(bym.items())}
        out["clean_by_joint"] = {f"{c} {s}": v for (c, s), v in sorted(clean.items())}
        if cond == "cref":   # identical before/after for clean joints: how often does it say "moved"?
            same = [R[i]["answers"]["detached"]["noul"] for i in R if not J[i]["defect"]]
            out["identical_moved"] = statistics.mean(same) if same else None
            out["shifted_moved_rate"] = sum(R[i]["answers"]["detached"]["noul"] > .5 for i in D) / len(D)
        sec[name] = out
    OUT[key] = sec

# ---------- real reviewed tiles: single frame, and pairs (both orders)
RL = {r["id"]: r for r in jl("real/labels.jsonl")}
RD = {r["id"]: r for r in jl("rounds/labels.jsonl")}


def single(dirname, L, subsets):
    sec = {}
    for m, p, name in MODELS:
        R = res(dirname, "solo", m, p)
        if not R: continue
        out = {}
        for sname, f in subsets:
            P = [R[i]["answers"]["defect"]["noul"] for i in R if L[i]["defect"] and f(L[i])]
            N = [R[i]["answers"]["defect"]["noul"] for i in R if not L[i]["defect"] and f(L[i])]
            out[sname] = detect_block(P, N)
        # same pose: rejected scored above its approved version
        pr = defaultdict(dict)
        for i in R: pr[L[i]["pair"]].setdefault(L[i]["defect"], []).append(R[i]["answers"]["defect"]["noul"])
        w = [a > d[False][0] for d in pr.values() if False in d and True in d for a in d[True]]
        out["same_pose"] = [sum(w), len(w)]
        out["scores"] = {i: R[i]["answers"]["defect"]["noul"] for i in R}
        sec[name] = out
    return sec


def pairs(dirname, L, subsets):
    sec = {}
    for m, p, name in MODELS:
        A, B = res(dirname, "pair", m, p), res(dirname, "pair", m, p, swap=True)
        ks = [k for k in A if k in B]
        if not ks: continue
        mm = {k: (A[k]["answers"]["worse"]["probabilities"][A[k]["truth"]] + B[k]["answers"]["worse"]["probabilities"][B[k]["truth"]]) / 2 for k in ks}
        out = {}
        for sname, f in subsets:
            v = [mm[k] for k in ks if f(L[k])]
            if v: out[sname] = dict(right=sum(x > .5 for x in v), n=len(v), mean=statistics.mean(v))
        i1 = sum(r["answers"]["worse"]["choice"] == "image_1" for r in list(A.values()) + list(B.values()))
        out["image1_share"] = i1 / (len(A) + len(B))
        out["per_pair"] = mm
        sec[name] = out
    return sec


real_subsets = [("all", lambda L: True), ("full_body", lambda L: "before_after" in L["id"]), ("sleeves", lambda L: "shoulders" in L["id"])]
OUT["real_single"] = single("real", RL, real_subsets)
OUT["real_pairs"] = pairs("real", RL, real_subsets)
round_subsets = [("all", lambda L: True), ("g1", lambda L: L["gen"] in ("g1", "g3")), ("g2", lambda L: L["gen"] in ("g2", "g3")),
                 ("fox", lambda L: L["char"] == "fox"), ("moose", lambda L: L["char"] == "moose")]
OUT["rounds_single"] = single("rounds", RD, round_subsets)
OUT["rounds_pairs"] = pairs("rounds", RD, [("all", lambda L: True), ("g1", lambda L: L["gen"] == "g1"), ("g2", lambda L: L["gen"] == "g2"),
                                           ("fox", lambda L: L["char"] == "fox"), ("moose", lambda L: L["char"] == "moose")])


# ---------- Box (Jev only)
def iou(a, b):
    ix = max(0, min(a["right"], b["right"]) - max(a["left"], b["left"])); iy = max(0, min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]))
    u = (a["right"] - a["left"]) * (a["bottom"] - a["top"]) + (b["right"] - b["left"]) * (b["bottom"] - b["top"]) - ix * iy
    return ix * iy / u if u > 0 else 0.0


def spearman(x, y):
    rk = lambda v: {i: r for r, i in enumerate(sorted(range(len(v)), key=lambda i: v[i]))}
    rx, ry = rk(x), rk(y); n = len(x); return 1 - 6 * sum((rx[i] - ry[i]) ** 2 for i in range(n)) / (n * (n * n - 1))


def reliability(conf, hit, bins=5):
    o = sorted(range(len(conf)), key=lambda i: conf[i]); k = len(o) // bins; rows = []; ece = 0
    for b in range(bins):
        idx = o[b * k:(b + 1) * k] if b < bins - 1 else o[b * k:]
        c, h = statistics.mean(conf[i] for i in idx), statistics.mean(hit[i] for i in idx)
        rows.append([c, h, len(idx)]); ece += len(idx) / len(conf) * abs(c - h)
    return rows, ece


def edge_ok(L, e, keys=("gt_box",)):
    return all(0.02 < L[k][e] < 0.98 for k in keys)


def delta(b0, b1, L, keys):
    dx = [b1[e] - b0[e] for e in ("left", "right") if edge_ok(L, e, keys)]
    dy = [b1[e] - b0[e] for e in ("top", "bottom") if edge_ok(L, e, keys)]
    return (statistics.mean(dx) if dx else 0.0), (statistics.mean(dy) if dy else 0.0)


def dname(dx, dy): return ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else ("down" if dy > 0 else "up")


def showable(L, keys):
    axis = ("left", "right") if L["direction"] in ("left", "right") else ("top", "bottom")
    return any(edge_ok(L, e, keys) for e in axis)


BOX = {}
JV = "jev-1.14.0"
Rj, Rm, Rc = res("jref", "joint", JV, "typesafe"), res("jref", "jref", JV, "typesafe"), res("jref", "cref", JV, "typesafe")
Z = {r["id"]: r for r in jl("zoom/labels.jsonl")}; Rz = res("zoom", "zoom", JV, "typesafe")
if Rj:
    for name, R, k in (("render only", Rj, "box_render"), ("with master", Rm, "box_render")):
        ids = [i for i in R]
        io = [iou(R[i]["answers"][k]["box"], J[i]["gt_box"]) for i in ids]; cf = [R[i]["answers"][k]["confidence"] for i in ids]
        rel, ece = reliability(cf, [v >= .5 for v in io])
        bj = defaultdict(list)
        for i, v in zip(ids, io): bj[base(J[i]["slot"])].append(v)
        BOX[f"loc_{name}"] = dict(miou=statistics.mean(io), hit=sum(v >= .5 for v in io) / len(io), rho=spearman(cf, io), ece=ece,
                                  rel=rel, by_joint={k_: statistics.mean(v) for k_, v in bj.items()},
                                  full=statistics.mean(v for i, v in zip(ids, io) if J[i]["gt_visible"] >= .9),
                                  conf=[min(cf), max(cf)])
    # edge error in crop fractions vs true movement
    errs = [abs(Rj[i]["answers"]["box_render"]["box"][e] - J[i]["gt_box"][e]) for i in Rj for e in ("left", "right", "top", "bottom") if edge_ok(J[i], e)]
    mv = defaultdict(list)
    for i in J:
        if J[i]["defect"]:
            for e in ("left", "right", "top", "bottom"):
                if edge_ok(J[i], e, ("gt_box", "gt_box_master")):
                    d = abs(J[i]["gt_box"][e] - J[i]["gt_box_master"][e])
                    if d > 1e-4: mv[J[i]["mag"]].append(d)
    BOX["edge_err"] = statistics.median(errs); BOX["edge_move"] = {str(k): statistics.median(v) for k, v in sorted(mv.items())}

    def dir_eval(get, keys, R_for_ids):
        D = [i for i in J if J[i]["defect"] and i in R_for_ids and showable(J[i], keys)]
        ok = []
        for i in D:
            g = get(i)
            if g is None: continue
            ok.append(dname(*delta(*g, J[i], keys)) == J[i]["direction"])
        return dict(acc=sum(ok) / len(ok) if ok else None, n=len(ok))

    clean_id = lambda i: f"{J[i]['char']}_clean__{J[i]['slot']}"
    BOX["dir_master_boxes"] = dir_eval(lambda i: (Rm[i]["answers"]["box_master"]["box"], Rm[i]["answers"]["box_render"]["box"]) if i in Rm else None,
                                       ("gt_box", "gt_box_master"), Rm)
    BOX["dir_prev_boxes_same_request"] = dir_eval(lambda i: (Rc[i]["answers"]["box_before"]["box"], Rc[i]["answers"]["box_after"]["box"]) if i in Rc else None,
                                                  ("gt_box", "gt_box_master"), Rc)
    BOX["dir_prev_boxes_separate"] = dir_eval(lambda i: (Rj[clean_id(i)]["answers"]["box_render"]["box"], Rj[i]["answers"]["box_render"]["box"])
                                              if clean_id(i) in Rj else None, ("gt_box", "gt_box_master"), Rj)

    def zoom_box(i):        # second-pass box mapped back to joint-crop fractions
        if i not in Rz: return None
        w = Z[i]["zoom_window"]; b = Rz[i]["answers"]["box_render"]["box"]; W, Hh = w[2] - w[0], w[3] - w[1]
        return dict(left=w[0] + b["left"] * W, right=w[0] + b["right"] * W, top=w[1] + b["top"] * Hh, bottom=w[1] + b["bottom"] * Hh)
    if Rz:
        zi_all = [i for i in Rz]
        BOX["dir_prev_boxes_zoom"] = dir_eval(lambda i: (zoom_box(clean_id(i)), zoom_box(i)) if zoom_box(i) and zoom_box(clean_id(i)) else None,
                                              ("gt_box", "gt_box_master"), Rz)
        zi = [i for i in Rz]
        io1 = [iou(Rj[i]["answers"]["box_render"]["box"], J[i]["gt_box"]) for i in zi]
        io2 = [iou(zoom_box(i), J[i]["gt_box"]) for i in zi]
        e2 = [abs(zoom_box(i)[e] - J[i]["gt_box"][e]) for i in zi for e in ("left", "right", "top", "bottom") if edge_ok(J[i], e)]
        BOX["zoom"] = dict(miou_first=statistics.mean(io1), miou_second=statistics.mean(io2), edge_err_second=statistics.median(e2), n=len(zi))
    BOX["dir_true_boxes"] = dir_eval(lambda i: (J[i]["gt_box_master"], J[i]["gt_box"]), ("gt_box", "gt_box_master"), J)
    # master boxes against the hand-placed master landmarks (hands): box should contain wrist and fingertip
    lm = {c: json.load(open(f"/work/comfy/experiments/2026-10-11-rig-annotations/{c}/annotations.json"))["master"]["points"] for c in ("fox", "moose")}
    inside = []
    for i in Rm:
        L = J[i]
        if base(L["slot"]) != "hand" or "master_crop" not in L: continue
        s = L["slot"][-1]; mc = L["master_crop"]; b = Rm[i]["answers"]["box_master"]["box"]
        pts = [lm[L["char"]][f"{n}_{s}"] for n in ("wrist", "fingertip")]
        loc = [((x - mc[0]) / (mc[2] - mc[0]), (y - mc[1]) / (mc[3] - mc[1])) for x, y in pts]
        pad = 0.04
        inside.append(all(b["left"] - pad <= x <= b["right"] + pad and b["top"] - pad <= y <= b["bottom"] + pad for x, y in loc))
    BOX["master_hand_landmarks"] = dict(rate=sum(inside) / len(inside), n=len(inside)) if inside else None
    # full-frame pointing (computed by score_box.py earlier; re-read)
    try:
        bs = json.load(open(H / f"jref/box_summary_{JV}.json")); BOX["point"] = bs.get("point_solo")
    except Exception: pass
OUT["box"] = BOX

# ---------- cost
cost = {}
for m, p, name in MODELS:
    rs = [r for f in H.glob(f"**/results_*_{p}_{m}.jsonl") for r in map(json.loads, open(f))]
    tok = sum(r["usage"]["input_tokens"] for r in rs if r.get("usage"))
    usd = {"clef-flash": 0.038, "clef": 0.24, "jev-1.14.0": 0.042}[m]
    cost[name] = dict(calls=len(rs), tokens=tok, usd=tok * usd / 1e6, latency=statistics.median(r["latency_s"] for r in rs))
OUT["cost"] = cost
json.dump(OUT, open(H / "metrics.json", "w"), indent=1, default=float)
print("ok")
