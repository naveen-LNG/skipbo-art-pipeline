"""Normalise: snap rough points, put each limb joint end up, choose each hand's mirror, write the outputs."""
import json
import math

import numpy as np
import pytest
from PIL import Image

import rig_annotations as ra
import rig_hands as rh
from conftest import ROOT
from synth_character import make_character

LIMBS = {"upperarm": ("shoulder", "elbow"), "forearm": ("elbow", "wrist"), "leg": ("hip", "hem"),
         "hand": ("wrist", "fingertip")}                       # feet are not turned
OUT_DIRS = ("body", "variants", "face-heads")


def _built(tmp_path, **kw):
    ann = ra.load(make_character(tmp_path, **kw))
    ra.snap_all(ann)
    return ann


def _outputs(ann):
    return {o.name: (p, o) for p in ann.pieces.values() for o in p.outputs}


def _files(root):
    return {str(f.relative_to(root)): f.read_bytes() for d in OUT_DIRS for f in sorted((root / d).glob("*.png"))}


def _alpha(path):
    return np.asarray(Image.open(path).convert("RGBA"))[..., 3] > 127


def _hand_key(ann, variant):
    return next(k for k, p in ann.pieces.items() if p.role == "hand" and p.variant == variant)


def test_snap_all_fills_points(tmp_path):
    ann = ra.load(make_character(tmp_path))
    master_at = dict(ann.master.points)
    ra.snap_all(ann)
    truth = json.loads((tmp_path / "truth.json").read_text())["pieces"]
    for key, p in ann.pieces.items():
        w, h = Image.open(ra.piece_image(ann, key)).size
        short = min(np.ptp(np.nonzero(_alpha(ra.piece_image(ann, key)))[i]) + 1 for i in (0, 1))
        for name, pt in p.points.items():
            if pt.kind == "point":
                assert pt.snap == "none" and pt.snapped is None
                continue
            if pt.kind == "round_end" or (p.role, name) in (("forearm", "wrist"), ("leg", "hem"), ("foot", "ankle"),
                                                            ("hips", "hip_l"), ("hips", "hip_r")):
                assert pt.snap == "ok", (key, name)
            if pt.snap == "failed":
                continue
            assert math.hypot((pt.snapped[0] - pt.at[0]) * w, (pt.snapped[1] - pt.at[1]) * h) <= 0.10 * short
            assert pt.width and pt.width > 0, (key, name)
            if pt.kind == "opening":
                assert pt.depth == pytest.approx(0.35 * pt.width)
            if pt.kind == "round_end":     # the fixture's round ends sit exactly on a circle's centre
                tx, ty = truth[key][name]
                assert math.hypot(pt.snapped[0] * w - tx, pt.snapped[1] * h - ty) < 2.0, (key, name)
    assert set(ann.master.snapped) == {f"{n}_{s}" for n in ("shoulder", "elbow", "wrist", "hip", "ankle")
                                       for s in "lr"}
    assert ann.master.points == master_at                     # the master's `at` is used as given


def test_snap_that_moves_too_far_is_rejected(tmp_path):
    ann = _built(tmp_path)
    truth = json.loads((tmp_path / "truth.json").read_text())["pieces"]
    key = _hand_key(ann, "thumbsup")
    pt = ann.pieces[key].points["wrist"]               # its rim snap drifts further than the guard allows
    assert pt.snap == "failed" and pt.snapped is None
    assert pt.width and pt.depth == pytest.approx(0.35 * pt.width)    # still measured at `at`
    assert not any(x["key"] == key for x in ra.doubts(ann))           # a confident piece: no question
    ra.normalise(ann)
    o = ann.pieces[key].outputs[0]
    w, h = Image.open(ra.piece_image(ann, key)).size
    x, y = pt.at[0] * w, pt.at[1] * h                              # the rough point is kept (painted upright)
    assert o.rotated == 0.0 and math.dist(o.points["wrist"], ((w - x) if o.mirrored else x, y)) < 1e-6
    assert math.dist((x, y), truth[key]["wrist"]) < 2
    boot = next(k for k, p in ann.pieces.items() if p.role == "foot" and p.side == "l")
    assert ann.pieces[boot].points["ankle"].snap == "ok"           # a good opening snap is kept


