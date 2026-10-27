"""T18: fit and connectivity in annotation mode - hips narrowed to the boots, upper arm to the forearm, the forearm
trimmed at its wrist under a glove, hand variants turned along the hand bone."""
import json
import math
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

import rig_annotations as ra
from conftest import ROOT, SCRIPTS
from synth_character import make_character


def _place(ann):
    import rig_place
    import spine_rig
    frame = spine_rig.load_master(ann.path.parent / "master.png")
    g = rig_place.global_scale(ann, frame)
    return frame, g, rig_place.place_from_annotations(ann, frame, g)


def _outs(ann):
    return {o.name: o for p in ann.pieces.values() for o in p.outputs}


def _drop_legs(ann):
    for p in ann.pieces.values():
        if p.role == "leg":
            p.status, p.role, p.points, p.outputs = "ignored", "", {}, []
    return ann


def _build(ann_path, out):
    root = ann_path.parent
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(root / "master.png"),
           "--annotations", str(ann_path), "--name", "synth", "--out", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return out


# ------------------------------------------------------------------ 1. hips narrowed to the boot openings

def _legless(tmp_path, layer="over_hips"):
    ann = _drop_legs(ra.load(make_character(tmp_path)))
    ann.master.layers = {"foot": layer} if layer else {}
    return ann


def _hips_opening_vs_ankle(ann, frame, g, pieces):
    """(hips leg-opening width, boot ankle-opening width) in master px, per side."""
    import rig_place
    G = g / frame.k
    o = _outs(ann)
    out = {}
    for s in "lr":
        hips = o["hips"].widths[f"hip_{s}"] * pieces["hips"]["unit"] * G
        boot = o[f"boot_{s}"].widths["ankle"] * pieces[f"boot_{s}"]["unit"] * G
        out[s] = (hips, boot)
    return out


@pytest.mark.slow
def test_hips_narrowed_to_the_boots_without_legs(tmp_path):
    import rig_place
    ann = _legless(tmp_path)
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    o = _outs(ann)
    # synthetic: hips openings 60, boot openings 56 (master px, at the sheet's scale): 0.8 x 56 / 60
    want = rig_place.HIPS_FOOT_FIT * 56 / 60
    fit = info["hips"]["width_fit"]
    assert fit["factor"] == pytest.approx(want, abs=0.01) and fit["raw"] == pytest.approx(want, abs=0.01)
    assert pieces["hips"]["unit"] == pytest.approx(want, abs=0.01)
    for s, (h, b) in _hips_opening_vs_ankle(ann, frame, g, pieces).items():
        assert h <= rig_place.HIPS_FOOT_FIT * b + 0.5, (s, h, b)
    # the height is kept; the waist stays on the master's waist and the bone runs down the centre line
    G = g / frame.k
    assert pieces["hips"]["unit_y"] == pytest.approx(1.0, abs=0.08)
    W, H = rig_place._master_size(ann)
    waist = np.array(ann.master.points["waist"]) * (W, H)
    xf = rig_place.Placement(pieces["hips"]["img"].size, pieces["hips"]["cx"], pieces["hips"]["cy"],
                             pieces["hips"]["unit"] * G, pieces["hips"]["unit_y"] * G, pieces["hips"]["angle"])
    assert np.linalg.norm(xf.world(o["hips"].points["waist"]) - waist) < 0.5
    assert abs(joints["hips"][0] - waist[0]) < 1.0
    xi, yi = np.round(joints["hips"]).astype(int)
    assert pieces["hips"]["mask"][yi, xi]
    assert not [d for d in doubts if d["reason"] == "hips_too_wide"], doubts


@pytest.mark.slow
@pytest.mark.parametrize("layer", [None, "under_hips"])
def test_hips_kept_when_feet_go_behind(tmp_path, layer):
    ann = _legless(tmp_path, layer)
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    assert pieces["hips"]["unit"] == pytest.approx(1.0)
    assert "width_fit" not in info["hips"]


