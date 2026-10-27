#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""rig_rest_legs.py - the rig's own lower body at rest (trousers, legs and feet, nothing else) as an image: image_3 of
the legs in-between sheets (references/prompts/spine/legs-inbetweens.txt), "drawing 1 exactly". Painted from it, a
sheet's first drawing matches the rig's own parts, which the legs animations show until their first swap.

  uv run rig_rest_legs.py rig/<name>.json out.png [--annotations annotations.json] [--px-per-unit 1.5]

Writes out.png (transparent, cropped) and out_grey.png (on the sheets' light grey, with a margin). The slots kept are
the ones whose part is a hips, leg or foot (from the annotations' roles; without them, guessed from the slot names),
with their worn back parts.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spine_qa  # noqa: E402
from rig_roles import role  # noqa: E402

GREY = (214, 214, 214, 255)       # the sheets' background
MARGIN = 40


def lower_slots(rig: dict, roles: dict | None) -> set:
    """The slots drawing the trousers, legs and feet at rest (and the feet's worn back slots)."""
    names = {s["name"] for s in rig["slots"]}
    keep = {n for n in names if role(n, roles)[1] in ("hips", "leg", "foot") and n != "legs"}
    keep |= {n for n in names if n.endswith("_back") and n[:-5] in keep}
    return keep


def render(rig_path: Path, roles: dict | None, ppu: float) -> Image.Image:
    d = json.loads(rig_path.read_text(encoding="utf-8"))
    keep = lower_slots(d, roles)
    for s in d["slots"]:
        if s["name"] not in keep:
            s.pop("attachment", None)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / rig_path.name
        d["skeleton"]["images"] = str((rig_path.parent / d["skeleton"].get("images", "./images/")).resolve()) + "/"
        p.write_text(json.dumps(d), encoding="utf-8")
        rig = spine_qa.Rig(p)
        canvas = spine_qa.Canvas(rig, int(rig.data["skeleton"]["height"] * 1.37 * ppu))
        frame = spine_qa.render(rig, canvas, None, 0.0, bg=(0, 0, 0, 0))[0]
    ys, xs = np.nonzero(np.asarray(frame)[..., 3] > 8)
    return frame.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rig", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--annotations", type=Path, help="annotations.json: the parts' roles (else guessed from the names)")
    ap.add_argument("--px-per-unit", type=float, default=1.5)
    a = ap.parse_args(argv)
    roles = None
    if a.annotations:
        import rig_annotations
        import rig_place
        roles = rig_place.output_roles(rig_annotations.load(a.annotations))
    img = render(a.rig, roles, a.px_per_unit)
    img.save(a.out)
    grey = Image.new("RGBA", (img.width + 2 * MARGIN, img.height + 2 * MARGIN), GREY)
    grey.alpha_composite(img, (MARGIN, MARGIN))
    grey.convert("RGB").save(a.out.with_name(a.out.stem + "_grey.png"))
    print(f"wrote {a.out} ({img.width}x{img.height}) and {a.out.stem}_grey.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
