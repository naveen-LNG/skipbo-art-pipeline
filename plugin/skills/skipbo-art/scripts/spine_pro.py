#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""spine_pro.py - upgrade a built spine_rig.py rig with the Spine primitives professional animators rig with.

  uv run spine_pro.py rig/beaver.json --out rig_pro/ [--skip underfill tail ...]

Reads a legacy rig folder (<name>.json, images/, report.json, annotations.resolved.json) and writes a new folder;
the legacy rig is never changed. Stages, in order (each can be switched off with --skip <stage>):

  container  `character` bone under root; jump keys move onto it, root is never animated; soft ground shadow
             (outside the container) that shrinks and fades with the jump height
  tail       3-4 bone chain along the tail's medial axis; the tail as a weighted mesh (rows on every pivot,
             narrow blend bands, tip rigid)
  torso      `chest` helper; torso as a mesh weighted torso -> chest; arms / head / neckwear under the chest with
             inherit noScale so breathing doesn't scale them
  head       every head attachment as a mesh weighted to head_base (rim) and a `face` helper (centre) for a fake
             3D turn; ear lobes found in the head's alpha get ear bones
  feet       green <foot>_ik targets under `character`; the feet follow them through transform constraints (or a
             one-bone IK on a leg); every animation's foot motion is baked onto the targets
  anims      new idle (2 s), look_around, talk; breathing on every animation
  secondary  tail and ear follow-through (damped springs driven by the body's motion) + sway, on every animation
  underfill  a darker dilated silhouette below each moving part (sleeves, hands, head, tail, feet, hips)
  organise   bone colours: controllers red, helpers yellow, IK targets green

Writes <out>/<name>.json, <name>.atlas, images/, preview.html (Spine web player 4.2, pinned), pro_report.json, and
copies report.json / annotations.resolved.json so spine_qa runs the same checks on it.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pro_common as pc  # noqa: E402
import pro_motion  # noqa: E402
import pro_parts  # noqa: E402
import rig_output  # noqa: E402
import spine_qa  # noqa: E402

STAGES = ("container", "tail", "torso", "head", "feet", "anims", "secondary", "underfill", "organise")
PLAYER = "4.2.120"     # @esotericsoftware/spine-player, pinned


def build(skeleton: Path, out: Path, skip: tuple = ()) -> dict:
    """Upgrade the rig at `skeleton` into folder `out`. Returns the report (also written to pro_report.json)."""
    skeleton, out = Path(skeleton), Path(out)
    src = skeleton.parent
    name = skeleton.stem
    data = json.loads(skeleton.read_text(encoding="utf-8"))
    if out.resolve() == src.resolve():
        raise SystemExit("--out must differ from the legacy rig folder")
    if (out / "images").exists():
        shutil.rmtree(out / "images")
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src / data["skeleton"].get("images", "./images/"), out / "images")
    for f in ("report.json", "annotations.resolved.json"):
        if (src / f).exists():
            shutil.copy(src / f, out / f)
    legacy = spine_qa.Rig(skeleton)

    @lru_cache(maxsize=None)
    def legacy_world(anim, t):
        return legacy.pose(anim, t)[0]

    rep = {"source": str(skeleton), "skipped": list(skip), "stages": {}}

    def run(stage, fn, *a, **k):
        if stage in skip:
            return None
        r = fn(*a, **k)
        rep["stages"].setdefault(stage, {})
        if isinstance(r, dict):
            rep["stages"][stage].update(r)
        else:
            rep["stages"][stage][fn.__name__] = r
        return r

    run("container", pro_parts.container, data, out, legacy_world)
    run("container", pro_parts.shadow, data, out)
    run("tail", pro_parts.tail_chain, data, out)
    run("torso", pro_parts.torso_chest, data, out)
    run("head", pro_parts.head_face, data, out)
    run("feet", pro_parts.feet, data, out, legacy_world)
    if "anims" not in skip:
        rep["stages"]["anims"] = {"idle": pro_motion.new_idle(data, out),
                                  "look_around": pro_motion.look_around(data, out),
                                  "talk": pro_motion.talk(data, out),
                                  "breathing": pro_motion.breathing(data)}
    if "container" not in skip:
        rep["stages"]["container"]["shadow_keys"] = pro_parts.shadow_keys(data, out)
    run("secondary", pro_motion.secondary, data, out)
    run("underfill", pro_parts.underfill, data, out)
    run("organise", pro_parts.organise, data)
    for k in ("ik", "transform"):
        if k in data and not data[k]:
            del data[k]
    (out / f"{name}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    images = sorted({a for atts in data["skins"][0]["attachments"].values() for a in atts})
    rig_output.write_atlas(out, name, images)
    for f in (out / "images").glob("*.png"):                 # images no attachment uses any more
        if f.stem not in images:
            f.unlink()
    first = "idle" if "idle" in data["animations"] else next(iter(data["animations"]), "")
    (out / "preview.html").write_text(PREVIEW.replace("{{NAME}}", name).replace("{{ANIM}}", first)
                                      .replace("{{V}}", PLAYER), encoding="utf-8")
    rep["bones"] = len(data["bones"])
    rep["slots"] = len(data["slots"])
    rep["animations"] = list(data["animations"])
    rep["constraints"] = {"ik": [c["name"] for c in data.get("ik", [])],
                          "transform": [c["name"] for c in data.get("transform", [])]}
    (out / "pro_report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    return rep


PREVIEW = """<!doctype html><html><head><meta charset="utf-8"><title>{{NAME}} pro rig</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/@esotericsoftware/spine-player@{{V}}/dist/iife/spine-player.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@esotericsoftware/spine-player@{{V}}/dist/spine-player.css">
<style>html,body{margin:0;height:100%;background:#d6d6d6;font:14px system-ui}#p{width:100%;height:100%}</style></head>
<body><div id="p"></div><script>
// ?anim=<name> picks the animation, &t=<seconds> freezes it at that time (for review screenshots), &bones shows bones
const q = new URLSearchParams(location.search), anim = q.get("anim") || "{{ANIM}}", t = q.get("t");
window.player = new spine.SpinePlayer("p", {jsonUrl: "{{NAME}}.json", atlasUrl: "{{NAME}}.atlas",
  animation: anim, premultipliedAlpha: false, backgroundColor: "#d6d6d6", showControls: !t,
  debug: {bones: q.has("bones"), regions: false, meshes: q.has("meshes")},
  success: p => {
    if (t !== null) { p.pause(); p.animationState.setAnimation(0, anim, true); p.animationState.update(parseFloat(t));
      p.animationState.apply(p.skeleton); p.skeleton.updateWorldTransform(spine.Physics.update); }
    window.ready = true; },
  error: (p, msg) => { window.loadError = msg; document.body.insertAdjacentText("afterbegin", msg); }});
</script></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("skeleton", type=Path, help="the legacy rig's <name>.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--skip", nargs="*", default=[], choices=STAGES)
    a = ap.parse_args(argv)
    rep = build(a.skeleton, a.out, tuple(a.skip))
    st = rep["stages"]
    print(f"wrote {a.out}/{a.skeleton.stem}.json: {rep['bones']} bones, {rep['slots']} slots, "
          f"constraints {rep['constraints']}, animations {', '.join(rep['animations'])}")
    for k, v in st.items():
        print(f"  {k}: {json.dumps(v, default=str)[:240]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