@pytest.mark.slow
def test_hips_kept_with_legs(tmp_path):
    ann = ra.load(make_character(tmp_path))
    ann.master.layers = {"foot": "over_hips"}
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    assert pieces["hips"]["unit"] == pytest.approx(1.0)


@pytest.mark.slow
def test_hips_too_wide_is_clamped_and_doubted(tmp_path):
    import rig_place
    ann = _legless(tmp_path)
    o = _outs(ann)["hips"]
    o.widths = {n: w * 1.5 for n, w in o.widths.items()}             # annotated openings far wider than the boots
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    lo = 1 - rig_place.WIDTH_FIT_MAX
    assert pieces["hips"]["unit"] == pytest.approx(lo, abs=1e-6)
    raw = rig_place.HIPS_FOOT_FIT * 56 / 60 / 1.5
    assert info["hips"]["width_fit"] == {"factor": pytest.approx(lo), "raw": pytest.approx(raw, abs=0.01)}
    d = [d for d in doubts if d["reason"] == "hips_too_wide"]
    assert len(d) == 1 and d[0]["part"] == "hips" and d[0]["ratio"] == pytest.approx(raw, abs=0.01)
    assert d[0]["limit"] == rig_place.WIDTH_FIT_MAX


def _xf(pieces, n, G):
    import rig_place
    pc = pieces[n]
    return rig_place.Placement(pc["img"].size, pc["cx"], pc["cy"], pc["unit"] * G, pc["unit_y"] * G, pc["angle"])


@pytest.mark.slow
def test_feet_follow_the_narrowed_hips(tmp_path):
    """T19: leg-less, feet over the hips: each boot's ankle opening centre sits under the placed hips' leg opening
    centre on its side (x), still on the master's ankle height (y); the shift is reported and is the ankle's push."""
    import rig_place
    ann = _legless(tmp_path)
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    G = g / frame.k
    o = _outs(ann)
    W, H = rig_place._master_size(ann)
    hips = _xf(pieces, "hips", G)
    for s in "lr":
        n = f"boot_{s}"
        hip = hips.world(o["hips"].points[f"hip_{s}"])
        ankle = _xf(pieces, n, G).world(o[n].points["ankle"])
        master = np.array(ann.master.points[f"ankle_{s}"]) * (W, H)
        assert ankle[0] == pytest.approx(hip[0], abs=0.5), s
        assert ankle[1] == pytest.approx(master[1], abs=0.5), s
        assert abs(hip[0] - master[0]) > 3                            # the narrowed hips moved the opening inwards
        dx = info[n]["ankle_shift"]["dx"]
        assert dx == pytest.approx(hip[0] - master[0], abs=0.01)
        assert info[n]["push"]["ankle"] == pytest.approx(abs(dx), abs=0.01)
        assert np.linalg.norm(joints[n] - ankle) < 0.5                # the bone pivots at the moved opening


@pytest.mark.slow
@pytest.mark.parametrize("legs", [True, False])
def test_feet_stay_on_the_master_ankles_otherwise(tmp_path, legs):
    """With leg pieces, or feet drawn under the hips, the feet stay on the master's ankles."""
    import rig_place
    ann = ra.load(make_character(tmp_path))
    if legs:
        ann.master.layers = {"foot": "over_hips"}
    else:
        ann = _drop_legs(ann)
        ann.master.layers = {"foot": "under_hips"}
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    G = g / frame.k
    W, H = rig_place._master_size(ann)
    for s in "lr":
        n = f"boot_{s}"
        ankle = _xf(pieces, n, G).world(_outs(ann)[n].points["ankle"])
        assert np.linalg.norm(ankle - np.array(ann.master.points[f"ankle_{s}"]) * (W, H)) < 0.5
        assert "ankle_shift" not in info[n] and "ankle" not in info[n]["push"]


