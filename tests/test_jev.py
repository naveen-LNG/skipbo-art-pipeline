"""The optional Jev review steps (jev_client, joint_crops, jev_facing, jev_hands, jev_qa, rig_annotations check --jev),
with the TypeSafe API mocked at urllib: no network, no key needed."""
import http.client
import io
import json
import subprocess
import sys
import urllib.error

import numpy as np
import pytest
from PIL import Image

import jev_client
import jev_facing
import jev_hands
import jev_qa
import joint_crops
import rig_annotations as ra
from conftest import ROOT, SCRIPTS
from synth_character import make_character, HANDS_RUN, HAND_FACING


# --- a fake Jev ---------------------------------------------------------------------------------------------------

def fake_answer(name, spec, overrides):
    """One answer of the shape Jev returns. overrides[name]: a float (noul / score), a choice key (P 0.9 to it) or a
    {choice: probability} dict; a callable gets the request's state and returns one of those."""
    v = overrides.get(name)
    if spec["type"] == "noul":
        return {"noul": 0.5 if v is None else v}
    if spec["type"] == "score":
        return {"score": 1.0 if v is None else v}
    keys = list(spec["criteria"])
    if isinstance(v, dict):
        probs = {k: v.get(k, 0.0) for k in keys}
    else:
        pick = v or keys[0]
        probs = {k: (0.9 if k == pick else 0.1 / (len(keys) - 1)) for k in keys}
    return {"choice": max(probs, key=probs.get), "probabilities": probs}


class FakeJev:
    def __init__(self, **overrides):
        self.overrides = overrides
        self.requests = []
        self.fail_first = 0

    def __call__(self, req, timeout=None):
        if self.fail_first:
            self.fail_first -= 1
            raise urllib.error.HTTPError(req.full_url, 429, "busy", {}, io.BytesIO(b"slow down"))
        body = json.loads(req.data)
        self.requests.append((req, body))
        ov = {k: (v(body["state"]) if callable(v) else v) for k, v in self.overrides.items()}
        ans = {n: fake_answer(n, s, ov) for n, s in body["questions"].items()}
        return io.BytesIO(json.dumps({"answers": ans, "usage": {"input_tokens": 100}, "model": body["model"]}).encode())


@pytest.fixture
def jev(monkeypatch):
    """Install a FakeJev (set its overrides in the test) and a key."""
    fake = FakeJev()
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(jev_client.urllib.request, "urlopen", fake)
    monkeypatch.setattr(jev_client.time, "sleep", lambda s: None)
    return fake


@pytest.fixture
def no_key(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(jev_client, "KEY_FILE", tmp_path / "missing.env")

    def refuse(*a, **k):
        raise AssertionError("no request may be sent without a key")
    monkeypatch.setattr(jev_client.urllib.request, "urlopen", refuse)


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    root = tmp_path_factory.mktemp("jev_synth")
    ann = make_character(root, pose_variants=True)
    out = root / "rig"
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(root / "master.png"),
           "--annotations", str(ann), "--name", "synth", "--out", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return out / "synth.json"


def png_bytes(colour):
    b = io.BytesIO()
    Image.new("RGB", (8, 8), colour).save(b, "PNG")
    return b.getvalue()


# --- client -------------------------------------------------------------------------------------------------------

def test_request_shape_retry_and_cache(jev, tmp_path):
    jev.fail_first = 1                                          # one 429, then an answer
    state = {"task": "t", "hand": "{hand}"}
    qs = {"up": {"type": "noul", "instructions": "Is `hand` up?", "criteria": {"true": "y", "false": "n"}}}
    jobs = [("a", state, qs, {"{hand}": png_bytes("red")}), ("b", state, qs, {"{hand}": png_bytes("blue")})]
    cache = tmp_path / "cache.jsonl"
    out = jev_client.run(jobs, cache=cache, workers=1, quiet=True)
    assert set(out) == {"a", "b"} and out["a"]["up"]["noul"] == 0.5
    req, body = jev.requests[0]
    assert req.get_header("Authorization") == "Bearer test-key"
    assert req.get_header("Typesafe-danger-zone-images") == "true"
    ref = body["state"]["hand"]
    assert ref.startswith("img-") and ref in body["assets"] and "{hand}" not in json.dumps(body)
    assert body["model"] == jev_client.MODEL
    n = len(jev.requests)
    again = jev_client.run(jobs, cache=cache, quiet=True)       # same pixels: answered from the cache
    assert again == out and len(jev.requests) == n
    jev_client.run([("c", state, qs, {"{hand}": png_bytes("green")})], cache=cache, quiet=True)
    assert len(jev.requests) == n + 1                           # new pixels: a new call


def test_dropped_connection_is_retried(jev, monkeypatch):
    calls = []

    def flaky(req, timeout=None):
        calls.append(1)
        if len(calls) < 3:
            raise http.client.RemoteDisconnected("Remote end closed connection without response")
        return jev(req, timeout)
    monkeypatch.setattr(jev_client.urllib.request, "urlopen", flaky)
    out = jev_client.run([("x", {"t": 1}, {"q": {"type": "noul", "instructions": "?"}}, {})], quiet=True)
    assert out["x"]["q"]["noul"] == 0.5 and len(calls) == 3


def test_a_failing_job_is_left_out(jev, monkeypatch, capsys):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"bad request"))
    monkeypatch.setattr(jev_client.urllib.request, "urlopen", boom)
    out = jev_client.run([("x", {"t": 1}, {}, {})], quiet=True)
    assert out == {} and "HTTP 400" in capsys.readouterr().err


