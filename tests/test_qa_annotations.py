"""spine_qa's annotation checks (thumbs, sockets, landmarks), active when rig/annotations.resolved.json exists."""
import json
import shutil
import subprocess
import sys

import pytest

import spine_qa
from conftest import ROOT, SCRIPTS
from synth_character import make_character

FOX = ROOT / "experiments" / "2026-10-11-part-variants" / "fox" / "rig" / "fox.json"


def _copy_rig(src_json, dst_dir):
    """A copy of a rig's json and resolved file whose images are the original's (symlinked)."""
    dst_dir.mkdir(parents=True)
    shutil.copy(src_json, dst_dir / src_json.name)
    res = src_json.parent / "annotations.resolved.json"
    if res.exists():
        shutil.copy(res, dst_dir / res.name)
    (dst_dir / "images").symlink_to(src_json.parent / "images")
    return dst_dir / src_json.name


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    root = tmp_path_factory.mktemp("qa_synth")
    ann = make_character(root, pose_variants=True)
    out = root / "rig"
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(root / "master.png"),
           "--annotations", str(ann), "--name", "synth", "--out", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return out / "synth.json"


def _load(path):
    rig = spine_qa.Rig(path)
    res = json.loads((path.parent / "annotations.resolved.json").read_text())
    return rig, res


def test_constants():
    assert (spine_qa.SOCKET_SPILL, spine_qa.LANDMARK_DRIFT) == (0.03, 0.01)


@pytest.mark.slow
def test_thumbs_pass_synthetic(synth):
    rig, res = _load(synth)
    out = spine_qa.check_thumbs(rig, res)
    assert out["pass"] is True, out
    assert set(out["thumbs"]) == {"point", "thumbs_up", "hold_card", "wave", "cheer_jump"}, out
    json.dumps(out)


@pytest.mark.slow
def test_thumbs_fail_when_mirror_flipped(synth):
    rig, res = _load(synth)
    for a in res["attachments"].values():
        p = a["points"]
        if "thumb_tip" in p:
            p["thumb_tip"][0] = 2 * p["wrist"][0] - p["thumb_tip"][0]      # flip the thumb's dx about the wrist
    out = spine_qa.check_thumbs(rig, res)
    assert out["pass"] is False
    assert all(e > 90 for e in out["thumbs"].values()), out


@pytest.mark.slow
def test_thumb_on_the_axis_is_unchecked(synth):
    rig, res = _load(synth)
    p = res["attachments"]["synth_hand_l_point"]["points"]
    p["thumb_tip"] = list(p["fingertip"])                              # on the hand's axis: no side
    out = spine_qa.check_thumbs(rig, res)
    assert "point" not in out["thumbs"] and "point" in out["unchecked"], out
    assert out["pass"] is True


@pytest.mark.slow
def test_sockets_pass_synthetic(synth):
    rig, res = _load(synth)
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    out = spine_qa.check_sockets(rig, canvas, res, list(rig.data["animations"]))
    assert out["pass"] is True, out
    assert set(out["sockets"]) == ({f"synth_leg_{s}/{p}" for s in "lr" for p in (f"synth_boot_{s}", "synth_hips")}
                                   | {f"synth_hand_{s}/synth_forearm_{s}" for s in "lr"})
    for v in out["sockets"].values():
        assert v["spill"] <= spine_qa.SOCKET_SPILL and v["off"] <= 1.0, out
    json.dumps(out)


@pytest.mark.slow
def test_socket_fail_when_leg_moved(synth, tmp_path):
    path = _copy_rig(synth, tmp_path / "rig")
    data = json.loads(path.read_text())
    data["skins"][0]["attachments"]["leg_l"]["synth_leg_l"]["x"] += 20
    path.write_text(json.dumps(data))
    rig, res = _load(path)
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    out = spine_qa.check_sockets(rig, canvas, res, ["idle"])
    assert out["pass"] is False, out
    bad = {k for k, v in out["sockets"].items() if v["spill"] > spine_qa.SOCKET_SPILL or v["off"] > 1.0}
    assert bad and all(k.startswith("synth_leg_l/") for k in bad), out