@pytest.mark.slow
def test_feet_shift_is_the_ankle_landmark_tolerance(tmp_path):
    """The resolved file carries the shift as the ankle's push-in (spine_qa's landmark tolerance), and the report
    lists it per foot."""
    import rig_place
    ann = _legless(tmp_path)
    ra.save(ann)
    out = _build(ann.path, tmp_path / "rig")
    res = json.loads((out / "annotations.resolved.json").read_text())
    rep = json.loads((out / "report.json").read_text())
    unit = rep["master_frame"]["units_per_px"]
    for s in "lr":
        dx = rep["parts"][f"boot_{s}"]["ankle_shift"]["dx"]
        assert abs(dx) > 3
        assert res["push_in"][f"ankle_{s}"] == pytest.approx(abs(dx) * unit, abs=0.01)
    assert "ankle" in rig_place.PUSHED_ORIGINS


# ------------------------------------------------------------------ 2. upper arm narrowed to the forearm

@pytest.mark.slow
def test_upper_arm_narrowed_to_the_forearm(tmp_path):
    ann = ra.load(make_character(tmp_path))
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    o = _outs(ann)
    for s in "lr":
        ua, fa = f"upperarm_{s}", f"forearm_{s}"
        want = 38 / 40                                                # synthetic: forearm elbow 38, upper arm 40
        assert info[ua]["width_fit"]["factor"] == pytest.approx(want, abs=1e-3)
        assert pieces[ua]["unit"] == pytest.approx(want, abs=1e-3)
        # equal elbow round ends in master px
        assert o[ua].widths["elbow"] * pieces[ua]["unit"] == pytest.approx(o[fa].widths["elbow"] * pieces[fa]["unit"],
                                                                          rel=1e-3)
        # the joints still land: shoulder and elbow on the master's
        W, H = (600, 900)
        assert np.linalg.norm(joints[ua] - np.array(ann.master.points[f"shoulder_{s}"]) * (W, H)) < 0.5
        assert np.linalg.norm(joints[fa] - np.array(ann.master.points[f"elbow_{s}"]) * (W, H)) < 0.5
    assert not [d for d in doubts if d["reason"] == "upperarm_too_wide"], doubts


@pytest.mark.slow
def test_upper_arm_never_widened_and_clamped(tmp_path):
    import rig_place
    ann = ra.load(make_character(tmp_path))
    o = _outs(ann)
    o["forearm_l"].widths["elbow"] *= 1.5                             # a forearm wider than the upper arm: no change
    o["upperarm_r"].widths["elbow"] *= 2.0                            # an upper arm twice the forearm: clamped
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    assert pieces["upperarm_l"]["unit"] == pytest.approx(1.0)
    lo = 1 - rig_place.WIDTH_FIT_MAX
    assert pieces["upperarm_r"]["unit"] == pytest.approx(lo)
    d = [d for d in doubts if d["reason"] == "upperarm_too_wide"]
    assert [x["part"] for x in d] == ["upperarm_r"], doubts
    assert d[0]["ratio"] == pytest.approx(38 / 80, abs=0.01) and d[0]["limit"] == rig_place.WIDTH_FIT_MAX


def test_variant_fit_ignores_the_narrowing():
    """T19: a raised sleeve is NOT narrowed with the rest upper arm (its bunched painted shape is intentional): it is
    scaled against the rest's un-narrowed width, across and along."""
    import rig_place

    class O:
        def __init__(self, name, pts, widths):
            self.name, self.points, self.widths, self.depths = name, pts, widths, {}

    class P:
        def __init__(self, role, variant, out):
            self.role, self.variant, self.outputs = role, variant, [out]

    class A:
        pass
    ann = A()
    ann.pieces = {"a": P("upperarm", None, O("upperarm_l", {"shoulder": (20, 10), "elbow": (20, 106)}, {"shoulder": 35.2})),
                  "b": P("upperarm", "raised", O("upperarm_l_raised", {"shoulder": (18, 9), "elbow": (18, 79)},
                                                 {"shoulder": 30.8}))}
    plain = rig_place.variant_fit(ann, "upperarm_l", "upperarm_l_raised", None, None, 1.0, 1.0)
    narrowed = rig_place.variant_fit(ann, "upperarm_l", "upperarm_l_raised", None, None, 0.75, 1.0, narrow=0.75)
    assert narrowed["sxy"][0] == pytest.approx(plain["sxy"][0])
    assert narrowed["sxy"][1] == pytest.approx(plain["sxy"][1])
    assert narrowed["turn"] == pytest.approx(plain["turn"], abs=0.02)


