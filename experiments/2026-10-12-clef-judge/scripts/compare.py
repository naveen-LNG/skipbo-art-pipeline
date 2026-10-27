#!/usr/bin/env python3
"""Clef Flash vs Clef 27B on identical items, every condition. Only items both models answered are compared."""
import json, math, statistics
from pathlib import Path

H = Path(__file__).parent
MODELS = ["clef-flash", "clef", "jev-1.14.0"]
PROV = {"clef-flash": "cloudflare", "clef": "cloudflare", "jev-1.14.0": "typesafe"}


def auroc(pos, neg):
    if not pos or not neg: return float("nan")
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def load(p):
    p = H / p
    return {r["id"]: r for r in map(json.loads, open(p)) if r.get("answers")} if p.exists() else {}


def labels(p): return {r["id"]: r for r in map(json.loads, open(H / p))}


def d4(probs):
    p = {k: v for k, v in probs.items() if k != "none"}; return max(p, key=p.get)


rows = []


def detect(name, lab, files, key, dir_ok=True):
    R = {m: load(files[0].format(m=m, p=PROV[m])) for m in MODELS}
    ids = [i for i in lab if all(i in R[m] for m in MODELS)]
    out = [name, len(ids)]
    for m in MODELS:
        if not ids: out += ["-", "-", "-"]; continue
        pos = [R[m][i]["answers"][key]["noul"] for i in ids if lab[i]["defect"]]
        neg = [R[m][i]["answers"][key]["noul"] for i in ids if not lab[i]["defect"]]
        th = sorted(neg)[int(.9 * len(neg)) - 1] if len(neg) >= 10 else None
        t10 = f"{sum(p > th for p in pos)/len(pos):.0%}" if th is not None else "-"
        D = [i for i in ids if lab[i]["defect"] and lab[i].get("direction") not in (None, "none")]
        dr = f"{sum(d4(R[m][i]['answers']['direction']['probabilities']) == lab[i]['direction'] for i in D)/len(D):.0%}" if D and dir_ok else "-"
        out += [f"{auroc(pos, neg):.2f}" if neg else f"mean {statistics.mean(pos):.2f}", t10, dr]
    rows.append(out)


detect("Joint crop, render only (R2)", labels("jref/labels.jsonl"), ["jref/results_joint_{p}_{m}.jsonl"], "detached")
detect("Joint crop + master crop (R2)", labels("jref/labels.jsonl"), ["jref/results_jref_{p}_{m}.jsonl"], "detached")
detect("Full frame, planted (120)", labels("data/labels.jsonl"), ["data/results_solo_{p}_{m}.jsonl"], "defect")
detect("Full frame + master (60, no clean)", labels("data/labels.jsonl"), ["data/results_ref_{p}_{m}.jsonl"], "defect")
detect("Full frame, real reviewed (38)", labels("real/labels.jsonl"), ["real/results_solo_{p}_{m}.jsonl"], "defect", False)

print(f"{'condition':38s} {'n':>4} | " + " | ".join(f"{m:^22s}" for m in MODELS))
print(f"{'':38s} {'':>4} | " + " | ".join(f"{'AUROC':>7} {'@10%FA':>6} {'dir':>5} " for _ in MODELS))
for r in rows:
    print(f"{r[0]:38s} {r[1]:>4} | " + " | ".join(f"{r[2+3*k]:>7} {r[3+3*k]:>6} {r[4+3*k]:>5} " for k in range(len(MODELS))))

# pairwise, order-debiased
for m in MODELS:
    A, B = load(f"real/results_pair_{PROV[m]}_{m}.jsonl"), load(f"real/results_pair_swap_{PROV[m]}_{m}.jsonl")
    ks = [k for k in A if k in B]
    if not ks: print(f"pairwise {m}: not run"); continue
    mm = {k: (A[k]["answers"]["worse"]["probabilities"][A[k]["truth"]] + B[k]["answers"]["worse"]["probabilities"][B[k]["truth"]]) / 2 for k in ks}
    bf = [v for k, v in mm.items() if "before_after" in k]; sh = [v for k, v in mm.items() if "shoulders" in k]
    i1 = sum(r["answers"]["worse"]["choice"] == "image_1" for r in list(A.values()) + list(B.values()))
    print(f"pairwise {m:10s}: {sum(v > .5 for v in mm.values())}/{len(mm)} | full body {sum(v > .5 for v in bf)}/{len(bf)} "
          f"(mean {statistics.mean(bf):.2f}) | sleeves {sum(v > .5 for v in sh)}/{len(sh)} (mean {statistics.mean(sh):.2f}) | image_1 bias {i1}/{len(A)+len(B)}")

# usage / latency
for m in MODELS:
    fs = list(H.glob(f"**/results_*_{PROV[m]}_{m}.jsonl"))
    rs = [r for f in fs for r in map(json.loads, open(f))]
    tok = sum(r["usage"]["input_tokens"] for r in rs)
    usd = {"clef-flash": 0.038, "clef": 0.24, "jev-1.14.0": 0.042}[m]
    print(f"usage {m:10s}: {len(rs)} calls, {tok/1e3:.0f}k tokens, ~${tok*usd/1e6:.3f}, median latency "
          f"{statistics.median(r['latency_s'] for r in rs):.2f}s")
