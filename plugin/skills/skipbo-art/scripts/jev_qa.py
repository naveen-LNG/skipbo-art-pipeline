#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""jev_qa.py - optional, beside spine_qa: Jev looks at the rig the way a viewer would, against approved rigs.

  uv run scripts/jev_qa.py <char>/rig/<char>.json [--ref <approved rig.json> ...] [--prev <previous build.json>]
                           [--annotations <char>/annotations.json] [--out <rig>/qa/jev]

Jev's absolute answers carry little: every joint of the approved fox and moose scores P(matches master) < 0.5. Its
comparisons carry a lot (the beaver's round 2: pairs against the previous build matched every visible change). So
nothing here is a threshold on one answer, and only one thing fails:

  joints  each hinge, master crop | render crop (joint_crops.py), Jev's 0-3 "how broken". WARN when above the worst
          score of that joint type (shoulder, elbow, ...) on the --ref rigs; without --ref, a ranked list
  pairs   with --prev: per joint, "which render matches the master better", asked in both orders and averaged.
          P(new better) > 0.6 BETTER, < 0.4 WARN worse. One pair is noise, a pattern is signal
  frames  6 frames per animation, P(rigging defect), ranked; frames above the --ref rigs' 90th percentile are
          listed to look at first (rig/qa/jev/frames_to_review.png)
  holds   jev_hands.check_holds: FAIL when a point or thumbs_up hold does not show the thumb up (AUROC 0.99);
          WARN when a hold doesn't read as its pose, a point aims across the body, or anatomy says the other hand

Writes <out>/jev_qa.json and prints a summary. Exit 1 only on a hold FAIL. The joints contact sheet (rig/qa/joints.png,
or <out>/joints.png with --out; no Jev needed) is written first; without a TypeSafe key the rest prints SKIP and exits 0. About 200 calls (~$0.02)
with two refs; answers are cached in <out>/jev_cache.jsonl, so the refs cost nothing the second time.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import jev_client
import jev_hands
import joint_crops as jc

TASK = ("Quality check of a 2D cutout character rig for a mobile game. `master` is the approved original illustration. "
        "`render` is the rig: the same character re-assembled from separately painted parts by a skeleton, in the same "
        "pose. Both images are crops of exactly the same place, around one joint.")
PAIR_TASK = TASK.replace("`render` is", "`render_1` and `render_2` are two builds of").replace(
    "Both images are", "All three images are")
FRAME_Q = {"defect": {"type": "noul",
                      "instructions": "Does the rendered frame in `frame` show a rigging or stitching defect: a part "
                                      "displaced from where it should attach, a visible gap or seam at a joint, a sleeve "
                                      "or limb that looks stuck on rather than part of the clothing, a part drawn in "
                                      "front of something it should be behind, or a mirrored part?",
                      "criteria": {"true": "At least one such defect is visible.",
                                   "false": "The frame looks like a clean, seamless illustration."}}}
FRAME_STATE = {"task": "A 2D cutout character rig for a mobile game, rendered on flat grey.", "frame": "{f}"}
BETTER, WORSE = 0.6, 0.4
FRAME_P = 0.9          # frames above this percentile of the approved rigs' are listed to look at
FRAME_H = 720
TO_REVIEW = 8


def broken_q(what: str) -> dict:
    return {"broken": {"type": "score", "instructions": f"How broken does {what} look in `render`, judged against "
                                                        "`master`?",
                       "criteria": ["Exactly as in the master.", "Slightly off: a small shift or size difference.",
                                    "Clearly off: a visible step, gap, wrong size or misplaced part.",
                                    "Badly broken: the parts obviously do not belong together."]}}


def closer_q(what: str) -> dict:
    return {"closer": {"type": "choice",
                       "instructions": f"Which render shows {what} more like `master`: the same part sizes and "
                                       "positions, the parts meeting the same way?",
                       "criteria": {"render_1": "`render_1` is closer to `master`.",
                                    "render_2": "`render_2` is closer to `master`."}}}


def joint_scores(rows: list, cache) -> dict:
    jobs = [(r["id"], {"task": TASK, "master": "{m}", "render": "{r}"}, broken_q(r["what"]),
             {"{m}": r["master"], "{r}": r["render"]}) for r in rows]
    ans = jev_client.run(jobs, cache=cache)
    return {r["joint"]: round(ans[r["id"]]["broken"]["score"], 2) for r in rows if r["id"] in ans}


def joint_verdicts(mine: dict, ref: dict) -> dict:
    """mine {joint: broken}; ref {joint type: [broken on the approved rigs]} -> {joint: {...}}, worst first."""
    out = {}
    for j, v in sorted(mine.items(), key=lambda kv: -kv[1]):
        r = ref.get(jc.kind(j))
        out[j] = {"broken": v, "ref_max": max(r) if r else None,
                  "verdict": ("no reference" if not r else
                              "WARN worse than approved" if v > max(r) else "within approved range")}
    return out


def pair_verdict(p_new: float) -> str:
    return "BETTER" if p_new > BETTER else "WARN worse" if p_new < WORSE else "about the same"


def pairs(rows: list, prev_rows: dict, cache) -> dict:
    """Both orders per joint; P(new closer) averaged so Jev's position preference cancels."""
    jobs = []
    for r in rows:
        pr = prev_rows.get(r["joint"])
        if not pr:
            continue
        for order, (a, b) in enumerate(((r["render"], pr["render"]), (pr["render"], r["render"]))):
            jobs.append((f"{r['joint']}__{order}", {"task": PAIR_TASK, "master": "{m}", "render_1": "{a}",
                                                    "render_2": "{b}"},
                         closer_q(r["what"]), {"{m}": r["master"], "{a}": a, "{b}": b}))
    ans = jev_client.run(jobs, cache=cache)
    out = {}
    for r in rows:
        j = r["joint"]
        if f"{j}__0" in ans and f"{j}__1" in ans:
            p = (ans[f"{j}__0"]["closer"]["probabilities"].get("render_1", 0)
                 + ans[f"{j}__1"]["closer"]["probabilities"].get("render_2", 0)) / 2
            out[j] = {"p_new_better": round(p, 2), "verdict": pair_verdict(p)}
    return out


def frame_scores(rig_json: Path, out: Path, n: int, cache) -> dict:
    """{frame id: {"anim", "t", "p_defect", "path"}}, n frames per animation, mid-interval."""
    import spine_qa as q
    rig = q.Rig(Path(rig_json))
    cv = q.Canvas(rig, FRAME_H)
    out.mkdir(parents=True, exist_ok=True)
    meta, jobs = {}, []
    for a in rig.data["animations"]:
        T = rig.duration(a)
        for i in range(n):
            t = round(T * (i + 0.5) / n, 3)
            fid = f"{rig.path.stem}__{a}_{t:.2f}"
            p = out / f"{fid}.png"
            q.render(rig, cv, a, t)[0].convert("RGB").save(p)
            meta[fid] = {"anim": a, "t": t, "path": str(p)}
            jobs.append((fid, FRAME_STATE, FRAME_Q, {"{f}": p}))
    ans = jev_client.run(jobs, cache=cache)
    return {k: {**m, "p_defect": round(ans[k]["defect"]["noul"], 3)} for k, m in meta.items() if k in ans}


def percentile(xs: list, p: float):
    return sorted(xs)[int(p * (len(xs) - 1))] if xs else None


def frames_sheet(items: list, path: Path) -> Path:
    t = 300
    cols = min(4, len(items))
    im = Image.new("RGB", (t * cols, t * (-(-len(items) // 4)) + 20), "white")
    for i, f in enumerate(items):
        fr = Image.open(f["path"])
        fr.thumbnail((t, t - 16))
        im.paste(fr, ((i % 4) * t, (i // 4) * t + 16))
        ImageDraw.Draw(im).text(((i % 4) * t + 3, (i // 4) * t + 2), f"{f['anim']} {f['t']}s P={f['p_defect']}",
                                fill="black")
    im.save(path)
    return path


def ref_annotations(rig_json: Path) -> Path:
    return jc.default_annotations(rig_json)


def run(a) -> dict:
    out = a.out or a.rig.parent / "qa" / "jev"
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "jev_cache.jsonl"
    report = {"rig": str(a.rig), "refs": [str(r) for r in a.ref], "prev": str(a.prev) if a.prev else None}

    al = jc.Aligned(a.rig, a.annotations)
    rows = jc.crops(al, out / "joints")
    report["joints_sheet"] = str(jc.sheet(rows, out / "joints.png" if a.out else a.rig.parent / "qa" / "joints.png"))
    if not jev_client.available():
        report["skipped"] = "no TYPESAFE_API_KEY"
        return report

    if "joints" not in a.skip:
        ref = {}
        for r in a.ref:
            rr = jc.crops(jc.Aligned(r, ref_annotations(r)), out / "joints_ref")
            for j, v in joint_scores(rr, cache).items():
                ref.setdefault(jc.kind(j), []).append(v)
        report["joints"] = joint_verdicts(joint_scores(rows, cache), ref)
    if a.prev and "pairs" not in a.skip:
        boxes = {r["joint"]: (tuple(r["box"]), r["what"]) for r in rows}
        prev = jc.crops(jc.Aligned(a.prev, a.annotations or jc.default_annotations(a.rig)), out / "joints_prev",
                        tag=f"prev_{al.char}", boxes=boxes)          # the same boxes: the same place in both
        report["pairs"] = pairs(rows, {r["joint"]: r for r in prev}, cache)
    if "frames" not in a.skip:
        ref_p = [f["p_defect"] for r in a.ref for f in frame_scores(r, out / "frames_ref", a.frames_per_anim,
                                                                     cache).values()]
        fs = frame_scores(a.rig, out / "frames", a.frames_per_anim, cache)
        cut = percentile(ref_p, FRAME_P)
        ranked = sorted(fs.values(), key=lambda f: -f["p_defect"])
        look = [f for f in ranked if cut is None or f["p_defect"] > cut][:TO_REVIEW]
        report["frames"] = {"n": len(fs), "mean": round(st.mean(f["p_defect"] for f in fs.values()), 3) if fs else None,
                            "ref_p90": cut, "ref_mean": round(st.mean(ref_p), 3) if ref_p else None,
                            "above_ref_p90": sum(cut is not None and f["p_defect"] > cut for f in ranked),
                            "to_review": [{k: f[k] for k in ("anim", "t", "p_defect")} for f in look]}
        if look:
            report["frames"]["sheet"] = str(frames_sheet(look, out / "frames_to_review.png"))
    if "holds" not in a.skip:
        report["holds"] = jev_hands.check_holds(a.rig, a.annotations or jc.default_annotations(a.rig),
                                                out / "holds", cache)
    report["fail"] = any(i.startswith("FAIL") for h in report.get("holds", {}).values() for i in h["issues"])
    report["jev"] = dict(jev_client.USAGE)
    return report


def summary(report: dict) -> list:
    lines = [f"joints sheet: {report['joints_sheet']}"]
    if report.get("skipped"):
        return lines + [jev_client.SKIP]
    if "joints" in report:
        lines.append("JOINTS  Jev 'broken' 0-3, worst first (approved max per joint type)")
        for j, v in report["joints"].items():
            ref = f"{v['ref_max']:.2f}" if v["ref_max"] is not None else "-"
            lines.append(f"  {j:11s} {v['broken']:.2f}  approved max {ref}  {v['verdict']}")
    if "pairs" in report:
        lines.append("PAIRS   P(new build closer to the master than the previous), both orders")
        lines += [f"  {j:11s} {v['p_new_better']:.2f}  {v['verdict']}" for j, v in report["pairs"].items()]
    if "frames" in report:
        f = report["frames"]
        lines.append(f"FRAMES  mean P(defect) {f['mean']} vs approved {f['ref_mean']} (p90 {f['ref_p90']}); "
                     f"{f['above_ref_p90']} above the approved p90; look first at:")
        lines += [f"  {x['anim']} {x['t']}s  P={x['p_defect']}" for x in f["to_review"]]
    if "holds" in report:
        lines.append("HOLDS")
        for k, h in report["holds"].items():
            lines.append(f"  {k:20s} reads={h['reads_as']:9s} P={h['p_variant']:.2f} P(up)={h['p_thumb_up']:.2f} "
                         f"finger={h['finger_deg']:4d} thumb={h['thumb_deg']:4d}  {'; '.join(h['issues']) or 'ok'}")
    u = report.get("jev", {})
    lines.append(f"{'FAIL' if report.get('fail') else 'DONE'}  jev_qa: {u.get('calls', 0)} call(s), "
                 f"{u.get('cached', 0)} cached")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rig", type=Path, help="<char>/rig/<char>.json")
    ap.add_argument("--ref", type=Path, action="append", default=[], help="an approved rig's json, repeatable")
    ap.add_argument("--prev", type=Path, help="the previous build's json, to compare joint by joint")
    ap.add_argument("--annotations", type=Path, help="default: <char>/annotations.json next to the rig folder")
    ap.add_argument("--out", type=Path, help="default: <rig>/qa/jev")
    ap.add_argument("--frames-per-anim", type=int, default=6)
    ap.add_argument("--skip", nargs="*", default=[], choices=["joints", "pairs", "frames", "holds"])
    a = ap.parse_args(argv)
    report = run(a)
    out = a.out or a.rig.parent / "qa" / "jev"
    (out / "jev_qa.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("\n".join(summary(report)))
    return 1 if report.get("fail") else 0


if __name__ == "__main__":
    sys.exit(main())