@pytest.mark.slow
def test_raised_sleeve_is_not_narrowed(tmp_path):
    root = tmp_path
    ann_path = make_character(root, pose_variants=True)
    out = _build(ann_path, root / "rig")
    skel = json.loads((out / "synth.json").read_text())
    skin = skel["skins"][0]["attachments"] if isinstance(skel["skins"], list) else skel["skins"]["default"]
    rest, raised = skin["upperarm_l"]["synth_upperarm_l"], skin["upperarm_l"]["synth_upperarm_l_raised"]
    ratio = 0.8 / 0.7                                                 # the pose sheet paints at 0.7 against 0.8
    report = json.loads((out / "report.json").read_text())
    factor = report["parts"]["upperarm_l"]["width_fit"]["factor"]
    assert factor == pytest.approx(38 / 40, abs=1e-3)                 # the rest upper arm is narrowed ...
    assert raised["scaleX"] == pytest.approx(rest["scaleX"] / factor * ratio, rel=0.01)   # ... the raised sleeve not


@pytest.mark.slow
def test_raised_sleeve_not_narrowed_on_the_guessed_path(tmp_path):
    """T19 fix: when variant_fit can't place a raised sleeve (no annotated widths) spine_rig guesses its joint and
    scale from the images; the rest's width fit is undone there too. A forearm elbow annotated at 0.7 x the upper
    arm's makes the fit big enough to see."""
    ann_path = make_character(tmp_path, pose_variants=True)
    ann = ra.load(ann_path)
    o = _outs(ann)
    for s in "lr":
        o[f"forearm_{s}"].widths["elbow"] = 0.7 * o[f"upperarm_{s}"].widths["elbow"]
        o[f"upperarm_{s}_raised"].widths = {}
    ra.save(ann)
    out = _build(ann_path, tmp_path / "rig")
    rep = json.loads((out / "report.json").read_text())
    assert rep["variants"]["synth_upperarm_l_raised"]["joint"] == "guessed"
    factor = rep["parts"]["upperarm_l"]["width_fit"]["factor"]
    assert factor == pytest.approx(0.7, abs=1e-3)
    skel = json.loads((out / "synth.json").read_text())
    skin = skel["skins"][0]["attachments"] if isinstance(skel["skins"], list) else skel["skins"]["default"]
    rest, raised = skin["upperarm_l"]["synth_upperarm_l"], skin["upperarm_l"]["synth_upperarm_l_raised"]
    ratio = rep["variants"]["synth_upperarm_l_raised"]["scale_vs_rest"]
    assert raised["scaleX"] == pytest.approx(rest["scaleX"] / factor * ratio, rel=0.01)


# ------------------------------------------------------------------ 3. forearm trimmed under a glove's cuff

FUR, CUFF = (120, 80, 40), (240, 200, 160)
C_FOREARM = (235, 185, 140)                                            # synth_character.C["forearm"]


def _furry_forearm(ann):
    """forearm_l past its wrist: a sleeve-coloured cuff (rows wrist+1..+5, the cuff's rounded bottom) and below it fur
    tufts (rows +6..+17). Returns (cuff box, tuft box) as (x0, x1, y0, y1)."""
    o = _outs(ann)["forearm_l"]
    f = ann.path.parent / o.file
    a = np.asarray(Image.open(f).convert("RGBA")).copy()
    wx, wy = o.points["wrist"]
    y = int(round(wy))
    need = y + 20 - a.shape[0]
    if need > 0:                                                      # make room below the wrist
        a = np.concatenate([a, np.zeros((need, a.shape[1], 4), np.uint8)], 0)
    cuff = (int(wx - 13), int(wx + 13), y + 1, y + 6)
    tufts = (int(wx - 10), int(wx + 10), y + 6, y + 18)
    a[cuff[2]:cuff[3], cuff[0]:cuff[1]] = CUFF + (255,)
    a[tufts[2]:tufts[3], tufts[0]:tufts[1]] = FUR + (255,)
    Image.fromarray(a, "RGBA").save(f)
    return cuff, tufts


