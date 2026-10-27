"""rig_variants.py - pose variants as extra attachments in a part's slot (spine_rig.py stage 4b): open / fist / point
hands, a raised sleeve, a tiptoe foot, a tail up.

Each variant is painted joint end up. It is scaled to its rest part's width at the joint, turned to the rest part's
axis (tubes only) and placed so its joint lands on the rest part's joint. With annotations the joint and scale come
from the variant's annotated points (rig_place.variant_fit) and forearms lose hand-coloured tufts past the wrist
(rig_place.wrist_trim). Worn feet are cut like their rest part (rig_slots.Export.worn_cut); a foot whose rest got a
hidden shaft under the hips (rig_shaft) gets the same one (with_shaft).

Whole legs (annotated role `legs`) are not a part's variants: they are the in-between drawings of a movement, painted
together on one sheet (variant <sheet>_<n>: squat_1 .. squat_5, jump_1 ..; drawing 1 the rest legs), plus in-betweens
painted later between two of them (<sheet>_<a>-<b>). add_legs puts them in two slots, `legs_a` and `legs_b`, each on
a bone of its own at the master's waist, world-upright, appended after the other bones (a weighted sleeve mesh names
its bones by index): rig_anim cross-fades between the two at every swap. The slots sit just above the trousers,
hidden at rest. Each sheet has one scale (a drawing-by-drawing scale flickers), fitted so its drawing 1 covers the
rig's own rest trousers and feet: as wide at the waist, as tall from the waist to the soles. An in-between's height is
declared halfway between its two drawings' (the model paints the shape halfway, not reliably the height), and it is
squashed to that height. rig_anim swaps the drawings in for the trousers and feet, starting from the rig's own parts
(squat, jump_hurdle, plant_seed; experiments/2026-10-16-keypose-refs, sections 2a and 2b).

  variant_report, mesh_skipped = rig_variants.add(ex, variant_dirs, place_info, mid_x, trust)
  legs = rig_variants.add_legs(ex, bones, world, master_px, trust)   # None without legs pieces
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

import rig_shaft
from rig_frame import axis_ends
from rig_image import solidify
from rig_roles import annotated_role, is_role, role

LEGS_ASPECT_DOUBT = 0.12   # a legs sheet stretched this much more one way than the other to fit the rig's rest legs: a doubt


def joint_axis_size(img: Image.Image, kind: str, root_left: bool = True):
    """(joint, axis, size) of a painted part in image px: the joint centre, the direction away from it, and the
    size to scale by - (width, length) for tubes (arm, forearm, leg), the wrist width for a hand, sqrt(area) for a
    foot or tail. root_left: a tail's root is its left end."""
    al = np.asarray(img)[..., 3] > 127
    ys_, xs_ = np.nonzero(al)
    pts = np.stack([xs_, ys_], 1).astype(np.float32)
    C = pts.mean(0)
    if kind == "back":                                   # tail: the root is the end towards the body
        x0, x1 = xs_.min(), xs_.max()
        sel = xs_ <= x0 + 0.12 * (x1 - x0) if root_left else xs_ >= x1 - 0.12 * (x1 - x0)
        band = float(np.ptp(ys_[sel]) + 1)
        J = np.array([x0 + band / 2 if root_left else x1 - band / 2, ys_[sel].mean()])
        return J, C - J, math.sqrt(al.sum())
    e1, e2, width = axis_ends(pts)
    top_end, other = (e1, e2) if e1[1] <= e2[1] else (e2, e1)
    L = float(np.linalg.norm(other - top_end))
    d = (other - top_end) / (L + 1e-9)
    if kind in ("arm", "forearm", "leg"):                # tube: width across the middle, length between joint centres
        proj, perp = (pts - top_end) @ d, (pts - top_end) @ np.array([-d[1], d[0]])
        mid = (proj > 0.3 * L) & (proj < 0.7 * L)
        size = float(np.percentile(perp[mid], 95) - np.percentile(perp[mid], 5))
        return top_end + d * min(size / 2, 0.45 * L), d, (size, max(1.0, L - size))
    # hand, foot: painted joint end up, so the joint is the middle of the top edge, half the wrist/ankle width down
    # (a principal axis fails on wide poses like a thumbs-up)
    r0 = int(ys_.min() + 0.08 * np.ptp(ys_))
    row = np.nonzero(al[r0])[0]
    size = float(np.ptp(row) + 1)
    J = np.array([row.mean(), ys_.min() + size / 2])
    return J, (C - J) / (np.linalg.norm(C - J) + 1e-9), (math.sqrt(al.sum()) if kind == "foot" else size)


