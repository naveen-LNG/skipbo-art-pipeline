"""rig_trousers.py - one-piece trousers: the belt-to-crotch hips over its two cuffed legs, as one hips piece
(spine_rig.py --annotations, master.layers leg: in_hips).

The body sheet paints the lower body as the template asks (hips to the crotch, each leg in two: leg, foot), and the
rig needs no leg bones: the hips piece is composited here at the sheet's scale, legs under the hips, so the rig is
leg-less and the feet go under the trouser cuffs (foot: under_hips, the default), as in a master whose cuffs lie over
the boots. Each leg's hip point goes into the hips' leg opening on its side, pushed in by a third of the opening's
depth and narrowed to the opening by up to NARROW_MAX, as rig_place does for a leg; the leg keeps its painted
(upright) direction. The composite's points: the hips' waist, and hip_l / hip_r at the legs' hems (the cuff
openings) with the hems' widths and depths, so the master's hip_l / hip_r are annotated at the trouser cuffs, as for
any leg-less hips. The leg pieces' outputs are dropped from the annotations in memory (rig_place.has_legs is False).

Before this, the rabbit, the red panda, the bear (and the beaver, 2026-10-15) each asked the sheet for the whole lower
body as ONE piece, which fights the template's "each leg in two": the model painted shorts or belt-to-hem trousers,
and each character rebuilt its trousers with an experiment-local make_trousers.py.

  info = rig_trousers.compose(ann, out_dir)     # None unless master.layers has leg: in_hips
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

NARROW_MAX = 0.15         # a leg's top may be narrowed this much to fit the hips' opening (rig_place.NARROW_MAX)
PUSH = 1 / 3              # the leg's top goes this x the opening's depth into the hips (rig_place's push-in)
DEPTH_FRAC = 0.35         # an opening without a measured depth: this x its width (rig_annotations.OPENING_DEPTH_FRAC)


def wanted(ann) -> bool:
    return ann is not None and ann.master.layers.get("leg") == "in_hips"


def compose(ann, out_dir: Path) -> dict | None:
    """Composite the rest hips over the rest legs into <out_dir>/trousers/<character>_hips.png and point the hips
    output at it; drop the legs' outputs. Returns {"file", "legs": {side: {"offset", "narrow"}}} or None."""
    if not wanted(ann):
        return None
    root = ann.path.parent
    rest = {o.name: (p, o) for p in ann.pieces.values() if p.variant in (None, "rest") for o in p.outputs}
    hips = next(((p, o) for p, o in rest.values() if p.role == "hips"), None)
    legs = {o.name[-1]: (p, o) for p, o in rest.values() if p.role == "leg" and o.name[-2:] in ("_l", "_r")}
    if hips is None or set(legs) != {"l", "r"}:
        raise SystemExit("annotations: master.layers leg: in_hips needs a rest hips piece and both rest legs "
                         f"(found hips: {hips is not None}, legs: {sorted(legs) or 'none'})")
    for s, (p, o) in legs.items():
        miss = [n for n in ("hip", "hem") if n not in o.points] + [n for n in ("hem",) if n not in o.widths]
        if miss or f"hip_{s}" not in hips[1].points:
            raise SystemExit(f"annotations: leg: in_hips: {o.name} needs hip, hem and the hem's width, and the hips "
                             f"its hip_{s} point (missing: {', '.join(miss) or f'hips hip_{s}'})")
    ho = hips[1]
    himg = Image.open(root / ho.file).convert("RGBA")
    placed, info = [], {"legs": {}}
    for s, (p, o) in sorted(legs.items()):
        limg = Image.open(root / o.file).convert("RGBA")
        wo, wl = ho.widths.get(f"hip_{s}"), o.widths.get("hip")
        f = float(np.clip(wo / wl, 1 - NARROW_MAX, 1.0)) if wo and wl else 1.0
        hx, sx = o.points["hip"][0], 1.0
        if f < 1.0:                                       # narrowed across
            nw = max(1, round(limg.width * f))
            sx = nw / limg.width
            limg = limg.resize((nw, limg.height), Image.LANCZOS)
        depth = ho.depths.get(f"hip_{s}") or (DEPTH_FRAC * wo if wo else 0.0)
        tx, ty = ho.points[f"hip_{s}"][0], ho.points[f"hip_{s}"][1] - PUSH * depth   # into the hips, upward
        off = np.array([tx - hx * sx, ty - o.points["hip"][1]])
        hem = np.array([o.points["hem"][0] * sx, o.points["hem"][1]]) + off
        placed.append((s, limg, off, hem, o.widths["hem"] * sx, o.depths.get("hem")))
        info["legs"][s] = {"offset": [round(float(v), 1) for v in off], "narrow": round(f, 3)}
    # one canvas holding the hips (at 0, 0) and both legs
    x0 = min([0.0] + [off[0] for _, _, off, *_ in placed])
    y0 = min([0.0] + [off[1] for _, _, off, *_ in placed])
    x1 = max([himg.width] + [off[0] + im.width for _, im, off, *_ in placed])
    y1 = max([himg.height] + [off[1] + im.height for _, im, off, *_ in placed])
    shift = np.array([-np.floor(x0), -np.floor(y0)])
    canvas = Image.new("RGBA", (int(np.ceil(x1 + shift[0])), int(np.ceil(y1 + shift[1]))), (0, 0, 0, 0))
    for _, im, off, *_ in placed:                         # legs first: the hips lie over their tops
        canvas.alpha_composite(im, tuple(int(round(v)) for v in off + shift))
    canvas.alpha_composite(himg, tuple(int(v) for v in shift))
    out = Path(out_dir) / "trousers"
    out.mkdir(parents=True, exist_ok=True)
    path = (out / f"{ann.character}_{ho.name}.png").resolve()
    canvas.save(path)
    pts = {n: (x + shift[0], y + shift[1]) for n, (x, y) in ho.points.items() if not n.startswith("hip_")}
    widths = {n: w for n, w in ho.widths.items() if not n.startswith("hip_")}
    depths = {n: d for n, d in ho.depths.items() if not n.startswith("hip_")}
    for s, _, off, hem, w, d in placed:
        pts[f"hip_{s}"] = (float(hem[0] + shift[0]), float(hem[1] + shift[1]))
        widths[f"hip_{s}"] = float(w)
        if d:
            depths[f"hip_{s}"] = float(d)
    ho.file, ho.points, ho.widths, ho.depths = str(path), pts, widths, depths
    for _, (p, _) in legs.items():
        p.outputs = []                                    # leg-less from here on (rig_place.has_legs)
    info["file"] = str(path)
    info["size"] = list(canvas.size)
    return info
