#!/usr/bin/env python3
"""Build the "master -> key poses" workflow: three key frames of an approved master in one action.

Writes:
  plugin/skills/skipbo-art/templates/keyposes.api.json             API format (agent use / testing)
  workflows/new/SKIPBO - Master key poses (Nano Banana Pro).json   UI format for the ComfyUI site

  python tools/build_keypose_workflow.py              # build files only
  python tools/build_keypose_workflow.py --publish    # also save the UI workflow to the server as a NEW file

The prompt is references/prompts/spine/keypose.txt. The three key frames (start, middle, end of an action, e.g. the
crouch, the top of the jump and the landing) share the story, the prop and the placement; each has its own pose
text. They are the animator's targets for the rig (experiments/2026-10-16-keypose-refs).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from build_spine_workflow import SKILL, nb, prompt_segments, strip_titles, to_ui  # noqa: E402
from comfy_snapshot import DEFAULT_SERVER, get_json  # noqa: E402

WORKFLOW_NAME = "SKIPBO - Master key poses (Nano Banana Pro).json"
EXP = ROOT / "experiments" / "2026-10-16-keypose-refs"
EXAMPLE_IMAGES = {"SKIPBO_REF_beaver_master.png": ROOT / "experiments/2026-10-15-beaver-jev-hands/beaver/beaver_master.png",
                  "SKIPBO_PROP_hurdle.png": ROOT / "experiments/2026-10-15-beaver-jev-hands/beaver/props/hurdle.png"}
KEYS = ("A", "B", "C")


def env(key: str) -> str:
    for line in (EXP / "prompts" / "keyposes.env").read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1]
    raise KeyError(key)


def graph() -> dict:
    g: dict = {}
    g["10"] = {"class_type": "LoadImage", "inputs": {"image": "{{IMAGE_1}}"}, "_title": "Approved master (rest pose)"}
    g["11"] = {"class_type": "LoadImage", "inputs": {"image": "{{IMAGE_2}}"}, "_title": "Prop (optional: bypass if none)"}
    g["20"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{CHARACTER}}"}, "_title": "CHARACTER NOTES (edit me)"}
    g["21"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{STORY}}"}, "_title": "WHAT IS HAPPENING: the action and why (edit me)"}
    g["22"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{PROP_ROLE}}"}, "_title": "PROP ROLE (clear it when there is no prop)"}
    g["23"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{PLACEMENT}}"}, "_title": "PLACEMENT (ground line, zoom)"}
    g["24"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{CHECK}}"}, "_title": "CHECK: one line the frames must meet"}
    for i, k in enumerate(KEYS):
        g[str(25 + i)] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{POSE_%s}}" % k}, "_title": f"KEY {k}: the pose in this frame (edit me)"}
    shared = {"{{CHARACTER}}": ["20", 0], "{{STORY}}": ["21", 0], "{{PROP_ROLE}}": ["22", 0], "{{PLACEMENT}}": ["23", 0], "{{CHECK}}": ["24", 0]}
    segs = prompt_segments("keypose")
    for i, k in enumerate(KEYS):
        nid = 300 + 40 * i
        slots = dict(shared, **{"{{POSE}}": [str(25 + i), 0]})
        links = []
        for j, seg in enumerate(segs):
            if seg in slots:
                links.append(slots[seg])
            else:
                g[str(nid + j)] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": seg}, "_title": f"key {k} prompt part {j + 1} (fixed)"}
                links.append([str(nid + j), 0])
        acc = links[0]
        for m, nxt in enumerate(links[1:]):
            cid = str(nid + 20 + m)
            g[cid] = {"class_type": "StringConcatenate", "inputs": {"string_a": acc, "string_b": nxt, "delimiter": ""}}
            acc = [cid, 0]
        g[str(40 + 2 * i)] = nb(acc, [["10", 0], ["11", 0]], "3:4", 0.5) | {"_title": f"Key {k} (Nano Banana Pro)"}
        g[str(41 + 2 * i)] = {"class_type": "SaveImage", "inputs": {"images": [str(40 + 2 * i), 0], "filename_prefix": "{{PREFIX}}/key_%s" % k}}
    return g


LAYOUT = {"10": (0, 0), "11": (0, 1), "20": (1, 0), "21": (1, 1.25), "22": (1, 2.5), "23": (1, 3.75), "24": (1, 5),
          "25": (2, 0), "26": (2, 1.25), "27": (2, 2.5), "40": (11, 0), "41": (12, 0), "42": (11, 1.25), "43": (12, 1.25),
          "44": (11, 2.5), "45": (12, 2.5)}
GROUPS = [("Inputs: the approved master + an optional prop", 0, 0, 1, 2),
          ("Edit per action: notes, story, prop role, placement, check", 1, 0, 2, 6),
          ("Edit per key frame: A start, B middle, C end", 2, 0, 3, 4),
          ("Fixed prompt text (collapsed, do not edit here)", 3, 0, 11, 4),
          ("Nano Banana Pro: three key frames", 11, 0, 13, 4)]
TALL = ("20", "21", "22", "23", "24", "25", "26", "27")


def place(nid: str) -> tuple[float, float, bool]:
    if nid in LAYOUT:
        return (*LAYOUT[nid], False)
    k = int(nid) - 300                                     # fixed prompt pieces and their joins, one row per key
    row, j = divmod(k, 40)
    return (3 + (j % 20) * 0.4, row * 1.25 + (0.5 if j >= 20 else 0), True)


HOW_TO = """## Master → key poses (animation targets)

