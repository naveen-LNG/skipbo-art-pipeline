#!/usr/bin/env python3
"""Build the "room components" workflow: one room fitting painted alone as a transparent asset.

Writes:
  plugin/skills/skipbo-art/templates/components.api.json            API format (agent use / testing)
  workflows/new/SKIPBO - Room components (Nano Banana Pro).json      UI format for the ComfyUI site

  python tools/build_components_workflow.py              # build files only
  python tools/build_components_workflow.py --publish    # also save the UI workflow to the server as a NEW file

The prompt is references/prompts/components.txt. One object per run: the room goes in as image_1 and is the only
authority on camera, eye level, light and palette; the object is painted alone on flat grey with its own contact
shadow, then `easy imageRemBg` cuts it to a transparent PNG that drops straight into the room's layout box.

This is the additive counterpart of the in-place edit used by experiments/2026-10-16-room-renovate: an edit can only
change pixels the room already has, so it cannot introduce an object the room never contained (a TV), and it fails
on the classes listed in the Blocks progression rules §12 (heroes, large structures, flat ground elements, strung
decorations). A component is generated from nothing, so none of those classes apply. What it has to earn instead is
the match: perspective, scale, light and palette, which is what the prompt spends its words on.

STYLE: the prompt carries the LR render block from references/styles/lr-render/block.md verbatim, minus its five
scene-composition paragraphs (FRAME AND EYE LEVEL, THE THREE BANDS, SIDE FRAMING, SAFE AREAS, GROUPING). Those
describe where things go in a 9:16 scene; here a single object fills the frame and image_1 fixes the camera. No
sentence of the block was reworded.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from build_spine_workflow import SKILL, nb, strip_titles, to_ui  # noqa: E402
from comfy_snapshot import DEFAULT_SERVER, get_json  # noqa: E402

WORKFLOW_NAME = "SKIPBO - Room components (Nano Banana Pro).json"
PROMPT = SKILL / "references" / "prompts" / "components.txt"
SCHEMA_CACHE = ROOT / "tools" / ".object_info.json"
EXP = ROOT / "experiments" / "2026-10-20-room-components"
V1 = ROOT / "experiments" / "2026-10-16-room-renovate"
LR = SKILL / "references" / "styles" / "lr-render" / "refs"
EXAMPLE_IMAGES = {"SKIPBO_ROOM_before.png": V1 / "game/assets/base.jpg",
                  "SKIPBO_STYLE_lr_block_01.png": LR / "EXAMPLE_LR_block_01.png",
                  "SKIPBO_STYLE_lr_block_02.png": LR / "EXAMPLE_LR_block_02.png"}
# node id -> (slot, widget title). Order is the order they are read in the prompt.
SLOTS = [("20", "ROOM", "THE ROOM: camera, eye level, light, palette (edit once per room)"),
         ("21", "COMPONENT", "COMPONENT: what this one object is (edit me)"),
         ("22", "PERSPECTIVE", "PERSPECTIVE: which way its edges recede, which faces show (edit me)"),
         ("23", "PLACEMENT", "PLACEMENT: where it stands and how big, measured (edit me)"),
         ("24", "CHECK", "CHECK: one line this component must meet (edit me)")]


def segments() -> list[str]:
    """Prompt text split around {{SLOT}} placeholders: ["text", "{{ROOM}}", "text", ...]."""
    return [p for p in re.split(r"(\{\{\w+\}\})", PROMPT.read_text(encoding="utf-8")) if p]


def item(key: str) -> str:
    """One field of the worked example from the experiment's items.tsv (id<TAB>component<TAB>...)."""
    cols = ("component", "perspective", "placement", "check")
    row, field = key.split(".")
    for line in (EXP / "prompts" / "items.tsv").read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if parts and parts[0] == row:
            return parts[1 + cols.index(field)]
    raise KeyError(key)


