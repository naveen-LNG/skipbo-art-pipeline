#!/usr/bin/env python3
"""Add a lip-sync mouth slot and one talk animation per line to a built rig (a copy; the source rig is untouched).

    uv run --with pillow scripts/spine_talk.py ../2026-10-15-beaver-jev-hands/beaver/rig beaver/rig_talk \
        --mouths beaver/mouths --line results/line1 --line results/line2

- Slot `mouth_patch` (spine_qa's name for a feathered overlay) on the head's bone, drawn right above the head slot, empty at rest: the expression heads keep
  their own mouths in every existing animation.
- Attachments `<char>_mouth_<X..H>`: the patches cropped to the mask's box, placed with the neutral head's own
  attachment transform, so they land exactly where extract_mouths.py registered them.
- Animation `talk_<line>`: only slot keys (mouth shapes from the cues, the neutral head with a blink now and then),
  no bones, so it plays on track 1 over `idle` (or walk, wave...) on track 0. An event `<line>` carries the audio
  file (Spine audio events) at time 0; a game plays the sound on that event.
Also writes talk.html: idle on track 0, the line on track 1, the track time locked to the audio clock.
"""
import argparse, json, math, os, shutil
from PIL import Image

SHAPES = "XABCDEFGH"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--mouths", required=True)
    ap.add_argument("--line", action="append", required=True)
    a = ap.parse_args()
    if os.path.exists(a.dst):
        shutil.rmtree(a.dst)
    os.makedirs(f"{a.dst}/images")
    name = next(f for f in os.listdir(a.src) if f.endswith(".json") and f != "report.json")[:-5]
    sk = json.load(open(f"{a.src}/{name}.json"))
    for f in os.listdir(f"{a.src}/images"):
        shutil.copy(f"{a.src}/images/{f}", f"{a.dst}/images/{f}")
    atlas = open(f"{a.src}/{name}.atlas").read().rstrip("\n") + "\n"

    head_slot = next(s for s in sk["slots"] if s["name"] == "head")
    skin = sk["skins"][0]["attachments"]
    neutral = skin["head"][f"{name}_head_neutral"]
    meta = json.load(open(f"{a.mouths}/mouths.json"))
    x0, y0, x1, y1 = meta["mask_bbox"]
    W, H = meta["head_size"]
    # the patch box's centre, relative to the head image's centre, y up, in the attachment's local space
    lx = ((x0 + x1) / 2 - W / 2) * neutral["scaleX"]
    ly = -((y0 + y1) / 2 - H / 2) * neutral["scaleY"]
    r = math.radians(neutral["rotation"])
    mx = neutral["x"] + lx * math.cos(r) - ly * math.sin(r)
    my = neutral["y"] + lx * math.sin(r) + ly * math.cos(r)
    mouth_att = {}
    for k in SHAPES:
        an = f"{name}_mouth_{k}"
        Image.open(f"{a.mouths}/mouth_{k}.png").crop((x0, y0, x1, y1)).save(f"{a.dst}/images/{an}.png")
        atlas += f"\nimages/{an}.png\nsize: {x1 - x0},{y1 - y0}\nfilter: Linear,Linear\n{an}\nbounds: 0,0,{x1 - x0},{y1 - y0}\n"
        mouth_att[an] = {"x": round(mx, 2), "y": round(my, 2), "scaleX": neutral["scaleX"], "scaleY": neutral["scaleY"],
                         "rotation": neutral["rotation"], "width": x1 - x0, "height": y1 - y0}
    i = sk["slots"].index(head_slot)
    sk["slots"].insert(i + 1, {"name": "mouth_patch", "bone": head_slot["bone"]})
    skin["mouth_patch"] = mouth_att
    # drawOrder keys store index offsets: a key that moves a slot across the new mouth slot must move one further
    old = [s["name"] for s in sk["slots"] if s["name"] != "mouth_patch"]
    new = [s["name"] for s in sk["slots"]]
    for an in sk["animations"].values():
        for key in an.get("drawOrder", []):
            for o in key.get("offsets", []):
                tgt = old.index(o["slot"]) + o["offset"]          # target index in the old order
                o["offset"] = (tgt + (tgt > i)) - new.index(o["slot"])
    sk.setdefault("events", {})
    for line in a.line:
        ln = os.path.basename(line)
        cues = json.load(open(line + ".cues.json"))
        shutil.copy(line + ".wav", f"{a.dst}/{ln}.wav")
        fps, dur = cues["fps"], cues["duration"]
        keys = [{"time": round(c["frame"] / fps, 4), "name": f"{name}_mouth_{c['shape']}"} for c in cues["cues"]]
        keys.append({"time": round(dur, 4), "name": None})
        neutral_name = f"{name}_head_neutral"
        head_keys = [{"time": 0, "name": neutral_name}]
        t = 1.6
        while t + 0.2 < dur:                       # blink every ~2.7 s while talking
            head_keys += [{"time": round(t, 3), "name": f"{name}_head_blink"}, {"time": round(t + 0.13, 3), "name": neutral_name}]
            t += 2.7
        sk["events"][ln] = {"audio": f"{ln}.wav"}
        sk["animations"][f"talk_{ln}"] = {"slots": {"mouth_patch": {"attachment": keys}, "head": {"attachment": head_keys}},
                                          "events": [{"time": 0, "name": ln}]}
    sk["skeleton"]["audio"] = "./"
    json.dump(sk, open(f"{a.dst}/{name}.json", "w"), indent=1)
    open(f"{a.dst}/{name}.atlas", "w").write(atlas)
    lines = [os.path.basename(l) for l in a.line]
    open(f"{a.dst}/talk.html", "w").write(HTML.replace("{{NAME}}", name).replace("{{LINES}}", json.dumps(lines)))
    print(json.dumps({"mouth_slot_after": head_slot["name"], "attachments": len(mouth_att), "animations": [f"talk_{l}" for l in lines]}))


