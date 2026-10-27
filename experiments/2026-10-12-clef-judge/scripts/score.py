#!/usr/bin/env python3
"""Score Clef results against ground truth.  python3 score.py <set dir> <results jsonl>"""
import json, statistics, sys
from collections import defaultdict
from pathlib import Path

SET, RES = Path(sys.argv[1]), Path(sys.argv[2])
lab = {r["id"]: r for r in map(json.loads, open(SET / "labels.jsonl"))}
res = [r for r in map(json.loads, open(RES)) if r.get("answers")]
rows = [(lab[r["id"]], r["answers"], r) for r in res]


def auroc(pos, neg):
    if not pos or not neg: return float("nan")
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def sig(L, A):  # two candidate defect signals
    return {"noul": A["defect"]["noul"], "1-P(kind=none)": 1 - A["kind"]["probabilities"]["none"]}


print(f"== {RES.name}: {len(rows)} scored")
lat = [r["latency_s"] for *_, r in rows]; tok = [r["usage"]["input_tokens"] for *_, r in rows]
print(f"latency median {statistics.median(lat):.2f}s p90 {sorted(lat)[int(.9*len(lat))-1]:.2f}s | "
      f"input tokens mean {statistics.mean(tok):.0f} total {sum(tok)}")
for s in ("noul", "1-P(kind=none)"):
    pos = [sig(L, A)[s] for L, A, _ in rows if L["defect"]]
    neg = [sig(L, A)[s] for L, A, _ in rows if not L["defect"]]
    print(f"[{s}] AUROC {auroc(pos, neg):.3f} | mean defect {statistics.mean(pos):.3f} vs clean "
          f"{statistics.mean(neg) if neg else float('nan'):.3f} | at 0.5: TPR {sum(p>0.5 for p in pos)/len(pos):.2f}"
          f" FPR {sum(n>0.5 for n in neg)/len(neg) if neg else float('nan'):.2f} (n+ {len(pos)}, n- {len(neg)})")

# by kind / magnitude
g = defaultdict(list)
for L, A, _ in rows:
    g[(L["kind"], L.get("mag", 0))].append(A["defect"]["noul"])
print("mean noul by (kind, shift px):", {f"{k[0]}{'/'+str(k[1]) if k[1] else ''}": f"{statistics.mean(v):.2f} (n{len(v)})"
                                         for k, v in sorted(g.items())})

# predicted kind
conf = defaultdict(lambda: defaultdict(int))
for L, A, _ in rows:
    conf[L["kind"]][A["kind"]["choice"]] += 1
print("kind confusion (true -> predicted):", {k: dict(v) for k, v in conf.items()})

# localisation on synthetic offsets
off = [(L, A) for L, A, _ in rows if L["kind"] == "offset"]
if off:
    def acc(f): return sum(f(L, A) for L, A in off) / len(off)
    print(f"offsets n={len(off)}: part acc {acc(lambda L,A: A['part']['choice']==L['part']):.2f} (chance ~0.11) | "
          f"direction acc {acc(lambda L,A: A['direction']['choice']==L['direction']):.2f} (chance 0.25 over 4 dirs) | "
          f"P(true dir) mean {statistics.mean(A['direction']['probabilities'][L['direction']] for L,A in off):.3f}")
    side_rows = [(L, A) for L, A in off if L.get("side")]
    if side_rows:
        print(f"  side acc (hands/feet/antlers) {sum(A['side']['choice']==L['side'] for L,A in side_rows)/len(side_rows):.2f} n={len(side_rows)}")
    for m in sorted({L["mag"] for L, _ in off}):
        sub = [(L, A) for L, A in off if L["mag"] == m]
        print(f"  shift {m:>2}px: noul {statistics.mean(A['defect']['noul'] for _,A in sub):.2f} "
              f"mag score {statistics.mean(A['magnitude']['score'] for _,A in sub):.2f} "
              f"dir acc {sum(A['direction']['choice']==L['direction'] for L,A in sub)/len(sub):.2f} n={len(sub)}")
    bypart = defaultdict(list)
    for L, A in off: bypart[L["part"]].append(A["defect"]["noul"])
    print("  noul by shifted part:", {k: round(statistics.mean(v), 2) for k, v in bypart.items()})

# paired before/after (real set)
pairs = defaultdict(dict)
for L, A, _ in rows:
    if "pair" in L: pairs[L["pair"]][L["defect"]] = A["defect"]["noul"]
pp = [(v[True], v[False], k) for k, v in pairs.items() if True in v and False in v]
if pp:
    print(f"paired before/after: defective tile scored higher in {sum(a>b for a,b,_ in pp)}/{len(pp)} pairs")
    for a, b, k in sorted(pp, key=lambda x: x[2]):
        print(f"   {k:32s} defect {a:.3f}  fixed {b:.3f}  {'OK' if a>b else 'MISS'}")
