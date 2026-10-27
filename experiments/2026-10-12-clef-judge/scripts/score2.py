#!/usr/bin/env python3
"""Score the joint-crop and pairwise conditions."""
import json, statistics, sys
from collections import defaultdict
from pathlib import Path

H = Path(__file__).parent
MODEL = sys.argv[1] if len(sys.argv) > 1 else "clef-flash"


def auroc(pos, neg):
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


# pairwise (real before/after)
P = [r for r in map(json.loads, open(H / f"real/results_pair_cloudflare_{MODEL}.jsonl")) if r.get("answers")]
ok = [r["answers"]["worse"]["choice"] == r["truth"] for r in P]
print(f"PAIR: picked the defective render in {sum(ok)}/{len(P)}; mean P(correct) "
      f"{statistics.mean(r['answers']['worse']['probabilities'][r['truth']] for r in P):.3f}; "
      f"answers: {dict((c, sum(r['answers']['worse']['choice']==c for r in P)) for c in ('image_1','image_2'))}")
for r in P:
    print(f"   {r['id'][5:40]:36s} truth {r['truth']}  P(truth) {r['answers']['worse']['probabilities'][r['truth']]:.3f}")

if not (H / f"data/joints/results_joint_cloudflare_{MODEL}.jsonl").exists(): raise SystemExit
# joint crops
lab = {r["id"]: r for r in map(json.loads, open(H / "data/joints/labels.jsonl"))}
J = [(lab[r["id"]], r["answers"]) for r in map(json.loads, open(H / f"data/joints/results_joint_cloudflare_{MODEL}.jsonl"))
     if r.get("answers")]
pos = [A["detached"]["noul"] for L, A in J if L["defect"]]; neg = [A["detached"]["noul"] for L, A in J if not L["defect"]]
print(f"\nJOINT: n={len(J)} (+{len(pos)} / -{len(neg)}) AUROC {auroc(pos, neg):.3f} | mean noul defect {statistics.mean(pos):.3f}"
      f" clean {statistics.mean(neg):.3f}")
for th in (0.3, 0.5, 0.7):
    print(f"  threshold {th}: TPR {sum(p>th for p in pos)/len(pos):.2f} FPR {sum(n>th for n in neg)/len(neg):.2f}")
by = defaultdict(list)
for L, A in J:
    if L["defect"]: by[L["mag"]].append(A["detached"]["noul"])
negs = sorted(neg)
for m in sorted(by):
    print(f"  shift {m:>2}px: mean noul {statistics.mean(by[m]):.2f}  AUROC vs clean {auroc(by[m], neg):.2f}  n={len(by[m])}")
bj = defaultdict(lambda: ([], []))
for L, A in J:
    k = L["slot"][:-2] if L["slot"][-2:] in ("_l", "_r") else L["slot"]
    bj[k][0 if L["defect"] else 1].append(A["detached"]["noul"])
for k, (p, n) in bj.items():
    if p and n: print(f"  joint {k:7s} AUROC {auroc(p, n):.2f} (+{len(p)}/-{len(n)})")
D = [(L, A) for L, A in J if L["defect"]]
d4 = sum(max({k: v for k, v in A["direction"]["probabilities"].items() if k != "none"}.items(), key=lambda x: x[1])[0]
         == L["direction"] for L, A in D)
d4b = [(L, A) for L, A in D if L["mag"] >= 16]
print(f"  direction (4-way) {d4}/{len(D)} = {d4/len(D):.2f}; on >=16px "
      f"{sum(max({k: v for k, v in A['direction']['probabilities'].items() if k != 'none'}.items(), key=lambda x: x[1])[0] == L['direction'] for L, A in d4b)}/{len(d4b)}")