def test_feet_are_not_rotated(tmp_path):
    ann = _built(tmp_path)
    ra.normalise(ann)
    for key, p in ann.pieces.items():
        if p.role == "foot":
            o = p.outputs[0]
            assert o.rotated == 0.0
            assert Image.open(tmp_path / o.file).size == Image.open(ra.piece_image(ann, key)).size


def test_hand_without_fingertip_turns_by_quarter_turns(tmp_path):
    ann = ra.load(make_character(tmp_path))
    key = _hand_key(ann, "thumbsup")
    ra.snap_all(ann)
    ra.normalise(ann)
    assert ann.pieces[key].outputs[0].rotated == 0.0          # painted upright, thumb off to one side
    path = ra.piece_image(ann, key)
    img = Image.open(path)
    w, h = img.size
    img.transpose(Image.Transpose.ROTATE_90).save(path)        # wrist now at the side
    for pt in ann.pieces[key].points.values():
        x, y = pt.at[0] * w, pt.at[1] * h
        pt.at = (y / h, (w - x) / w)
    ra.snap_all(ann)
    ra.normalise(ann)
    for o in ann.pieces[key].outputs:
        assert abs(o.rotated) == 90.0
        assert o.points["wrist"][1] < o.points["thumb_tip"][1] + 20
        assert Image.open(tmp_path / o.file).size == (w, h)    # an exact quarter turn back


def test_snap_failure_keeps_rough_point(tmp_path):
    ann = ra.load(make_character(tmp_path))
    key = next(k for k, p in ann.pieces.items() if p.role == "upperarm")
    path = ra.piece_image(ann, key)
    Image.new("RGBA", Image.open(path).size, (0, 0, 0, 0)).save(path)   # nothing left to snap to
    at = ann.pieces[key].points["elbow"].at
    ra.snap_all(ann)
    pt = ann.pieces[key].points["elbow"]
    assert pt.snap == "failed" and pt.snapped is None and pt.width is None and pt.at == at
    assert not [x for x in ra.doubts(ann) if x["key"] == key]          # confident: a failed snap is no question
    ann.pieces[key].confidence = 0.5
    d = [x for x in ra.doubts(ann) if x["key"] == key]
    assert len(d) == 1                                                   # one question per piece
    assert "confidence" in d[0]["reason"] and "elbow" in d[0]["reason"] and "shoulder" in d[0]["reason"]
    assert d[0]["options"]


def test_normalise_rotates_joint_up(tmp_path):
    ann = _built(tmp_path)
    ra.normalise(ann)
    seen = set()
    for p in ann.pieces.values():
        if p.role not in LIMBS:
            continue
        prox, dist = LIMBS[p.role]
        for o in p.outputs:
            if dist not in o.points:
                continue
            seen.add(p.role)
            (px, py), (dx, dy) = o.points[prox], o.points[dist]
            assert py < dy, o.name
            assert abs(px - dx) < 3, (o.name, px, dx)
    assert seen == set(LIMBS)


def test_normalise_rotates_a_sideways_piece(tmp_path):
    ann = ra.load(make_character(tmp_path))
    key = next(k for k, p in ann.pieces.items() if p.role == "forearm" and p.side == "l")
    upright = ann.pieces[key].outputs[0].points                  # the fixture's own joint-end-up output
    path = ra.piece_image(ann, key)
    img = Image.open(path)
    w, h = img.size
    img.transpose(Image.Transpose.ROTATE_90).save(path)          # a quarter turn anticlockwise
    for pt in ann.pieces[key].points.values():                   # (x, y) -> (y, w - x), then normalised
        x, y = pt.at[0] * w, pt.at[1] * h
        pt.at = (y / h, (w - x) / w)
        pt.snapped, pt.snap = None, "none"
    ra.snap_all(ann)
    ra.normalise(ann)
    o = ann.pieces[key].outputs[0]
    assert abs(abs(o.rotated) - 90) < 3
    (ex, ey), (wx, wy) = o.points["elbow"], o.points["wrist"]
    assert ey < wy and abs(ex - wx) < 3
    for name in ("elbow", "wrist"):                              # turned back to where the fixture had it
        assert math.dist(o.points[name], upright[name]) < 3, name
    alpha = _alpha(tmp_path / o.file)
    assert alpha.shape[0] > alpha.shape[1]                        # tall again
    for x, y in ((ex, ey), (wx, wy)):
        assert alpha[int(y), int(x)]