def with_shaft(ann, name: str, img: Image.Image, Jv, Jr, k: float, sh: dict) -> tuple:
    """A foot variant (output `name`, joint Jv in its image px) with the hidden shaft its rest foot got (rig_shaft):
    k rest image px per variant image px (feet keep the rest's rotation), so the shaft rises sh["rows"] / k px, as
    high in master px, as wide as the rest's, and is kept where it maps onto the rest's hidden region (sh["hidden"],
    rest canvas px, its joint Jr). The variant output's points move down by the rows added (resolved).
    Returns (image, joint, {"rows", "kept_px"})."""
    rows = int(round(sh["rows"] / k))
    out = next((o for p in ann.pieces.values() for o in p.outputs if o.name == name), None) if ann else None
    depth = (out.depths.get("ankle") if out is not None else None) or sh["depth"] / k
    layer = rig_shaft.layer(img, Jv, sh["width"] / k, depth, rows)
    J2 = np.asarray(Jv, float) + np.array([0.0, rows])
    h, w = layer.shape[:2]
    yy, xx = np.mgrid[:h, :w].astype(np.float64) + 0.5
    X = np.floor(Jr[0] + (xx - J2[0]) * k).astype(int)
    Y = np.floor(Jr[1] + (yy - J2[1]) * k).astype(int)
    hid = sh["hidden"]
    ok = (X >= 0) & (X < hid.shape[1]) & (Y >= 0) & (Y < hid.shape[0])
    hidden = np.zeros((h, w), bool)
    hidden[ok] = hid[Y[ok], X[ok]]
    if out is not None:
        out.points = {n: (float(x), float(y) + rows) for n, (x, y) in out.points.items()}
    return (rig_shaft.compose(img, layer, rows, hidden), J2,
            {"rows": rows, "kept_px": int((layer[..., 3] > 0)[hidden].sum())})


