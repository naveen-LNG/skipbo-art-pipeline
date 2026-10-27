"""spine_diff.py: an animator's edits to a generated rig, as labelled corrections (synthetic edits on the synthetic
character's pro rig)."""
import copy
import json
import subprocess
import sys

import pytest

from conftest import ROOT, SCRIPTS
from synth_character import make_character

import pro_common as pc
import spine_diff


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    root = tmp_path_factory.mktemp("diff")
    ann = make_character(root)
    r = subprocess.run([sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(root / "master.png"),
                        "--annotations", str(ann), "--name", "synth", "--out", str(root / "rig")],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    import spine_pro
    spine_pro.build(root / "rig" / "synth.json", root / "pro")
    return root, json.loads((root / "pro" / "synth.json").read_text())


def _kinds(recs):
    return {(r["kind"], r["target"]) for r in recs}


def test_identical_is_empty(gen):
    _, g = gen
    assert spine_diff.diff(g, copy.deepcopy(g)) == []


def test_bone_edits(gen):
    _, g = gen
    e = copy.deepcopy(g)
    pc.bone(e, "chest")["x"] += 12                   # pivot moved (Alt-redraw)
    pc.bone(e, "forearm_l")["rotation"] += 7
    pc.bone(e, "head_base")["inherit"] = "noRotationOrReflection"
    pc.bone(e, "tail3")["parent"] = "tail"           # reparented
    e["bones"].append({"name": "chest2", "parent": "chest", "x": 20, "length": 40, "color": pc.YELLOW})
    recs = spine_diff.diff(g, e, character="synth")
    k = _kinds(recs)
    assert ("bone_moved", "chest") in k and ("bone_rotated", "forearm_l") in k
    assert ("bone_inherit_changed", "head_base") in k and ("bone_reparented", "tail3") in k
    assert ("bone_added", "chest2") in k
    for r in recs:
        assert r["bucket"] == "anthro-biped-animal" and r["character"] == "synth" and r["id"]
    st = {r["target"]: r["stage"] for r in recs}
    assert st["chest"] == "helper-bones" and st["forearm_l"] == "skeleton" and st["chest2"] == "helper-bones"
    moved = next(r for r in recs if r["kind"] == "bone_moved")
    assert moved["detail"]["local_delta"] == [12.0, 0.0] and moved["detail"]["world_delta_frac_height"] > 0


def test_weight_and_mesh_edits(gen):
    _, g = gen
    e = copy.deepcopy(g)
    tail = e["skins"][0]["attachments"]["tail"]
    att = next(iter(tail))
    v = tail[att]["vertices"]
    # find a two-bone vertex and shift 0.2 of its weight between its bones
    k = 0
    while k < len(v):
        c = int(v[k])
        if c == 2:
            v[k + 4] -= 0.2
            v[k + 8] += 0.2
            break
        k += 1 + 4 * c
    head = e["skins"][0]["attachments"]["head"]
    h = next(iter(head))
    head[h]["uvs"][0] += 0.01
    recs = spine_diff.diff(g, e)
    kinds = [r["kind"] for r in recs]
    assert "weights_changed" in kinds and "mesh_uvs_moved" in kinds
    w = [r for r in recs if r["kind"] == "weights_changed"]
    assert {r["stage"] for r in w} == {"mesh-weights"} and all(r["detail"]["vertices_changed"] == 1 for r in w)
    assert {r["target"].split("@")[1] for r in w} == set(r["target"].split("@")[1] for r in w) and len(w) == 2


def test_remesh_and_type_change(gen):
    _, g = gen
    e = copy.deepcopy(g)
    sk = e["skins"][0]["attachments"]
    hips = next(iter(sk["hips"]))
    sk["hips"][hips] = {"type": "mesh", "uvs": [0, 0, 1, 0, 1, 1, 0, 1], "triangles": [0, 1, 2, 0, 2, 3],
                        "vertices": [0, 0, 10, 0, 10, 10, 0, 10], "hull": 4}
    t = next(iter(sk["torso"]))
    sk["torso"][t]["uvs"] = sk["torso"][t]["uvs"][:-2]
    recs = spine_diff.diff(g, e)
    k = _kinds(recs)
    assert ("attachment_type_changed", f"hips/{hips}") in k and ("mesh_remeshed", f"torso/{t}") in k


def test_constraint_slot_and_animation_edits(gen):
    _, g = gen
    e = copy.deepcopy(g)
    e["transform"][0]["mixRotate"] = 0.5
    e["transform"].append({"name": "ear_follow", "bones": ["tail2"], "target": "tail", "mixRotate": 0.3})
    names = [s["name"] for s in e["slots"]]
    i, j = names.index("hand_l"), names.index("torso")
    e["slots"][i], e["slots"][j] = e["slots"][j], e["slots"][i]
    e["animations"]["idle"]["bones"]["head_base"]["rotate"][5]["value"] += 3
    del e["animations"]["talk"]
    e["animations"]["wave2"] = copy.deepcopy(e["animations"]["wave"])
    recs = spine_diff.diff(g, e)
    k = _kinds(recs)
    assert ("constraint_changed", g["transform"][0]["name"]) in k and ("constraint_added", "ear_follow") in k
    assert ("draw_order_changed", "hand_l") in k
    assert ("timeline_changed", "idle:bones.head_base.rotate") in k
    assert ("animation_removed", "talk") in k and ("animation_added", "wave2") in k
    st = {r["kind"]: r["stage"] for r in recs}
    assert st["constraint_added"] == "constraints" and st["draw_order_changed"] == "organize"
    assert st["timeline_changed"] == "animate"
    tl = next(r for r in recs if r["kind"] == "timeline_changed")
    assert tl["detail"]["keys_changed"] == 1 and abs(tl["detail"]["max_value_delta"] - 3) < 1e-6


def test_cli_writes_jsonl(gen, tmp_path):
    root, g = gen
    e = copy.deepcopy(g)
    pc.bone(e, "face")["y"] += 4
    (tmp_path / "edited.json").write_text(json.dumps(e))
    out = tmp_path / "corrections.jsonl"
    r = subprocess.run([sys.executable, str(SCRIPTS / "spine_diff.py"), str(root / "pro" / "synth.json"),
                        str(tmp_path / "edited.json"), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lines = [json.loads(x) for x in out.read_text().splitlines()]
    assert lines[0]["kind"] == "bone_moved" and lines[0]["character"] == "synth"
    assert lines[0]["stage"] == "helper-bones"
    # the head meshes are weighted to `face` with unchanged binds, so their vertices moved with it (as in Spine)
    assert {x["kind"] for x in lines[1:]} == {"mesh_vertices_moved"}
    assert all(x["target"].startswith(("head/", "head_under/")) for x in lines[1:])