def test_normalise_hand_mirror(tmp_path):
    ann = _built(tmp_path, hand_thumb_wrong=True)
    ra.normalise(ann)
    outs = _outputs(ann)
    assert outs["hand_l_point"][1].mirrored != outs["hand_l_open"][1].mirrored
    for v in ("open", "fist", "point", "thumbsup", "grip"):
        for side in "lr":
            o = outs[f"hand_{side}_{v}"][1]
            (wx, wy), (tx, ty) = o.points["wrist"], o.points["thumb_tip"]
            got = rh.thumb_world_deg((tx - wx, ty - wy), rh.side_deg(rh.HOLD_FOREARM_DEG[v], side))
            assert rh.ang_diff(got, rh.target_deg(rh.THUMB_TARGET[v], side)) < rh.THUMB_TOL, o.name


def test_normalise_reproduces_fixture_outputs(tmp_path):
    ann = ra.load(make_character(tmp_path))
    want = {o.name: (o.file, o.mirrored) for p in ann.pieces.values() for o in p.outputs}
    ra.snap_all(ann)
    ra.normalise(ann)
    got = {o.name: (o.file, o.mirrored) for p in ann.pieces.values() for o in p.outputs}
    assert got == want
    for p in ann.pieces.values():
        for o in p.outputs:
            for name, pt in p.points.items():
                if pt.snap == "ok":
                    assert o.widths[name] == pytest.approx(pt.width)
                if pt.snap == "ok" and pt.kind == "opening":
                    assert o.depths[name] == pytest.approx(pt.depth)


def test_normalise_is_idempotent(tmp_path):
    ann = _built(tmp_path)
    (tmp_path / "variants" / "synth_hand_l_wave.png").write_bytes(b"stale")
    (tmp_path / "variants" / "other_keep.png").write_bytes(b"not ours")
    ra.normalise(ann)
    first = _files(tmp_path)
    recorded = {o.file for p in ann.pieces.values() for o in p.outputs}
    assert set(first) == recorded | {"variants/other_keep.png"}
    ra.save(ann)
    again = ra.load(ann.path)
    ra.snap_all(again)
    ra.normalise(again)
    assert _files(tmp_path) == first
    assert ra.to_json(again) == ra.to_json(ann)


def test_points_follow_transform(tmp_path):
    ann = _built(tmp_path, hand_thumb_wrong=True)
    ra.normalise(ann)
    for name in ("hand_l_point", "hand_r_point", "hand_l", "hand_r_fist"):
        o = _outputs(ann)[name][1]
        alpha = _alpha(tmp_path / o.file)
        x, y = o.points["wrist"]
        assert alpha[int(y), int(x)], name
        assert y < 0.25 * alpha.shape[0], name


def test_draft_pieces_are_skipped(tmp_path):
    ann = _built(tmp_path)
    key = next(k for k, p in ann.pieces.items() if p.role == "tail")
    p = ann.pieces[key]
    p.role, p.status, p.outputs = "", "proposed", []
    ra.normalise(ann)
    assert p.outputs == []
    assert not (tmp_path / "body" / "synth_tail.png").exists()


