# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Palm or back for hand pieces, from Jev's observable cues (run_facing_cues.CUES), averaged over 8 turns x mirror.

  uv run jev_facing.py <out dir> <name>=<piece.png> ...

Bands, set on the user-confirmed fox and moose pieces (12/13 confident calls right, 5 sent to a person):
  score >= -0.05  palm      score <= -0.20  back      in between: ask
Also reports Jev's thumb direction on the upright piece (for placing thumb_tip) and its pose reading."""
import json, statistics as st, sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import jev  # noqa: E402
from hands_set import on_grey  # noqa: E402
from score_hands import circ_mean  # noqa: E402

import run_hands  # noqa: E402
from run_facing_cues import CUES, Q, palm_score as score  # noqa: E402
UPQ = {k: run_hands.Q[k] for k in ("finger_dir", "thumb_dir", "gesture")}
PALM, BACK = -0.05, -0.20
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
state = {"task": "A painted hand (or paw) of a cartoon character, cut out as one piece of a 2D animation rig and shown on a "
                 "flat grey background. The piece may be turned to any angle or mirrored.", "hand": "{hand}"}
jobs, names = [], []
for spec in sys.argv[2:]:
    name, path = spec.split("=", 1); names.append(name)
    im = Image.open(path).convert("RGBA")
    for m in (0, 1):
        base = im.transpose(Image.FLIP_LEFT_RIGHT) if m else im
        for rot in range(0, 360, 45):
            p = out / f"{name}__m{m}_r{rot:03d}.png"
            on_grey(base.rotate(rot, expand=True, resample=Image.BICUBIC)).save(p)
            q = dict(Q, **UPQ) if (m, rot) == (0, 0) else Q
            jobs.append((p.stem, state, q, {"{hand}": p}, {}))
res_path = out / "facing.jsonl"
jev.run_many(jobs, res_path, 4)
res = {json.loads(l)["id"]: json.loads(l)["answers"] for l in open(res_path)}
report = {}
for n in names:
    sc = [score(a) for k, a in res.items() if k.split("__")[0] == n]
    up = res[f"{n}__m0_r000"]
    m = st.mean(sc)
    report[n] = {"score": round(m, 3), "facing": "palm" if m >= PALM else "back" if m <= BACK else "ask",
                 "n": len(sc), "thumb_dir_upright": up["thumb_dir"]["choice"],
                 "thumb_deg_upright": round(circ_mean(up["thumb_dir"]["probabilities"])[0]),
                 "finger_dir_upright": up["finger_dir"]["choice"], "reads_as": up["gesture"]["choice"]}
    print(f"{n:24s} score={m:+.3f} -> {report[n]['facing']:5s} thumb={report[n]['thumb_dir_upright']:10s} "
          f"fingers={report[n]['finger_dir_upright']:10s} reads={report[n]['reads_as']}")
json.dump(report, open(out / "facing.json", "w"), indent=1)