def _furry_hands(ann):
    """The rest hands get a fur cuff at their wrist (as the moose's glove): opaque pixels down to 8 px past it."""
    for s in "lr":
        o = _outs(ann)[f"hand_{s}"]
        f = ann.path.parent / o.file
        a = np.asarray(Image.open(f).convert("RGBA")).copy()
        top = int(o.points["wrist"][1]) + 8
        sel = a[:top, :, 3] > 0
        a[:top, :, :3][sel] = FUR
        Image.fromarray(a, "RGBA").save(f)


def _solid_alpha(ann, o):
    import spine_rig
    return np.asarray(spine_rig.solidify(Image.open(ann.path.parent / o.file), spine_rig.TRUST_ALPHA_ANNOTATED))[..., 3]


def test_trim_beyond_wrist_unit():
    import rig_place
    a = np.zeros((40, 20, 4), np.uint8)
    a[..., 3] = 255
    img = Image.fromarray(a, "RGBA")
    out, inf = rig_place.trim_beyond(img, (10.0, 20.0), (0.0, 1.0), 0.0)
    al = np.asarray(out)[..., 3]
    assert (al[:19] == 255).all()                                     # proximal side kept (beyond the 2 px feather)
    assert (al[21:] == 0).all()                                       # distal side gone
    assert 0 < al[19, 0] < 255 and 0 < al[20, 0] < 255                 # the 2 px feather
    assert inf["trimmed_px"] == int((al == 0).sum()) and inf["trimmed_px"] >= 19 * 20
    out2, inf2 = rig_place.trim_beyond(img, (10.0, 20.0), (0.0, 1.0), 4.0)    # the line moves 4 px toward the elbow
    assert (np.asarray(out2)[..., 3][17:] == 0).all() and inf2["trimmed_px"] > inf["trimmed_px"]


@pytest.mark.slow
@pytest.mark.parametrize("layer", ["over_forearm", "under_forearm", None])
def test_forearm_trimmed_under_the_glove(tmp_path, layer):
    """Past the wrist rim only what is coloured like the glove (its cuff's fur) goes: the sleeve's own cuff stays.
    T19: whatever the hand's layer (the moose's hand under_forearm: its cream cuff overlaps the glove's fur band)."""
    ann = ra.load(make_character(tmp_path))
    cuff, tufts = _furry_forearm(ann)
    _furry_hands(ann)
    ann.master.layers = {"hand": layer} if layer else {}
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    o = _outs(ann)["forearm_l"]
    out = np.asarray(pieces["forearm_l"]["img"]).astype(int)
    al = out[..., 3]
    x0, x1, y0, y1 = tufts
    assert (al[y0 + 1:y1, x0:x1] == 0).all()                          # the tufts are gone
    c0, c1, d0, d1 = cuff
    assert (al[d0:d1 - 2, c0:c1] == 255).all()                        # the cuff past the rim stays (no straight chop)
    raw = _solid_alpha(ann, o)
    keep = int(o.points["wrist"][1]) - 3
    assert (al[:keep] == raw[:keep]).all()                            # the sleeve before the rim is untouched
    gone = al[y0 + 1:y1, x0:x1] == 0                                  # no fur colour left in the transparent pixels
    assert np.abs(out[y0 + 1:y1, x0:x1, :3][gone] - np.array(FUR)).sum(1).min() > 60
    t = info["forearm_l"]["wrist_trim"]
    assert t["trimmed_px"] >= (x1 - x0) * (y1 - y0 - 1) and t["kept_px"] >= (c1 - c0) * (d1 - d0 - 2)
    assert "wrist_trim" in info["forearm_r"]


