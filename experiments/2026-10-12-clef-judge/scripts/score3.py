#!/usr/bin/env python3
"""Compare joint crops with vs without the master reference, on identical crops."""
import json, random, statistics, sys
from collections import defaultdict
from pathlib import Path

H = Path(__file__).parent / "jref"
lab = {r["id"]: r for r in map(json.loads, open(H / "labels.jsonl"))}
MODEL = sys.argv[1] if len(sys.argv) > 1 else "clef-flash"
PROV = "typesafe" if MODEL.startswith("jev") else "cloudflare"
COND = {"no reference": f"results_joint_{PROV}_{MODEL}.jsonl", "with master crop": f"results_jref_{PROV}_{MODEL}.jsonl"}


def auroc(pos, neg):
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg)) if pos and neg else float("nan")


def boot_ci(pos, neg, n=400):
    rnd = random.Random(0); v = []
    for _ in range(n):
        v.append(auroc([rnd.choice(pos) for _ in pos], [rnd.choice(neg) for _ in neg]))
    v.sort(); return v[int(.025 * n)], v[int(.975 * n)]


def tpr_at_fpr(pos, neg, fpr=0.10):
    th = sorted(neg)[int((1 - fpr) * len(neg)) - 1]
    return sum(p > th for p in pos) / len(pos), th


def base(s): return s[:-2] if s[-2:] in ("_l", "_r") else s


def dir4(a):
    p = {k: v for k, v in a["direction"]["probabilities"].items() if k != "none"}
    return max(p, key=p.get)


summary = {}
for name, f in COND.items():
    R = {r["id"]: r["answers"] for r in map(json.loads, open(H / f)) if r.get("answers")}
    ids = [i for i in lab if i in R]
    pos = [R[i]["detached"]["noul"] for i in ids if lab[i]["defect"]]
    neg = [R[i]["detached"]["noul"] for i in ids if not lab[i]["defect"]]
    lo, hi = boot_ci(pos, neg)
    t, th = tpr_at_fpr(pos, neg)
    print(f"\n== {name}: n={len(ids)} (+{len(pos)}/-{len(neg)})")
    print(f"  detection AUROC {auroc(pos, neg):.3f}  [95% CI {lo:.2f}-{hi:.2f}] | mean P defect {statistics.mean(pos):.3f} clean {statistics.mean(neg):.3f}")
    print(f"  at 10% false alarms (threshold {th:.2f}): catches {t:.0%} of shifted joints")
    for m in (8, 16, 24):
        pm = [R[i]["detached"]["noul"] for i in ids if lab[i]["defect"] and lab[i]["mag"] == m]
        dm = [i for i in ids if lab[i]["defect"] and lab[i]["mag"] == m]
        print(f"  shift {m:>2}px: AUROC {auroc(pm, neg):.2f}  direction {sum(dir4(R[i]) == lab[i]['direction'] for i in dm)/len(dm):.0%} (n={len(dm)})")
    byj = defaultdict(lambda: ([], []))
    for i in ids:
        byj[base(lab[i]["slot"])][0 if lab[i]["defect"] else 1].append(R[i]["detached"]["noul"])
    print("  by joint: " + "  ".join(f"{k} {auroc(p, n):.2f}" for k, (p, n) in sorted(byj.items())))
    D = [i for i in ids if lab[i]["defect"]]
    acc = sum(dir4(R[i]) == lab[i]["direction"] for i in D) / len(D)
    axis = sum((dir4(R[i]) in ("up", "down")) == (lab[i]["direction"] in ("up", "down")) for i in D) / len(D)
    conf = defaultdict(lambda: defaultdict(int))
    for i in D: conf[lab[i]["direction"]][dir4(R[i])] += 1
    print(f"  direction 4-way {acc:.0%} (chance 25%) | right axis (vertical vs horizontal) {axis:.0%} (chance 50%)")
    print("  direction confusion true->pred:", {k: dict(v) for k, v in conf.items()})
    pd = defaultdict(list)
    for i in D: pd[base(lab[i]["slot"])].append(dir4(R[i]) == lab[i]["direction"])
    print("  direction by joint: " + "  ".join(f"{k} {sum(v)/len(v):.0%}" for k, v in sorted(pd.items())))
    # same joint, clean render vs shifted: does the shifted one score higher?
    clean = {(lab[i]["char"], lab[i]["slot"]): R[i]["detached"]["noul"] for i in ids if lab[i]["shifted"] == "none"}
    w = [R[i]["detached"]["noul"] > clean[(lab[i]["char"], lab[i]["slot"])] for i in D if (lab[i]["char"], lab[i]["slot"]) in clean]
    print(f"  shifted joint scores above the same joint in the clean render: {sum(w)}/{len(w)} = {sum(w)/len(w):.0%}")
    summary[name] = dict(auroc=auroc(pos, neg), ci=(lo, hi), tpr10=t, dir=acc, axis=axis, paired=sum(w) / len(w),
                         pos=statistics.mean(pos), neg=statistics.mean(neg))
json.dump(summary, open(H / ("summary.json" if MODEL == "clef-flash" else f"summary_{MODEL}.json"), "w"), indent=1)
