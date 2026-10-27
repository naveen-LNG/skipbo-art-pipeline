"""Shared-pipeline fixes from the 2026-10-16 cast (rabbit, red panda, bear), each worked around locally at the time:
1. a foot variant scaled against an ankle width measured unlike its rest's (the bear's 3.17x tiptoe clog), and the
   spine_qa variant_size check that fails such a variant even when it closes its joint;
2. the global scale cross-checked against the torso's width and the head's (rabbit: a low torso waist point shrank
   the rig silently to IoU 0.64), with a scale_disagree doubt;
3. spine_qa --contract's keyable check (pale fur keyed out as holes against the grey background);
4. one-piece trousers: master.layers leg: in_hips composites the cuffed legs under the hips (rig_trousers);
5. leg-less feet under the hips get a hidden shaft rising under the cuff, rest and tiptoe alike (rig_shaft: the red
   panda's make_boots.py, the bear's ankle stubs), so walk and run no longer pull the boots out of the trousers."""
import json
import math
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

import rig_annotations as ra
import rig_place
import rig_shaft
import rig_trousers
import spine_qa
import spine_rig
from conftest import ROOT, SCRIPTS
from synth_character import BG, POSE_SCALE, SCALE, make_character

CAST = ROOT / "experiments" / "2026-10-16-cast"


def _build(ann_path, out):
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(ann_path.parent / "master.png"),
           "--annotations", str(ann_path), "--name", "synth", "--out", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return r.stdout


def _skin(skel):
    return skel["skins"][0]["attachments"] if isinstance(skel["skins"], list) else skel["skins"]["default"]


# ------------------------------------------------------------------ 1. foot variants: sizing and the QA size check

class _Pt:
    def __init__(self, snap):
        self.snap = snap


class _Out:
    def __init__(self, name, pts, widths):
        self.name, self.points, self.widths, self.depths = name, pts, widths, {}


class _Piece:
    def __init__(self, role, variant, out, snap):
        self.role, self.variant, self.outputs = role, variant, [out]
        self.points = {"ankle": _Pt(snap)}


class _Ann:
    pass


def _clog(w, h):
    """A clog-like blob: an ellipse filling w x h."""
    yy, xx = np.mgrid[0:h, 0:w]
    a = (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2 <= 1).astype(np.uint8) * 255
    return Image.fromarray(np.dstack([np.full((h, w, 3), 120, np.uint8), a]), "RGBA")


def _foot_ann(w_rest, w_var, snaps=("failed", "ok")):
    ann = _Ann()
    ann.pieces = {"a": _Piece("foot", None, _Out("clog_l", {"ankle": (100, 20)}, {"ankle": w_rest}), snaps[0]),
                  "b": _Piece("foot", "tiptoe", _Out("clog_l_tiptoe", {"ankle": (150, 30)}, {"ankle": w_var}), snaps[1])}
    return ann


def test_foot_variant_widths_measured_unlike_fall_back_to_area():
    """The bear, round 4: the rest clog's ankle snap failed (cross width 362 px), the tiptoe's snapped to its 137 px
    rim; width ratio 2.64 against an area ratio of 0.625 (the tiptoe painted 1.6x bigger) gave scaleX 3.17."""
    rest, var = _clog(400, 200), _clog(640, 320)
    fit = rig_place.variant_fit(_foot_ann(362.0, 137.0), "clog_l", "clog_l_tiptoe", rest, var, 1.2, 1.2)
    area = math.sqrt((np.asarray(rest)[..., 3] > 127).sum() / (np.asarray(var)[..., 3] > 127).sum())
    assert fit["ratio"] == pytest.approx(area, rel=1e-6)
    assert fit["sxy"][0] == pytest.approx(1.2 * area, rel=1e-6)
    assert fit["scale_check"] == {"from": "area", "width_ratio": round(362 / 137, 3), "area_ratio": round(area, 3),
                                  "snaps": ["failed", "ok"]}