def test_either_painted_as_writes_both_sides(tmp_path):
    ann = _built(tmp_path)
    key = next(k for k, p in ann.pieces.items() if p.role == "foot" and p.side == "l")
    other = next(k for k, p in ann.pieces.items() if p.role == "foot" and p.side == "r")
    del ann.pieces[other]
    ann.pieces[key].side, ann.pieces[key].painted_as = "either", "l"
    ra.normalise(ann)
    got = {o.name: o.mirrored for o in ann.pieces[key].outputs}
    assert got == {"boot_l": False, "boot_r": True}
    a = np.asarray(Image.open(tmp_path / "body" / "synth_boot_l.png"))
    b = np.asarray(Image.open(tmp_path / "body" / "synth_boot_r.png"))
    assert (a == b[:, ::-1]).all()


def test_doubts_low_confidence(tmp_path):
    ann = _built(tmp_path)
    ra.normalise(ann)
    before = ra.doubts(ann)
    # the thumbsup wrist fails to snap, but every piece is confident
    assert before == []
    key = next(k for k, p in ann.pieces.items() if p.role == "leg")
    ann.pieces[key].confidence = 0.5
    d = [x for x in ra.doubts(ann) if x not in before]
    assert [x["key"] for x in d] == [key] and "confidence" in d[0]["reason"]
    assert set(d[0]) == {"key", "reason", "options"} and len(d[0]["options"]) >= 2


def test_doubts_ambiguous_mirror(tmp_path):
    ann = _built(tmp_path)
    key = _hand_key(ann, "fist")
    p = ann.pieces[key]
    wx, wy = p.points["wrist"].snapped
    p.points["thumb_tip"].at = (wx, min(1.0, wy + 0.5))       # thumb straight along the hand: no side to pick
    msgs = ra.normalise(ann)
    assert any(key in m for m in msgs)
    d = [x for x in ra.doubts(ann) if x["key"] == key]
    assert d and d[0]["options"] == ["away from body", "towards body"]


def test_doubts_rest_hand_facing(tmp_path):
    ann = _built(tmp_path)
    key = _hand_key(ann, None)
    ann.pieces[key].facing = "back"
    ra.normalise(ann)
    d = [x for x in ra.doubts(ann) if x["key"] == key]
    assert d and "back" in d[0]["reason"] and d[0]["options"] == ["palm", "back"]


@pytest.mark.parametrize("deg", [20, 45, 71])
def test_snap_all_on_a_tilted_limb(tmp_path, deg):
    ann = ra.load(make_character(tmp_path))
    truth = json.loads((tmp_path / "truth.json").read_text())["pieces"]
    key = next(k for k, p in ann.pieces.items() if p.role == "upperarm")
    path = ra.piece_image(ann, key)
    img = Image.open(path).convert("RGBA")
    out = img.convert("RGBa").rotate(deg, resample=Image.BICUBIC, expand=True).convert("RGBA")
    out.save(path)
    true = {n: ra._turn(tuple(xy), deg, img.size, out.size) for n, xy in truth[key].items()}
    for n, pt in ann.pieces[key].points.items():
        pt.at = (true[n][0] / out.size[0], true[n][1] / out.size[1])    # the agent's point is exactly on the joint
    ra.snap_all(ann)
    for n, pt in ann.pieces[key].points.items():
        assert pt.snap == "ok", (deg, n)
        sx, sy = pt.snapped[0] * out.size[0], pt.snapped[1] * out.size[1]
        assert math.dist((sx, sy), true[n]) < 3.0, (deg, n)


def test_fist_leftover_tilt_after_quarter_turn_is_a_doubt(tmp_path):
    ann = _built(tmp_path)
    key = _hand_key(ann, "fist")
    p = ann.pieces[key]
    ra.normalise(ann)
    assert not any(x["key"] == key and "leftover tilt" in x["reason"] for x in ra.doubts(ann))
    # wrist-to-centroid about 45 degrees off a quarter turn: the nearest quarter leaves ~45 degrees
    img = Image.open(ra.piece_image(ann, key))
    w, h = img.size
    ys, xs = np.nonzero(np.asarray(img.convert("RGBA"))[..., 3] >= ra.ALPHA_MIN)
    cx, cy = xs.mean() + 0.5, ys.mean() + 0.5
    a = math.radians(45)
    p.points["wrist"].snap, p.points["wrist"].snapped = "none", None
    p.points["wrist"].at = ((cx - 40 * math.cos(a)) / w, (cy - 40 * math.sin(a)) / h)
    ra.normalise(ann)
    d = [x for x in ra.doubts(ann) if x["key"] == key and "leftover tilt" in x["reason"]]
    assert d and d[0]["options"] == ["looks right", "re-annotate wrist"]
    assert any(t in d[0]["reason"] for t in ("tilt 44", "tilt 45", "tilt 46")), d[0]["reason"]