HTML = """<!doctype html><html><head><meta charset="utf-8"><title>{{NAME}} lip sync</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://unpkg.com/@esotericsoftware/spine-player@4.2.43/dist/iife/spine-player.js"></script>
<link rel="stylesheet" href="https://unpkg.com/@esotericsoftware/spine-player@4.2.43/dist/spine-player.css">
<style>html,body{margin:0;height:100%;background:#d6d6d6;font:14px system-ui}#p{width:100%;height:calc(100% - 52px)}
#bar{height:52px;display:flex;gap:8px;align-items:center;padding:0 12px}button{font:inherit;padding:8px 14px}</style></head>
<body><div id="bar"></div><div id="p"></div><script>
// idle on track 0, talk_<line> on track 1; every frame track 1's time is set from the audio clock, so picture and sound cannot drift.
const lines = {{LINES}}, q = new URLSearchParams(location.search);
let audio = null, entry = null;
window.player = new spine.SpinePlayer("p", {jsonUrl: "{{NAME}}.json", atlasUrl: "{{NAME}}.atlas", animation: "idle",
  premultipliedAlpha: false, backgroundColor: "#d6d6d6", showControls: false,
  viewport: {x: -380, y: 520, width: 760, height: 820, padLeft: 0, padRight: 0, padTop: 0, padBottom: 0},
  success: p => {
    for (const l of lines) {
      const b = document.createElement("button"); b.textContent = "Play " + l;
      b.onclick = () => { if (audio) audio.pause(); audio = new Audio(l + ".wav");
        entry = p.animationState.setAnimation(1, "talk_" + l, false); entry.mixDuration = 0;
        audio.play(); };
      document.getElementById("bar").append(b);
    }
    const tick = () => { if (audio && entry) { entry.trackTime = audio.currentTime; if (audio.ended) { p.animationState.setEmptyAnimation(1, 0); entry = null; } }
      requestAnimationFrame(tick); };
    tick();
    if (q.get("anim")) { const t = parseFloat(q.get("t") || "0"); p.pause();
      p.animationState.setAnimation(0, "idle", true); const e = p.animationState.setAnimation(1, q.get("anim"), false);
      p.animationState.update(t); p.animationState.apply(p.skeleton); p.skeleton.updateWorldTransform(spine.Physics.update); }
    window.ready = true; },
  error: (p, msg) => { window.loadError = msg; document.body.insertAdjacentText("afterbegin", msg); }});
</script></body></html>
"""

if __name__ == "__main__":
    main()