def test_foot_variant_widths_that_agree_are_kept():
    rest, var = _clog(400, 200), _clog(640, 320)
    fit = rig_place.variant_fit(_foot_ann(100.0, 150.0, ("ok", "ok")), "clog_l", "clog_l_tiptoe", rest, var, 1.2, 1.2)
    assert fit["ratio"] == pytest.approx(100 / 150)
    assert "scale_check" not in fit


@pytest.fixture(scope="module")
def mis_measured_rig(tmp_path_factory):
    """The synthetic character with its tiptoe boots' ankle widths at 0.4x (measured unlike the rest's)."""
    root = tmp_path_factory.mktemp("tiptoe")
    p = make_character(root, pose_variants=True)
    ann = ra.load(p)
    for piece in ann.pieces.values():
        if piece.variant == "tiptoe":
            for o in piece.outputs:
                o.widths["ankle"] *= 0.4
    ra.save(ann)
    out = root / "rig"
    log = _build(p, out)
    return out, log


@pytest.mark.slow
def test_mis_measured_tiptoe_scaled_by_area_with_a_doubt(mis_measured_rig):
    out, log = mis_measured_rig
    rep = json.loads((out / "report.json").read_text())
    for s in "lr":
        v = rep["variants"][f"synth_boot_{s}_tiptoe"]
        assert v["scale_check"]["from"] == "area"
        # the pose sheet paints at 0.7 against 0.8; the tiptoe is the rest foot narrowed 0.75 and drawn out 1.3
        assert v["scale_vs_rest"] == pytest.approx(SCALE / POSE_SCALE / math.sqrt(0.75 * 1.3), rel=0.05)
        assert any(d.get("reason") == "variant_scale_disagree" and d["part"] == f"boot_{s}_tiptoe" for d in rep["doubts"])
    assert "variant_scale_disagree" not in log or "scaled by area" in log


@pytest.mark.slow
def test_variant_size_check(mis_measured_rig, tmp_path):
    """Correctly sized variants pass variant_size; a tiptoe blown up as the bear's was (scaleX 3.17 where ~1.2 was
    right) fails it, although it still covers its joint."""
    out, _ = mis_measured_rig
    rig = spine_qa.Rig(out / "synth.json")
    st = spine_qa.check_structure(rig, spine_qa.Canvas(rig, spine_qa.CHECK_H))
    assert st["variant_size"] == {}, st["variant_size"]
    skel = json.loads((out / "synth.json").read_text())
    att = _skin(skel)["boot_l"]["synth_boot_l_tiptoe"]
    att["scaleX"] *= 2.6
    att["scaleY"] *= 2.6
    if "synth_boot_l_tiptoe_back" in _skin(skel).get("boot_l_back", {}):
        b = _skin(skel)["boot_l_back"]["synth_boot_l_tiptoe_back"]
        b["scaleX"], b["scaleY"] = att["scaleX"], att["scaleY"]
    big = out / "synth_big.json"
    big.write_text(json.dumps(skel))
    rig2 = spine_qa.Rig(big)
    st2 = spine_qa.check_structure(rig2, spine_qa.Canvas(rig2, spine_qa.CHECK_H))
    assert not st2["pass"]
    assert st2["variant_size"]["synth_boot_l_tiptoe"]["size_vs_rest"] > spine_qa.VARIANT_SIZE
    assert "synth_boot_r_tiptoe" not in st2["variant_size"]


# ------------------------------------------------------------------ 2. the global scale's cross-checks

class _Frame:
    k = 1.0


def _outs(ann):
    return {o.name: o for p in ann.pieces.values() for o in p.outputs}


def test_scale_estimates_agree_on_the_synthetic_character(tmp_path):
    ann = ra.load(make_character(tmp_path))
    r = rig_place.scale_estimates(ann, _Frame())
    assert r["used"] == "torso_length" and r["doubt"] is None
    assert set(r["estimates"]) == {"torso_length", "torso_width", "head_width"}
    for v in r["estimates"].values():                  # the sheet paints at 0.8 of the master's scale
        assert v == pytest.approx(1 / SCALE, rel=0.05)
    assert rig_place.global_scale(ann, _Frame()) == pytest.approx(r["g"])


