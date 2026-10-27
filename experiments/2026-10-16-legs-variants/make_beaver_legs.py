"""The beaver's annotations plus its two legs sheets (role legs), for a rig built through the pipeline's legs path.

  python3 make_beaver_legs.py        # writes beaver/annotations.json and beaver_garden/annotations.json

The drawings are the key-pose experiment's in-between sheets, cut and colour-matched to the rig's trousers and boots
(../2026-10-16-keypose-refs/legs/{squat,jump}_{1..5}.png, scripts/cut_sheet.py), and its four midpoint in-betweens
(squat_34, squat_45, jump_23, jump_34: legs-midpoint.txt, cut_mid.py), annotated as <sheet>_<a>-<b>; metrics.jsonl
gives each one's buckle row, belt middle and width, and soles' row. The rig declares an in-between's height itself,
halfway between its two drawings', as cut_mid.py does. They are referenced in place. Each drawing's waist point sits
above its buckle as far as the master's waist point sits above the master's buckle (scaled by belt width); ground is
the soles' row. squat_2 is `ignored`: it is as tall as drawing 1 and barely bent, so kp_rig's sequence skips it too.
Every other piece is the beaver's own (experiments/2026-10-15-beaver-jev-hands/beaver), its output files referenced
in place; beaver_garden/ starts from the garden experiment's copy instead (its `look` heads, for plant_seed and water
with ../2026-10-16-garden-grow/garden/props.json).
"""
import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "2026-10-15-beaver-jev-hands" / "beaver"
KP = HERE.parent / "2026-10-16-keypose-refs" / "legs"
REL = "../../2026-10-15-beaver-jev-hands/beaver/"
GARDEN = HERE.parent / "2026-10-16-garden-grow" / "garden"
REL_GARDEN = "../../2026-10-16-garden-grow/garden/"
REL_KP = "../../2026-10-16-keypose-refs/legs/"
MASTER_BUCKLE_Y, MASTER_BELT_W = 1460.0, 679.0   # the master's own buckle row and belt width, px (cut_legs on the master)
IGNORED = {"squat_2": "as tall as drawing 1 and barely bent; kp_rig's sequence skips it too"}
MIDS = {"squat": [(3, 4), (4, 5)], "jump": [(2, 3), (3, 4)]}   # in-betweens legs/<sheet>_<ab>.png (cut_mid.py)


def write(src: Path, rel: str, out: Path):
    """src's annotations with its relative paths moved to out's folder (rel: src's folder from there), plus the
    legs pieces."""
    ann = json.loads((src / "annotations.json").read_text())

    def moved(f):
        return f if f.startswith("../../") else rel + f    # the garden copy already points into the beaver's folder
    ann["master"]["image"] = moved(ann["master"]["image"])
    for p in ann["pieces"].values():
        for o in p.get("outputs", []):
            o["file"] = moved(o["file"])
    metrics = {json.loads(l)["name"]: json.loads(l) for l in (KP / "metrics.jsonl").read_text().splitlines()}
    with Image.open(SRC / "beaver_master.png") as m:
        up = MASTER_BUCKLE_Y - ann["master"]["points"]["waist"][1] * m.height     # waist above the buckle, master px
    for sheet in ("squat", "jump"):
        for k_, n in enumerate([str(i) for i in range(1, 6)] + [f"{a}-{b}" for a, b in MIDS[sheet]]):
            v, cut = f"{sheet}_{n}", f"{sheet}_{n.replace("-", "")}"
            m = metrics[cut]
            with Image.open(KP / f"{cut}.png") as im:
                w, h = im.size
            x = m["belt_top"][0]
            pts = {"waist": (x, m["buckle_y"] - up * m["belt_w"] / MASTER_BELT_W), "ground": (x, m["sole_y"])}
            ann["pieces"][f"beaver-legs-{sheet}-parts/{k_:02d}"] = {
                "role": "legs", "name": "legs", "variant": v, "side": "",
                "status": "ignored" if v in IGNORED else "confirmed", "confidence": 0.9,
                "note": IGNORED.get(v, "the key-pose experiment's in-between sheet (cut_sheet.py)" if "-" not in n else
                                    "the key-pose experiment's midpoint in-between (legs-midpoint.txt, cut_mid.py)"),
                "points": {k: {"at": [round(px / w, 4), round(py / h, 4)], "kind": "point"} for k, (px, py) in pts.items()},
                "outputs": [] if v in IGNORED else [
                    {"name": f"legs_{v}", "file": REL_KP + f"{cut}.png", "mirrored": False, "rotated": 0.0,
                     "points": {k: [round(px, 2), round(py, 2)] for k, (px, py) in pts.items()}, "widths": {}, "depths": {}}]}
    out.mkdir(exist_ok=True)
    (out / "annotations.json").write_text(json.dumps(ann, indent=1))
    print("wrote", out / "annotations.json")


def main():
    write(SRC, REL, HERE / "beaver")
    write(GARDEN, REL_GARDEN, HERE / "beaver_garden")


if __name__ == "__main__":
    main()
