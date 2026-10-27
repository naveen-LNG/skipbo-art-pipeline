"""The rig_annotations.py command line: propose, check, confirm (subprocess on the synthetic character)."""
import json
import subprocess
import sys

from PIL import Image

import rig_annotations as ra
from conftest import SCRIPTS
from synth_character import make_character, BODY_RUN, HANDS_RUN

CLI = str(SCRIPTS / "rig_annotations.py")


def run(*args):
    return subprocess.run([sys.executable, CLI, *map(str, args)], capture_output=True, text=True)


EXTRA_RUN = "synth-extra-parts"


def add_extra_run(root):
    """A fresh split run (two copies of a raw hand piece) that has no annotations yet."""
    d = root / "runs" / EXTRA_RUN
    d.mkdir(parents=True)
    src = sorted((root / "runs" / HANDS_RUN).glob("*_00.png"))[0]
    for i in (0, 1):
        Image.open(src).save(d / f"synth_{i:02d}.png")
    return d


def last_json(proc):
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_help_works():
    p = run("--help")
    assert p.returncode == 0 and "propose" in p.stdout and "confirm" in p.stdout


def test_propose_adds_pieces(tmp_path):
    make_character(tmp_path)
    new = tmp_path / "fresh.json"
    p = run("propose", tmp_path / "runs" / HANDS_RUN, "--annotations", new, "--character", "synth")
    assert p.returncode == 0, p.stderr
    ann = ra.load(new)
    assert ann.master.status == "proposed" and ann.master.image == "master.png"
    assert ann.master.points == {} and ann.master.hands == {} and ann.master.layers == {}
    keys = sorted(ann.pieces)
    assert keys and all(k.startswith(HANDS_RUN + "/") for k in keys)
    for piece in ann.pieces.values():
        assert (piece.role, piece.status, piece.confidence) == ("", "proposed", 0)
        assert set(piece.points) == {"top", "bottom"}
        assert all(pt.kind == "round_end" for pt in piece.points.values())
        assert piece.points["top"].at[1] <= piece.points["bottom"].at[1]
    sheet = tmp_path / "annotations" / f"{HANDS_RUN}_numbered.png"
    assert sheet.exists() and str(sheet) in p.stdout
    assert Image.open(sheet).width > 0


def test_propose_keeps_pieces_with_a_role(tmp_path):
    path = make_character(tmp_path)
    before = ra.to_json(ra.load(path))["pieces"]
    p = run("propose", tmp_path / "runs" / BODY_RUN, "--annotations", path)
    assert p.returncode == 0, p.stderr
    assert ra.to_json(ra.load(path))["pieces"] == before


def test_propose_needs_character_for_new_file(tmp_path):
    make_character(tmp_path)
    p = run("propose", tmp_path / "runs" / HANDS_RUN, "--annotations", tmp_path / "fresh.json")
    assert p.returncode == 2 and "--character" in p.stderr


def test_check_writes_overlays_and_doubts(tmp_path):
    path = make_character(tmp_path)
    p = run("check", path)
    assert p.returncode == 0, p.stderr
    out = tmp_path / "annotations"
    for f in ("master_overlay.png", f"{BODY_RUN}_overlay.png", f"{HANDS_RUN}_overlay.png",
              f"{BODY_RUN}_worn.png", f"{HANDS_RUN}_worn.png"):
        assert (out / f).exists(), f
        assert str(out / f) in p.stdout
    res = last_json(p)
    assert set(res) == {"doubts", "worn", "unconfirmed", "snap_failed"}
    assert isinstance(res["doubts"], list) and res["unconfirmed"] == []
    assert res["worn"] and all(v in (True, False, None) for v in res["worn"].values())


def test_check_only_one_sheet(tmp_path):
    path = make_character(tmp_path)
    p = run("check", path, "--sheet", HANDS_RUN)
    assert p.returncode == 0, p.stderr
    out = tmp_path / "annotations"
    assert (out / f"{HANDS_RUN}_overlay.png").exists() and not (out / f"{BODY_RUN}_overlay.png").exists()


def test_check_skips_drafts_and_lists_them(tmp_path):
    path = make_character(tmp_path)
    p = run("propose", add_extra_run(tmp_path), "--annotations", path)
    assert p.returncode == 0, p.stderr
    p = run("check", path)
    assert p.returncode == 0, p.stderr
    res = last_json(p)
    drafts = [k for k in res["unconfirmed"] if k.startswith(EXTRA_RUN + "/")]
    assert drafts and "master" not in res["unconfirmed"]