def test_rest_hand_without_master_thumb_side_is_a_doubt(tmp_path):
    ann = _built(tmp_path)
    key = _hand_key(ann, None)
    for h in ann.master.hands.values():
        h.pop("thumb_side", None)
    notes = ra.normalise(ann)                       # with a facing, anatomy decides: the thumb_side is not needed
    assert not any(key in m for m in notes), notes
    assert not [x for x in ra.doubts(ann) if x["key"] == key]
    ann.pieces[key].facing = None                   # without one, the legacy rule needs the master's thumb_side
    notes = ra.normalise(ann)
    assert any(key in m for m in notes)
    d = [x for x in ra.doubts(ann) if x["key"] == key and "thumb_side" in x["reason"]]
    assert d and len(d[0]["options"]) >= 2
    assert [x for x in ra.doubts(ann) if x["key"] == key and "facing missing" in x["reason"]]


# --- T17b: anatomy fixes the mirror; gestures choose a pose the hand can do ---

def test_hand_mirror_follows_facing_not_the_gesture(tmp_path):
    ann = _built(tmp_path)
    ra.normalise(ann)
    outs = _outputs(ann)
    for v in ("point", "thumbsup", "grip", "open", "fist", None):
        for side in "lr":
            name = f"hand_{side}" + (f"_{v}" if v else "")
            p, o = outs[name]
            tv = rh.thumb_vector(o.points["wrist"], o.points["thumb_tip"], o.points.get("fingertip"))
            assert (tv[0] > 0) == (rh.anatomical_thumb_sign(side, p.facing) > 0), name   # worn on anatomy's side
    key = _hand_key(ann, "point")
    ann.pieces[key].facing = "back"                 # the same drawing called a back: both mirrors flip ...
    ra.normalise(ann)
    flipped = _outputs(ann)
    for side in "lr":
        assert flipped[f"hand_{side}_point"][1].mirrored != outs[f"hand_{side}_point"][1].mirrored
        o = flipped[f"hand_{side}_point"][1]        # ... and the point gesture goes across the body to show it
        tv = rh.thumb_vector(o.points["wrist"], o.points["thumb_tip"], o.points.get("fingertip"))
        assert rh.hold_pose("point", tv, side)["pose"] == "across"
    assert not [x for x in ra.doubts(ann) if x["key"] == key]


def test_grip_that_cannot_show_its_thumb_up_is_a_doubt(tmp_path):
    ann = _built(tmp_path)
    key = _hand_key(ann, "grip")
    ann.pieces[key].facing = "palm"                 # a palm-facing grip across the belly has its thumb down
    ra.normalise(ann)
    d = [x for x in ra.doubts(ann) if x["key"] == key]
    assert d and "hold_card" in d[0]["reason"] and d[0]["options"] == ["palm", "back"]


def test_rest_hand_facing_must_match_the_master(tmp_path):
    ann = _built(tmp_path)
    key = _hand_key(ann, None)
    ann.master.hands["l"].pop("facing")
    ra.normalise(ann)
    d = [x for x in ra.doubts(ann) if x["key"] == key]
    assert d and "no facing" in d[0]["reason"]


@pytest.mark.parametrize("bad", ["", "a/b", "a\\b", "x*", "x?", "x[1]", ".."])
def test_validate_rejects_unsafe_character_names(tmp_path, bad):
    ann = ra.load(make_character(tmp_path))
    assert ra.validate(ann) == []
    ann.character = bad
    errs = ra.validate(ann)
    assert any("character" in e for e in errs), (bad, errs)


# --- T10b: spare pieces the rig does not use ---