def test_low_torso_waist_point_is_outvoted(tmp_path):
    """The rabbit: the torso's waist annotated at the bib's hem, below the master's waist, made neck-to-waist 1.3x
    too long and shrank the whole rig. Torso width and head width agree with each other: they set the scale."""
    ann = ra.load(make_character(tmp_path))
    t = _outs(ann)["torso"]
    n, w = np.asarray(t.points["neck"], float), np.asarray(t.points["waist"], float)
    t.points["waist"] = tuple(n + 1.3 * (w - n))
    r = rig_place.scale_estimates(ann, _Frame())
    assert r["estimates"]["torso_length"] == pytest.approx(1 / SCALE / 1.3, rel=0.03)
    assert r["used"] == "others"
    assert r["g"] == pytest.approx(1 / SCALE, rel=0.05)
    assert r["doubt"]["reason"] == "scale_disagree" and "torso_length" in r["doubt"]["off_by"]


def test_one_disagreeing_estimate_is_a_doubt_only(tmp_path):
    """A head painted 0.7x on its own (or a torso painted wider for its height than the master, the bear) can't
    say which estimate is wrong: the torso's neck-to-waist stays, with a doubt."""
    ann = ra.load(make_character(tmp_path))
    h = _outs(ann)["head_base"]
    im = Image.open(ann.path.parent / h.file)
    small = im.resize((round(im.width * 0.7), round(im.height * 0.7)), Image.LANCZOS)
    small.save(tmp_path / "small_head.png")
    h.file = "small_head.png"
    h.points["neck"] = tuple(0.7 * np.asarray(h.points["neck"], float))
    r = rig_place.scale_estimates(ann, _Frame())
    assert r["used"] == "torso_length"
    assert r["g"] == pytest.approx(r["estimates"]["torso_length"], rel=1e-3)
    assert set(r["doubt"]["off_by"]) == {"head_width"}


def test_arms_touching_the_body_give_no_torso_width():
    """A run across the torso that reaches past an annotated shoulder-elbow-wrist line is an arm, not the torso."""
    m = np.zeros((100, 100), bool)
    m[20:80, 30:70] = True                                 # torso
    m[20:80, 70:80] = True                                 # an arm touching it
    arm = [np.array([72.0, 20.0]), np.array([75.0, 50.0]), np.array([76.0, 80.0])]
    assert rig_place._run_width(m, (50, 50), (0.0, 1.0)) == pytest.approx(50, abs=1)
    assert rig_place._run_width(m, (50, 50), (0.0, 1.0), [arm]) is None
    m[:, 70:74] = False                                    # a gap: the torso alone
    assert rig_place._run_width(m, (50, 50), (0.0, 1.0), [arm]) == pytest.approx(40, abs=1)


# ------------------------------------------------------------------ 3. contract: can the pipeline key this master?

def _master(patch_rgb):
    a = np.full((400, 300, 3), BG, np.uint8)
    a[60:380, 90:210] = (60, 90, 200)                      # body
    a[30:80, 110:190] = (230, 150, 90)                     # head
    a[150:230, 120:180] = patch_rgb                        # a patch inside the body (a white muzzle, a pale paw)
    return a


def test_keyable_fails_pale_fur_inside_the_figure():
    pale = np.array(BG) + 6                                # 0.04 from the background: under the 0.06 key
    rgb = _master(pale).astype(np.float32) / 255
    dist = np.linalg.norm(rgb - np.array(BG) / 255, axis=2)
    assert spine_qa.key_holes(dist > 0.06, dist) > spine_qa.KEY_HOLES


def test_keyable_passes_real_background_enclosed_by_the_figure():
    """An arm loop (hand on the hip) encloses real background: flat, at the background's colour, not a hole."""
    rgb = _master(BG).astype(np.float32) / 255
    dist = np.linalg.norm(rgb - np.array(BG) / 255, axis=2)
    assert spine_qa.key_holes(dist > 0.06, dist) < 0.001