def add(ex, variant_dirs: list, place_info: dict, mid_x: float, trust: int | None) -> tuple:
    """Every <prefix><part>_<variant>.png in variant_dirs as an attachment in its part's slot of ex (a
    rig_slots.Export with the rest parts written). place_info: rig_place's per-part record (annotations; {} legacy);
    mid_x: the master's centre line, full-res px; trust: solidify's edge trust.
    Returns (variant_report: attachment -> scale / turn / joint record, mesh_skipped: variants a sleeve mesh drops)."""
    pieces, prefix, skin, ann, doubts = ex.pieces, ex.prefix, ex.skin, ex.ann, ex.doubts
    if ann is not None:
        import rig_place
    variant_report, mesh_skipped = {}, []
    tail_root_left = True
    tail_n = next((n for n in pieces if is_role(n, ex.roles, "tail", ("tail",))), None)
    if tail_n:
        tail_root_left = pieces[tail_n]["cx"] > mid_x         # tail on the picture's right: its root is its left end
    for vd in variant_dirs:
        for f in sorted(vd.glob(f"{prefix}*.png")):
            stem = f.stem[len(prefix):]
            if annotated_role(stem, ex.roles) == "legs":       # whole legs: add_legs
                continue
            slot = next((n for n in sorted(pieces, key=len, reverse=True) if stem.startswith(n + "_") and not n.endswith("_patch")), None)
            if slot is None or slot == "head_base":
                print(f"  ! variant {f.name}: no part it belongs to; skipped")
                continue
            var = stem[len(slot) + 1:]
            if var == "rest":
                continue
            if "mesh" in pieces[slot] or "mesh_of" in pieces[slot]:     # a sleeve mesh has no raised-sleeve swap
                print(f"  variant {f.name}: skipped (that arm is one sleeve mesh)")
                mesh_skipped.append(f"{prefix}{slot}_{var}")
                continue
            kind = role(slot, ex.roles)[1]
            rest_att = skin[slot][f"{prefix}{slot}"]
            rest_img, img = pieces[slot]["img"], solidify(Image.open(f), trust)
            s_r = rest_att["scaleX"]
            trim = None
            if ann is not None and kind == "forearm":          # hand-coloured tufts past the wrist (rig_place)
                img, trim = rig_place.wrist_trim(ann, stem, img)
                if trim and trim.get("skipped") == "ambiguous_colours":
                    doubts.append({"part": stem, "reason": "wrist_trim_ambiguous"})
                    print(f"  ? doubt: {stem}: the hand shares the sleeve's colours at the wrist; forearm not trimmed")
            # annotations: the joint is the variant's annotated point, the scale its annotated widths (rig_place); a
            # rest narrowed to fit (upper arm to its forearm) passes its factor so its variants are scaled against
            # its un-narrowed width (a raised sleeve keeps its painted width) - on the guessed path below too
            wf = place_info.get(slot, {}).get("width_fit", {}).get("factor", 1.0)
            # a foot with a hidden shaft (rig_shaft): sizing and the guessed joint go by the painted foot alone; the
            # rest output's points already include the shaft's rows
            sh = pieces[slot].get("shaft")
            fit_img = sh["plain"] if sh else rest_img
            fit = rig_place.variant_fit(ann, slot, stem, fit_img, img, s_r, rest_att["scaleY"], wf) \
                if ann is not None else None
            if fit is not None:
                Jr, Jv, sxy, ratio, turn = fit["Jr"], fit["Jv"], fit["sxy"], fit["ratio"], fit["turn"]
                if "scale_check" in fit:                       # ankle widths measured unlike for like: scaled by area
                    c_ = fit["scale_check"]
                    doubts.append({"part": stem, "reason": "variant_scale_disagree", **c_})
                    print(f"  ? doubt: {stem}: ankle widths give scale {c_['width_ratio']} but the areas "
                          f"{c_['area_ratio']} (snaps {'/'.join(c_['snaps'])}); scaled by area, check the ankle points")
            else:
                Jr, ar, sr = joint_axis_size(fit_img, kind, tail_root_left)
                if sh:
                    Jr = Jr + np.array([0.0, sh["rows"]])
                Jv, av, sv = joint_axis_size(img, kind, tail_root_left)
                s_w = s_r / wf                                 # the rest's width scale before any width fit
                ky = rest_att["scaleY"] / s_w                  # a rest part stretched along its length (annotations)
                if isinstance(sr, tuple):                      # tube: own width ratio and length ratio (scaleX, scaleY)
                    ratio = sr[0] / max(sv[0], 1.0)
                    stretch = float(np.clip((sr[1] * ky / max(sv[1], 1.0)) / ratio, 0.75, 1.33))   # keep the painting within +-33%
                    sxy = (s_w * ratio, s_w * ratio * stretch)
                else:                                          # variant sheets paint at their own scale
                    ratio = sr / max(sv, 1.0)
                    sxy = (s_r * ratio, s_r * ratio)
                turn = (math.atan2(-ar[1], ar[0]) - math.atan2(-av[1], av[0])) if kind in ("arm", "forearm", "leg") else 0.0
            th_r = math.radians(rest_att["rotation"])
            th_v = th_r + turn
            if fit is not None and kind == "hand":
                # annotations: the variant's own image-down (joint end up: wrist -> fingers) along the hand bone, which
                # continues the forearm at the holds; not the rest's turn, which matches the master's bent wrist
                th_v = math.radians(90.0)

            shaft_v = None
            if sh:                                           # the rest's shaft, as high in master px, hidden as much
                img, Jv, shaft_v = with_shaft(ann, stem, img, Jv, Jr, sxy[0] / s_r, sh)

            def local(J, im, s_, th):                        # image px -> attachment-local units, rotated
                sx_, sy_ = s_ if isinstance(s_, tuple) else (s_, s_)
                qx, qy = (J[0] - im.width / 2) * sx_, -(J[1] - im.height / 2) * sy_
                return np.array([qx * math.cos(th) - qy * math.sin(th), qx * math.sin(th) + qy * math.cos(th)])
            B = np.array([rest_att["x"], rest_att["y"]]) + local(Jr, rest_img, (s_r, rest_att["scaleY"]), th_r)
            t_v = B - local(Jv, img, sxy, th_v)
            att = f"{prefix}{slot}_{var}"
            ex.worn_cut(slot, stem, att, img).save(ex.out / "images" / f"{att}.png")
            ex.images.append(att)
            skin[slot][att] = {"x": round(float(t_v[0]), 2), "y": round(float(t_v[1]), 2), "scaleX": round(sxy[0], 4), "scaleY": round(sxy[1], 4),
                               "rotation": round(math.degrees(th_v), 2), "width": img.width, "height": img.height}
            if f"{att}_back" in ex.worn.get(slot, {}).get("atts", {}).values():
                skin[ex.worn[slot]["slot"]][f"{att}_back"] = dict(skin[slot][att])
            variant_report[att] = {"scale_vs_rest": round(ratio, 3), "turn_deg": round(math.degrees(turn), 1)}
            if fit is not None and "scale_check" in fit:
                variant_report[att]["scale_check"] = fit["scale_check"]
            if ann is not None:
                variant_report[att]["joint"] = "annotated" if fit is not None else "guessed"
                if fit is None:                                # the annotations couldn't place it: check it by eye
                    doubts.append({"part": stem, "reason": "variant_guessed", "attachment": att})
                    print(f"  ? doubt: {att}: its annotated joint or widths are missing; placed on the guessed "
                          "joint path (painted top centre / principal axis)")
            if trim is not None:
                variant_report[att]["wrist_trim"] = trim
            if shaft_v is not None:
                variant_report[att]["shaft"] = shaft_v
    if variant_report:
        print(f"  variants: {', '.join(sorted(variant_report))}")
        by_kind = {}
        for att_, r_ in variant_report.items():
            by_kind.setdefault(role(att_[len(prefix):].rsplit("_", 1)[0], ex.roles)[1], []).append(r_["scale_vs_rest"])
        for att_, r_ in variant_report.items():       # one sheet paints at one scale: an outlier is a mis-measured piece
            med = float(np.median(by_kind[role(att_[len(prefix):].rsplit("_", 1)[0], ex.roles)[1]]))
            if abs(r_["scale_vs_rest"] / med - 1) > 0.3:
                print(f"  ! variant {att_}: scale {r_['scale_vs_rest']} vs {med:.2f} for its sheet-mates; check the piece")
    return variant_report, mesh_skipped