def test_trim_keeps_sleeve_coloured_pixels_unit():
    import rig_place
    a = np.zeros((40, 40, 4), np.uint8)
    a[..., 3] = 255
    a[..., :3] = (230, 220, 200)                                      # sleeve (its cuff runs on past the line)
    a[24:, 13:27, :3] = (90, 60, 30)                                  # fur past the line
    a[32:34, 19:21, :3] = (230, 220, 200)                             # a light highlight on the fur: not the sleeve
    out, inf = rig_place.trim_beyond(Image.fromarray(a, "RGBA"), (20.0, 20.0), (0.0, 1.0), 0.0,
                                     hand_cols=np.array([[90, 60, 30], [40, 30, 25]]),
                                     sleeve_cols=np.array([[230, 220, 200]]))
    o = np.asarray(out).astype(int)
    assert (o[22:, 0:11, 3] == 255).all() and (o[22:, 29:, 3] == 255).all()  # sleeve-coloured: kept past the line
    assert (o[26:, 14:26, 3] == 0).all()                                      # fur and its highlight: gone
    assert 0 < o[30, 12, 3] < 255 or 0 < o[30, 13, 3] < 255                   # the colour cut is feathered
    assert (np.abs(o[26:, 14:26, :3] - (90, 60, 30)).sum(-1) > 100).all()    # bled: no fur RGB under alpha 0
    assert inf["kept_px"] > 0


@pytest.mark.slow
def test_trim_is_a_noop_for_a_sleeve_coloured_cuff(tmp_path):
    """T19: the trim always runs, but a forearm whose cuff is sleeve-coloured (the fox's) keeps every pixel."""
    ann = ra.load(make_character(tmp_path))
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    for s in "lr":
        o = _outs(ann)[f"forearm_{s}"]
        assert (np.asarray(pieces[f"forearm_{s}"]["img"])[..., 3] == _solid_alpha(ann, o)).all()
        t = info[f"forearm_{s}"]["wrist_trim"]
        assert t["trimmed_px"] == 0 and t["feathered_px"] == 0


def test_wrist_trim_helper_for_forearms_with_a_hand(tmp_path):
    """spine_rig trims forearm variants with the same helper: by output name, whatever the hand's layer; not an upper
    arm, and not a forearm without a rest hand on its side to take the colours from (colour-aware only)."""
    import rig_place
    ann = ra.load(make_character(tmp_path))
    o = _outs(ann)
    img = Image.open(ann.path.parent / o["forearm_l"].file).convert("RGBA")
    for layer in (None, "under_forearm", "over_forearm"):
        ann.master.layers = {"hand": layer} if layer else {}
        got, inf = rig_place.wrist_trim(ann, "forearm_l", img)
        assert inf is not None and inf["trimmed_px"] >= 0
    assert rig_place.wrist_trim(ann, "upperarm_l", img)[1] is None
    for p in ann.pieces.values():
        if p.role == "hand" and p.variant in (None, "rest"):
            p.outputs = [x for x in p.outputs if x.name != "hand_l"]
    got, inf = rig_place.wrist_trim(ann, "forearm_l", img)              # T19 fix: the skip is recorded
    assert inf == {"skipped": "no_rest_hand"} and got is img


def test_distinct_hand_colours_unit():
    """T19 fix: hand colours within WRIST_SHARED_RGB of any sleeve colour can't tell the two apart: dropped."""
    import rig_place
    hand = np.array([[90, 60, 30], [232, 222, 205], [40, 30, 25]], float)
    sleeve = np.array([[230, 220, 200], [120, 120, 200]], float)
    got = rig_place.distinct_hand_colours(hand, sleeve)
    assert got.tolist() == [[90, 60, 30], [40, 30, 25]]
    assert len(rig_place.distinct_hand_colours(hand[1:2], sleeve)) == 0
    assert rig_place.WRIST_SHARED_RGB == 40