@pytest.mark.parametrize("name,keyable", [("rabbit_master_orig.png", False), ("rabbit_master.png", True)])
def test_contract_keyable_on_the_rabbit(name, keyable):
    """The rabbit's first master (pale fur, white muzzle on light grey) passed every contract check; the master
    with its background recoloured (make_master_bg.py) keys cleanly."""
    path = CAST / "rabbit" / name
    if not path.exists():
        pytest.skip(f"{path} not in this checkout")
    res = spine_qa.check_contract(path)
    assert res["keyable"] is keyable, res["key_holes_pct_of_silhouette"]


def test_contract_keyable_on_the_synthetic_master(tmp_path):
    make_character(tmp_path)
    res = spine_qa.check_contract(tmp_path / "master.png")
    assert res["keyable"] and res["key_holes_pct_of_silhouette"] < 0.1


# ------------------------------------------------------------------ 4. one-piece trousers (leg: in_hips)

def _trousers_character(root, **kw):
    """The synthetic character with master.layers leg: in_hips and the master's hip points at the trouser cuffs."""
    p = make_character(root, **kw)
    truth = json.loads((root / "truth.json").read_text())
    W, H = truth["master_size"]
    ann = ra.load(p)
    for s in "lr":
        hx, hy = truth["placed"][f"leg_{s}"]["hem"]
        ann.master.points[f"hip_{s}"] = (hx / W, hy / H)
    ann.master.layers = {"leg": "in_hips"}
    ra.save(ann)
    return p


def test_layers_leg_validated(tmp_path):
    p = make_character(tmp_path)
    d = json.loads(p.read_text())
    d["master"]["layers"] = {"leg": "in_hips"}
    p.write_text(json.dumps(d))
    ra.load(p)
    d["master"]["layers"] = {"leg": "merged"}
    p.write_text(json.dumps(d))
    with pytest.raises(ra.AnnotationError):
        ra.load(p)


def test_trousers_composite(tmp_path):
    ann = ra.load(_trousers_character(tmp_path))
    o = _outs(ann)
    legs = {s: (o[f"leg_{s}"].points["hip"], o[f"leg_{s}"].points["hem"], o[f"leg_{s}"].widths["hem"]) for s in "lr"}
    assert rig_place.has_legs(ann)
    info = rig_trousers.compose(ann, tmp_path / "rig")
    assert not rig_place.has_legs(ann)
    hips = _outs(ann)["hips"]
    img = np.asarray(Image.open(hips.file))[..., 3] > 127
    for s in "lr":
        hx, hy = hips.points[f"hip_{s}"]
        assert img[int(hy) - 3, int(hx)]                                   # leg cloth just above the cuff
        assert not img[min(img.shape[0] - 1, int(hy) + 6), int(hx)]        # nothing below it
        assert hips.widths[f"hip_{s}"] == pytest.approx(legs[s][2] * info["legs"][s]["narrow"])
        assert hy - hips.points["waist"][1] > legs[s][1][1] - legs[s][0][1]     # a whole leg below the waist
    assert "waist" in hips.points and img.shape[0] > Image.open(tmp_path / "body" / "synth_hips.png").height


def test_trousers_off_by_default(tmp_path):
    ann = ra.load(make_character(tmp_path))
    assert rig_trousers.compose(ann, tmp_path / "rig") is None and rig_place.has_legs(ann)


@pytest.mark.slow
def test_trousers_rig_is_leg_less(tmp_path):
    p = _trousers_character(tmp_path)
    out = tmp_path / "rig"
    log = _build(p, out)
    assert "one-piece trousers" in log
    skel = json.loads((out / "synth.json").read_text())
    bones = {b["name"] for b in skel["bones"]}
    assert not {"leg_l", "leg_r"} & bones and "hips" in bones
    slots = [s["name"] for s in skel["slots"]]
    assert slots.index("boot_l") < slots.index("hips")                     # the feet under the cuffs
    rig = spine_qa.Rig(out / "synth.json")
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    (out / "qa").mkdir(exist_ok=True)
    assert spine_qa.check_setup(rig, canvas, tmp_path / "master.png", out / "qa")["silhouette_iou"] >= spine_qa.SETUP_IOU
    lm = spine_qa.check_landmarks(rig, json.loads((out / "annotations.resolved.json").read_text()))
    assert lm["pass"], lm