def test_key_file(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    f = tmp_path / "typesafe.env"
    f.write_text("# TypeSafe\nOTHER=1\nTYPESAFE_API_KEY=abc123\n")
    monkeypatch.setattr(jev_client, "KEY_FILE", f)
    assert jev_client.api_key() == "abc123" and jev_client.available()
    monkeypatch.setenv("TYPESAFE_API_KEY", "from-env")
    assert jev_client.api_key() == "from-env"


# --- palm / back --------------------------------------------------------------------------------------------------

def cues(palm, back, curl):
    a = {k: {"noul": palm if side == "palm" else back} for k, (side, _) in jev_facing.CUES.items()}
    a["curl"] = {"probabilities": {"toward": curl, "away": 1 - curl, "flat": 0.0}}
    return a


def test_palm_score_bands():
    assert jev_facing.band(jev_facing.palm_score(cues(0.8, 0.2, 0.7))) == "palm"
    assert jev_facing.band(jev_facing.palm_score(cues(0.2, 0.8, 0.2))) == "back"
    assert jev_facing.band(-0.12) == "ask"
    assert (jev_facing.band(-0.05), jev_facing.band(-0.20)) == ("palm", "back")     # the band edges are inclusive


def test_facing_doubt_only_on_a_confident_disagreement():
    back = {"score": -0.40, "facing": "back"}
    assert "Jev reads the back" in jev_facing.facing_doubt("palm", back)
    assert jev_facing.facing_doubt("back", back) is None
    assert jev_facing.facing_doubt("palm", {"score": -0.1, "facing": "ask"}) is None
    assert jev_facing.facing_doubt(None, back) is None           # facing missing is already a doubt of its own
    assert jev_facing.facing_doubt("palm", None) is None


def test_score_pieces_asks_16_turns(jev, tmp_path):
    piece = tmp_path / "hand_00.png"
    im = Image.new("RGBA", (60, 90), (0, 0, 0, 0))
    im.paste((200, 120, 60, 255), (10, 10, 50, 80))
    im.save(piece)
    jev.overrides.update(pads=0.9, creases=0.9, thumb_front=0.9, knuckles=0.1, smooth_top=0.1, curl="toward",
                         thumb_dir="up", finger_dir="down", gesture="fist")
    res = jev_facing.score_pieces({"h": piece})["h"]
    assert res["n"] == 16 and res["facing"] == "palm" and res["score"] > 0.5
    assert (res["thumb_dir"], res["finger_dir"], res["reads_as"]) == ("up", "down", "fist")
    sizes = {Image.open(io.BytesIO(__import__("base64").b64decode(next(iter(b["assets"].values()))["data_base64"]))).size
             for _, b in jev.requests}
    assert sizes == {(jev_hands.SIDE, jev_hands.SIDE)}           # every turn on grey at Jev's 448 px
    assert sum("thumb_dir" in b["questions"] for _, b in jev.requests) == 1    # directions only on the upright piece


# --- rig_annotations check --jev ----------------------------------------------------------------------------------

def check_json(capsys, *argv):
    assert ra.main(["check", *map(str, argv)]) == 0
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_check_jev_turns_a_confident_disagreement_into_a_doubt(jev, tmp_path, capsys):
    ann = make_character(tmp_path)
    jev.overrides.update(pads=0.1, creases=0.1, thumb_front=0.1, knuckles=0.9, smooth_top=0.9, curl="away")
    out = check_json(capsys, ann, "--sheet", HANDS_RUN, "--jev")
    palm = {k for k, p in ra.load(ann).pieces.items() if k.startswith(HANDS_RUN) and p.facing == "palm"}
    jev_ds = [d for d in out["doubts"] if "Jev reads" in d["reason"]]
    assert {d["key"] for d in jev_ds} == palm and palm       # every palm-annotated hand; the back-facing grip none
    assert all(d["options"] == ["palm", "back"] for d in jev_ds)
    assert all(v["facing"] == "back" for v in out["jev"].values()) and len(out["jev"]) == len(HAND_FACING) - 1
    n = len(jev.requests)
    out2 = check_json(capsys, ann, "--sheet", HANDS_RUN, "--jev")              # cached: no new call
    assert len(jev.requests) == n and out2["doubts"] == out["doubts"]
    assert (ann.parent / "annotations" / "jev_cache.jsonl").is_file()


def test_check_jev_agreeing_or_unsure_raises_nothing(jev, tmp_path, capsys):
    ann = make_character(tmp_path)
    jev.overrides.update(pads=0.5, creases=0.5, thumb_front=0.5, knuckles=0.6, smooth_top=0.6, curl="flat")   # -0.1
    out = check_json(capsys, ann, "--sheet", HANDS_RUN, "--jev")
    assert not [d for d in out["doubts"] if "Jev reads" in d["reason"]]
    assert {v["facing"] for v in out["jev"].values()} == {"ask"}


def test_check_without_key_skips_jev(no_key, tmp_path, capsys):
    ann = make_character(tmp_path)
    plain = check_json(capsys, ann, "--sheet", HANDS_RUN)
    out = check_json(capsys, ann, "--sheet", HANDS_RUN, "--jev")
    assert out["jev"] == {"skipped": "no TYPESAFE_API_KEY"}
    assert out["doubts"] == plain["doubts"] and "jev" not in plain


# --- hold rules ---------------------------------------------------------------------------------------------------

def hold_answers(finger, thumb, gesture, p_up):
    return {"finger_dir": {"probabilities": {finger: 1.0}}, "thumb_dir": {"probabilities": {thumb: 1.0}},
            "gesture": {"choice": max(gesture, key=gesture.get), "probabilities": gesture},
            "thumb_up": {"noul": p_up}}


def test_judge_hold_rules():
    point_l = {"anim": "point", "side": "l", "variant": "point", "facing": "palm"}
    ok = jev_hands.judge_hold(point_l, hold_answers("right", "up", {"point": 0.9}, 0.9))
    assert ok["issues"] == []
    down = jev_hands.judge_hold(point_l, hold_answers("right", "down", {"point": 0.9}, 0.1))
    assert "FAIL thumb not up" in down["issues"]
    across = jev_hands.judge_hold(point_l, hold_answers("left", "up", {"grip": 0.8, "point": 0.1}, 0.8))
    assert "WARN points across the body" in across["issues"] and any("reads as 'grip'" in i for i in across["issues"])
    card = {"anim": "hold_card", "side": "l", "variant": "grip", "facing": "back"}
    assert not any(i.startswith("FAIL") for i in
                   jev_hands.judge_hold(card, hold_answers("up", "down", {"grip": 0.9}, 0.0))["issues"])
    # a left hand pointing right (0°) with its palm showing has its thumb up (90°): the right hand's thumb is down
    mirrored = jev_hands.judge_hold(point_l, hold_answers("right", "down", {"point": 0.9}, 0.9))
    assert any("other hand" in i for i in mirrored["issues"])


def test_painted_side_matches_anatomy():
    assert jev_hands.painted_side(270, 0, "palm") == "l"      # joint end up, thumb on the image right
    assert jev_hands.painted_side(270, 0, "back") == "r"
    assert jev_hands.painted_side(270, 180, "palm") == "r"


def test_verdicts():
    v = jev_qa.joint_verdicts({"shoulder_l": 2.4, "elbow_l": 1.0, "neck": 0.5}, {"shoulder": [1.5, 2.0], "elbow": [1.2]})
    assert list(v) == ["shoulder_l", "elbow_l", "neck"]          # worst first
    assert v["shoulder_l"]["verdict"].startswith("WARN") and v["elbow_l"]["verdict"] == "within approved range"
    assert v["neck"]["verdict"] == "no reference"
    assert [jev_qa.pair_verdict(p) for p in (0.7, 0.5, 0.3)] == ["BETTER", "about the same", "WARN worse"]


# --- on a built rig -----------------------------------------------------------------------------------------------

@pytest.mark.slow
def test_joint_crops_align_render_and_master(synth, tmp_path):
    al = joint_crops.Aligned(synth)
    assert al.render.size == al.master.size
    boxes = al.boxes()
    assert {"shoulder_l", "elbow_r", "wrist_l", "neck", "ankle_r", "tail"} <= set(boxes)
    for j in ("shoulder_l", "neck", "ankle_r"):       # the same place in both: the crops look alike
        box, _ = boxes[j]
        m = np.asarray(joint_crops.cut(al.master, box), float)
        r = np.asarray(joint_crops.cut(al.render, box), float)
        assert np.abs(m - r).mean() < 25, j
    assert joint_crops.main([str(synth), "--out", str(tmp_path / "j"), "--sheet", str(tmp_path / "j.png")]) == 0
    assert (tmp_path / "j.png").is_file() and len((tmp_path / "j" / "labels.jsonl").read_text().splitlines()) == len(boxes)
    assert (tmp_path / "onion.png").is_file() and (tmp_path / "motion.png").is_file()      # the review sheets


@pytest.mark.slow
def test_jev_qa_fails_only_on_a_thumb_down_hold(synth, jev, tmp_path, capsys):
    jev.overrides.update(thumb_up=0.1, broken=1.0, defect=0.2)
    out = tmp_path / "qa"
    assert jev_qa.main([str(synth), "--ref", str(synth), "--out", str(out), "--frames-per-anim", "2"]) == 1
    rep = json.loads((out / "jev_qa.json").read_text())
    fails = {k for k, h in rep["holds"].items() if any(i.startswith("FAIL") for i in h["issues"])}
    assert {k.split("/")[0] for k in fails} == {"point", "thumbs_up"}       # hold_card / wave never FAIL
    assert all(v["verdict"] == "within approved range" for v in rep["joints"].values())
    assert (out / "joints.png").is_file() and "FAIL" in capsys.readouterr().out

    jev.overrides.update(thumb_up=0.9)
    assert jev_qa.main([str(synth), "--out", str(tmp_path / "qa2"), "--skip", "frames", "joints"]) == 0   # new cache


@pytest.mark.slow
def test_jev_qa_pairs_cancel_position_bias(synth, jev, tmp_path):
    jev.overrides.update(closer={"render_1": 0.7, "render_2": 0.3})    # always prefers the first image shown
    out = tmp_path / "qa"
    assert jev_qa.main([str(synth), "--prev", str(synth), "--out", str(out), "--skip", "frames", "holds"]) == 0
    pairs = json.loads((out / "jev_qa.json").read_text())["pairs"]
    assert pairs and {v["p_new_better"] for v in pairs.values()} == {0.5}
    assert {v["verdict"] for v in pairs.values()} == {"about the same"}


@pytest.mark.slow
def test_jev_qa_without_key_writes_the_joints_sheet_and_skips(synth, no_key, tmp_path, capsys):
    out = tmp_path / "qa"
    assert jev_qa.main([str(synth), "--ref", str(synth), "--out", str(out)]) == 0
    assert (out / "joints.png").is_file()
    assert json.loads((out / "jev_qa.json").read_text())["skipped"] == "no TYPESAFE_API_KEY"
    assert "SKIP" in capsys.readouterr().out
    assert jev_facing.main(["--piece", f"x={out / 'joints.png'}"]) == 0