def test_ignored_pieces_are_not_normalised_or_doubted(tmp_path):
    ann = _built(tmp_path)
    ra.normalise(ann)
    key = next(k for k, p in ann.pieces.items() if p.role == "tail")
    p = ann.pieces[key]
    f = tmp_path / p.outputs[0].file
    assert f.exists()
    p.status, p.role, p.points, p.confidence = "ignored", "", {}, 0.1
    ra.normalise(ann)
    assert p.outputs == [] and not f.exists()
    assert not any(x["key"] == key for x in ra.doubts(ann))
    ra.snap_all(ann)                              # nothing to snap, no error
    assert p.points == {}


def test_ignored_piece_with_leftover_draft_points_is_left_alone(tmp_path):
    ann = _built(tmp_path)
    key = next(k for k, p in ann.pieces.items() if p.role == "tail")
    p = ann.pieces[key]
    p.status, p.role, p.name = "ignored", "wing", "wing"
    p.points = {"top": ra.Point("top", (0.5, 0.1), "round_end")}
    ra.snap_all(ann)
    ra.normalise(ann)
    assert p.points["top"].snap == "none" and p.outputs == []
    assert not any(x["key"] == key for x in ra.doubts(ann))


def test_rest_hand_missing_thumb_tip_says_so(tmp_path):
    ann = _built(tmp_path)
    key = _hand_key(ann, None)
    p = ann.pieces[key]
    p.status = "proposed"
    del p.points["thumb_tip"]
    notes = ra.normalise(ann)
    assert any(key in m for m in notes)
    d = [x for x in ra.doubts(ann) if x["key"] == key and "thumb" in x["reason"]]
    assert d and all("thumb_tip" in x["reason"] and "thumb_side" not in x["reason"] for x in d)
    assert d[0]["options"] == ["away from body", "towards body"]
    for h in ann.master.hands.values():            # the master's missing thumb_side is still named when it is the cause
        h.pop("thumb_side", None)
    p.facing = None                                # (only without a facing: with one, anatomy decides)
    p.points["thumb_tip"] = ra.Point("thumb_tip", (0.5, 0.5), "point")
    ra.normalise(ann)
    d = [x for x in ra.doubts(ann) if x["key"] == key and "thumb" in x["reason"] and "facing missing" not in x["reason"]]
    assert d and all("thumb_side" in x["reason"] and "thumb_tip" not in x["reason"] for x in d)


# --- T3b: failed snaps are facts, not questions; a failed round end still has a width ---

def test_failed_round_end_still_gets_a_width(tmp_path, monkeypatch):
    import rig_snap
    ann = ra.load(make_character(tmp_path))
    key = next(k for k, p in ann.pieces.items() if p.role == "upperarm" and p.side == "l")
    monkeypatch.setattr(rig_snap, "snap_round_end", lambda *a, **k: None)
    ra.snap_all(ann)
    p = ann.pieces[key]
    for name, want in (("shoulder", 44 * 0.8), ("elbow", 40 * 0.8)):    # the fixture's capsule end diameters
        pt = p.points[name]
        assert pt.snap == "failed" and pt.snapped is None
        assert pt.width == pytest.approx(want, abs=2.5), name
    ra.normalise(ann)
    o = p.outputs[0]
    assert o.widths["elbow"] == pytest.approx(p.points["elbow"].width)
    assert "elbow" not in o.depths
    ra.save(ann)
    assert ra.load(ann.path).pieces[key].points["elbow"].width == pytest.approx(p.points["elbow"].width, abs=0.01)


