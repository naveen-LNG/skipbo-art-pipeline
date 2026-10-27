"""Whole-legs sheets (annotated role legs: squat_1..n, jump_1..n, in-betweens squat_a-b): two cross-fading slots on
bones of their own with one scale per sheet (rig_variants.add_legs), swapped in for the trousers and feet by progress
in squat, jump_hurdle and plant_seed (rig_anim.leg_track, cross_fade), on the synthetic character; without them the
squat keeps squashing the hips."""
import copy
import json
import subprocess
import sys

import pytest

import rig_annotations as ra
from conftest import ROOT, SCRIPTS
from synth_character import LEGS_MIDS, LEGS_SHEETS, MID_SHORT, make_character
from test_props import _build, _garden_props, _props

LEGS_ANIMS = ("squat", "jump_hurdle")
DRAWINGS = [f"{s}_{i}" for s, fr in LEGS_SHEETS.items() for i in range(1, len(fr) + 1)] + \
    [f"{s}_{a}-{b}" for s, ms in LEGS_MIDS.items() for a, b in ms]
LEGS_SLOTS = ("legs_a", "legs_b")


@pytest.fixture(scope="module")
def legs_rig(tmp_path_factory):
    root = tmp_path_factory.mktemp("legs")
    make_character(root, pose_variants=True, legs=True)
    return root, _build(root, root / "rig", "--props", str(_props(root)))


@pytest.fixture(scope="module")
def plain_rig(tmp_path_factory):
    root = tmp_path_factory.mktemp("plain")
    make_character(root, pose_variants=True)
    return root, _build(root, root / "rig", "--props", str(_props(root)))


def _report(root):
    return json.loads((root / "rig" / "report.json").read_text())["variants"]


def _fails(rep, anim):
    return {(k, part) for k, v in rep[anim].items() if isinstance(v, dict) for part in v}


