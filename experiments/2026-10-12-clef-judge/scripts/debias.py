#!/usr/bin/env python3
"""Order-debiased pairwise accuracy.  python3 debias.py <model>"""
import json, sys
from pathlib import Path
H = Path(__file__).parent / "real"; M = sys.argv[1]; P = "typesafe" if M.startswith("jev") else "cloudflare"
A = {r["id"]: r for r in map(json.loads, open(H / f"results_pair_{P}_{M}.jsonl"))}
B = {r["id"]: r for r in map(json.loads, open(H / f"results_pair_swap_{P}_{M}.jsonl"))}
rows = [(k, (A[k]["answers"]["worse"]["probabilities"][A[k]["truth"]] + B[k]["answers"]["worse"]["probabilities"][B[k]["truth"]]) / 2)
        for k in A if k in B]
bf = [m for k, m in rows if "before_after" in k]; sh = [m for k, m in rows if "shoulders" in k]
i1 = sum(r["answers"]["worse"]["choice"] == "image_1" for r in list(A.values()) + list(B.values()))
print(f"{M}: debiased {sum(m > .5 for _, m in rows)}/{len(rows)} | full-body {sum(m > .5 for m in bf)}/{len(bf)} | "
      f"sleeves {sum(m > .5 for m in sh)}/{len(sh)} | answered image_1 {i1}/{len(A) + len(B)}")
for k, m in rows: print(f"   {k[5:40]:36s} {m:.2f}")