def _row_width(alpha: np.ndarray, y: float, half: int) -> float:
    """Median opaque width (first to last opaque px) over the rows y - half .. y + half of a boolean mask."""
    ws = []
    for r in range(max(0, int(round(y)) - half), min(alpha.shape[0], int(round(y)) + half + 1)):
        xs = np.nonzero(alpha[r])[0]
        if len(xs):
            ws.append(float(xs[-1] - xs[0] + 1))
    return float(np.median(ws)) if ws else 0.0


LEGS_SLOTS = ("legs_a", "legs_b")    # a swap cross-fades from one to the other


def add_legs(ex, bones: list, world: dict, master_px: dict, trust: int | None) -> dict | None:
    """The legs sheets' drawings (annotated role legs) on their own bones and slots (module doc). ex: rig_slots.Export
    with the rest parts written; bones / world as rig_bones.skeleton returns them (appended to); master_px: the
    master's waist point, full-resolution px. Returns None without legs pieces, else {"slots": LEGS_SLOTS (each on the
    bone of its name), "atts": {variant: attachment}, "height": {variant or "rig": waist-to-soles, units}, "seq":
    {sheet: ["rig", variant, ...]} (the drawings in order of progress, drawing 1 replaced by the rig's own parts),
    "hide": {slot: rest attachment}, "report"}."""
    import rig_annotations as ra
    ann, pieces, prefix = ex.ann, ex.pieces, ex.prefix
    outs = {p.variant: o for p in (ann.pieces.values() if ann is not None else ()) if p.role == "legs"
            and p.status != "ignored" for o in p.outputs}
    if not outs:
        return None
    lower = [n for n in pieces if role(n, ex.roles)[1] in ("hips", "leg", "foot")]
    parsed = {v: ra.legs_variant(v) for v in outs}
    sheets = sorted({p_[0] for p_ in parsed.values()})
    missing = [s_ for s_ in sheets if f"{s_}_1" not in outs]
    if "hips" not in pieces or "hips" not in world or missing:
        why = f"no drawing 1 (the rest legs) on {', '.join(missing)}" if missing else "no trousers (hips)"
        print(f"  ! legs: {why}; skipped")
        ex.doubts.append({"part": "legs", "reason": "legs_no_rest" if missing else "legs_no_hips"})
        return None
    wx, wy = master_px["waist"]
    unit = ex.units((1.0, 0.0))[0] - ex.units((0.0, 0.0))[0]           # Spine units per master px
    # the rig's own rest legs: the trousers' width at the waist, the waist to the lowest sole
    belt_rig = _row_width(pieces["hips"]["mask"], wy, 3) * unit
    soles = max(float(np.nonzero(pieces[n]["mask"].any(1))[0].max()) for n in lower if pieces[n]["mask"].any())
    rest_h = (soles - wy) * unit
    if belt_rig <= 0 or rest_h <= 0:
        print("  ! legs: the trousers have no width at the master's waist; skipped")
        ex.doubts.append({"part": "legs", "reason": "legs_no_belt"})
        return None
    # the bones: at the waist, children of the hips, world-upright (each one's scaleY is its drawing's height)
    (hx, hy), hrot = world["hips"]
    bx, by = ex.units((wx, wy))
    c_, s_ = math.cos(math.radians(-hrot)), math.sin(math.radians(-hrot))
    dx, dy = bx - hx, by - hy
    at = next(i for i, s_ in enumerate(ex.slots) if s_["name"] == "hips")
    for k_, name in enumerate(LEGS_SLOTS):
        bones.append({"name": name, "parent": "hips", "x": round(dx * c_ - dy * s_, 2),
                      "y": round(dx * s_ + dy * c_, 2), "rotation": round(-hrot, 2)})
        world[name] = ((bx, by), 0.0)
        ex.slots.insert(at + 1 + k_, {"name": name, "bone": name})     # just above the trousers, under the torso
        ex.skin.setdefault(name, {})
    atts, height, seq, report = {}, {"rig": rest_h}, {}, {}
    for sheet in sheets:
        def order(v):
            _, a_, b_ = parsed[v]
            return a_ + (0.5 if b_ else 0.0)
        drawings = sorted((v for v in outs if parsed[v][0] == sheet), key=order)
        imgs, belt, span = {}, {}, {}
        for v in drawings:
            o = outs[v]
            img = solidify(Image.open(ann.path.parent / o.file), trust)
            al = np.asarray(img)[..., 3] > 127
            w_, g_ = o.points["waist"], o.points["ground"]
            imgs[v], belt[v], span[v] = (img, w_), max(_row_width(al, w_[1], 2), 1.0), max(g_[1] - w_[1], 1.0)
        first = f"{sheet}_1"
        sx, sy = belt_rig / belt[first], rest_h / span[first]           # drawing 1 covers the rig's rest legs
        if abs(sy / sx - 1) > LEGS_ASPECT_DOUBT:
            ex.doubts.append({"part": first, "reason": "legs_aspect", "factor": round(sy / sx, 3)})
            print(f"  ? doubt: legs_{first}: fitting the rig's rest legs stretches the sheet x{sy / sx:.2f} tall against "
                  "its width (painted at other proportions, or its waist / ground points are off)")
        for v in drawings:
            img, (ux, uy) = imgs[v]
            _, a_, b_ = parsed[v]
            px_h = span[v]
            if b_:                                                      # an in-between: halfway in height, declared
                ends = [f"{sheet}_{a_}", f"{sheet}_{b_}"]
                if all(e in span for e in ends):
                    px_h = 0.5 * (span[ends[0]] + span[ends[1]])
                else:
                    ex.doubts.append({"part": f"legs_{v}", "reason": "legs_inbetween_alone"})
                    print(f"  ? doubt: legs_{v}: drawing {a_} or {b_} is missing, so its own height is used")
            ky = sy * px_h / span[v]                                     # squashed to its declared height
            att = f"{prefix}legs_{v}"
            img.save(ex.out / "images" / f"{att}.png")
            ex.images.append(att)
            for name in LEGS_SLOTS:
                ex.skin[name][att] = {"x": round((img.width / 2 - ux) * sx, 2), "y": round(-(img.height / 2 - uy) * ky, 2),
                                      "scaleX": round(sx, 5), "scaleY": round(ky, 5), "width": img.width, "height": img.height}
            atts[v], height[v] = att, px_h * sy
            report[att] = {"scale": [round(sx, 5), round(ky, 5)], "height_units": round(height[v], 2),
                           "height_vs_rest": round(height[v] / rest_h, 3)}
            if b_:
                report[att]["squash"] = round(px_h / span[v], 3)
        seq[sheet] = ["rig"] + drawings[1:]
    hide = {s_["name"]: s_["attachment"] for s_ in ex.slots if s_["name"] in lower and s_.get("attachment")}
    print(f"  legs: {', '.join(f'{s_} ' + ' '.join(f'{height[v]:.0f}' for v in seq[s_]) for s_ in sheets)} units waist "
          f"to soles; hides {', '.join(hide)}")
    return {"slots": LEGS_SLOTS, "atts": atts, "height": height, "seq": seq, "hide": hide, "report": report}