def _qa(root, *anims):
    r = subprocess.run([sys.executable, str(SCRIPTS / "spine_qa.py"), str(root / "rig" / "synth.json"), "--master",
                        str(root / "master.png"), "--anims", "idle", *anims], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode in (0, 1), r.stderr[-3000:]
    return json.loads((root / "rig" / "qa" / "report.json").read_text())


def _soles(root, skel, anim):
    """(time, [world y of the soles of every legs drawing on screen]) per frame (empty while only the rig's own legs
    show): both drawings of a cross-fade stand on the ground."""
    import qa_constraints
    import spine_qa
    rig = spine_qa.Rig(root / "rig" / "synth.json")
    rep = _report(root)
    out = []
    for i in range(int(round(rig.duration(anim) * 30))):
        world, active = rig.pose(anim, i / 30)
        ys = []
        for slot in LEGS_SLOTS:
            att = active.get(slot)
            if att and (qa_constraints.slot_color(rig.data, {"name": slot}, anim, i / 30) or (1, 1, 1, 1))[3] > 0.02:
                a, b, c, d, x, y = world[slot]
                ys.append(y - d * rep[att]["height_units"])
        out.append((i / 30, ys))
    return out


def _shown(an):
    """The drawings in the order they come on screen (both legs slots), None for the rig's own legs."""
    keys = sorted((k["time"], k["name"]) for s in LEGS_SLOTS for k in an["slots"][s]["attachment"] if k["name"])
    seq = [None]
    for _, n in keys:
        if n != seq[-1]:
            seq.append(n)
    return seq


def test_legs_role_validation(tmp_path):
    ann = ra.load(make_character(tmp_path, legs=True))
    assert sorted(p.variant for p in ann.pieces.values() if p.role == "legs") == sorted(DRAWINGS)
    assert ra.validate(ann) == []
    bad = copy.deepcopy(ann)
    p = next(p for p in bad.pieces.values() if p.role == "legs")
    for v in ("crouch", "squat_0", "kneel_2", "squat_3-5", "squat_4-3", None):
        p.variant = v
        assert any("a drawing of a legs sheet" in e for e in ra.validate(bad)), v
    p.variant, p.name = "squat_3", "trousers"
    assert any("must be 'legs'" in e for e in ra.validate(bad))
    p.name, p.status, p.variant = "legs", "ignored", "anything"       # a spare drawing on the sheet
    assert ra.validate(bad) == []
    del next(p for p in ann.pieces.values() if p.role == "legs").points["ground"]
    assert any("missing required point 'ground'" in e for e in ra.validate(ann))


@pytest.mark.slow
def test_legs_bone_appended_and_slot_above_the_trousers(legs_rig, plain_rig):
    _, skel = legs_rig
    _, plain = plain_rig
    names = [b["name"] for b in skel["bones"]]
    # every bone the rig had keeps its index (weighted meshes name bones by index); the legs bones come after them
    assert names[:names.index("legs_a")] == [b["name"] for b in plain["bones"] if not b["name"].startswith("prop_")]
    assert names.index("legs_b") == names.index("legs_a") + 1
    hips = next(b for b in skel["bones"] if b["name"] == "hips")
    for s in LEGS_SLOTS:
        legs = next(b for b in skel["bones"] if b["name"] == s)
        assert legs["parent"] == "hips" and legs["rotation"] == pytest.approx(-hips.get("rotation", 0.0), abs=0.01)
    slots = [s["name"] for s in skel["slots"]]
    assert slots.index("legs_a") == slots.index("hips") + 1 and slots.index("legs_b") == slots.index("hips") + 2
    for s in LEGS_SLOTS:
        assert "attachment" not in skel["slots"][slots.index(s)]             # hidden at rest
        assert sorted(skel["skins"][0]["attachments"][s]) == sorted(f"synth_legs_{v}" for v in DRAWINGS)


@pytest.mark.slow
def test_one_scale_per_sheet_fitted_on_drawing_1(legs_rig):
    root, _ = legs_rig
    rep = _report(root)
    for sheet, fracs in LEGS_SHEETS.items():
        scales = {tuple(rep[f"synth_legs_{sheet}_{i}"]["scale"]) for i in range(1, len(fracs) + 1)}
        assert len(scales) == 1                                             # no per-drawing flicker
        for i, f in enumerate(fracs, 1):                                    # the drawings keep their own ratios
            assert rep[f"synth_legs_{sheet}_{i}"]["height_vs_rest"] == pytest.approx(f, abs=0.02)
        sx = rep[f"synth_legs_{sheet}_1"]["scale"][0]
        for a, b in LEGS_MIDS[sheet]:                                       # an in-between: declared halfway, its
            r = rep[f"synth_legs_{sheet}_{a}-{b}"]                          # painted height squashed to it
            assert r["height_vs_rest"] == pytest.approx(0.5 * (fracs[a - 1] + fracs[b - 1]), abs=0.02)
            assert r["squash"] == pytest.approx(1 / MID_SHORT, abs=0.02) and r["scale"][0] == sx
    # painted at POSE_SCALE (0.7): ~1/0.7 master px per drawing px, about the same both ways
    k = json.loads((root / "rig" / "report.json").read_text())["master_frame"]["units_per_px"]
    sx, sy = rep["synth_legs_squat_1"]["scale"]
    assert sx / k == pytest.approx(1 / 0.7, rel=0.06) and sy / sx == pytest.approx(1.0, abs=0.06)


@pytest.mark.slow
def test_squat_starts_from_the_rig_and_keeps_the_soles_down(legs_rig):
    root, skel = legs_rig
    sq = skel["animations"]["squat"]
    n = len(LEGS_SHEETS["squat"])
    mids = {b: f"synth_legs_squat_{a}-{b}" for a, b in LEGS_MIDS["squat"]}
    down = [None] + [d for i in range(2, n + 1) for d in ([mids[i]] if i in mids else []) + [f"synth_legs_squat_{i}"]]
    # the rig's own legs first (no pop), drawing 1 never shown, down through every drawing and in-between and back
    assert _shown(sq) == down + down[-2:0:-1]
    for slot in LEGS_SLOTS:                         # drawings alternate between the two slots: a cross-fade each swap
        keys = [k["name"] for k in sq["slots"][slot]["attachment"] if k["name"]]
        assert len(keys) >= 2 and len(set(keys)) >= 2
    for slot in ("hips", "leg_l", "leg_r", "boot_l", "boot_r"):     # the rig's parts fade out and back in
        keys = sq["slots"][slot]
        assert keys["attachment"][0]["name"] == f"synth_{slot}" and keys["attachment"][-1]["name"] == f"synth_{slot}"
        alpha = [int(k["color"][6:], 16) for k in keys["rgba"]]
        assert alpha[0] == 255 and 0 in alpha and alpha[-1] == 255
    import qa_constraints
    import spine_qa
    rig = spine_qa.Rig(root / "rig" / "synth.json")
    faded = 0
    for i in range(61):                             # one drawing (or the rig's own legs) is always fully opaque
        t = i / 30
        _, active = rig.pose("squat", t)
        alpha = [(qa_constraints.slot_color(skel, {"name": s}, "squat", t) or (1, 1, 1, 1))[3]
                 for s in (*LEGS_SLOTS, "hips") if active.get(s)]
        assert max(alpha) > 0.99, (t, alpha)
        faded += any(0.02 < a < 0.98 for a in alpha)
    assert faded >= 4                               # and the swaps do fade
    assert "scale" not in sq["bones"]["hips"]                       # no squashed trousers
    rep = _report(root)
    low = min(k["y"] for k in sq["bones"]["hips"]["translate"])
    assert low == pytest.approx(rep[f"synth_legs_squat_{n}"]["height_units"] - rep["synth_legs_squat_1"]["height_units"], rel=0.02)
    H = skel["skeleton"]["height"]
    for t, ys in _soles(root, skel, "squat"):                       # every drawing on screen stands on the ground
        assert all(abs(y) < 0.01 * H for y in ys), (t, ys)
    for s in LEGS_SLOTS:                                            # each drawing squashed or stretched a little
        for k in sq["bones"][s]["scale"]:
            assert 0.85 < k["y"] < 1.15


@pytest.mark.slow
def test_jump_tucks_the_legs_over_the_bar(legs_rig):
    root, skel = legs_rig
    jh = skel["animations"]["jump_hurdle"]
    shown = _shown(jh)
    n = len(LEGS_SHEETS["jump"])
    assert f"synth_legs_jump_{n}" in shown                          # the full tuck
    for a, b in LEGS_MIDS["jump"]:                                  # the in-betweens on the way up and down
        assert shown.count(f"synth_legs_jump_{a}-{b}") == 2
    assert shown.count(f"synth_legs_squat_{len(LEGS_SHEETS['squat'])}") == 2      # take-off and landing crouch
    soles = [max(ys) for _, ys in _soles(root, skel, "jump_hurdle") if ys]
    bar = json.loads((root / "props.json").read_text())["hurdle"]["height"]
    assert max(soles) > bar * float(skel["skeleton"]["height"]) * 0.9


@pytest.mark.slow
def test_legs_moves_pass_spine_qa(legs_rig):
    root, _ = legs_rig
    rep = _qa(root, *LEGS_ANIMS)
    # the fixture's tail reads detached from the hips in idle (known); the same while the rig's own legs show
    known = _fails(rep, "idle")
    for anim in LEGS_ANIMS:
        assert _fails(rep, anim) <= known, (anim, _fails(rep, anim) - known)


@pytest.mark.slow
def test_plant_seed_crouches_on_the_squat_sheet(tmp_path):
    make_character(tmp_path, pose_variants=True, legs=True)
    skel = _build(tmp_path, tmp_path / "rig", "--props", str(_garden_props(tmp_path)))
    ps = skel["animations"]["plant_seed"]
    assert f"synth_legs_squat_{len(LEGS_SHEETS['squat'])}" in _shown(ps)
    assert "scale" not in ps["bones"]["hips"] and [e["name"] for e in ps["events"]] == ["seed"]
    assert "head" in ps["slots"]                                    # the look heads kept beside the legs keys
    H = skel["skeleton"]["height"]
    for t, ys in _soles(tmp_path, skel, "plant_seed"):
        assert all(abs(y) < 0.01 * H for y in ys), (t, ys)
    rep = _qa(tmp_path, "plant_seed")
    assert _fails(rep, "plant_seed") <= _fails(rep, "idle"), _fails(rep, "plant_seed") - _fails(rep, "idle")


@pytest.mark.slow
def test_without_legs_the_squat_squashes_the_hips(plain_rig):
    _, skel = plain_rig
    assert not {"legs_a", "legs_b"} & {b["name"] for b in skel["bones"]}
    assert "scale" in skel["animations"]["squat"]["bones"]["hips"]
    assert "legs_a" not in skel["animations"]["jump_hurdle"].get("slots", {})


@pytest.mark.slow
def test_rest_legs_render(legs_rig, tmp_path):
    root, _ = legs_rig
    out = tmp_path / "rest.png"
    r = subprocess.run([sys.executable, str(SCRIPTS / "rig_rest_legs.py"), str(root / "rig" / "synth.json"), str(out),
                        "--annotations", str(root / "annotations.json")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    from PIL import Image
    im = Image.open(out)
    assert 1.6 < im.height / im.width < 2.6          # trousers, legs and boots only: no torso, arms or head
    assert (tmp_path / "rest_grey.png").exists()


def test_legs_inbetweens_prompt_lints():
    sys.path.insert(0, str(SCRIPTS))
    import comfy
    text = (SCRIPTS.parent / "references" / "prompts" / "spine" / "legs-inbetweens.txt").read_text()
    for var in ("{{REST_USE}}", "{{COUNT}}", "{{MOVE}}", "{{STEPS}}", "{{CHARACTER}}"):
        assert var in text
    assert comfy.lint(text, "nb", {1, 2, 3}) == []
    assert "gold buckle" not in text and "red boots" not in text      # no one character's costume in the template


def test_legs_midpoint_prompt_lints():
    sys.path.insert(0, str(SCRIPTS))
    import comfy
    text = (SCRIPTS.parent / "references" / "prompts" / "spine" / "legs-midpoint.txt").read_text()
    assert "{{MOVE}}" in text and "image_1 exactly" in text and "image_2 exactly" in text
    assert comfy.lint(text, "nb", {1, 2}) == []
    assert "gold buckle" not in text and "red boots" not in text