def test_check_exit_2_on_invalid(tmp_path):
    path = make_character(tmp_path)
    raw = json.loads(path.read_text())
    raw["pieces"][next(iter(raw["pieces"]))]["role"] = "wing"
    path.write_text(json.dumps(raw))
    p = run("check", path)
    assert p.returncode == 2
    assert "wing" in p.stdout + p.stderr


def test_confirm_sheet(tmp_path):
    path = make_character(tmp_path)
    ann = ra.load(path)
    for piece in ann.pieces.values():
        piece.status = "proposed"
    ann.master.status = "proposed"
    ra.save(ann)
    p = run("confirm", path, "--sheet", HANDS_RUN)
    assert p.returncode == 0, p.stderr
    ann = ra.load(path)
    for k, piece in ann.pieces.items():
        assert piece.status == ("confirmed" if k.startswith(HANDS_RUN + "/") else "proposed")
    p = run("confirm", path, "--master")
    assert p.returncode == 0, p.stderr
    assert ra.load(path).master.status == "confirmed"


def test_confirm_refuses_roleless_piece(tmp_path):
    path = make_character(tmp_path)
    p = run("propose", add_extra_run(tmp_path), "--annotations", path)
    assert p.returncode == 0
    before = path.read_text()
    p = run("confirm", path, "--sheet", EXTRA_RUN)
    assert p.returncode == 2 and "role" in p.stderr
    assert path.read_text() == before


def test_confirm_refuses_incomplete_master(tmp_path):
    path = make_character(tmp_path)
    ann = ra.load(path)
    ann.master.status = "proposed"
    del ann.master.points["neck"]
    ra.save(ann)
    before = path.read_text()
    p = run("confirm", path, "--master")
    assert p.returncode == 2 and "neck" in p.stderr
    assert path.read_text() == before


# --- T10b: spare pieces the rig does not use ---

def test_confirm_sheet_leaves_ignored_pieces(tmp_path):
    path = make_character(tmp_path)
    p = run("propose", add_extra_run(tmp_path), "--annotations", path)
    assert p.returncode == 0, p.stderr
    ann = ra.load(path)
    keys = sorted(k for k in ann.pieces if k.startswith(EXTRA_RUN + "/"))
    for k in keys:                                  # still role-less: confirm must not refuse over them
        ann.pieces[k].status = "ignored"
    ra.save(ann)
    p = run("confirm", path, "--sheet", EXTRA_RUN)
    assert p.returncode == 0, p.stderr
    ann = ra.load(path)
    assert [ann.pieces[k].status for k in keys] == ["ignored", "ignored"]


def test_check_ignored_not_pending_or_doubted_and_drafts_not_doubted(tmp_path):
    path = make_character(tmp_path)
    assert run("propose", add_extra_run(tmp_path), "--annotations", path).returncode == 0
    ann = ra.load(path)
    k0, k1 = sorted(k for k in ann.pieces if k.startswith(EXTRA_RUN + "/"))
    ann.pieces[k0].status = "ignored"
    ra.save(ann)
    p = run("check", path)
    assert p.returncode == 0, p.stderr
    res = last_json(p)
    assert res["unconfirmed"] == [k1]                      # the draft is listed, the ignored piece is not
    assert not any(d["key"] in (k0, k1) for d in res["doubts"])     # a role-less draft is no doubt
    assert not any(s.startswith(EXTRA_RUN + "/") for s in res["snap_failed"])   # nor are its draft snaps listed
    assert (tmp_path / "annotations" / f"{EXTRA_RUN}_overlay.png").exists()


def test_check_lists_failed_snaps_without_asking_about_them(tmp_path):
    path = make_character(tmp_path)
    ann = ra.load(path)
    fist = next(k for k, p in ann.pieces.items() if p.variant == "thumbsup")   # its wrist snap drifts too far
    p = run("check", path)
    assert p.returncode == 0, p.stderr
    res = last_json(p)
    assert f"{fist}:wrist" in res["snap_failed"]
    assert res["snap_failed"] == sorted(res["snap_failed"])
    assert not any(d["key"] == fist for d in res["doubts"])           # every fixture piece is confident
    p = run("check", path, "--sheet", BODY_RUN)
    assert not any(s.startswith(HANDS_RUN + "/") for s in last_json(p)["snap_failed"])
