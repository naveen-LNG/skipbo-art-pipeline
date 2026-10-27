"""Jev judges each hinge of a rig against the master: pixel-aligned crops from joint_crops.py.

  python3 jev_joints.py <crops dir> [--tag name]   -> <crops dir>/jev_joints_<tag>.jsonl and a table

Per joint, one request with `master` and `render` in the state (the same box of each) and four questions:
  matches_master  noul  the render's join looks like the master's (sizes, position, how the parts meet)
  seamless        noul  the render's parts meet like one drawing, not cut-out pieces stuck on top of each other
  size            choice the render's part is smaller / the same / larger than in the master
  worst           score  how broken the join looks, 0 (as in the master) .. 3 (obviously broken)
A joint is flagged when P(matches) < 0.5 or P(seamless) < 0.5."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jev  # noqa: E402

D = Path(sys.argv[1]); tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "run"
rows = [json.loads(l) for l in open(D / "labels.jsonl")]
TASK = ("Quality check of a 2D cutout character rig for a mobile game. `master` is the approved original illustration. "
        "`render` is the rig: the same character re-assembled from separately painted parts by a skeleton, in the same "
        "pose. Both images are crops of exactly the same place, around one joint.")


def questions(what):
    return {
        "matches_master": {"type": "noul",
                           "instructions": f"Look at {what}. Does `render` show this join the way `master` does: the parts at "
                                           "the same sizes and in the same places, meeting each other the same way? Ignore "
                                           "small differences in shading or texture.",
                           "criteria": {"true": "The join in `render` looks like the join in `master`.",
                                        "false": "The join in `render` differs from `master`: a part is a different size, "
                                                 "shifted, turned, missing, or the parts meet differently."}},
        "seamless": {"type": "noul",
                     "instructions": f"Look at {what} in `render` only. Do the parts meet like one continuous drawing, for "
                                     "example a sleeve that grows out of the shoulder like a real garment, or does it look "
                                     "like separate cut-out pieces stuck on top of each other, with visible round ends, "
                                     "steps, gaps or overlaps?",
                     "criteria": {"true": "One continuous drawing: the join looks natural.",
                                  "false": "Cut-out pieces: round ends, steps, gaps or a part stuck on top shows."}},
        "size": {"type": "choice",
                 "instructions": f"Compared with `master`, how big is the part at {what} in `render`?",
                 "criteria": {"smaller": "Noticeably smaller or thinner in `render`.", "same": "About the same size.",
                              "larger": "Noticeably larger or thicker in `render`."}},
        "broken": {"type": "score",
                   "instructions": f"How broken does {what} look in `render`, judged against `master`?",
                   "criteria": ["Exactly as in the master.", "Slightly off: a small shift or size difference.",
                                "Clearly off: a visible step, gap, wrong size or misplaced part.",
                                "Badly broken: the parts obviously do not belong together."]},
    }


jobs = [(r["id"], {"task": TASK, "master": "{master}", "render": "{render}"}, questions(r["what"]),
         {"{master}": D / f"{r['id']}__master.png", "{render}": D / f"{r['id']}__render.png"}, {"joint": r["joint"]})
        for r in rows]
out = D / f"jev_joints_{tag}.jsonl"
if out.exists():
    out.unlink()
jev.run_many(jobs, out, 4)
res = {json.loads(l)["id"]: json.loads(l) for l in open(out)}
print(f"{'joint':12s} {'P(match)':>8s} {'P(seam)':>8s} {'size':>8s} {'broken':>7s}  flag")
for r in rows:
    a = res[r["id"]]["answers"]
    pm, ps = a["matches_master"]["noul"], a["seamless"]["noul"]
    print(f"{r['joint']:12s} {pm:8.2f} {ps:8.2f} {a['size']['choice']:>8s} {a['broken']['score']:7.2f}  "
          f"{'FLAG' if pm < 0.5 or ps < 0.5 else ''}")
