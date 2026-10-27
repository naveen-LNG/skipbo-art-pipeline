"""Real painted hands (the committed fox hands split run): the thumb rule must decide them clearly.

On real art the thumb tip sits far down the hand, so wrist -> thumb_tip mostly follows the hand's axis;
only its component across that axis says which side the thumb is on (T3b).

The fox's point hand shows the BACK of the hand (T17b): anatomy fixes its mirror, and a back-facing point hand can
only show its thumb up by pointing ACROSS the body (pointing outward, the thumb would hang down)."""
import shutil
from pathlib import Path

import pytest

import rig_annotations as ra
import rig_hands as rh
import rig_overlay as ro

ROOT = Path(__file__).resolve().parent.parent
RUN = "fox-hands-parts"
SRC = ROOT / "experiments" / "2026-10-11-part-variants" / "fox" / "runs" / RUN
POINT = f"{RUN}/05"


def _fox_point(tmp_path, facing="back"):
    if not SRC.is_dir():
        pytest.skip("the committed fox hands run is missing")
    shutil.copytree(SRC, tmp_path / "runs" / RUN)
    shutil.copy(next(SRC.glob("*_05.png")), tmp_path / "master.png")      # snap_all needs some master image
    pts = {"wrist": (0.50, 0.03), "thumb_tip": (0.95, 0.58), "fingertip": (0.55, 0.97)}
    piece = ra.Piece(key=POINT, role="hand", name="hand", variant="point", side="either",
                     points={n: ra.Point(n, at, ra.default_kind("hand", n)) for n, at in pts.items()},
                     facing=facing, status="confirmed", confidence=0.9)
    hands = {s: {"thumb_side": "medial", "facing": "back"} for s in "lr"}
    ann = ra.Annotations(version=ra.VERSION, character="fox", path=tmp_path / "annotations.json",
                         master=ra.Master(image="master.png", points={}, hands=hands, layers={}, status="proposed"),
                         pieces={POINT: piece})
    assert ra.validate(ann) == []
    ra.save(ann)
    ann = ra.load(ann.path)
    ra.snap_all(ann)
    return ann


def _worn_thumb(o):
    return rh.thumb_vector(o.points["wrist"], o.points["thumb_tip"], o.points.get("fingertip"))


def test_real_back_point_hand_points_across(tmp_path):
    ann = _fox_point(tmp_path, "back")
    notes = ra.normalise(ann)
    got = {o.name: o.mirrored for o in ann.pieces[POINT].outputs}
    # painted thumb on image +x; the back of a left hand has it on -x, the right hand's on +x
    assert got == {"hand_l_point": True, "hand_r_point": False}
    assert not notes, notes
    assert not any("unclear" in d["reason"] or "facing" in d["reason"] for d in ra.doubts(ann))
    for o in ann.pieces[POINT].outputs:
        side = o.name.split("_")[1]
        mirror, margin = ra._hand_rule(ann, ann.pieces[POINT], side, o.points)
        assert margin > 0.8, (o.name, margin)                   # the thumb runs clearly sideways
        h = rh.hold_pose("point", _worn_thumb(o), side)
        assert h["pose"] == "across" and h["ok"] is True, (o.name, h)
        assert h["errors"]["outward"] > 135                       # pointing outward its thumb would hang down


def test_real_palm_point_hand_points_outward(tmp_path):
    ann = _fox_point(tmp_path, "palm")
    ann.master.hands = {s: {"thumb_side": "lateral", "facing": "palm"} for s in "lr"}
    ra.normalise(ann)
    got = {o.name: o.mirrored for o in ann.pieces[POINT].outputs}
    assert got == {"hand_l_point": False, "hand_r_point": True}
    for o in ann.pieces[POINT].outputs:
        assert rh.hold_pose("point", _worn_thumb(o), o.name.split("_")[1])["pose"] == "outward", o.name


def test_real_point_hand_without_facing_is_a_doubt(tmp_path):
    ann = _fox_point(tmp_path, None)
    notes = ra.normalise(ann)
    got = {o.name: o.mirrored for o in ann.pieces[POINT].outputs}
    assert got == {"hand_l_point": False, "hand_r_point": True}          # the legacy thumb-target rule
    assert any("facing missing" in n for n in notes), notes
    assert [d for d in ra.doubts(ann) if d["key"] == POINT and "facing missing" in d["reason"]]


def test_real_point_hand_worn_verdict(tmp_path):
    ann = _fox_point(tmp_path, "back")
    ra.normalise(ann)
    _, verdicts = ro.render_worn_strip(ann, RUN, tmp_path / "worn.png")
    assert dict(verdicts) == {"hand_l_point": True, "hand_r_point": True}
    piece = ann.pieces[POINT]
    for o in piece.outputs:                                  # drawn at the pose the gesture will use, side labelled
        _, lines, ok, _ = ro._worn_item(ann, piece, o)
        assert ok is True and "across" in " ".join(lines) and "back" in " ".join(lines), lines