def graph() -> dict:
    g: dict = {}
    g["10"] = {"class_type": "LoadImage", "inputs": {"image": "{{IMAGE_1}}"}, "_title": "The room this object belongs to (before or after)"}
    g["11"] = {"class_type": "LoadImage", "inputs": {"image": "{{IMAGE_2}}"}, "_title": "Style ref A: LR render"}
    g["12"] = {"class_type": "LoadImage", "inputs": {"image": "{{IMAGE_3}}"}, "_title": "Style ref B: LR render"}
    for nid, slot, title in SLOTS:
        g[nid] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{%s}}" % slot}, "_title": title}
    links_for = {"{{%s}}" % slot: [nid, 0] for nid, slot, _ in SLOTS}
    links = []
    for j, seg in enumerate(segments()):
        if seg in links_for:
            links.append(links_for[seg])
        else:
            g[str(300 + j)] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": seg}, "_title": f"prompt part {j + 1} (fixed)"}
            links.append([str(300 + j), 0])
    acc = links[0]
    for m, nxt in enumerate(links[1:]):
        cid = str(360 + m)
        g[cid] = {"class_type": "StringConcatenate", "inputs": {"string_a": acc, "string_b": nxt, "delimiter": ""}}
        acc = [cid, 0]
    g["40"] = nb(acc, [["10", 0], ["11", 0], ["12", 0]], "{{ASPECT}}", 0.35) | {"_title": "Component on flat grey (Nano Banana Pro)"}
    g["41"] = {"class_type": "SaveImage", "inputs": {"images": ["40", 0], "filename_prefix": "{{PREFIX}}_flat"}, "_title": "Flat render (keep: shows what the matte ate)"}
    g["42"] = {"class_type": "easy imageRemBg", "inputs": {"images": ["40", 0], "rem_mode": "{{MODE}}", "image_output": "Hide", "save_prefix": "x"}, "_title": "Cut the grey away"}
    g["43"] = {"class_type": "SaveImage", "inputs": {"images": ["42", 0], "filename_prefix": "{{PREFIX}}"}, "_title": "Transparent component PNG"}
    return g


LAYOUT = {"10": (0, 0), "11": (0, 1), "12": (0, 2),
          "20": (1, 0), "21": (1, 1.25), "22": (1, 2.5), "23": (1, 3.75), "24": (1, 5),
          "40": (11, 0), "41": (12, 0), "42": (12, 1.25), "43": (13, 1.25)}
GROUPS = [("Inputs: the room + the two LR style refs (keep these two)", 0, 0, 1, 3),
          ("Edit these five boxes: one object per run", 1, 0, 2, 6),
          ("Fixed prompt text (collapsed, do not edit here)", 2, 0, 11, 4),
          ("Nano Banana Pro -> transparent component", 11, 0, 14, 3)]
TALL = tuple(nid for nid, _, _ in SLOTS)


