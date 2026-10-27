"""rig_output.py - the files spine_rig.py writes besides the part images.

  <name>.json                 Spine skeleton (write_skeleton)
  <name>.atlas                one page per image (write_atlas)
  placement.png               debug: every piece outline and bone drawn on the master (write_placement)
  report.json                 match scores, scales, renames, variants; with annotations doubts, gestures, worn items
                              and sleeve meshes (write_report)
  annotations.resolved.json   annotations only: every annotated point per attachment, for spine_qa (write_resolved)
  preview.html                Spine web player preview (write_preview)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def write_skeleton(out: Path, name: str, spine: str, pieces: dict, units, bones: list, slots: list, skin: dict,
                   anims: dict, size: tuple):
    """<name>.json; its bounds are those of every piece's rest mask (units: master px -> Spine units; size: the
    master's (width, height), full-res px)."""
    Wf, Hf = size
    allm = np.zeros((Hf, Wf), bool)
    for pc in pieces.values():
        allm |= pc["mask"]
    ys_, xs_ = np.nonzero(allm)
    x0, y0 = units((xs_.min(), ys_.max()))
    x1, y1 = units((xs_.max(), ys_.min()))
    skeleton = {"skeleton": {"hash": "", "spine": spine, "x": round(x0, 1), "y": round(y0, 1), "width": round(x1 - x0, 1),
                             "height": round(y1 - y0, 1), "images": "./images/", "audio": ""},
                "bones": bones, "slots": slots, "skins": [{"name": "default", "attachments": skin}], "animations": anims}
    events = sorted({e["name"] for an in anims.values() for e in an.get("events", [])})   # rig_anim: seed, pour
    if events:
        skeleton["events"] = {e: {} for e in events}
    (out / f"{name}.json").write_text(json.dumps(skeleton, indent=1), encoding="utf-8")


def write_atlas(out: Path, name: str, images: list):
    """<name>.atlas: one page per saved image in <out>/images."""
    atlas = []
    for att in images:
        im = Image.open(out / "images" / f"{att}.png")
        atlas += [f"images/{att}.png", f"size: {im.width},{im.height}", "filter: Linear,Linear", att, f"bounds: 0,0,{im.width},{im.height}", ""]
    (out / f"{name}.atlas").write_text("\n".join(atlas), encoding="utf-8")


def write_placement(out: Path, rgb: np.ndarray, pieces: dict, joints: dict, bone_dir: dict):
    """placement.png: the master (rgb 0..1, full res) at 35% with every piece's outline, pivot and bone direction."""
    Hf, Wf = rgb.shape[:2]
    small = 0.35
    dbg = Image.fromarray((rgb * 255).astype(np.uint8)).convert("RGB").resize((int(Wf * small), int(Hf * small)))
    d = ImageDraw.Draw(dbg)
    for n, pc in pieces.items():
        edge = pc["mask"][::6, ::6] & ~(np.roll(pc["mask"][::6, ::6], 1, 0) & np.roll(pc["mask"][::6, ::6], -1, 0) & np.roll(pc["mask"][::6, ::6], 1, 1) & np.roll(pc["mask"][::6, ::6], -1, 1))
        ey, ex = np.nonzero(edge)
        for x_, y_ in zip(ex, ey):
            d.point((x_ * 6 * small, y_ * 6 * small), fill=(255, 0, 180))
        jx, jy = joints[n] * small
        tx, ty = (joints[n] + bone_dir[n] * 0.5) * small
        d.line((jx, jy, tx, ty), fill=(0, 160, 255), width=2)
        d.ellipse((jx - 4, jy - 4, jx + 4, jy + 4), fill=(0, 200, 255))
        d.text((jx + 5, jy - 5), n, fill=(0, 0, 0))
    dbg.save(out / "placement.png")