**In:** the approved master in its rest pose, and optionally a prop already painted for the game (a hurdle, a flag, a soil mound). **Out:** three key frames of one action, `key_A/B/C`: the same character on the same canvas, in the poses the animation must reach.

The rig only knows the rest pose. These frames show the start, middle and end of an action, so the rig can be built to hit them, and they supply drawings the rig lacks, such as bent legs for a squat or tucked legs in a jump.

1. Load the master into **Approved master**. If there's a prop, load it into **Prop** and describe it in **PROP ROLE**. With no prop, bypass the Prop node (Ctrl+B) and clear **PROP ROLE**.
2. **WHAT IS HAPPENING:** the action and its purpose. "Crouching to plant a seed" gives a different crouch from "squats at the gym".
3. **KEY A/B/C:** one pose each.
   - Say where the knees and elbows go: "knees bent and spread out to the picture's left and right".
   - Say how low in measured terms: "the belt is now half as high as in the master, the head moves down with it".
   - Say where the eyes look.
4. Queue. That makes 3 Nano Banana Pro calls (billed), about 1–2 minutes.
5. Check each frame:
   - face, chest and buckle still face the viewer;
   - knees really bend (without a measured "how low" the model keeps the legs straight);
   - same character and size.

Lessons from the beaver: without the "paper puppet, never turns" camera paragraph the body turned to three-quarter view, and a crouch without a measured drop came back with straight legs. The model may also put a held prop in the other paw; mirror the frame when reading it.
Maintained in the `comfy/` repo (`tools/build_keypose_workflow.py`, prompt `references/prompts/spine/keypose.txt`)."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--publish", action="store_true", help="save the UI workflow to the server as a new file")
    ap.add_argument("--replace", action="store_true", help="with --publish: overwrite THIS workflow (never any other file)")
    a = ap.parse_args()

    g = graph()
    meta = {"engine": "nb", "billed": "Gemini gemini-3-pro-image-preview x3",
            "description": "Approved master -> three key frames of one action (keypose.txt). IMAGE_1 = master, IMAGE_2 = prop. Vars: CHARACTER, STORY, PROP_ROLE, PLACEMENT, CHECK, POSE_A, POSE_B, POSE_C.",
            "defaults": {}}
    (SKILL / "templates" / "keyposes.api.json").write_text(json.dumps({"_meta": meta, **strip_titles(g)}, indent=2, ensure_ascii=False), encoding="utf-8")

    schemas = {}
    for t in sorted({n["class_type"] for n in g.values()}):
        schemas.update(get_json(a.server, "/object_info/" + urllib.parse.quote(t)))
    names = list(EXAMPLE_IMAGES)
    values = {"IMAGE_1": names[0], "IMAGE_2": names[1], "CHARACTER": env("CHARACTER"), "STORY": env("STORY_HURDLE"),
              "PROP_ROLE": env("ROLE_HURDLE"), "PLACEMENT": env("PLACE_AIR"), "CHECK": env("CHECK_HURDLE"),
              "POSE_A": env("POSE_HURDLE_CROUCH"), "POSE_B": env("POSE_HURDLE_AIR"), "POSE_C": env("POSE_HURDLE_LAND"),
              "PREFIX": "SKIPBO_KEYPOSES/character"}
    ui = to_ui(g, schemas, values, place=place, groups=GROUPS, how_to=HOW_TO, tall=TALL)
    out = ROOT / "workflows" / "new" / WORKFLOW_NAME
    out.write_text(json.dumps(ui, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(ui['nodes'])} nodes, {len(ui['links'])} links)")

    if a.publish:
        existing = {w["path"] for w in get_json(a.server, "/api/userdata?dir=workflows&recurse=true&split=false&full_info=true")}
        if WORKFLOW_NAME in existing and not a.replace:
            print(f"'{WORKFLOW_NAME}' already exists on the server; not overwriting.")
            return 1
        inputs = set(get_json(a.server, "/object_info/LoadImage")["LoadImage"]["input"]["required"]["image"][0])
        for server_name, local_path in EXAMPLE_IMAGES.items():
            if server_name in inputs:
                print(f"input {server_name} already on server, reusing")
                continue
            b = "----skipbo"
            body = (f'--{b}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\nfalse\r\n'
                    f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="{server_name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + local_path.read_bytes() + f"\r\n--{b}--\r\n".encode()
            up = urllib.request.Request(a.server + "/upload/image", data=body, method="POST", headers={"Content-Type": f"multipart/form-data; boundary={b}"})
            with urllib.request.urlopen(up, timeout=60) as r:
                print("uploaded example input:", r.read().decode())
        path = "/api/userdata/" + urllib.parse.quote("workflows/" + WORKFLOW_NAME, safe="") + ("?overwrite=true" if a.replace else "?overwrite=false") + "&full_info=true"
        req = urllib.request.Request(a.server + path, data=out.read_bytes(), method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            print("published:", r.status, r.read().decode()[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
