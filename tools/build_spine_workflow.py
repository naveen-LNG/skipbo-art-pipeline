#!/usr/bin/env python3
"""Build the "character reference -> Spine parts" pipeline from one definition.

Writes:
  plugin/skills/skipbo-art/templates/parts-split.api.json   sheet -> transparent parts (agent use)
  plugin/skills/skipbo-art/templates/spine-parts.api.json   full chain, API format (agent use / testing)
  workflows/new/SKIPBO - Character to Spine parts (Nano Banana Pro).json   UI format for the ComfyUI site

  python tools/build_spine_workflow.py              # build files only
  python tools/build_spine_workflow.py --publish    # also save the UI workflow to the server as a NEW file
                                                    # (refuses to overwrite an existing workflow)
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
from comfy_snapshot import DEFAULT_SERVER, get_json, widget_names  # noqa: E402

SKILL = ROOT / "plugin" / "skills" / "skipbo-art"
PROMPTS = SKILL / "references" / "prompts" / "spine"
WORKFLOW_NAME = "SKIPBO - Character to Spine parts (Nano Banana Pro).json"
STYLE_REFS = {"SKIPBO_STYLE_blocks_hippo_atlas.jpg": "shipped-hippo-atlas-small.jpg",
              "SKIPBO_STYLE_blocks_raccoon_atlas.jpg": "shipped-raccoon-atlas.jpg"}  # server name -> local ref
EXAMPLE_REF = ("SKIPBO_REF_moose_turnaround.png", ROOT / "references" / "characters" / "moose" / "moose_turn_00006_.png")


def prompt_segments(name: str) -> list[str]:
    """Prompt text split around {{SLOT}} placeholders: ["text", "{{CHARACTER}}", "text", ...]."""
    text = (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")
    return [part for part in re.split(r"(\{\{\w+\}\})", text) if part]


def moose_example(section: str) -> str:
    md = (SKILL / "references" / "characters" / "moose.md").read_text(encoding="utf-8")
    return re.search(rf"## {section}.*?~~~~text\n(.*?)\n~~~~", md, re.S).group(1)


def split_chain(g: dict, base: int, sheet: list, prefix: str) -> None:
    """Sheet image -> BEN2 cut-out -> one RGBA png per separated piece (soft alpha kept)."""
    n = lambda i: str(base + i)  # noqa: E731
    g[n(0)] = {"class_type": "easy imageRemBg", "inputs": {"images": sheet, "rem_mode": "{{MODE}}", "image_output": "Hide", "save_prefix": "x"}}
    g[n(1)] = {"class_type": "ThresholdMask", "inputs": {"mask": [n(0), 1], "value": 0.3}}
    g[n(2)] = {"class_type": "GrowMask", "inputs": {"mask": [n(1), 0], "expand": 8, "tapered_corners": True}}
    g[n(3)] = {"class_type": "MaskToSEGS", "inputs": {"mask": [n(2), 0], "combined": False, "crop_factor": 1.0, "bbox_fill": False, "drop_size": 24, "contour_fill": True}}
    g[n(4)] = {"class_type": "SetDefaultImageForSEGS", "inputs": {"segs": [n(3), 0], "image": [n(0), 0], "override": True}}
    g[n(5)] = {"class_type": "ImpactDecomposeSEGS", "inputs": {"segs": [n(4), 0]}}
    g[n(6)] = {"class_type": "ImpactFrom_SEG_ELT", "inputs": {"seg_elt": [n(5), 1]}}
    g[n(7)] = {"class_type": "SplitImageWithAlpha", "inputs": {"image": [n(6), 1]}}
    g[n(8)] = {"class_type": "InvertMask", "inputs": {"mask": [n(7), 1]}}
    g[n(9)] = {"class_type": "MaskComposite", "inputs": {"destination": [n(8), 0], "source": [n(6), 2], "x": 0, "y": 0, "operation": "multiply"}}
    g[n(10)] = {"class_type": "InvertMask", "inputs": {"mask": [n(9), 0]}}
    g[n(11)] = {"class_type": "JoinImageWithAlpha", "inputs": {"image": [n(7), 0], "alpha": [n(10), 0]}}
    g[n(12)] = {"class_type": "SaveImage", "inputs": {"images": [n(11), 0], "filename_prefix": prefix}}


def nb(prompt_link: list, images: list, aspect: str, temp: float) -> dict:
    inputs = {"model_name": "gemini-3-pro-image-preview", "prompt": prompt_link, "image_count": 1, "use_search": False,
              "aspect_ratio": aspect, "image_size": "2K", "temperature": temp}
    for i, img in enumerate(images, 1):
        inputs[f"image_{i}"] = img
    return {"class_type": "NanoBananaAIO", "inputs": inputs}


PROMPT_ORDER = ("master", "body-sheet", "face-sheet", "hands-sheet", "poses-sheet")   # prompt pieces: ids 300 + 20 * index
SPLIT_ROWS = {1: 6, 2: 7, 4: 8, 5: 9}   # split chain id // 100 -> canvas row (body, face, hands, poses)


def full_graph() -> dict:
    g: dict = {}
    g["10"] = {"class_type": "LoadImage", "inputs": {"image": "{{IMAGE_1}}"}, "_title": "Character reference (any view, any style)"}
    g["11"] = {"class_type": "LoadImage", "inputs": {"image": "{{IMAGE_2}}"}, "_title": "Style ref A: shipped Hippo atlas"}
    g["12"] = {"class_type": "LoadImage", "inputs": {"image": "{{IMAGE_3}}"}, "_title": "Style ref B: shipped Raccoon atlas"}
    g["20"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{CHARACTER}}"}, "_title": "CHARACTER NOTES (edit me)"}
    g["21"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{PIECES}}"}, "_title": "PIECES for the body sheet (edit me)"}
    g["22"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{HANDS}}"}, "_title": "HANDS: 6 hand poses (edit me)"}
    g["23"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "{{POSES}}"}, "_title": "POSES: piece + variant rows (edit me)"}
    slots = {"{{CHARACTER}}": ["20", 0], "{{PIECES}}": ["21", 0], "{{HANDS}}": ["22", 0], "{{POSES}}": ["23", 0]}
    final = {}
    for i, name in enumerate(PROMPT_ORDER):
        nid = 300 + 20 * i
        links = []
        for j, seg in enumerate(prompt_segments(name)):
            if seg in slots:
                links.append(slots[seg])
            else:
                g[str(nid + j)] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": seg}, "_title": f"{name} prompt part {j + 1} (fixed)"}
                links.append([str(nid + j), 0])
        acc = links[0]
        for k, nxt in enumerate(links[1:]):
            cid = str(nid + 10 + k)
            g[cid] = {"class_type": "StringConcatenate", "inputs": {"string_a": acc, "string_b": nxt, "delimiter": ""}}
            acc = [cid, 0]
        final[name] = acc
    g["40"] = nb(final["master"], [["10", 0], ["11", 0], ["12", 0]], "3:4", 0.6) | {"_title": "1 Master in Blocks style"}
    g["41"] = {"class_type": "SaveImage", "inputs": {"images": ["40", 0], "filename_prefix": "{{PREFIX}}/master"}}
    g["50"] = nb(final["body-sheet"], [["40", 0], ["11", 0]], "1:1", 0.4) | {"_title": "2 Body parts sheet"}
    g["51"] = {"class_type": "SaveImage", "inputs": {"images": ["50", 0], "filename_prefix": "{{PREFIX}}/body_sheet"}}
    g["60"] = nb(final["face-sheet"], [["40", 0], ["11", 0]], "1:1", 0.4) | {"_title": "3 Face sheet: 9 expression heads"}
    g["61"] = {"class_type": "SaveImage", "inputs": {"images": ["60", 0], "filename_prefix": "{{PREFIX}}/face_sheet"}}
    g["70"] = nb(final["hands-sheet"], [["40", 0], ["11", 0]], "3:2", 0.4) | {"_title": "4 Hands sheet: 6 poses x 2 hands"}
    g["71"] = {"class_type": "SaveImage", "inputs": {"images": ["70", 0], "filename_prefix": "{{PREFIX}}/hands_sheet"}}
    g["80"] = nb(final["poses-sheet"], [["40", 0], ["11", 0]], "16:9", 0.4) | {"_title": "5 Poses sheet: raised sleeve, tiptoe, tail up"}
    g["81"] = {"class_type": "SaveImage", "inputs": {"images": ["80", 0], "filename_prefix": "{{PREFIX}}/poses_sheet"}}
    split_chain(g, 100, ["50", 0], "{{PREFIX}}/body_part")
    split_chain(g, 200, ["60", 0], "{{PREFIX}}/face_head")
    split_chain(g, 400, ["70", 0], "{{PREFIX}}/hand_variant")
    split_chain(g, 500, ["80", 0], "{{PREFIX}}/pose_variant")
    return g


def strip_titles(g: dict) -> dict:
    return {k: {kk: vv for kk, vv in v.items() if kk != "_title"} for k, v in g.items()}


# ---------------------------------------------------------------- API -> UI conversion

WIDGET_KINDS = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}
LAYOUT = {  # node id -> (column, row) on the canvas
    "10": (0, 0), "11": (0, 1), "12": (0, 2), "20": (1, 0), "21": (1, 1.25), "22": (1, 2.5), "23": (1, 3.75),
    "40": (11, 0), "41": (12, 0), "50": (11, 1), "51": (12, 1), "60": (11, 2), "61": (12, 2),
    "70": (11, 3), "71": (12, 3), "80": (11, 4), "81": (12, 4),
}
GROUPS = [("Inputs: character ref + shipped style atlases (keep these two)", 0, 0, 1, 3),
          ("Edit these four boxes per character", 1, 0, 2, 5),
          ("Fixed prompt text (collapsed, do not edit here)", 2, 0, 11, 5),
          ("Nano Banana Pro: 1 master, 2 body, 3 face, 4 hands, 5 poses", 11, 0, 13, 5),
          ("Split sheets into transparent parts (BEN2): body, face, hands, poses", 0, 6, 13, 10)]


def place(nid: str) -> tuple[float, float, bool]:
    """(column, row, collapsed) for a node id."""
    if nid in LAYOUT:
        return (*LAYOUT[nid], False)
    i = int(nid)
    if 300 <= i < 400:  # fixed prompt pieces: one row per prompt, collapsed
        k = i - 300
        return (2 + (k % 20) * 0.45, k // 20 + (0.5 if k % 20 >= 10 else 0), True)
    return (i % 100, SPLIT_ROWS[i // 100], False)  # split chains


def to_ui(api: dict, schemas: dict, values: dict, place=place, groups=None, how_to=None, tall=("20", "21", "22", "23")) -> dict:
    """UI-format workflow from an API graph: nodes placed by place(id) -> (column, row, collapsed), the groups as
    (title, c0, r0, c1, r1), a "How to use" note, tall text boxes for the ids in `tall`."""
    groups_, how_to = GROUPS if groups is None else groups, HOW_TO if how_to is None else how_to
    nodes, links = [], []
    link_id = 0
    out_links: dict[tuple, list] = {}
    col_w, row_h = 420, 360
    for nid, node in api.items():
        ctype = node["class_type"]
        schema = schemas[ctype]
        c, r, collapsed = place(nid)
        ui_inputs, widgets = [], []
        spec_all = {**schema["input"].get("required", {}), **schema["input"].get("optional", {})}
        for name, spec in spec_all.items():
            kind = spec[0]
            is_widget = isinstance(kind, list) or kind in WIDGET_KINDS
            val = node["inputs"].get(name)
            linked = isinstance(val, list) and len(val) == 2 and isinstance(val[0], str)
            if linked:
                link_id += 1
                src, slot = val
                ltype = schemas[api[src]["class_type"]]["output"][slot]
                links.append([link_id, int(src), slot, int(nid), len(ui_inputs), ltype])
                out_links.setdefault((src, slot), []).append(link_id)
                entry = {"name": name, "type": "COMBO" if isinstance(kind, list) else kind, "link": link_id}
                if is_widget:
                    entry["widget"] = {"name": name}
                ui_inputs.append(entry)
            elif not is_widget and name in node["inputs"]:
                ui_inputs.append({"name": name, "type": kind, "link": None})
        for wname in widget_names(schema):
            if wname == "upload":
                widgets.append("image")
            elif wname.endswith("(after generate)"):
                widgets.append("fixed")
            else:
                v = node["inputs"].get(wname, (spec_all.get(wname, [None, {}])[1] or {}).get("default") if len(spec_all.get(wname, [])) > 1 else None)
                if isinstance(v, list):  # linked widget keeps a placeholder value
                    v = "" if spec_all[wname][0] == "STRING" else (spec_all[wname][1] or {}).get("default")
                if isinstance(v, str) and "{{" in v:
                    v = re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), m.group(0))), v)
                widgets.append(v)
        ui = {"id": int(nid), "type": ctype, "pos": [c * col_w, r * row_h], "size": [380, 420 if nid in tall else 160],
              "flags": {"collapsed": True} if collapsed else {}, "order": 0, "mode": 0, "inputs": ui_inputs, "outputs": [],
              "properties": {"Node name for S&R": ctype}, "widgets_values": widgets}
        if node.get("_title"):
            ui["title"] = node["_title"]
        nodes.append(ui)
    by_id = {str(n["id"]): n for n in nodes}
    for nid, node in api.items():
        schema = schemas[node["class_type"]]
        by_id[nid]["outputs"] = [{"name": nm, "type": t, "links": out_links.get((nid, i), []), "slot_index": i}
                                 for i, (t, nm) in enumerate(zip(schema["output"], schema.get("output_name") or schema["output"]))]
    for i, n in enumerate(sorted(nodes, key=lambda n: (n["pos"][0], n["pos"][1]))):
        n["order"] = i
    note = {"id": 1, "type": "MarkdownNote", "pos": [0, -440], "size": [1240, 380], "flags": {}, "order": len(nodes), "mode": 0,
            "inputs": [], "outputs": [], "properties": {}, "title": "How to use", "widgets_values": [how_to]}
    nodes.append(note)
    groups = [{"title": t, "bounding": [c0 * col_w - 20, r0 * row_h - 60, (c1 - c0) * col_w + 0, (r1 - r0) * row_h + 40], "color": "#3f789e", "font_size": 24}
              for t, c0, r0, c1, r1 in groups_]
    return {"last_node_id": max(n["id"] for n in nodes), "last_link_id": link_id, "nodes": nodes, "links": links,
            "groups": groups, "config": {}, "extra": {"ds": {"scale": 0.45, "offset": [60, 520]}}, "version": 0.4}


HOW_TO = """## Character reference → Spine parts (Blocks style)

