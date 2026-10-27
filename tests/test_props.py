"""Props not in the master (rig_props: a held flag, a hurdle) and the body moves (rig_anim: walk, run, squat,
jump_hurdle, wave_flag) on the synthetic character."""
import json
import subprocess
import sys

import pytest
from PIL import Image, ImageDraw

from conftest import ROOT, SCRIPTS
from synth_character import make_character

NEW = ("walk", "run", "squat", "jump_hurdle", "wave_flag")


def _props(root):
    flag = Image.new("RGBA", (120, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(flag)
    d.rectangle((10, 10, 22, 295), fill=(150, 100, 60, 255))           # the stick
    d.rectangle((22, 14, 110, 90), fill=(245, 245, 245, 255))          # the cloth
    flag.save(root / "flag.png")
    hurdle = Image.new("RGBA", (300, 160), (0, 0, 0, 0))
    d = ImageDraw.Draw(hurdle)
    d.rectangle((10, 10, 30, 158), fill=(150, 100, 60, 255))
    d.rectangle((270, 10, 290, 158), fill=(150, 100, 60, 255))
    d.rectangle((30, 30, 270, 55), fill=(220, 40, 40, 255))
    hurdle.save(root / "hurdle.png")
    p = root / "props.json"
    p.write_text(json.dumps({
        "flag": {"image": "flag.png", "kind": "held", "grip": [0.13, 0.85], "tip": [0.13, 0.04], "length": 0.36},
        "hurdle": {"image": "hurdle.png", "kind": "ground", "base": [0.5, 0.99], "height": 0.2, "front": 0.05}}))
    return p


def _build(root, out, *extra):
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(root / "master.png"),
           "--annotations", str(root / "annotations.json"), "--name", "synth", "--out", str(out), *extra]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return json.loads((out / "synth.json").read_text())


@pytest.fixture(scope="module")
def props_rig(tmp_path_factory):
    root = tmp_path_factory.mktemp("props")
    make_character(root, pose_variants=True)
    return root, _build(root, root / "rig", "--props", str(_props(root)))


@pytest.mark.slow
def test_props_hang_from_their_bones_hidden_at_rest(props_rig):
    _, skel = props_rig
    bones = {b["name"]: b for b in skel["bones"]}
    assert bones["prop_flag"]["parent"].startswith("hand_") and bones["prop_hurdle"]["parent"] == "root"
    slots = [s["name"] for s in skel["slots"]]
    for s in skel["slots"]:
        if s["name"].startswith("prop_"):
            assert "attachment" not in s                               # hidden in the setup pose
    hand = next(s for s in skel["slots"] if s["name"] == bones["prop_flag"]["parent"])
    assert slots.index("prop_flag") < slots.index(hand["name"])        # the fist closes over the stick
    assert slots[-1] == "prop_hurdle"                                   # in front of the legs at the start
    assert set(NEW) <= set(skel["animations"])
    jh = skel["animations"]["jump_hurdle"]
    (key,) = [k for k in jh["drawOrder"] if k.get("offsets")]           # behind the jumper from the top of the jump
    assert key["offsets"] == [{"slot": "prop_hurdle", "offset": -slots.index("prop_hurdle")}]
    assert jh["slots"]["prop_hurdle"]["attachment"][0]["name"].endswith("prop_hurdle")
    assert skel["animations"]["wave_flag"]["slots"]["prop_flag"]["attachment"][0]["name"].endswith("prop_flag")


@pytest.mark.slow
def test_body_moves_pass_spine_qa(props_rig):
    root, _ = props_rig
    r = subprocess.run([sys.executable, str(SCRIPTS / "spine_qa.py"), str(root / "rig" / "synth.json"), "--master",
                        str(root / "master.png"), "--anims", "idle", *NEW], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode in (0, 1), r.stderr[-3000:]
    rep = json.loads((root / "rig" / "qa" / "report.json").read_text())

    def fails(a):
        return {(k, part) for k, v in rep[a].items() if isinstance(v, dict) for part in v}
    known = fails("idle")                    # the fixture's own (its tail reads detached in idle too)
    for anim in NEW:
        assert fails(anim) <= known, (anim, fails(anim) - known)
    assert all(not k.startswith("synth_leg") or v["off"] <= 1.0 for k, v in rep["sockets"]["sockets"].items())


@pytest.mark.slow
def test_without_props_only_the_moves_that_need_none(tmp_path):
    make_character(tmp_path, pose_variants=True)
    skel = _build(tmp_path, tmp_path / "rig")
    assert {"walk", "run", "squat"} <= set(skel["animations"])
    assert not {"jump_hurdle", "wave_flag"} & set(skel["animations"])
    assert not any(b["name"].startswith("prop_") for b in skel["bones"])


GARDEN = ("plant_seed", "water", "grow_0", "grow_1", "grow_2")


def _garden_props(root):
    can = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(can)
    d.ellipse((60, 10, 140, 90), outline=(70, 140, 220, 255), width=14)              # the handle
    d.rectangle((50, 60, 170, 190), fill=(70, 140, 220, 255))                       # the body
    d.polygon([(165, 120), (290, 40), (295, 60), (170, 150)], fill=(70, 140, 220, 255))   # the spout
    can.save(root / "can.png")
    stream = Image.new("RGBA", (60, 300), (0, 0, 0, 0))
    ImageDraw.Draw(stream).rounded_rectangle((10, 5, 50, 295), 18, fill=(170, 220, 250, 255))
    stream.save(root / "stream.png")
    stages = []
    for i in range(3):                                                              # one mound, a taller plant each time
        im = Image.new("RGBA", (200, 300), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if i:
            d.rectangle((95, 240 - 80 * i, 105, 250), fill=(60, 160, 60, 255))
        d.ellipse((20, 230, 180, 330), fill=(100, 60, 30, 255))
        im.save(root / f"plant_{i}.png")
        stages.append(f"plant_{i}.png")
    p = root / "garden.json"
    p.write_text(json.dumps({
        "can": {"image": "can.png", "kind": "held", "grip": [0.33, 0.05], "tip": [0.97, 0.25], "length": 0.25, "use": "water"},
        "stream": {"image": "stream.png", "kind": "attached", "on": "can", "at": [0.96, 0.27], "top": [0.5, 0.03], "fall": 0.6, "use": "water"},
        "plant": {"stages": stages, "kind": "ground", "width": 0.22, "x": 0.55, "front": 0.03, "behind": True, "use": "grow"}}))
    return p


@pytest.fixture(scope="module")
def garden_rig(tmp_path_factory):
    root = tmp_path_factory.mktemp("garden")
    make_character(root, pose_variants=True)
    return root, _build(root, root / "rig", "--props", str(_garden_props(root)))


@pytest.mark.slow
def test_garden_props_stage_hang_and_fire_events(garden_rig):
    _, skel = garden_rig
    bones = {b["name"]: b for b in skel["bones"]}
    slots = [s["name"] for s in skel["slots"]]
    assert bones["prop_stream"]["parent"] == "prop_can" and bones["prop_stream"]["inherit"] == "noRotationOrReflection"
    assert bones["prop_plant"]["parent"] == "root" and bones["prop_plant"]["x"] > 0          # to the viewer's right
    assert slots[0] == "prop_plant"                                                         # behind the character
    assert slots.index("prop_stream") < slots.index("prop_can") < slots.index(bones["prop_can"]["parent"])
    stages = list(skel["skins"][0]["attachments"]["prop_plant"])
    assert len(stages) == 3 and stages[1].endswith("prop_plant_1")
    assert set(GARDEN) <= set(skel["animations"]) and "grow_3" not in skel["animations"]
    assert not {"jump_hurdle", "wave_flag"} & set(skel["animations"])                       # those take props without `use`
    assert skel["events"] == {"pour": {}, "seed": {}}
    an = skel["animations"]
    assert [e["name"] for e in an["plant_seed"]["events"]] == ["seed"]
    assert [e["name"] for e in an["water"]["events"]] == ["pour"]
    for i in range(3):                                                                      # each grow holds its stage
        assert an[f"grow_{i}"]["slots"]["prop_plant"]["attachment"][0]["name"] == stages[i]
    order = list(slots)                                                                     # can and arm over the body
    for k in an["water"].get("drawOrder", [{}])[0].get("offsets", []):
        order.remove(k["slot"])
    for k in sorted(an["water"].get("drawOrder", [{}])[0].get("offsets", []), key=lambda k: slots.index(k["slot"]) + k["offset"]):
        order.insert(slots.index(k["slot"]) + k["offset"], k["slot"])
    hand = bones["prop_can"]["parent"]
    assert order.index("torso") < order.index("prop_stream") < order.index("prop_can") < order.index(hand)
    pour = an["water"]["slots"]["prop_stream"]["attachment"]
    assert pour[0]["name"] is None and pour[1]["name"] and pour[-1]["name"] is None         # the stream only while pouring


@pytest.mark.slow
def test_garden_moves_pass_spine_qa(garden_rig):
    root, _ = garden_rig
    r = subprocess.run([sys.executable, str(SCRIPTS / "spine_qa.py"), str(root / "rig" / "synth.json"), "--master",
                        str(root / "master.png"), "--anims", "idle", *GARDEN], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode in (0, 1), r.stderr[-3000:]
    rep = json.loads((root / "rig" / "qa" / "report.json").read_text())

    def fails(a):
        return {(k, part) for k, v in rep[a].items() if isinstance(v, dict) for part in v}
    known = fails("idle")
    for anim in GARDEN:
        assert fails(anim) <= known, (anim, fails(anim) - known)
