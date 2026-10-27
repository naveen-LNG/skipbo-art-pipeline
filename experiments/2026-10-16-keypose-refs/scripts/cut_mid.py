"""Cut the in-between out of a legs-midpoint image (prompts/legs-midpoint.txt: A copy | in-between | B copy), bring it
to the real drawings' pixel scale (by the copies' belt widths), colour-match it to the rig, and add it as
legs/<name>.png with its metrics. Its height is declared halfway between A's and B's (height_px): the model draws
the shape halfway but not reliably the height, and the squash to that height is small.

  uv run --with numpy --with pillow --with scipy scripts/cut_mid.py <mid image> <A name> <B name> <out name> <rig images>
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cut_sheet as cs  # noqa: E402
from cut_legs import cut, metrics  # noqa: E402

EXP = Path(__file__).resolve().parent.parent
src, a_name, b_name, name, rig_images = sys.argv[1:6]
mets = {json.loads(l)["name"]: json.loads(l) for l in (EXP / "legs/metrics.jsonl").read_text().splitlines()}
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / "legs").mkdir()
    (tmp / "legs/metrics.jsonl").write_text("")
    cs.EXP = tmp
    cs.main(Path(src).resolve(), "m", Path(rig_images))
    got = [json.loads(l) for l in (tmp / "legs/metrics.jsonl").read_text().splitlines()]
    assert len(got) == 3, f"expected 3 drawings, found {len(got)}"
    A, M, B = got
    a, b = mets[a_name], mets[b_name]
    h = lambda m: m["sole_y"] - m["buckle_y"]
    f = 0.5 * (a["belt_w"] / A["belt_w"] + b["belt_w"] / B["belt_w"])   # the copies' belts -> the real drawings' belts
    im = Image.open(tmp / "legs/m_2.png")
    im = im.resize((round(im.width * f), round(im.height * f)), Image.LANCZOS)
    im.save(EXP / f"legs/{name}.png")
    al = np.asarray(im)
    m = metrics(al[..., 3] > 127, al[..., :3])
    with open(EXP / "legs/metrics.jsonl", "a") as fh:
        fh.write(json.dumps(dict(m, name=name, height_px=0.5 * (h(a) + h(b)))) + "\n")   # declared: halfway
    print(name, f"scale {f:.3f}", json.dumps(m), "| A", h(a), "B", h(mets[b_name]), "mid", round(m["sole_y"] - m["buckle_y"], 1))