def test_cross_width_on_a_tilted_bar():
    import rig_snap
    a = np.zeros((200, 200), dtype=bool)
    yy, xx = np.mgrid[0:200, 0:200]
    d = np.array([math.cos(math.radians(30)), math.sin(math.radians(30))])
    rel = np.stack([xx - 100, yy - 100], -1)
    a[(np.abs(rel @ d) <= 80) & (np.abs(rel @ np.array([-d[1], d[0]])) <= 12)] = True   # 24 px wide, 30 deg tilt
    assert rig_snap.cross_width(a, (100 + 40 * d[0], 100 + 40 * d[1])) == pytest.approx(25, abs=2)
    off = (100 + 40 * d[0] - 5 * d[1], 100 + 40 * d[1] + 5 * d[0])      # off the centre line: same width
    assert rig_snap.cross_width(a, off) == pytest.approx(25, abs=2)
    assert rig_snap.cross_width(np.zeros((10, 10), dtype=bool), (5, 5)) is None
    past_end = (100 + 95 * d[0], 100 + 95 * d[1])                        # 15 px beyond the bar's end
    assert rig_snap.cross_width(a, past_end) == pytest.approx(25, abs=3)
    assert rig_snap.cross_width(a, past_end, axis=(d[0], d[1])) == pytest.approx(25, abs=3)
    assert rig_snap.cross_width(a, (100, 100), axis=(0.0, 0.0)) is None


def test_failed_opening_still_gets_a_width_and_depth(tmp_path):
    # a 60 x 200 bar; the ankle (opening) is marked 60 px inside the top rim, so the snap runs to the rim and
    # the displacement guard rejects it
    run = tmp_path / "runs" / "r"
    run.mkdir(parents=True)
    img = Image.new("RGBA", (100, 240), (0, 0, 0, 0))
    img.paste((200, 90, 40, 255), (20, 20, 80, 220))
    img.save(run / "x_00.png")
    img.save(tmp_path / "master.png")
    pts = {"ankle": ra.Point("ankle", (0.5, 80 / 240), "opening"), "ground": ra.Point("ground", (0.5, 0.9), "point")}
    piece = ra.Piece(key="r/00", role="foot", name="foot", variant=None, side="l", points=pts, facing=None,
                     status="confirmed", confidence=0.9)
    ann = ra.Annotations(version=ra.VERSION, character="bar", path=tmp_path / "annotations.json", pieces={"r/00": piece},
                         master=ra.Master(image="master.png", points={}, hands={}, layers={}, status="proposed"))
    ra.snap_all(ann)
    pt = piece.points["ankle"]
    assert pt.snap == "failed" and pt.snapped is None
    assert pt.width == pytest.approx(60, abs=2)                      # across the inward (downward) axis
    assert pt.depth == pytest.approx(0.35 * pt.width)
    ra.normalise(ann)
    o = piece.outputs[0]
    assert o.widths["ankle"] == pytest.approx(pt.width) and o.depths["ankle"] == pytest.approx(pt.depth)


def _one_piece(tmp_path, img, role, pts):
    """An annotations file with a single confirmed piece `img` of `role`; pts: name -> (x, y) pixels."""
    run = tmp_path / "runs" / "r"
    run.mkdir(parents=True, exist_ok=True)
    img.save(run / "x_00.png")
    img.save(tmp_path / "master.png")
    w, h = img.size
    points = {n: ra.Point(n, (x / w, y / h), ra.default_kind(role, n)) for n, (x, y) in pts.items()}
    piece = ra.Piece(key="r/00", role=role, name=role, variant=None, side="", points=points, facing=None,
                     status="confirmed", confidence=0.9)
    return ra.Annotations(version=ra.VERSION, character="x", path=tmp_path / "annotations.json",
                          pieces={"r/00": piece},
                          master=ra.Master(image="master.png", points={}, hands={}, layers={}, status="proposed"))


def _hips_shape():
    """A tall hips block with two leg tubes 120 px wide whose bottoms are rounded off, like painted shorts."""
    from PIL import ImageDraw
    img = Image.new("RGBA", (400, 480), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 379, 300], fill=(150, 90, 60, 255))
    for x0 in (40, 240):
        d.rectangle([x0, 290, x0 + 119, 420], fill=(150, 90, 60, 255))
        d.ellipse([x0, 380, x0 + 119, 460], fill=(150, 90, 60, 255))
    return img