**In:** one image of the character (any style, any views). **Out:** a master in the shipped Blocks style and four sheets, with every piece cut out as its own transparent PNG:
- body sheet → `body_part_*`
- 9 expression heads → `face_head_*`
- 12 hand poses → `hand_variant_*`
- pose variants (raised sleeve, tiptoe foot, tail up) → `pose_variant_*`

1. Load the character reference into **Character reference**. Keep the two shipped atlases, since they define the style.
2. Fill in the four boxes; the Moose shows the format for each.
   - **CHARACTER NOTES:** look, costume, colours.
   - **PIECES:** every body piece named for this character, in 4 rows. Say where a piece ends when clothing hides the split ("ending at the belt", "down to its hem").
   - **HANDS:** the 6 hand poses.
   - **POSES:** each piece followed by its variants. Say "an upper arm is only the sleeve from shoulder to elbow, without any cuff".
3. Queue. That makes 5 Nano Banana Pro calls (billed) and takes about 3–6 minutes.
4. Check the **master** first. If it's wrong, fix the notes and re-run before using the parts.
5. Check every sheet:
   - **body:** upper arm and forearm separate, nothing merged;
   - **hands:** chunky mittens like the master, wrist up;
   - **poses:** the rest arm has no cuff.
6. Name the parts by looking at them. Put the variants in `variants/` as `CHAR_part_variant.png`, each turned joint end up, with the right-hand set mirrored from the left. Then build the rig with `spine_rig.py --variants` (see the skill's `spine-parts.md`).

Body sheet: each arm in 3 pieces, each leg in 2, every hat, ear, horn, scarf and bell separately, every joint end fully round, torso painted with the arms removed, hips including the crotch. The rig uses every piece as final art; the master only positions them.
Maintained in the `comfy/` repo (`tools/build_spine_workflow.py`); edit there, not here."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--publish", action="store_true", help="save the UI workflow to the server as a new file")
    ap.add_argument("--replace", action="store_true", help="with --publish: overwrite THIS workflow (never any other file)")
    a = ap.parse_args()

    full = full_graph()
    tdir = SKILL / "templates"
    meta_full = {"engine": "nb", "billed": "Gemini gemini-3-pro-image-preview x5",
                 "description": "Character ref -> Blocks master -> body, face, hands and poses sheets -> transparent parts. IMAGE_1 = character ref, IMAGE_2/3 = shipped atlases. Vars: CHARACTER, PIECES, HANDS, POSES.",
                 "defaults": {"MODE": "BEN2"}}
    (tdir / "spine-parts.api.json").write_text(json.dumps({"_meta": meta_full, **strip_titles(full)}, indent=2, ensure_ascii=False), encoding="utf-8")
    split = {"10": {"class_type": "LoadImage", "inputs": {"image": "{{IMAGE_1}}"}}}
    split_chain(split, 100, ["10", 0], "{{PREFIX}}/part")
    (tdir / "parts-split.api.json").write_text(json.dumps({"_meta": {"engine": "", "description": "Parts sheet on a flat background -> one transparent PNG per separated piece (BEN2 cut-out, soft alpha).",
                                                                     "defaults": {"MODE": "BEN2"}}, **split}, indent=2), encoding="utf-8")

    types = sorted({n["class_type"] for n in full.values()})
    schemas = {}
    for t in types:
        schemas.update(get_json(a.server, "/object_info/" + urllib.parse.quote(t)))
    names = list(STYLE_REFS)
    values = {"IMAGE_1": EXAMPLE_REF[0], "IMAGE_2": names[0], "IMAGE_3": names[1], "MODE": "BEN2",
              "CHARACTER": moose_example("CHARACTER"), "PIECES": moose_example("PIECES"),
              "HANDS": moose_example("HANDS"), "POSES": moose_example("POSES"),
              "PREFIX": "SKIPBO_SPINE/character"}
    ui = to_ui(full, schemas, values)
    out = ROOT / "workflows" / "new" / WORKFLOW_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ui, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(ui['nodes'])} nodes, {len(ui['links'])} links)")

    if a.publish:
        existing = {w["path"] for w in get_json(a.server, "/api/userdata?dir=workflows&recurse=true&split=false&full_info=true")}
        if WORKFLOW_NAME in existing and not a.replace:
            print(f"'{WORKFLOW_NAME}' already exists on the server; not overwriting. Rename or delete it in the UI first.")
            return 1
        inputs = set(get_json(a.server, "/object_info/LoadImage")["LoadImage"]["input"]["required"]["image"][0])
        refs = {k: SKILL / "references" / "styles" / "blocks-characters" / "refs" / v for k, v in STYLE_REFS.items()}
        refs[EXAMPLE_REF[0]] = EXAMPLE_REF[1]
        for server_name, local_path in refs.items():
            if server_name in inputs:
                print(f"input {server_name} already on server, reusing")
                continue
            data = local_path.read_bytes()
            b = "----skipbo"
            body = (f'--{b}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\nfalse\r\n'
                    f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="{server_name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + data + f"\r\n--{b}--\r\n".encode()
            up = urllib.request.Request(a.server + "/upload/image", data=body, method="POST", headers={"Content-Type": f"multipart/form-data; boundary={b}"})
            with urllib.request.urlopen(up, timeout=60) as r:
                print("uploaded style ref:", r.read().decode())
        path = "/api/userdata/" + urllib.parse.quote("workflows/" + WORKFLOW_NAME, safe="") + ("?overwrite=true" if a.replace else "?overwrite=false") + "&full_info=true"
        req = urllib.request.Request(a.server + path, data=out.read_bytes(), method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            print("published:", r.status, r.read().decode()[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
