#!/usr/bin/env python3
"""Check the components workflow: the graph's StringConcatenate chain must rebuild components.txt exactly.

    uv run python tools/test_components_workflow.py

A wrong node order or a dropped segment silently sends a mangled prompt to a billed Nano Banana call, which is
the one failure this cannot afford, so it is checked by evaluating the graph the same way ComfyUI would.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_components_workflow as C  # noqa: E402


def resolve(g: dict, ref, slots: dict) -> str:
    nid, _ = ref
    n = g[nid]
    if n["class_type"] == "PrimitiveStringMultiline":
        v = n["inputs"]["value"]
        return slots.get(v, v)
    if n["class_type"] == "StringConcatenate":
        return resolve(g, n["inputs"]["string_a"], slots) + n["inputs"]["delimiter"] + resolve(g, n["inputs"]["string_b"], slots)
    raise AssertionError(f"unexpected node in the prompt chain: {n['class_type']}")


def demo() -> None:
    g = C.graph()
    want = C.PROMPT.read_text(encoding="utf-8")
    slots = {"{{%s}}" % s: "{{%s}}" % s for _, s, _ in C.SLOTS}   # identity: the rebuilt text keeps the slots
    got = resolve(g, g["40"]["inputs"]["prompt"], slots)
    assert got == want, f"prompt chain rebuilt {len(got)} chars, components.txt is {len(want)}"

    api = json.loads((C.SKILL / "templates" / "components.api.json").read_text(encoding="utf-8"))
    assert api["40"]["inputs"]["model_name"] == "gemini-3-pro-image-preview"
    assert api["42"]["inputs"]["images"] == ["40", 0], "the cut-out must read the Nano Banana image"
    assert api["43"]["inputs"]["images"] == ["42", 0], "the transparent save must read the cut-out"
    for nid in ("10", "11", "12"):
        assert api[nid]["class_type"] == "LoadImage"

    ui = json.loads((ROOT / "workflows" / "new" / C.WORKFLOW_NAME).read_text(encoding="utf-8"))
    ids = {n["id"] for n in ui["nodes"]}
    assert len(ids) == len(ui["nodes"]), "duplicate node ids in the UI workflow"
    for a, src, sslot, dst, dslot, _ in ui["links"]:
        assert src in ids and dst in ids, f"link {a} points at a node that is not in the file"
    print(f"ok: prompt chain rebuilds components.txt ({len(want)} chars), {len(ui['nodes'])} UI nodes, {len(ui['links'])} links")


if __name__ == "__main__":
    demo()