# ------------------------------------------------------------------ 5. leg-less feet: a hidden shaft under the cuff

def test_shaft_wanted_only_leg_less_under_the_hips(tmp_path):
    ann = ra.load(make_character(tmp_path))
    assert not rig_shaft.wanted(ann, True, True)                      # legs: the leg goes into the boot
    assert rig_shaft.wanted(ann, False, True)
    assert not rig_shaft.wanted(ann, False, False)                    # no hips to hide it under
    ann.master.layers = {"foot": "over_hips"}                         # boots over the trouser legs ride with the hips
    assert not rig_shaft.wanted(ann, False, True)


def test_shaft_in_the_foots_colours_and_kept_where_hidden():
    a = np.zeros((60, 40, 4), np.uint8)
    a[10:60, 8:32] = (120, 70, 30, 255)                               # the boot
    a[6:14, 8:32] = (40, 20, 10, 255)                                 # its dark opening (the painted inside)
    foot = Image.fromarray(a, "RGBA")
    rows = 30
    layer = rig_shaft.layer(foot, (20.0, 10.0), 20.0, 8.0, rows)
    assert layer.shape[:2] == (90, 40)
    assert np.allclose(layer[5, 20, :3], (120, 70, 30), atol=2)       # the boot's colour, not the inside's dark
    hidden = np.zeros((90, 40), bool)
    hidden[:, :20] = True                                             # the hips cover the left half only
    out = np.asarray(rig_shaft.compose(foot, layer, rows, hidden))
    assert out[5, 15, 3] == 255 and out[5, 25, 3] == 0                # kept under the hips, dropped beside them
    solid = a[..., 3] == 255
    assert (out[rows:][solid] == a[solid]).all()                      # the foot itself lies over the shaft, unchanged


@pytest.mark.slow
def test_leg_less_feet_stay_in_the_trousers(tmp_path):
    """test_trousers_rig_is_leg_less's rig (with tiptoe boots) used to show detached / unstitched boots in walk and
    run: the boot was only as tall as the master's visible boot. With the hidden shaft both pass, the setup pose is
    unchanged and the tiptoe fits like its rest boot."""
    p = _trousers_character(tmp_path, pose_variants=True)
    out = tmp_path / "rig"
    _build(p, out)
    rep = json.loads((out / "report.json").read_text())
    for s in "lr":
        assert rep["parts"][f"boot_{s}"]["shaft"]["kept_px"] > 0
        assert rep["variants"][f"synth_boot_{s}_tiptoe"]["shaft"]["rows"] > 0
    assert not [d for d in rep["doubts"] if d["part"].startswith("boot")]    # the cross-check judges the painted boot
    rig = spine_qa.Rig(out / "synth.json")
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    (out / "qa").mkdir(exist_ok=True)
    assert spine_qa.check_setup(rig, canvas, tmp_path / "master.png", out / "qa")["silhouette_iou"] >= spine_qa.SETUP_IOU
    lm = spine_qa.check_landmarks(rig, json.loads((out / "annotations.resolved.json").read_text()))
    assert lm["pass"], lm
    st = spine_qa.check_structure(rig, canvas)
    assert not {k: v for k, v in st["variant_misfit"].items() if "boot" in k}, st["variant_misfit"]
    assert not {k: v for k, v in st["variant_size"].items() if "boot" in k}, st["variant_size"]
    for anim in ("walk", "run"):
        r = spine_qa.check_anim(rig, canvas, anim, 30, out / "qa")
        assert r["pass"], (anim, {k: v for k, v in r.items() if v and k not in ("pass", "frames", "duration")})