def test_trim_skipped_when_glove_and_sleeve_share_colours_unit():
    """Past the line the 'fur' is the sleeve's own colour: nothing can be told apart, so nothing is trimmed."""
    import rig_place
    a = np.zeros((40, 40, 4), np.uint8)
    a[..., 3] = 255
    a[..., :3] = (230, 220, 200)
    img = Image.fromarray(a, "RGBA")
    got, inf = rig_place.trim_wrist_colours(img, (20.0, 20.0), (0.0, -1.0), 0.0,
                                            np.array([[228, 218, 205]], float), np.array([[230, 220, 200]], float))
    assert inf == {"skipped": "ambiguous_colours"} and got is img


@pytest.mark.slow
def test_shared_colours_skip_the_trim_with_a_doubt(tmp_path):
    """A glove painted in the sleeve's colours near its wrist: the trim is skipped (the forearm is drawn whole) and the
    build carries a wrist_trim_ambiguous doubt; parts.forearm_l.wrist_trim records the skip."""
    ann = ra.load(make_character(tmp_path))
    _furry_forearm(ann)
    o = _outs(ann)["hand_l"]
    f = ann.path.parent / o.file
    h = np.asarray(Image.open(f).convert("RGBA")).copy()
    h[..., :3][h[..., 3] > 0] = C_FOREARM                               # the glove in the sleeve's colour
    Image.fromarray(h, "RGBA").save(f)
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    assert info["forearm_l"]["wrist_trim"] == {"skipped": "ambiguous_colours"}
    assert (np.asarray(pieces["forearm_l"]["img"])[..., 3] == _solid_alpha(ann, _outs(ann)["forearm_l"])).all()
    assert [d for d in doubts if d["reason"] == "wrist_trim_ambiguous"] == [
        {"part": "forearm_l", "reason": "wrist_trim_ambiguous"}]
    assert "skipped" not in info["forearm_r"]["wrist_trim"]


# ------------------------------------------------------------------ 4. hand variants along the hand bone

def _tilted_rest_hand(root):
    """A rest hand whose wrist -> fingertip leans off image-down (as the moose's glove is painted): its fingertip
    annotation moved sideways, so the rest hand turns to the master and its image-down no longer runs along it."""
    ann_path = make_character(root)
    ann = ra.load(ann_path)
    for p in ann.pieces.values():
        if p.role == "hand" and p.variant in (None, "rest"):
            for o in p.outputs:
                x, y = o.points["fingertip"]
                o.points["fingertip"] = (x + 14.0, y)
    ra.save(ann)
    return ann_path


def _deg(v):
    return math.degrees(math.atan2(v[1], v[0]))


def _wrap(d):
    return (d + 180) % 360 - 180


