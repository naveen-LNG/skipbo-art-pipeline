#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""spine_rig.py - place generated parts on the master and write a Spine skeleton.

  uv run spine_rig.py --master moose_master.png --body body/ --heads face-heads/ --variants variants/ --name moose --out rig/
  (or: pip install numpy pillow; python spine_rig.py ...)

Finds where every generated part sits on the master (masked colour matching over scale and rotation),
fixes left/right on pairs by trying both sides, chains the limbs so each joint is the centre of both
round ends (shoulder, elbow, wrist, hip, ankle), and writes:
  rig/<name>.json      Spine 4.2 skeleton: bones, slots, default skin with pose variants as swappable
                       attachments, animations (idle, blink, wave, cheer_jump, thumbs_up, point, hold_card, emotions)
  rig/<name>.atlas     one page per image, so the Spine web player / runtimes can load it as-is
  rig/images/*.png     the parts (renamed if left/right was corrected)
  rig/preview.html     Spine web player preview (serve the folder over http)
  rig/placement.png    debug: every part outline drawn on the master
  rig/report.json      match scores, scales, rotations, renames

Import into the Spine editor with Import Data -> <name>.json (images path ./images/).
Part names follow <name>_<part>[_l|_r]; _l = the character's left = the picture's right.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np

import rig_anim
import rig_annotations
import rig_bones
import rig_chain
import rig_colours
import rig_cut
import rig_frame
import rig_match
import rig_output
import rig_pieces
import rig_place
import rig_props
import rig_sleeves
import rig_slots
import rig_trousers
import rig_variants
from rig_image import TRUST_ALPHA_ANNOTATED, load_rgba
from rig_match import Matcher, load_master, make_band, match_parts
from rig_roles import LAYERS, LAYERS_MASTER_CUT, ann_roles

# Kept importable from spine_rig, where they lived before the stage modules were split out:
from rig_anim import WAVE_FA_FALLBACK, across_hold, wave_forearm  # noqa: F401,E402
from rig_frame import axis_ends, grow  # noqa: F401,E402
from rig_image import BLEED_PX, RIM_PX, TRUST_ALPHA, solidify  # noqa: F401,E402
from rig_match import (BANDS, BG_WEIGHT, WORK_H, MasterFrame, ears_in_heads, masked_ssd,  # noqa: F401,E402
                       master_mask, placed_points, transform)
from rig_roles import (LIMBS, ROLE_SLOTS, annotated_role, foot_of, headgear, is_role, role,  # noqa: F401,E402
                       role_from_name, soft_kind)

# ------------------------------------------------------------------ stages
#
#   0    annotations, leg: in_hips: hips and cuffed legs as one     rig_trousers
#   1-2  global scale, parts matched on the master by colour       rig_match (rig_place.scale_estimates: annotations)
#   3    pieces at full master resolution                          rig_frame, rig_pieces; heads: rig_match
#   3a'' annotations: every part placed from its joints            rig_place (place_annotated below)
#        leg-less, feet under the hips: hidden shafts             rig_shaft (variants: rig_variants.with_shaft)
#   3a'  generated limbs pinned end to end                         rig_chain
#   3a-b --cut-from-master: limbs and lower body cut from master   rig_cut (rig_colours)
#   3c-d pivots for the rest, hidden roots                         rig_bones
#   3e   --cut-from-master: orphan patches                         rig_cut
#   4    bones                                                     rig_bones
#   4a   slots, default skin, worn back slots, expression heads    rig_slots
#   4b   pose variants; whole-legs poses on a bone of their own     rig_variants
#   4c   props not in the master (a held flag, a hurdle)          rig_props
#   5    animations                                                rig_anim
#   5b   sleeve meshes                                             rig_sleeves
#   6    skeleton json, atlas, placement.png, report, preview      rig_output


def parse_args(argv=None):
    """The command line, checked: (args, annotations or None). Sets LAYERS for --cut-from-master and for the
    annotations' master.layers; with annotations --name, --heads and --variants default to theirs."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--master", required=True, type=Path)
    ap.add_argument("--body", type=Path, help="folder of body part PNGs (required without --annotations; ignored with it)")
    ap.add_argument("--heads", type=Path, help="folder of expression head PNGs (<name>_head_<expr>.png)")
    ap.add_argument("--name",
                    help="character prefix used in the file names, e.g. moose; must match the prefix of the part, head and "
                         "variant files (required without --annotations; with it, defaults to the annotations' "
                         "character, and must equal it when given)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--variants", type=Path, nargs="*", default=[],
                    help="folder(s) of pose variants <name>_<part>_<variant>.png, each painted joint end up (hands wrist up)")
    ap.add_argument("--cut-from-master", action="store_true",
                    help="legacy: cut arms, legs, hands, feet and hips out of the master instead of using the generated parts")
    ap.add_argument("--annotations", type=Path,
                    help="annotations.json: place the rest parts from its confirmed joints (rig_place.py) instead of by colour. "
                         "Body parts come from its outputs, so --body is ignored; --heads/--variants default to its outputs' folders")
    ap.add_argument("--allow-proposed", action="store_true",
                    help="with --annotations: build even if pieces are still proposed (experiments only; stamped in report.json)")
    ap.add_argument("--spine", default="4.2.00")
    ap.add_argument("--props", type=Path, help="props.json: props not in the master (a held flag, a hurdle), rig_props")
    a = ap.parse_args(argv)
    if a.cut_from_master:
        LAYERS[:] = LAYERS_MASTER_CUT
    ann = None
    if a.annotations:
        if a.cut_from_master:
            ap.error("--annotations and --cut-from-master don't combine")
        try:
            ann = rig_annotations.load(a.annotations)
        except rig_annotations.AnnotationError as e:
            raise SystemExit(f"invalid annotations:\n{e}")
        todo = rig_annotations.unconfirmed(ann)
        if todo and not a.allow_proposed:
            raise SystemExit("annotations still proposed (confirm them, or --allow-proposed for experiments): " + ", ".join(todo))
        if todo:
            print(f"WARNING: --allow-proposed: building from annotations still proposed: {', '.join(todo)} "
                  "(an experiment, not a deliverable; stamped in report.json)")
        if a.name is None:
            a.name = ann.character
        elif a.name != ann.character:
            raise SystemExit(f"--name {a.name} does not match the annotations' character {ann.character!r} (its output "
                             f"files are {ann.character}_<part>.png); leave --name out or pass --name {ann.character}")
        trousers = rig_trousers.compose(ann, a.out)       # leg: in_hips - hips and cuffed legs as one piece
        if trousers:
            narrowed = ", ".join(f"{s_} {v_['narrow']}" for s_, v_ in trousers["legs"].items())
            print(f"one-piece trousers: hips over both cuffed legs -> {trousers['file']} (legs narrowed {narrowed})")
        LAYERS[:] = rig_place.apply_layers(ann.master.layers, LAYERS, rig_place.has_legs(ann), rig_place.has_neckwear(ann))
        heads_dir, variant_dirs = rig_place.default_dirs(ann)
        a.heads, a.variants = a.heads or heads_dir, a.variants or variant_dirs
    elif a.body is None:
        ap.error("--body is required without --annotations")
    elif a.name is None:
        ap.error("--name is required without --annotations")
    return a, ann


def place_annotated(ann, frame, g: float, pl, head_mask) -> tuple:
    """Stage 3a'': every part placed from the annotations (rig_place): joints lined up, then the colour matcher as a
    second opinion. Ears the expression heads already include (head_mask; None without heads) are dropped.
    Adds to pl (rig_pieces.Placement); returns (doubts, place_info)."""
    pieces_a, joints_a, dirs_a, doubts, place_info = rig_place.place_from_annotations(ann, frame, g, (pl.ff.W, pl.ff.H))
    if head_mask is not None:
        rig_match.drop_ears({n: p["mask"] for n, p in pieces_a.items()}, head_mask, pl.roles,
                            pieces_a, joints_a, dirs_a, place_info)
    pl.pieces.update(pieces_a)
    pl.joints.update(joints_a)
    pl.bone_dir.update(dirs_a)
    doubts += rig_place.cross_check(ann, frame, g, pieces_a)       # the colour matcher as a second opinion
    for d_ in doubts:
        print(f"  ? doubt: {d_}")
    return doubts, place_info


# ------------------------------------------------------------------ main

def main() -> int:
    a, ann = parse_args()
    annotated = ann is not None
    roles = ann_roles(ann)                 # annotated roles set layers and parents (None: guessed from the names)

    out = a.out
    if (out / "images").exists():          # replace generated images only; hand-written files (README) stay
        shutil.rmtree(out / "images")
    (out / "images").mkdir(parents=True, exist_ok=True)
    prefix = a.name + "_"
    trust = TRUST_ALPHA_ANNOTATED if annotated else None     # solidify's edge trust (heads, variants)

    # 1-2. the global scale, then (legacy) every body part's place on the master by colour
    frame = load_master(a.master)
    master = load_rgba(a.master)[..., :3]
    matcher = Matcher(frame.work, frame.fg)
    band = make_band(frame)
    parts = {}
    for f in (sorted(a.body.glob(f"{prefix}*.png")) if ann is None else []):
        parts[f.stem[len(prefix):]] = (f, load_rgba(f))
    if ann is None and "head_base" not in parts and "torso" not in parts:
        raise SystemExit("need at least head_base or torso among the body parts to find the scale")
    if ann is None:
        placed, renames, g = match_parts(frame, parts, a.cut_from_master)
    else:                                  # annotations: every part is placed at stage 3a'' by rig_place
        scale = rig_place.scale_estimates(ann, frame)
        placed, renames, g = {}, {}, scale["g"]
        print(f"global scale: {g / frame.k:.3f} master px per part px "
              f"({'annotated neck-to-waist' if scale['used'] == 'torso_length' else 'torso width and head width'}; "
              f"estimates {scale['estimates']})")
        if scale["doubt"]:
            print(f"  ? doubt: {scale['doubt']}")

    # 3. pieces at full master resolution; the expression heads replace any ears they include
    ff = rig_frame.full_frame(master, frame, g)
    pl = rig_pieces.Placement(ff, placed, {n: ff.full_mask(m) for n, m in placed.items()}, roles)
    heads = sorted(a.heads.glob(f"{prefix}head_*.png")) if a.heads else []
    head_pc = head_mask = None
    if heads:
        head_pc, head_mask = rig_match.match_heads(heads, matcher, band, g, ff)
        rig_match.drop_ears(pl.masks, head_mask, roles, placed, pl.masks)
    pl.add_generated(g)                    # generated parts keep their painted image
    doubts, place_info = [], {}
    if annotated:                          # 3a''. placed from the annotations: joints lined up
        doubts, place_info = place_annotated(ann, frame, g, pl, head_mask)
        if scale["doubt"]:
            doubts.insert(0, scale["doubt"])
    pal = rig_colours.Palette(ff.rgb, parts, renames)
    if a.cut_from_master:                  # 3a, 3b. limbs and lower body cut from the master
        rig_cut.cut_arms(pl, pal)
        rig_cut.cut_lower_body(pl, pal, frame.half_w)
    elif not annotated:                    # 3a'. generated limbs pinned end to end (the default)
        rig_chain.chain_arms(pl, pal, frame.half_w)
        rig_chain.stand_legs(pl, frame.top)
    rig_bones.pivots(pl, annotated, a.cut_from_master)        # 3c. the rest: pivot at the overlap with the parent
    rig_bones.hidden_roots(pl, annotated)                     # 3d. hidden roots under the parent
    patches = rig_cut.orphan_patches(pl, pal) if a.cut_from_master else {}   # 3e. orphan patches

    # 4. bones
    bones, world, order = rig_bones.skeleton(pl, annotated)
    pieces, joints, bone_dir = pl.pieces, pl.joints, pl.bone_dir

    # 4a. slots, default skin and images; 4b. pose variants as extra attachments
    ex = rig_slots.Export(out, prefix, pieces, patches, world, ff.units, LAYERS, ann, doubts)
    ex.write_parts()
    ex.add_heads(heads, head_pc, trust)
    variant_report, mesh_skipped = rig_variants.add(ex, a.variants, place_info, ff.mid, trust)
    legs = None
    if annotated:                          # whole legs (rest, half, crouch, tuck): a legs bone appended, hidden at rest
        mp = {n: (ann.master.points[n][0] * ff.W, ann.master.points[n][1] * ff.H) for n in ("waist", "ground")}
        legs = rig_variants.add_legs(ex, bones, world, mp, trust)
        if legs:
            variant_report.update(legs["report"])
    # 4c. props not in the master (rig_props): own bones and slots, hidden at rest
    body_h_units = float(np.ptp(np.nonzero(ff.fg)[0])) * ff.unit
    props = rig_props.add(ex, bones, world, a.props, body_h_units, joints, bone_dir, ff.unit)

    # 5. animations, the arms kept clear of the whole head assembly
    head_any = head_mask.copy() if heads and head_pc is not None else (pieces["head_base"]["mask"].copy() if "head_base" in pieces else None)
    zone = rig_anim.head_zone(head_any, pieces, lambda n: rig_bones.parent_of(pl, n, annotated), int(14 * ff.U), roles)
    geo = rig_anim.Geometry(pieces, joints, bone_dir, {n: world[n][1] for n in order}, zone, ff.fg, ff.unit, ann,
                            {b["name"]: b.get("parent") for b in bones}, props, legs)
    anim = rig_anim.build(geo, ex, [f.stem for f in heads], doubts)
    anims = anim.anims
    ex.sync_worn(anims)

    # 5b. sleeve meshes, now that the animations say how far each elbow bends
    mesh_report = rig_sleeves.write(ex, anims, bones, place_info, anim.crossing)

    # 6. files
    size = (ff.W, ff.H)
    rig_output.write_skeleton(out, a.name, a.spine, pieces, ff.units, bones, ex.slots, ex.skin, anims, size)
    rig_output.write_atlas(out, a.name, ex.images)
    rig_output.write_placement(out, ff.rgb, pieces, joints, bone_dir)
    rig_output.write_report(out, g=g, k=frame.k, renames=renames, pieces=pieces, unit=ff.unit, variants=variant_report,
                            size=size, mid_x=ff.mid, ground_y=ff.ground, placed=placed, ann=ann,
                            annotations=a.annotations, allow_proposed=a.allow_proposed, doubts=doubts,
                            gesture_info=anim.gesture_info, place_info=place_info, worn=ex.worn_report,
                            meshes=mesh_report, mesh_skipped=mesh_skipped)
    rig_output.write_resolved(out, ann, prefix, ex.skin, anims, bones, place_info, ff.units, ff.unit,
                              float(np.ptp(np.nonzero(ff.fg)[0])) * ff.unit, size, variant_report, anim.gesture_info)
    rig_output.write_preview(out, a.name, anims)
    print(f"wrote {out}/{a.name}.json ({len(bones)} bones, {len(ex.slots)} slots, {len(ex.images)} images, animations: {', '.join(anims)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