@pytest.mark.parametrize("snaps", [True, False])
def test_hip_openings_measure_the_leg_tube(tmp_path, monkeypatch, snaps):
    import rig_snap
    if not snaps:                                    # the failed-snap fallback measures the same way
        monkeypatch.setattr(rig_snap, "snap_opening", lambda *a, **k: None)
    ann = _one_piece(tmp_path, _hips_shape(), "hips", {"waist": (200, 22), "hip_l": (300, 450), "hip_r": (100, 450)})
    ra.snap_all(ann)
    for n in ("hip_l", "hip_r"):
        pt = ann.pieces["r/00"].points[n]
        assert pt.snap == ("ok" if snaps else "failed"), n
        assert pt.width == pytest.approx(120, rel=0.05), (n, pt.width)
        assert pt.depth == pytest.approx(0.35 * pt.width)


def test_opening_inward_points_at_the_partner():
    pts = {"waist": (200, 20), "hip_l": (300, 420), "ground": (90, 100), "hip": (0, -50), "elbow": (30, 40),
           "fingertip": (0, 60)}
    # upright pieces have fixed axes, whatever their other points say
    assert ra.opening_inward("hips", "hip_l", pts["hip_l"], pts) == (0.0, -1.0)
    assert ra.opening_inward("hips", "hip_r", (0, 0), {}) == (0.0, -1.0)
    assert ra.opening_inward("foot", "ankle", (50, 0), pts) == (0.0, 1.0)            # not toward the toe-side ground
    # the rest point at their partner
    assert ra.opening_inward("leg", "hem", (0, 50), pts) == (0.0, -1.0)
    assert ra.opening_inward("forearm", "wrist", (0, 0), pts) == pytest.approx((0.6, 0.8))
    assert ra.opening_inward("hand", "wrist", (0, 0), pts) == (0.0, 1.0)
    assert ra.opening_inward("leg", "hem", (0, 0), {}) is None               # no hip: inward_axis instead
    assert ra.opening_inward("hand", "wrist", (0, 0), {}) is None            # no fingertip: the centroid
    assert ra.opening_inward("torso", "shoulder_l", (180, 50), pts) is None  # a plain point now
    openings = {k for k, v in ra.DEFAULT_KIND.items() if v == "opening"}
    assert set(ra.OPENING_PARTNER) | set(ra.FIXED_INWARD) == openings


def test_real_moose_hips_openings_match_the_visible_legs(tmp_path):
    src = sorted((ROOT / "experiments/2026-10-11-part-variants/moose/runs/moose-body-a-parts").glob("*_10.png"))
    if not src:
        pytest.skip("the committed moose body run is missing")
    img = Image.open(src[0]).convert("RGBA")
    w, h = img.size
    ann = _one_piece(tmp_path, img, "hips", {"waist": (0.50 * w, 0.15 * h), "hip_l": (0.79 * w, 0.95 * h),
                                             "hip_r": (0.21 * w, 0.95 * h)})
    ra.snap_all(ann)
    # the visible opening: each leg's widest horizontal run in the bottom 30% of the piece (below the crotch)
    a = np.asarray(img)[..., 3] >= ra.ALPHA_MIN
    visible = {"hip_r": 0, "hip_l": 0}
    for y in range(int(0.7 * h), h):
        xs = np.nonzero(a[y])[0]
        for run in np.split(xs, np.nonzero(np.diff(xs) > 1)[0] + 1):
            if len(run):
                n = "hip_l" if run.mean() > w / 2 else "hip_r"         # the character's left = picture right
                visible[n] = max(visible[n], len(run))
    for n in ("hip_l", "hip_r"):
        pt = ann.pieces["r/00"].points[n]
        assert pt.width == pytest.approx(visible[n], rel=0.15), (n, pt.snap, pt.width, visible[n])


def test_ignored_piece_with_known_role_and_real_points_is_not_normalised(tmp_path):
    ann = _built(tmp_path)
    key = next(k for k, p in ann.pieces.items() if p.role == "leg")
    p = ann.pieces[key]
    p.status = "ignored"
    assert ra.validate(ann) == []
    ra.normalise(ann)
    assert p.outputs == [] and set(p.points) == {"hip", "hem"}