@pytest.mark.slow
def test_hand_variants_run_along_the_hand_bone(tmp_path):
    import spine_qa
    out = _build(_tilted_rest_hand(tmp_path), tmp_path / "rig")
    res = json.loads((out / "annotations.resolved.json").read_text())
    rig = spine_qa.Rig(out / "synth.json")

    def down(slot, att, world):
        """World direction of the attachment's image-down at its wrist, and the wrist's world position."""
        M = rig.att_matrix(slot, att, world)
        w = res["attachments"][att]["points"]["wrist"]
        p0, p1 = spine_qa._xy(M, w), spine_qa._xy(M, (w[0], w[1] + 10.0))
        return p1 - p0, p0

    checked = 0
    for s in "lr":
        slot = f"hand_{s}"
        for v in ("open", "fist", "point", "thumbsup", "grip"):
            att = f"synth_hand_{s}_{v}"
            world, _ = rig.pose(None, 0.0, {slot: att})
            a_, _, c_, _, x_, y_ = world[slot]
            d, p = down(slot, att, world)
            assert abs(_wrap(_deg(d) - math.degrees(math.atan2(c_, a_)))) < 1.0, (att, _deg(d))
            assert np.linalg.norm(p - np.array([x_, y_])) < 0.01 * res["body_height_units"], att
            checked += 1
    assert checked == 10
    # the rest hand still matches the master at setup: its wrist -> fingertip runs along the master's
    world, _ = rig.pose(None, 0.0)
    mp = res["master_points_units"]
    for s in "lr":
        att = f"synth_hand_{s}"
        M = rig.att_matrix(f"hand_{s}", att, world)
        pts = res["attachments"][att]["points"]
        got = spine_qa._xy(M, pts["fingertip"]) - spine_qa._xy(M, pts["wrist"])
        want = np.array(mp[f"fingertip_{s}"]) - np.array(mp[f"wrist_{s}"])
        assert abs(_wrap(_deg(got) - _deg(want))) < 1.0, s
    # cheer_jump: the fists continue the forearms at the hold
    world, active = rig.pose("cheer_jump", 0.95)
    for s in "lr":
        assert active[f"hand_{s}"] == f"synth_hand_{s}_fist"
        d, _ = down(f"hand_{s}", f"synth_hand_{s}_fist", world)
        a_, _, c_, *_ = world[f"forearm_{s}"]
        assert abs(_wrap(_deg(d) - math.degrees(math.atan2(c_, a_)))) < 1.0, s


@pytest.mark.slow
@pytest.mark.parametrize("layer", ["over_forearm", "under_forearm"])
def test_sockets_judge_a_trimmed_forearm_at_its_moved_rim(tmp_path, layer):
    """The forearm trimmed under the glove: its wrist rim now lies WRIST_TRIM_INSET x depth inside, recorded as the
    attachment's rim_inset; spine_qa's socket spill is measured past that rim, not past the old one.
    T19: under either hand layer, whenever the trim removed something."""
    import rig_place
    import spine_qa
    ann_path = make_character(tmp_path)
    ann = ra.load(ann_path)
    _furry_forearm(ann)
    _furry_hands(ann)
    ann.master.layers = {"hand": layer}
    ra.save(ann)
    out = _build(ann_path, tmp_path / "rig")
    res = json.loads((out / "annotations.resolved.json").read_text())
    o = _outs(ann)["forearm_l"]
    assert res["attachments"]["synth_forearm_l"]["rim_inset"] == {
        "wrist": pytest.approx(rig_place.WRIST_TRIM_INSET * o.depths["wrist"], abs=0.01)}
    assert "rim_inset" not in res["attachments"]["synth_upperarm_l"]
    rig = spine_qa.Rig(out / "synth.json")
    canvas = spine_qa.Canvas(rig, height_px=spine_qa.CHECK_H)
    key = "synth_hand_l/synth_forearm_l"
    got = spine_qa.check_sockets(rig, canvas, res, [])["sockets"][key]["spill"]
    assert got <= spine_qa.SOCKET_SPILL
    assert "rim_inset" not in res["attachments"]["synth_forearm_r"]   # no fur there: nothing trimmed, rim kept
    res["attachments"]["synth_forearm_l"].pop("rim_inset")   # the old rim (no inset): the trimmed strip is spill
    old = spine_qa.check_sockets(rig, canvas, res, [])["sockets"][key]["spill"]
    assert old > got, (old, got)


@pytest.mark.slow
def test_no_rim_inset_when_the_trim_removed_nothing(tmp_path):
    """T19: a forearm the trim left whole (a sleeve-coloured cuff) keeps its rim where it was: no rim_inset, so QA
    judges its socket exactly as before."""
    out = _build(make_character(tmp_path), tmp_path / "rig")
    res = json.loads((out / "annotations.resolved.json").read_text())
    rep = json.loads((out / "report.json").read_text())
    for s in "lr":
        assert rep["parts"][f"forearm_{s}"]["wrist_trim"]["trimmed_px"] == 0
        assert "rim_inset" not in res["attachments"][f"synth_forearm_{s}"]