@pytest.mark.slow
def test_socket_spill_when_leg_slides_sideways(synth, tmp_path):
    """Moved across the boot, the leg's hem shows beside it below the rim."""
    path = _copy_rig(synth, tmp_path / "rig")
    data = json.loads(path.read_text())
    data["skins"][0]["attachments"]["leg_l"]["synth_leg_l"]["y"] += 25
    path.write_text(json.dumps(data))
    rig, res = _load(path)
    out = spine_qa.check_sockets(rig, spine_qa.Canvas(rig, spine_qa.CHECK_H), res, [])
    assert out["sockets"]["synth_leg_l/synth_boot_l"]["spill"] > spine_qa.SOCKET_SPILL, out
    assert out["pass"] is False


@pytest.mark.slow
def test_landmarks_pass_synthetic(synth):
    rig, res = _load(synth)
    out = spine_qa.check_landmarks(rig, res)
    assert out["pass"] is True, out
    assert set(out["landmarks"]) == set(res["point_bones"])
    json.dumps(out)


@pytest.mark.slow
def test_landmarks_fail_when_master_point_moves(synth):
    rig, res = _load(synth)
    x, y = res["master_points_units"]["elbow_l"]
    res["master_points_units"]["elbow_l"] = [x + 0.03 * res["body_height_units"], y]
    out = spine_qa.check_landmarks(rig, res)
    assert out["pass"] is False and set(out["failed"]) == {"elbow_l"}, out


@pytest.mark.slow
def test_landmarks_allow_push_in(synth):
    """A pushed-in joint may sit its push-in depth (plus the drift) from its master point."""
    rig, res = _load(synth)
    x, y = res["master_points_units"]["hip_l"]
    res["master_points_units"]["hip_l"] = [x, y + 0.5 * res["push_in"]["hip_l"]]
    assert spine_qa.check_landmarks(rig, res)["pass"] is True
    res["push_in"]["hip_l"] = 0.0
    res["master_points_units"]["hip_l"] = [x, y + 0.02 * res["body_height_units"]]
    assert spine_qa.check_landmarks(rig, res)["pass"] is False


@pytest.mark.slow
def test_main_reports_annotation_checks(synth, tmp_path, monkeypatch):
    path = _copy_rig(synth, tmp_path / "rig")
    _stub_heavy_checks(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["spine_qa.py", str(path), "--anims", "idle"])
    spine_qa.main()
    report = json.loads((path.parent / "qa" / "report.json").read_text())
    assert {"thumbs", "sockets", "landmarks"} <= set(report)
    assert report["thumbs"]["pass"] and report["sockets"]["pass"] and report["landmarks"]["pass"], report


def _stub_heavy_checks(monkeypatch):
    monkeypatch.setattr(spine_qa, "check_structure", lambda rig, canvas: {"pass": True})
    monkeypatch.setattr(spine_qa, "check_seams", lambda rig, canvas, frames: {"pass": True})
    monkeypatch.setattr(spine_qa, "check_anim", lambda rig, canvas, anim, fps, outdir: {"pass": True})


@pytest.mark.skipif(not FOX.exists(), reason="the part-variants fox rig is not in this checkout")
def test_old_rig_unaffected(tmp_path, monkeypatch):
    assert not (FOX.parent / "annotations.resolved.json").exists()
    path = _copy_rig(FOX, tmp_path / "rig")
    _stub_heavy_checks(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["spine_qa.py", str(path), "--anims", "idle"])
    assert spine_qa.main() == 0
    report = json.loads((path.parent / "qa" / "report.json").read_text())
    assert not {"thumbs", "sockets", "landmarks"} & set(report), set(report)