def place(nid: str) -> tuple[float, float, bool]:
    if nid in LAYOUT:
        return (*LAYOUT[nid], False)
    k = int(nid) - 300                                      # fixed prompt pieces (300+) and their joins (360+)
    return (2 + (k % 60) * 0.14, (0.6 if k >= 60 else 0) + (k % 60) // 30 * 1.2, True)


HOW_TO = """## Room components: one fitting at a time, as a transparent asset

**In:** the room the object belongs to (image_1) and the two LR style refs. **Out:** `<name>_flat` (the raw render on
grey) and `<name>` (the same object cut to a transparent PNG), ready to drop onto the room at a fixed box.

This is the additive way to build a makeover room. An in-place edit of the room can only rearrange pixels the room
already has, so it can never introduce something the room never contained, and it fails outright on heroes, large
structures, flat ground elements and strung decorations. A component is painted from nothing, so none of that
applies. The price is the **match**, and that is all the prompt talks about: the room's camera and eye level, which
way this object's own edges recede, its measured footprint, the room's one light direction, and its contact shadow.

1. Load the room. If the object replaces something, load the **before** room; if it is being added to a finished
   room, load that. Keep both style refs.
2. **THE ROOM** is written once per room and reused for every component: the camera height, where the eye line
   crosses the frame, which wall faces the camera, which way the floor runs, where the key light comes from, and
   the three theme colours. Copy it unchanged between runs.
3. **COMPONENT** is the object and nothing about the room.
4. **PERSPECTIVE** and **PLACEMENT** are the two that decide whether this works. Say which faces are visible and
   which way the receding edges go ("its top is seen from above, its right-hand side recedes to the upper right").
   Give the size against something measurable, never "medium-sized".
5. Set **aspect_ratio** on the Nano Banana node to the shape of the object's own box: a rug is 16:9, a window 3:4,
   a floor lamp 9:16.
6. Queue. One Nano Banana Pro call (billed), about 30 seconds.
7. Check the **flat** render first, then the cut-out:
   - does the eye level match the room, or is the object seen from a different height?
   - did the matte keep the contact shadow, or eat it? BEN2 usually keeps a soft one and drops a detached one.
   - is the palette the room's, or a cleaner, cooler version of it?

Maintained in the `comfy/` repo (`tools/build_components_workflow.py`, prompt `references/prompts/components.txt`)."""


def schemas_for(server: str, types: list[str]) -> dict:
    """Node schemas from the server, with a cache so a build still works while the GPU box is down.

    The server always wins and refreshes the cache; the cache is only read for a type the server could not be
    asked about. tools/.object_info.json was seeded by hand from the two published workflows while the server was
    down, and that seed is checked by rebuilding the keypose workflow from it and diffing against the published
    file, so a wrong schema would show up as a diff rather than as a broken workflow on the site.
    """
    cache = json.loads(SCHEMA_CACHE.read_text(encoding="utf-8")) if SCHEMA_CACHE.exists() else {}
    out, fetched = {}, False
    for t in types:
        try:
            got = get_json(server, "/object_info/" + urllib.parse.quote(t))
        except (urllib.error.URLError, OSError) as e:
            if t not in cache:
                raise SystemExit(f"no schema for {t!r}: server unreachable ({e}) and nothing cached in {SCHEMA_CACHE.name}")
            print(f"server unreachable, using cached schema for {t!r}", file=sys.stderr)
            out[t] = cache[t]
            continue
        out.update(got)
        cache.update(got)
        fetched = True
    if fetched:
        SCHEMA_CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--publish", action="store_true", help="save the UI workflow to the server as a new file")
    ap.add_argument("--replace", action="store_true", help="with --publish: overwrite THIS workflow (never any other file)")
    a = ap.parse_args()

    g = graph()
    meta = {"engine": "nb", "billed": "Gemini gemini-3-pro-image-preview",
            "description": "One room component painted alone from the room's camera (components.txt), cut to a transparent PNG. "
                           "IMAGE_1 = the room, IMAGE_2/3 = LR style refs. Vars: ROOM, COMPONENT, PERSPECTIVE, PLACEMENT, CHECK, ASPECT, MODE.",
            "defaults": {"ASPECT": "1:1", "MODE": "BEN2"}}
    api = SKILL / "templates" / "components.api.json"
    api.write_text(json.dumps({"_meta": meta, **strip_titles(g)}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {api.relative_to(ROOT)} ({len(g)} nodes)")

    names = list(EXAMPLE_IMAGES)
    values = {"IMAGE_1": names[0], "IMAGE_2": names[1], "IMAGE_3": names[2], "ASPECT": "1:1", "MODE": "BEN2",
              "ROOM": (EXP / "prompts" / "room.txt").read_text(encoding="utf-8").strip(),
              "COMPONENT": item("sofa.component"), "PERSPECTIVE": item("sofa.perspective"),
              "PLACEMENT": item("sofa.placement"), "CHECK": item("sofa.check"),
              "PREFIX": "SKIPBO_COMPONENTS/room/sofa"}
    ui = to_ui(g, schemas_for(a.server, sorted({n["class_type"] for n in g.values()})), values,
               place=place, groups=GROUPS, how_to=HOW_TO, tall=TALL)
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
