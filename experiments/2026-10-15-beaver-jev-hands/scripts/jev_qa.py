# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Jev QA next to spine_qa: what a viewer would notice, scored against approved rigs instead of a 0.5 threshold.

  uv run jev_qa.py <char>=<rig dir> --ref fox=<rig dir> --ref moose=<rig dir> [--prev <rig dir>] --out <dir>

Each rig dir sits next to its annotations.json and master (the rig-annotations layout). Four passes:
  joints   each hinge, master crop | render crop (joint_crops.py), Jev's 0-3 "how broken" score. A joint is WORSE when
           its score is above the approved rigs' worst score for that joint type (shoulder, elbow, wrist, ...): Jev
           scores every rig's joints below 0.5 "matches", so only the comparison carries information.
  pairs    with --prev: per joint, "which render matches the master better", both orders averaged (Jev has no
           position bias on pairs). P(new better) > 0.6 = BETTER, < 0.4 = WORSE.
  frames   6 frames per animation, whole frame, P(rigging defect) (round 5: AUROC 0.89 one frame at a time on real
           rejected frames). Frames above the approved rigs' 90th percentile are listed for a person to look at first.
  holds    jev_rig_check.py (pose reads, thumb up, finger direction, anatomy).
Writes <out>/jev_qa.json and <out>/frames_to_review.png; prints a summary."""
import argparse, json, statistics as st, subprocess, sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import jev  # noqa: E402
import joint_crops as jc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("rig"); ap.add_argument("--ref", action="append", default=[]); ap.add_argument("--prev")
ap.add_argument("--out", required=True); ap.add_argument("--frames-per-anim", type=int, default=6)
args = ap.parse_args()
OUT = Path(args.out); OUT.mkdir(parents=True, exist_ok=True)
HERE = Path(__file__).parent


def spec(s):
    c, d = s.split("=", 1); d = Path(d)
    return c, d, d.parent / "annotations.json"


def kind(j):
    return j.split("_")[0]


JQ_TASK = ("Quality check of a 2D cutout character rig for a mobile game. `master` is the approved original illustration. "
           "`render` is the rig: the same character re-assembled from separately painted parts by a skeleton, in the same "
           "pose. Both images are crops of exactly the same place, around one joint.")


def broken_q(what):
    return {"broken": {"type": "score", "instructions": f"How broken does {what} look in `render`, judged against `master`?",
                       "criteria": ["Exactly as in the master.", "Slightly off: a small shift or size difference.",
                                    "Clearly off: a visible step, gap, wrong size or misplaced part.",
                                    "Badly broken: the parts obviously do not belong together."]}}


def joint_scores(c, rigdir, ann, tag):
    d = OUT / f"joints_{tag}"; d.mkdir(exist_ok=True)
    rows, *_ = jc.crops(c, rigdir, ann, d, tag=tag)
    jobs = [(r["id"], {"task": JQ_TASK, "master": "{m}", "render": "{r}"}, broken_q(r["what"]),
             {"{m}": d / f"{r['id']}__master.png", "{r}": d / f"{r['id']}__render.png"}, {}) for r in rows]
    p = d / "jev.jsonl"; p.unlink(missing_ok=True); jev.run_many(jobs, p, 4)
    a = {json.loads(l)["id"]: json.loads(l)["answers"] for l in open(p)}
    return {r["joint"]: round(a[r["id"]]["broken"]["score"], 2) for r in rows}, rows, d


FRAME_Q = {"defect": {"type": "noul",
                      "instructions": "Does the rendered frame in `frame` show a rigging or stitching defect: a part "
                                      "displaced from where it should attach, a visible gap or seam at a joint, a sleeve "
                                      "or limb that looks stuck on rather than part of the clothing, a part drawn in front "
                                      "of something it should be behind, or a mirrored part?",
                      "criteria": {"true": "At least one such defect is visible.",
                                   "false": "The frame looks like a clean, seamless illustration."}}}


def frame_scores(c, rigdir, tag):
    import spine_qa as q
    rig = q.Rig(rigdir / f"{c}.json"); cv = q.Canvas(rig, 720)
    d = OUT / f"frames_{tag}"; d.mkdir(exist_ok=True)
    jobs, meta = [], {}
    for a in rig.data["animations"]:
        T = rig.duration(a); n = args.frames_per_anim
        for i in range(n):
            t = round(T * (i + 0.5) / n, 3)
            fr, *_ = q.render(rig, cv, a, t)
            fid = f"{c}__{a}_{t:.2f}"; p = d / f"{fid}.png"; fr.convert("RGB").save(p)
            jobs.append((fid, {"task": "A 2D cutout character rig for a mobile game, rendered on flat grey.", "frame": "{f}"},
                         FRAME_Q, {"{f}": p}, {})); meta[fid] = (a, t, p)
    p = d / "jev.jsonl"; p.unlink(missing_ok=True); jev.run_many(jobs, p, 4)
    a = {json.loads(l)["id"]: json.loads(l)["answers"]["defect"]["noul"] for l in open(p)}
    return {k: (meta[k][0], meta[k][1], round(v, 3), str(meta[k][2])) for k, v in a.items()}


report = {}
c, rigdir, ann = spec(args.rig)
sys.path.insert(0, str(jc.REPO / "plugin/skills/skipbo-art/scripts"))

# 1. joints against approved references
ref_joint = {}
for r in args.ref:
    rc, rd, ra = spec(r)
    sc, *_ = joint_scores(rc, rd, ra, f"ref_{rc}")
    for j, v in sc.items():
        ref_joint.setdefault(kind(j), []).append(v)
mine, jrows, jdir = joint_scores(c, rigdir, ann, c)
report["joints"] = {j: {"broken": v, "ref_max": max(ref_joint.get(kind(j), [3])), "ref_mean": round(st.mean(ref_joint.get(kind(j), [0])), 2),
                        "verdict": "WORSE than approved" if v > max(ref_joint.get(kind(j), [3])) else "within approved range"}
                    for j, v in mine.items()}

# 2. pairs against the previous build
if args.prev:
    prev_scores, prows, pdir = joint_scores(c, Path(args.prev), ann, "prev")
    jobs = []
    for r in jrows:
        pid = r["id"].replace(f"__{c}__", "__prev__")
        for order in (0, 1):
            a_, b_ = (jdir / f"{r['id']}__render.png", pdir / f"{pid}__render.png")
            if order:
                a_, b_ = b_, a_
            jobs.append((f"{r['joint']}__{order}", {"task": JQ_TASK.replace("`render` is", "`render_1` and `render_2` are two builds of")
                         .replace("Both images are", "All three images are"), "master": "{m}", "render_1": "{a}", "render_2": "{b}"},
                         {"closer": {"type": "choice", "instructions": f"Which render shows {r['what']} more like `master`: the "
                                     "same part sizes and positions, the parts meeting the same way?",
                                     "criteria": {"render_1": "`render_1` is closer to `master`.", "render_2": "`render_2` is closer to `master`."}}},
                         {"{m}": jdir / f"{r['id']}__master.png", "{a}": a_, "{b}": b_}, {}))
    p = OUT / "pairs.jsonl"; p.unlink(missing_ok=True); jev.run_many(jobs, p, 4)
    pa = {json.loads(l)["id"]: json.loads(l)["answers"]["closer"]["probabilities"] for l in open(p)}
    report["pairs"] = {}
    for r in jrows:
        j = r["joint"]
        p_new = (pa[f"{j}__0"]["render_1"] + pa[f"{j}__1"]["render_2"]) / 2
        report["pairs"][j] = {"p_new_better": round(p_new, 2), "prev_broken": prev_scores.get(j), "new_broken": mine[j],
                              "verdict": "BETTER" if p_new > 0.6 else "WORSE" if p_new < 0.4 else "about the same"}

# 3. frames against approved references
ref_frames = []
for r in args.ref:
    rc, rd, _ = spec(r)
    ref_frames += [v[2] for v in frame_scores(rc, rd, f"ref_{rc}").values()]
fs = frame_scores(c, rigdir, c)
p90 = sorted(ref_frames)[int(0.9 * (len(ref_frames) - 1))] if ref_frames else 0.5
flagged = sorted(((v[2], k, v) for k, v in fs.items() if v[2] > p90), reverse=True)
report["frames"] = {"ref_p90": round(p90, 3), "ref_mean": round(st.mean(ref_frames), 3) if ref_frames else None,
                    "mean": round(st.mean(v[2] for v in fs.values()), 3), "n": len(fs),
                    "to_review": [{"anim": v[0], "t": v[1], "p_defect": v[2]} for _, _, v in flagged[:8]]}
if flagged:
    T = 300; sheet = Image.new("RGB", (T * min(4, len(flagged)), T * ((min(8, len(flagged)) + 3) // 4) + 20), "white")
    for i, (_, k, v) in enumerate(flagged[:8]):
        im = Image.open(v[3]); im.thumbnail((T, T - 16))
        sheet.paste(im, ((i % 4) * T, (i // 4) * T + 16)); ImageDraw.Draw(sheet).text(((i % 4) * T + 3, (i // 4) * T + 2), f"{v[0]} {v[1]}s P={v[2]}", fill="black")
    sheet.save(OUT / "frames_to_review.png")

# 4. holds
hr = subprocess.run(["uv", "run", "-q", str(HERE / "jev_rig_check.py"), args.rig, "--out", str(OUT / "holds")], capture_output=True, text=True)
report["holds"] = json.load(open(OUT / "holds/jev_rig_check.json")) if (OUT / "holds/jev_rig_check.json").exists() else hr.stdout[-800:]

json.dump(report, open(OUT / "jev_qa.json", "w"), indent=1)
print("JOINTS (Jev 'broken' 0-3; approved fox/moose max per joint type)")
for j, v in report["joints"].items():
    print(f"  {j:11s} {v['broken']:.2f}  approved max {v['ref_max']:.2f}  {v['verdict']}")
if "pairs" in report:
    print("PAIRS vs previous build (P new closer to master, both orders)")
    for j, v in report["pairs"].items():
        print(f"  {j:11s} {v['p_new_better']:.2f}  {v['verdict']}  ({v['prev_broken']} -> {v['new_broken']})")
f = report["frames"]
print(f"FRAMES mean P(defect) {f['mean']} vs approved {f['ref_mean']} (p90 {f['ref_p90']}); {len(flagged)} above approved p90")
for x in f["to_review"]:
    print(f"  look at {x['anim']} {x['t']}s  P={x['p_defect']}")
print("HOLDS"); print(hr.stdout.strip()[-1500:])