def write_report(out: Path, *, g: float, k: float, renames: dict, pieces: dict, unit: float, variants: dict,
                 size: tuple, mid_x: float, ground_y: float, placed: dict, ann=None, annotations=None,
                 allow_proposed: bool = False, doubts: list = (), gesture_info: dict | None = None,
                 place_info: dict | None = None, worn: dict | None = None, meshes: dict | None = None,
                 mesh_skipped: list = ()):
    """report.json. g, k: work px per part px and per master px; size, mid_x, ground_y: the master frame, full-res px;
    placed: the colour-matched parts (legacy). With annotations (ann): the annotations path, doubts, each hold's
    gesture record (rig_anim, by (animation, side)), how each part was placed (place_info), the worn cuts and, when
    there are any, the sleeve meshes."""
    report = {
        "global_scale_master_px_per_part_px": round(g / k, 4), "renamed": renames,
        "from_master": sorted(n for n in pieces if pieces[n]["unit"] == unit), "variants": variants,
        "master_frame": {"width": size[0], "height": size[1], "mid_x": round(mid_x, 2), "ground_y": round(ground_y, 2),
                         "units_per_px": round(unit, 6)},
        "parts": {n: {"err": round(m["err"], 5), "scale_rel": round(m["scale"] / g, 3), "angle": m["angle"]} for n, m in placed.items()}}
    if ann is not None:
        gestures_r = {}
        for (anim_, side_), g_info in sorted(gesture_info.items()):
            gestures_r.setdefault(anim_, {})[side_] = g_info
        report.update({"annotations": str(annotations), "allow_proposed": bool(allow_proposed), "doubts": doubts,
                       "gestures": gestures_r,
                       "parts": {n: {k_: i_[k_] for k_ in ("method", "stretch", "narrow", "width_fit", "wrist_trim",
                                                           "ankle_shift", "shaft") if k_ in i_}
                                 for n, i_ in place_info.items()},
                       "worn": worn})
        if meshes:                         # sleeve meshes only: rigs without one report exactly as before
            report.update({"meshes": meshes, "mesh_skipped_variants": sorted(mesh_skipped)})
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def write_resolved(out: Path, ann, prefix: str, skin: dict, anims: dict, bones: list, place_info: dict, units,
                   unit: float, height: float, size: tuple, variants: dict, gesture_info: dict):
    """annotations.resolved.json (rig_place.resolved) with each hold's actual pose and thumb target (gesture_info);
    without annotations a stale one is removed, since it would switch spine_qa's annotation checks on.
    height: the character's height in Spine units; size: the master's (width, height), full-res px."""
    if ann is None:
        if (out / "annotations.resolved.json").exists():
            (out / "annotations.resolved.json").unlink()
        return
    import rig_place
    res = rig_place.resolved(ann, prefix, skin, anims, [b["name"] for b in bones], place_info, units, unit, height, size,
                             {k_: r_["wrist_trim"] for k_, r_ in variants.items() if "wrist_trim" in r_})
    for anim_, h_ in res.get("holds", {}).items():     # the pose each hold actually uses, and its thumb's target
        g_info = gesture_info.get((anim_, h_["side"]))
        if g_info is not None:
            h_["pose"] = g_info["pose"]
            if g_info["thumb_target_deg"] is not None:
                h_["thumb_target"] = g_info["thumb_target_deg"]
    (out / "annotations.resolved.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


def write_preview(out: Path, name: str, anims: dict):
    """preview.html, opening on idle (or the first animation)."""
    first = "idle" if "idle" in anims else next(iter(anims), "")
    (out / "preview.html").write_text(PREVIEW.replace("{{NAME}}", name).replace("{{ANIM}}", first), encoding="utf-8")


PREVIEW = """<!doctype html><html><head><meta charset="utf-8"><title>{{NAME}} rig preview</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://unpkg.com/@esotericsoftware/spine-player@4.2.*/dist/iife/spine-player.js"></script>
<link rel="stylesheet" href="https://unpkg.com/@esotericsoftware/spine-player@4.2.*/dist/spine-player.css">
<style>html,body{margin:0;height:100%;background:#d6d6d6;font:14px system-ui}#p{width:100%;height:100%}</style></head>
<body><div id="p"></div><script>
// ?anim=<name> picks the animation, &t=<seconds> freezes it at that time (for review screenshots)
const q = new URLSearchParams(location.search), anim = q.get("anim") || "{{ANIM}}", t = q.get("t");
window.player = new spine.SpinePlayer("p", {jsonUrl: "{{NAME}}.json", atlasUrl: "{{NAME}}.atlas",
  animation: anim, premultipliedAlpha: false, backgroundColor: "#d6d6d6", showControls: !t,
  debug: {bones: q.has("bones"), regions: false},
  success: p => {
    if (t !== null) { p.pause(); p.animationState.setAnimation(0, anim, true); p.animationState.update(parseFloat(t));
      p.animationState.apply(p.skeleton); p.skeleton.updateWorldTransform(spine.Physics.update); }
    window.ready = true; },
  error: (p, msg) => { window.loadError = msg; document.body.insertAdjacentText("afterbegin", msg); }});
</script></body></html>"""
