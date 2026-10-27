"""spine_rig.py --annotations: placing the rest parts from confirmed annotations (rig_place)."""
import json
import math
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

import rig_annotations as ra
import rig_hands as rh
from conftest import ROOT, SCRIPTS
from synth_character import BG, make_character


# ------------------------------------------------------------------ unit tests

def _xf(tp, size, p, fy=None):
    """World position of image point p under a two_point placement."""
    w, h = size
    fx, fy = tp["unit"], tp["unit_y"] if fy is None else fy
    vx, vy = (p[0] - w / 2) * fx, (p[1] - h / 2) * fy
    c, s = math.cos(math.radians(tp["angle"])), math.sin(math.radians(tp["angle"]))
    return np.array([tp["cx"] + c * vx + s * vy, tp["cy"] - s * vx + c * vy])


def test_two_point_hits_both_joints():
    import rig_place
    size = (80, 200)
    Jp, Jd = (40.0, 20.0), (52.0, 170.0)                 # a slightly slanted limb, joint end up
    g = 1.25
    L = math.hypot(Jd[0] - Jp[0], Jd[1] - Jp[1]) * g * 1.10   # a 10% stretch
    P = np.array([300.0, 400.0])
    d = np.array([math.cos(math.radians(-70)), math.sin(math.radians(70))])
    D = P + d * L
    tp = rig_place.two_point(size, Jp, Jd, tuple(P), tuple(D), g)
    assert tp["unit"] == pytest.approx(g)
    assert tp["stretch"] == pytest.approx(1.10, abs=1e-6)
    assert np.linalg.norm(_xf(tp, size, Jp) - P) < 0.5
    assert np.linalg.norm(_xf(tp, size, Jd) - D) < 0.5


def test_two_point_clamps_and_reports():
    import rig_place
    size = (60, 160)
    Jp, Jd = (30.0, 10.0), (30.0, 150.0)                 # vertical: unit_y is exactly g x the clamped ratio
    g = 0.8
    P = (100.0, 100.0)
    D = (100.0, 100.0 + 140 * g * 1.3)                    # 30% too long
    tp = rig_place.two_point(size, Jp, Jd, P, D, g)
    assert tp["unit"] == pytest.approx(g)
    assert tp["unit_y"] == pytest.approx(g * 1.15)
    assert tp["stretch"] == pytest.approx(1.3)
    assert np.linalg.norm(_xf(tp, size, Jp) - np.array(P)) < 0.5   # the proximal joint still lands


def test_push_in():
    import rig_place
    assert rig_place.push_in((10.0, 20.0), (0.0, -1.0), 9.0) == pytest.approx((10.0, 17.0))


def test_narrow_clamps():
    import rig_place
    assert rig_place.narrow(50.0, 60.0) == pytest.approx((1.0, 1.2))        # wider opening: no change
    assert rig_place.narrow(50.0, 45.0) == pytest.approx((0.9, 0.9))
    f, raw = rig_place.narrow(50.0, 30.0)
    assert f == pytest.approx(1 - rig_place.NARROW_MAX) and raw == pytest.approx(0.6)
    assert (rig_place.STRETCH_MAX, rig_place.NARROW_MAX, rig_place.MATCHER_DISAGREE) == (0.15, 0.15, 0.04)


def test_apply_layers_under_torso():
    import rig_place
    import spine_rig
    base = list(spine_rig.LAYERS)
    out = rig_place.apply_layers({"upperarm": "under_torso"}, base)
    # only the upper arm goes under the torso (a vest over the sleeve top); forearm and hand stay in front of it
    assert out == ["back", "leg", "foot", "hips", "arm", "torso", "hand", "forearm", "neckwear", "head", "hat", "front"]
    assert rig_place.apply_layers({}, base) == base
    assert rig_place.apply_layers({"upperarm": "over_torso"}, base) == base
    assert base == spine_rig.LAYERS                                          # not mutated


def test_apply_layers_foot_without_legs():
    import rig_place
    import spine_rig
    base = list(spine_rig.LAYERS)
    over = ["back", "leg", "hips", "foot", "torso", "hand", "forearm", "arm", "neckwear", "head", "hat", "front"]
    # no leg pieces: the feet go behind the hips by default, in front of them with over_hips
    assert rig_place.apply_layers({}, base, has_legs=False) == base
    assert rig_place.apply_layers({"foot": "under_hips"}, base, has_legs=False) == base
    assert rig_place.apply_layers({"foot": "over_hips"}, base, has_legs=False) == over
    # with legs the order stays as it is, whatever the key says
    assert rig_place.apply_layers({"foot": "over_hips"}, base, has_legs=True) == base
    assert rig_place.apply_layers({"foot": "over_hips"}, base) == base
    both = rig_place.apply_layers({"foot": "over_hips", "upperarm": "under_torso"}, base, has_legs=False)
    assert both.index("foot") > both.index("hips") and both.index("arm") < both.index("torso")
    assert base == spine_rig.LAYERS


# ------------------------------------------------------------------ building the synthetic rig

def _build(ann_path, out, *extra):
    root = ann_path.parent
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(root / "master.png"),
           "--annotations", str(ann_path), "--name", "synth", "--out", str(out), *extra]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def _world_bones(skel):
    """Bone origins in Spine units (y up), composing parent rotations (no bone scales are written)."""
    world = {}
    for b in skel["bones"]:
        if "parent" not in b:
            world[b["name"]] = (np.zeros(2), 0.0)
            continue
        (px, rot) = world[b["parent"]]
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        x, y = b.get("x", 0.0), b.get("y", 0.0)
        world[b["name"]] = (px + np.array([c * x - s * y, s * x + c * y]), rot + b.get("rotation", 0.0))
    return world


def _body_height(master_png):
    arr = np.asarray(Image.open(master_png).convert("RGB")).astype(int)
    rows = np.nonzero((np.abs(arr - np.array(BG)).sum(2) > 30).any(1))[0]
    return float(rows.max() - rows.min())


@pytest.fixture(scope="module")
def synth_rig(tmp_path_factory):
    root = tmp_path_factory.mktemp("synth")
    ann = make_character(root, pose_variants=True)
    out = root / "rig"
    r = _build(ann, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return root, out


@pytest.mark.slow
def test_synthetic_rig_joints_on_master(synth_rig):
    root, out = synth_rig
    truth = json.loads((root / "truth.json").read_text())
    report = json.loads((out / "report.json").read_text())
    skel = json.loads((out / "synth.json").read_text())
    mf = report["master_frame"]
    world = _world_bones(skel)
    tol = 0.01 * _body_height(root / "master.png")
    expect = {f"{bone}_{s}": truth["master"][f"{joint}_{s}"] for s in "lr"
              for bone, joint in (("upperarm", "shoulder"), ("forearm", "elbow"), ("hand", "wrist"), ("leg", "hip"))}
    expect["head_base"] = truth["master_extra"]["head_neck"]      # matched by colour; the annotated neck is its pivot
    for bone, want in expect.items():
        (ux, uy), _ = world[bone]
        px = np.array([ux / mf["units_per_px"] + mf["mid_x"], mf["ground_y"] - uy / mf["units_per_px"]])
        err = float(np.linalg.norm(px - np.array(want)))
        assert err <= tol, f"{bone}: {err:.1f} px from the master's joint {want} (tolerance {tol:.1f})"
    assert report["annotations"] == str(root / "annotations.json")
    assert report["allow_proposed"] is False
    assert isinstance(report["doubts"], list)
    assert not [d for d in report["doubts"] if d["reason"] in ("stretch", "narrow", "ground_miss")], report["doubts"]
    parts = report["parts"]
    for n in ("torso", "hips", "upperarm_l", "forearm_r", "leg_l"):
        assert parts[n]["method"] == "two_point" and isinstance(parts[n]["stretch"], float), (n, parts[n])
    assert isinstance(parts["leg_r"]["narrow"], float)
    # the torso's shoulder sockets are plain points (no width), so no opening narrows the upper arm here
    assert parts["upperarm_l"]["narrow"] is None
    assert parts["head_base"]["method"] == "matcher" and parts["tail"]["method"] == "matcher"
    assert parts["boot_l"]["method"] == "socket" and parts["boot_l"]["stretch"] is None
    assert parts["hand_r"]["method"] == "hand"


@pytest.fixture(scope="module")
def synth_placed(tmp_path_factory):
    import rig_place
    import spine_rig
    root = tmp_path_factory.mktemp("placed")
    ann = ra.load(make_character(root))
    frame = spine_rig.load_master(root / "master.png")
    g = rig_place.global_scale(ann, frame)
    return root, ann, frame, g, rig_place.place_from_annotations(ann, frame, g)


@pytest.mark.slow
def test_synthetic_leg_inside_boot(synth_placed):
    _, ann, frame, g, (pieces, joints, bone_dir, doubts, info) = synth_placed
    G = g / frame.k
    outs = {o.name: o for p in ann.pieces.values() for o in p.outputs}
    for s in "lr":
        hem = joints[f"leg_{s}"] + bone_dir[f"leg_{s}"]
        rim = joints[f"boot_{s}"]                                    # the boot's ankle opening centre
        a = outs[f"boot_{s}"].widths["ankle"] * G / 2                 # half its width
        b = outs[f"boot_{s}"].depths["ankle"] * G                     # how far it runs down into the boot
        dx, dy = hem - rim
        assert dy > 0, f"leg_{s} hem above the boot rim"
        assert (dx / a) ** 2 + (dy / b) ** 2 <= 1.0, f"leg_{s} hem {hem} outside the boot opening at {rim}"
        assert pieces[f"leg_{s}"]["unit_y"] > 0
    for n in ("torso", "hips", "upperarm_l", "forearm_r", "hand_l", "leg_r", "boot_l", "head_base", "tail"):
        assert n in pieces and n in joints and n in bone_dir, n
        assert set(pieces[n]) >= {"img", "cx", "cy", "unit", "unit_y", "angle", "mask"}


@pytest.mark.slow
def test_push_in_recorded(synth_placed):
    _, ann, frame, g, (pieces, joints, bone_dir, doubts, info) = synth_placed
    G = g / frame.k
    outs = {o.name: o for p in ann.pieces.values() for o in p.outputs}
    for s in "lr":
        assert info[f"leg_{s}"]["push"]["hip"] == pytest.approx(outs["hips"].depths[f"hip_{s}"] * G / 3, abs=0.01)
        assert info[f"leg_{s}"]["push"]["hem"] == pytest.approx(outs[f"boot_{s}"].depths["ankle"] * G / 3, abs=0.01)
        assert f"shoulder_{s}" not in outs["torso"].depths            # a plain point: nothing to push into
        assert info[f"upperarm_{s}"]["push"] == {"shoulder": 0.0}    # it hangs from the master's shoulder
        assert info[f"forearm_{s}"]["push"] == {}


@pytest.mark.slow
def test_synthetic_tail_matched_at_its_angle(synth_placed):
    from synth_character import TAIL_DEG, TAIL_ROOT, placer, world_dir
    root, ann, frame, g, (pieces, joints, bone_dir, doubts, info) = synth_placed
    tol = 0.03 * _body_height(root / "master.png")
    centre = np.array(placer(TAIL_ROOT, world_dir(TAIL_DEG, "l"))((0.0, 73.5)))   # middle of the tail's painted box
    got = np.array([pieces["tail"]["cx"], pieces["tail"]["cy"]])
    assert np.linalg.norm(got - centre) <= tol, f"tail centre {got} vs {centre}"
    assert np.linalg.norm(joints["tail"] - np.array(TAIL_ROOT)) <= tol, f"tail pivot {joints['tail']} vs {TAIL_ROOT}"


def test_ears_covered_by_heads_are_dropped():
    import spine_rig
    head = np.zeros((100, 100), bool)
    head[20:60, 30:70] = True
    inside, outside, other = (np.zeros((100, 100), bool) for _ in range(3))
    inside[15:30, 30:40] = True              # two thirds under the head
    outside[0:12, 80:95] = True              # clear of it
    other[20:40, 30:50] = True               # not an ear
    masks = {"ear_l": inside, "ear_r": outside, "hat": other}
    assert spine_rig.ears_in_heads(masks, head) == ["ear_l"]


def _set_status(ann_path, key, status):
    ann = ra.load(ann_path)
    ann.pieces[key].status = status
    ra.save(ann)


def test_refuses_proposed(tmp_path):
    ann_path = make_character(tmp_path)
    key = next(k for k, p in ra.load(ann_path).pieces.items() if p.role == "tail")
    _set_status(ann_path, key, "proposed")
    r = _build(ann_path, tmp_path / "rig")
    assert r.returncode != 0
    assert key in r.stderr
    assert not (tmp_path / "rig" / "synth.json").exists()


@pytest.mark.slow
def test_allow_proposed_is_stamped(tmp_path):
    ann_path = make_character(tmp_path)
    key = next(k for k, p in ra.load(ann_path).pieces.items() if p.role == "tail")
    _set_status(ann_path, key, "proposed")
    r = _build(ann_path, tmp_path / "rig", "--allow-proposed")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    report = json.loads((tmp_path / "rig" / "report.json").read_text())
    assert report["allow_proposed"] is True
    assert report["annotations"] == str(ann_path)
    warn = next((ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith("WARNING")), "")
    assert "--allow-proposed" in warn and key in warn, r.stdout[-3000:] + r.stderr[-3000:]


def _build_named(ann_path, out, *name):
    root = ann_path.parent
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(root / "master.png"),
           "--annotations", str(ann_path), "--out", str(out), *name]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def test_name_must_match_the_annotations(tmp_path):
    ann_path = make_character(tmp_path)
    r = _build_named(ann_path, tmp_path / "rig", "--name", "fox")
    assert r.returncode != 0 and "Traceback" not in r.stderr, r.stderr[-2000:]
    assert "--name fox" in r.stderr and "'synth'" in r.stderr, r.stderr[-2000:]
    assert not (tmp_path / "rig").exists()


@pytest.mark.slow
def test_name_defaults_to_the_annotations_character(tmp_path):
    ann_path = make_character(tmp_path)
    r = _build_named(ann_path, tmp_path / "rig")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert (tmp_path / "rig" / "synth.json").exists()


def test_legacy_still_needs_a_name(tmp_path):
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", "m.png", "--body", "b", "--out", str(tmp_path)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 2 and "--name" in r.stderr, r.stderr[-2000:]


@pytest.mark.slow
def test_sleeve_under_vest_draw_order(tmp_path):
    ann_path = make_character(tmp_path)
    ann = ra.load(ann_path)
    ann.master.layers = {"upperarm": "under_torso"}
    ra.save(ann)
    r = _build(ann_path, tmp_path / "rig")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    slots = [s["name"] for s in json.loads((tmp_path / "rig" / "synth.json").read_text())["slots"]]
    assert slots.index("upperarm_l") < slots.index("torso"), slots
    for n in ("forearm_r", "hand_l"):
        assert slots.index(n) > slots.index("torso"), slots


@pytest.mark.slow
def test_synthetic_without_tail_or_feet(tmp_path):
    ann_path = make_character(tmp_path, tail=False, feet="hoof")
    r = _build(ann_path, tmp_path / "rig")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    skel = json.loads((tmp_path / "rig" / "synth.json").read_text())
    names = {b["name"] for b in skel["bones"]}
    assert {"hoof_l", "hoof_r", "leg_l", "leg_r"} <= names and "tail" not in names


# ------------------------------------------------------------------ Task 11: variants, resolved file, cross-check

def _setup_px(world, bone, mf):
    """A bone's setup-pose origin in master px."""
    (ux, uy), _ = world[bone]
    return np.array([ux / mf["units_per_px"] + mf["mid_x"], mf["ground_y"] - uy / mf["units_per_px"]])


@pytest.mark.slow
def test_resolved_written(synth_rig):
    root, out = synth_rig
    res = json.loads((out / "annotations.resolved.json").read_text())
    assert set(res) >= {"attachments", "sockets", "holds", "thumb_targets", "master_points_units", "point_bones",
                        "body_height_units", "push_in"}
    skin = json.loads((out / "synth.json").read_text())["skins"][0]["attachments"]
    atts = res["attachments"]
    hands = {a: r for a, r in atts.items() if r["slot"].startswith("hand_")}
    assert len(hands) == 12, sorted(hands)                     # rest + open, fist, point, thumbsup, grip per side
    for a, r in hands.items():
        assert {"wrist", "thumb_tip"} <= set(r["points"]), a
        assert a in skin[r["slot"]] and r["side"] == r["slot"][-1]
        assert ("fingertip" in r["points"]) == (r["variant"] not in ("fist", "thumbsup")), a   # every annotated point
    assert atts["synth_hand_l_point"]["variant"] == "point" and atts["synth_hand_l"]["variant"] is None
    assert atts["synth_upperarm_r_raised"]["side"] == "r" and atts["synth_tail_up"]["side"] == ""
    assert atts["synth_boot_l"]["widths"]["ankle"] == pytest.approx(56 * 0.8)
    want = {"point": (1.2, "point"), "thumbs_up": (1.2, "thumbsup"), "hold_card": (1.2, "grip"),
            "wave": (0.75, "open"), "cheer_jump": (0.95, "fist")}
    assert set(res["holds"]) == set(want)
    for anim, (t, v) in want.items():
        h = res["holds"][anim]
        assert (h["time"], h["slot"], h["variant"], h["side"]) == (t, "hand_l", v, "l"), (anim, h)
    # T17b: each hold records the pose it uses and its own thumb target (palm-facing synth hands point outward)
    poses = {anim: res["holds"][anim]["pose"] for anim in want}
    assert poses == {"point": "outward", "thumbs_up": "outward", "hold_card": "hold_card", "wave": "wave",
                     "cheer_jump": "cheer"}
    assert res["holds"]["point"]["thumb_target"] == 90.0 and res["holds"]["hold_card"]["thumb_target"] == 90.0
    gest = json.loads((out / "report.json").read_text())["gestures"]
    wave = gest["wave"]["l"]                          # no pose choice: the target is where a palm puts the thumb
    assert wave["facing"] == "palm"
    assert wave["thumb_target_deg"] == pytest.approx(rh.anatomical_thumb_deg(wave["forearm_deg"], "l", "palm"), abs=0.1)
    assert res["holds"]["wave"]["thumb_target"] == wave["thumb_target_deg"]
    assert set(gest["cheer_jump"]) == {"l", "r"} and gest["point"]["l"]["errors"]["outward"] < 45
    tt = res["thumb_targets"]
    assert tt["synth_hand_l_point"] == 90.0 and tt["synth_hand_r_thumbsup"] == 90.0
    assert tt["synth_hand_l"] == 0.0 and tt["synth_hand_r"] == 180.0          # rest: lateral
    assert tt["synth_hand_l_fist"] == 180.0 and tt["synth_hand_r_open"] == 0.0  # medial
    assert set(tt) == set(hands)
    pb = {}                                                    # no neck: the head is matched, with its own pivot
    for s in "lr":
        pb.update({f"shoulder_{s}": f"upperarm_{s}", f"elbow_{s}": f"forearm_{s}", f"wrist_{s}": f"hand_{s}",
                   f"hip_{s}": f"leg_{s}", f"ankle_{s}": f"boot_{s}"})
    assert res["point_bones"] == pb
    mf = json.loads((out / "report.json").read_text())["master_frame"]
    truth = json.loads((root / "truth.json").read_text())["master"]
    assert set(res["master_points_units"]) == set(ra.MASTER_POINTS)
    for n, (x, y) in truth.items():
        want_u = ((x - mf["mid_x"]) * mf["units_per_px"], (mf["ground_y"] - y) * mf["units_per_px"])
        assert res["master_points_units"][n] == pytest.approx(want_u, abs=0.5 * mf["units_per_px"]), n
    assert res["body_height_units"] == pytest.approx(_body_height(root / "master.png") * mf["units_per_px"], rel=0.03)
    socks = {(s_["child"], s_["child_point"], s_["parent"], s_["parent_point"]): s_["width"] for s_ in res["sockets"]}
    for s in "lr":
        assert socks[(f"synth_leg_{s}", "hem", f"synth_boot_{s}", "ankle")] == pytest.approx(56 * 0.8)
        assert socks[(f"synth_leg_{s}", "hip", "synth_hips", f"hip_{s}")] == pytest.approx(60 * 0.8)
    for s in "lr":
        assert socks[(f"synth_hand_{s}", "wrist", f"synth_forearm_{s}", "wrist")] == pytest.approx(36 * 0.8)
    assert len(socks) == 6                                     # the torso's shoulders are plain points: no socket
    assert set(res["push_in"]) == {"hip_l", "hip_r", "shoulder_l", "shoulder_r", "wrist_l", "wrist_r"}
    assert all(res["push_in"][k] > 0 for k in ("hip_l", "hip_r", "wrist_l", "wrist_r"))
    assert res["push_in"]["shoulder_l"] == res["push_in"]["shoulder_r"] == 0.0     # a point has no depth


@pytest.mark.slow
def test_variant_wrist_on_rest_wrist(synth_rig):
    import spine_qa
    root, out = synth_rig
    res = json.loads((out / "annotations.resolved.json").read_text())
    rig = spine_qa.Rig(out / "synth.json")
    tol = 0.015 * res["body_height_units"]
    joint = {"hand": "wrist", "upperarm": "shoulder", "boot": "ankle", "tail": "root"}
    checked = set()
    for att, r in res["attachments"].items():
        if r["variant"] is None or r["slot"] == "head":
            continue
        slot, j = r["slot"], joint[r["slot"].split("_")[0]]
        world, active = rig.pose(None, 0.0, {slot: att})
        assert active[slot] == att

        def at(a):
            x, y = res["attachments"][a]["points"][j]
            return (rig.att_matrix(slot, a, world) @ np.array([x, y, 1.0]))[:2]
        err = float(np.linalg.norm(at(att) - at(f"synth_{slot}")))
        assert err <= tol, f"{att}: its {j} is {err:.2f} units from the rest {j} (tolerance {tol:.2f})"
        checked.add(att)
    assert {"synth_hand_l_point", "synth_hand_r_fist", "synth_upperarm_l_raised", "synth_boot_r_tiptoe",
            "synth_tail_up"} <= checked, checked


@pytest.mark.slow
def test_variant_scale_from_annotated_widths(synth_rig):
    _, out = synth_rig
    v = json.loads((out / "report.json").read_text())["variants"]
    for h in ("open", "fist", "point", "thumbsup", "grip"):     # every hand sheet paints the same wrist width
        assert v[f"synth_hand_l_{h}"]["scale_vs_rest"] == pytest.approx(1.0, abs=0.01), (h, v[f"synth_hand_l_{h}"])
    for n in ("synth_upperarm_l_raised", "synth_boot_r_tiptoe"):  # the pose sheet paints at 0.7 against 0.8
        assert v[n]["scale_vs_rest"] == pytest.approx(0.8 / 0.7, abs=0.01), (n, v[n])


@pytest.mark.slow
def test_gesture_angles_from_rig_hands(tmp_path):
    import spine_qa
    ann_path = make_character(tmp_path)
    patched = {"point": (30.0, 60.0), "thumbs_up": (-40.0, 20.0), "hold_card": (-80.0, 160.0)}
    out = tmp_path / "rig"
    argv = ["spine_rig.py", "--master", str(tmp_path / "master.png"), "--annotations", str(ann_path),
            "--name", "synth", "--out", str(out)]
    code = (f"import sys\nsys.path.insert(0, {str(SCRIPTS)!r})\nimport rig_hands\n"
            f"rig_hands.GESTURE_ARM_DEG.update({patched!r})\nimport spine_rig\nsys.argv = {argv!r}\n"
            "raise SystemExit(spine_rig.main())\n")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    rig = spine_qa.Rig(out / "synth.json")
    for anim, (ua, fa) in patched.items():
        world, _ = rig.pose(anim, 1.2)
        for bone, want in (("upperarm_l", ua), ("forearm_l", fa)):
            a_, _, c_, *_ = world[bone]
            got = math.degrees(math.atan2(c_, a_))
            assert abs((got - want + 180) % 360 - 180) < 0.5, (anim, bone, got, want)


@pytest.mark.slow
def test_matcher_disagreement_reported(synth_rig, synth_placed):
    import copy
    import rig_place
    _, out = synth_rig
    report = json.loads((out / "report.json").read_text())
    assert not [d for d in report["doubts"] if d["reason"] == "matcher_disagreement"], report["doubts"]
    root, ann, frame, g, (pieces, *_) = synth_placed
    assert rig_place.cross_check(ann, frame, g, pieces) == []
    moved = copy.deepcopy(ann)
    W = Image.open(root / "master.png").width
    x, y = moved.master.points["wrist_l"]
    moved.master.points["wrist_l"] = (x + 0.10 * _body_height(root / "master.png") / W, y)
    placed = rig_place.place_from_annotations(moved, frame, g)
    doubts = rig_place.cross_check(moved, frame, g, placed[0])
    bad = [d for d in doubts if d["reason"] == "matcher_disagreement"]
    assert {d["part"] for d in bad} & {"forearm_l", "hand_l"}, doubts
    for d in bad:
        assert d["distance_frac"] > rig_place.MATCHER_DISAGREE
        assert len(d["annotation"]) == 2 and len(d["matcher"]) == 2


@pytest.mark.slow
def test_unplaced_rest_output_is_a_doubt(tmp_path):
    import rig_place
    import spine_rig
    ann = ra.load(make_character(tmp_path))
    frame = spine_rig.load_master(tmp_path / "master.png")
    g = rig_place.global_scale(ann, frame)
    leg = next(o for p in ann.pieces.values() for o in p.outputs if o.name == "leg_l")
    leg.name = "leg"                                         # no side: nothing places it
    pieces, _, _, doubts, _ = rig_place.place_from_annotations(ann, frame, g)
    assert "leg" not in pieces
    assert {"part": "leg", "reason": "not_placed"} in doubts


def test_allow_proposed_missing_points_exit_cleanly(tmp_path):
    import rig_place
    import spine_rig
    ann_path = make_character(tmp_path)
    frame = spine_rig.load_master(tmp_path / "master.png")
    ann = ra.load(ann_path)
    key, p = next((k, p) for k, p in ann.pieces.items() if p.role == "leg" and p.side == "l")
    p.status = "proposed"
    del p.points["hem"]
    del p.outputs[0].points["hem"]
    with pytest.raises(SystemExit) as e:
        rig_place.place_from_annotations(ann, frame, 1.0)
    assert key in str(e.value) and "hem" in str(e.value)
    ra.save(ann)
    r = _build(ann_path, tmp_path / "rig", "--allow-proposed")
    assert r.returncode != 0 and key in r.stderr and "Traceback" not in r.stderr, r.stderr[-2000:]

    ann = ra.load(make_character(tmp_path / "m"))
    ann.master.status = "proposed"
    del ann.master.points["elbow_l"]
    with pytest.raises(SystemExit) as e:
        rig_place.global_scale(ann, frame)
    assert "master" in str(e.value) and "elbow_l" in str(e.value)


@pytest.mark.slow
def test_feet_without_legs(tmp_path):
    ann_path = make_character(tmp_path, pose_variants=True)
    ann = ra.load(ann_path)
    for k in [k for k, p in ann.pieces.items() if p.role == "leg"]:
        del ann.pieces[k]
    ra.save(ann)
    out = tmp_path / "rig"
    r = _build(ann_path, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    skel = json.loads((out / "synth.json").read_text())
    bones = {b["name"]: b for b in skel["bones"]}
    assert "leg_l" not in bones and "leg_r" not in bones
    slots = [s["name"] for s in skel["slots"]]
    for s in "lr":
        assert bones[f"boot_{s}"]["parent"] == "hips"
        assert slots.index(f"boot_{s}") < slots.index("hips"), slots
    report = json.loads((out / "report.json").read_text())
    mf = report["master_frame"]
    truth = json.loads((tmp_path / "truth.json").read_text())["master"]
    world = _world_bones(skel)
    tol = 0.01 * _body_height(tmp_path / "master.png")
    for bone, joint in (("boot_l", "ankle_l"), ("boot_r", "ankle_r"), ("upperarm_l", "shoulder_l"), ("hand_r", "wrist_r")):
        err = float(np.linalg.norm(_setup_px(world, bone, mf) - np.array(truth[joint])))
        assert err <= tol, f"{bone}: {err:.1f} px from {joint}"
    assert report["parts"]["boot_l"]["method"] == "socket"
    keys = skel["animations"]["cheer_jump"]["slots"]["boot_l"]["attachment"]
    assert "synth_boot_l_tiptoe" in {k["name"] for k in keys}
    res = json.loads((out / "annotations.resolved.json").read_text())
    assert not [s_ for s_ in res["sockets"] if "leg" in s_["child"]]
    assert "hip_l" not in res["point_bones"] and res["point_bones"]["ankle_l"] == "boot_l"


def _slot_order(rig):
    return [s["name"] for s in json.loads((rig / "synth.json").read_text())["slots"]]


def _drop_legs(ann_path):
    ann = ra.load(ann_path)
    for p in ann.pieces.values():
        if p.role == "leg":
            p.status, p.role, p.points, p.outputs = "ignored", "", {}, []
    return ann


@pytest.mark.slow
@pytest.mark.parametrize("layer,over", [(None, False), ("under_hips", False), ("over_hips", True)])
def test_feet_draw_order_without_legs(tmp_path, layer, over):
    ann_path = make_character(tmp_path)
    ann = _drop_legs(ann_path)
    ann.master.layers = {"foot": layer} if layer else {}
    ra.save(ann)
    r = _build(ann_path, tmp_path / "rig")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    slots = _slot_order(tmp_path / "rig")
    assert "leg_l" not in slots and "boot_l" in slots
    assert (slots.index("boot_l") > slots.index("hips")) == over, slots


@pytest.mark.slow
def test_feet_draw_order_with_legs_ignores_over_hips(tmp_path):
    ann_path = make_character(tmp_path)
    ann = ra.load(ann_path)
    ann.master.layers = {"foot": "over_hips"}
    ra.save(ann)
    r = _build(ann_path, tmp_path / "rig")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    slots = _slot_order(tmp_path / "rig")
    assert slots.index("leg_l") < slots.index("boot_l") < slots.index("hips"), slots


def _scale_boot(ann_path, factor):
    """Repaint boot_l `factor` times larger: the image and every one of its output measurements."""
    ann = ra.load(ann_path)
    o = next(o for p in ann.pieces.values() for o in p.outputs if o.name == "boot_l")
    f = ann_path.parent / o.file
    im = Image.open(f)
    im.resize((round(im.width * factor), round(im.height * factor)), Image.LANCZOS).save(f)
    o.points = {n: (x * factor, y * factor) for n, (x, y) in o.points.items()}
    o.widths = {n: w * factor for n, w in o.widths.items()}
    o.depths = {n: d * factor for n, d in o.depths.items()}
    ra.save(ann)
    return ann_path


def _foot_height(ann_path):
    """(placed boot_l ankle-to-ground height, the master's), master px, plus the placement's doubts."""
    import rig_place
    import spine_rig
    ann = ra.load(ann_path)
    frame = spine_rig.load_master(ann_path.parent / "master.png")
    g = rig_place.global_scale(ann, frame)
    pieces, joints, bone_dir, doubts, info = rig_place.place_from_annotations(ann, frame, g)
    W, H = rig_place._master_size(ann)
    mp = ann.master.points
    master = (mp["ground"][1] - mp["ankle_l"][1]) * H
    return float(bone_dir["boot_l"][1]), float(master), doubts


@pytest.mark.slow
@pytest.mark.parametrize("factor", [1.0, 1.15])
def test_foot_height_matches_the_master(tmp_path, factor):
    ann_path = make_character(tmp_path)
    if factor != 1.0:
        _scale_boot(ann_path, factor)
    got, want, doubts = _foot_height(ann_path)
    assert got == pytest.approx(want, rel=0.02)
    assert not [d for d in doubts if d["reason"] == "ground_miss"], doubts


@pytest.mark.slow
def test_foot_scale_clamp_raises_ground_miss(tmp_path):
    ann_path = _scale_boot(make_character(tmp_path), 1.4)
    got, want, doubts = _foot_height(ann_path)
    assert got > want * 1.1                                        # the clamp held it above the master's height
    miss = [d for d in doubts if d["reason"] == "ground_miss"]
    assert len(miss) == 1 and miss[0]["part"] == "boot_l"
    assert miss[0]["ratio"] == pytest.approx(1 / 1.4, abs=0.05)    # the raw ratio, not the clamped one


# ------------------------------------------------------------------ Task 16: fixes from the real fox and moose

def _place(ann):
    import rig_place
    import spine_rig
    frame = spine_rig.load_master(ann.path.parent / "master.png")
    g = rig_place.global_scale(ann, frame)
    return frame, g, rig_place.place_from_annotations(ann, frame, g)


def _master_px(ann, name):
    import rig_place
    W, H = rig_place._master_size(ann)
    x, y = ann.master.points[name]
    return np.array([x * W, y * H])


def _torso_output(ann):
    return next(o for p in ann.pieces.values() for o in p.outputs if o.name == "torso")


@pytest.mark.slow
def test_upper_arm_hangs_from_the_master_shoulder(tmp_path):
    """Ruling 1: the upper arm's proximal joint is the master's shoulder, not the torso's (single source of truth)."""
    ann = ra.load(make_character(tmp_path))
    t = _torso_output(ann)
    t.points["shoulder_l"] = (t.points["shoulder_l"][0] + 40.0, t.points["shoulder_l"][1] - 30.0)   # a stray point
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    for s in "lr":
        assert np.linalg.norm(joints[f"upperarm_{s}"] - _master_px(ann, f"shoulder_{s}")) < 0.5, s
        assert info[f"upperarm_{s}"]["push"] == {"shoulder": 0.0}
    miss = [d for d in doubts if d["reason"] == "shoulder_mismatch"]
    assert [d["point"] for d in miss] == ["shoulder_l"], doubts
    assert miss[0]["part"] == "torso" and miss[0]["distance_frac"] > 0.04 and miss[0]["limit"] == 0.04


@pytest.mark.slow
def test_torso_without_shoulders_places(tmp_path):
    ann = ra.load(make_character(tmp_path))
    t = _torso_output(ann)
    for s in "lr":
        del t.points[f"shoulder_{s}"]
        t.widths.pop(f"shoulder_{s}", None)
        next(p for p in ann.pieces.values() if p.role == "torso").points.pop(f"shoulder_{s}")
    assert ra.validate(ann) == []
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    for s in "lr":
        assert np.linalg.norm(joints[f"upperarm_{s}"] - _master_px(ann, f"shoulder_{s}")) < 0.5, s
    assert not [d for d in doubts if d["reason"] == "shoulder_mismatch"], doubts


@pytest.mark.slow
def test_synthetic_torso_shoulders_agree(synth_placed):
    *_, (pieces, joints, bone_dir, doubts, info) = synth_placed
    assert not [d for d in doubts if d["reason"] == "shoulder_mismatch"], doubts


@pytest.mark.slow
def test_hand_pushed_into_the_cuff(synth_placed):
    """Ruling 2: the hand's wrist goes a third of the cuff's depth into the forearm, along the forearm's axis."""
    _, ann, frame, g, (pieces, joints, bone_dir, doubts, info) = synth_placed
    G = g / frame.k
    outs = {o.name: o for p in ann.pieces.values() for o in p.outputs}
    for s in "lr":
        fa = f"forearm_{s}"
        wrist = joints[fa] + bone_dir[fa]
        up = -bone_dir[fa] / np.linalg.norm(bone_dir[fa])             # from the wrist toward the elbow
        want = outs[fa].depths["wrist"] * G / 3
        assert info[f"hand_{s}"]["push"] == {"wrist": pytest.approx(want, abs=0.01)}
        assert np.linalg.norm(joints[f"hand_{s}"] - (wrist + up * want)) < 0.5, s
        assert info[f"hand_{s}"]["method"] == "hand"


@pytest.mark.slow
def test_hips_bone_points_into_the_hips(synth_placed):
    """Ruling 6: the hips bone runs from the waist toward the leg openings, into its own part."""
    _, ann, frame, g, (pieces, joints, bone_dir, doubts, info) = synth_placed
    mid = (_master_px(ann, "hip_l") + _master_px(ann, "hip_r")) / 2
    d = bone_dir["hips"] / np.linalg.norm(bone_dir["hips"])
    assert float(np.dot(d, (mid - joints["hips"]) / np.linalg.norm(mid - joints["hips"]))) > 0.99


def test_pivot_onto_part():
    """Ruling 6: a pivot outside its part moves to the nearest opaque pixel; inside it stays."""
    import rig_place
    m = np.zeros((50, 60), bool)
    m[10:20, 30:40] = True
    assert rig_place.onto_part(m, (35.0, 15.0)) == pytest.approx((35.0, 15.0))
    assert rig_place.onto_part(m, (35.0, 30.0)) == pytest.approx((35.0, 19.0))
    assert rig_place.onto_part(m, (5.0, 12.0)) == pytest.approx((30.0, 12.0))
    assert rig_place.onto_part(np.zeros((5, 5), bool), (1.0, 2.0)) == pytest.approx((1.0, 2.0))   # nothing to land on


@pytest.mark.slow
def test_matched_pivots_on_their_parts(synth_placed):
    _, ann, frame, g, (pieces, joints, bone_dir, doubts, info) = synth_placed
    for n in ("head_base", "tail"):
        x, y = np.round(joints[n]).astype(int)
        assert pieces[n]["mask"][y, x], n


@pytest.mark.slow
def test_resolved_hand_socket_and_no_neck(synth_rig):
    """Rulings 2 and 3: the hand sits in a socket of its forearm; the neck has no point bone (the head is matched)."""
    _, out = synth_rig
    res = json.loads((out / "annotations.resolved.json").read_text())
    socks = {(s_["child"], s_["child_point"], s_["parent"], s_["parent_point"]): s_["width"] for s_ in res["sockets"]}
    for s in "lr":
        assert socks[(f"synth_hand_{s}", "wrist", f"synth_forearm_{s}", "wrist")] == pytest.approx(36 * 0.8)
        assert res["push_in"][f"wrist_{s}"] > 0
    assert "neck" not in res["point_bones"]


def _ear_rgba(colour, inner, w=90, h=44):
    """A horizontal ear painted on its own: an outer ellipse with an inner one, float RGBA."""
    from PIL import ImageDraw
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((2, 2, w - 3, h - 3), fill=colour + (255,))
    d.ellipse((18, 12, w - 18, h - 12), fill=inner + (255,))
    return np.asarray(im, np.float32) / 255.0


def test_headgear_keeps_its_annotated_side_and_root(tmp_path):
    """T16 item 7 (the moose's ears): the sheet painted each ear with the other side's lighting. By colour alone the
    pair swaps sides and each root ends up outside the head; match_headgear keeps the annotated side and puts the
    annotated root on the head."""
    import rig_place
    import spine_rig
    from PIL import ImageDraw
    W, H = 480, 640
    dark, dark_in, pink, pink_in = (120, 80, 60), (150, 110, 90), (170, 110, 90), (240, 140, 130)
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((180, 300, 300, 600), fill=(60, 110, 190))               # a body, so the frame has a ground
    # master ears: picture left (the character's right) dark, picture right (left) pink; roots under the head
    d.ellipse((126, 158, 216, 202), fill=dark)
    d.ellipse((144, 170, 198, 190), fill=dark_in)
    d.ellipse((264, 158, 354, 202), fill=pink)
    d.ellipse((282, 170, 336, 190), fill=pink_in)
    d.ellipse((180, 120, 300, 300), fill=(240, 200, 90))                 # the head, drawn over the ear roots
    im.save(tmp_path / "master.png")
    frame = spine_rig.load_master(tmp_path / "master.png")
    assert frame.k == 1.0
    head = np.zeros((H, W), bool)
    yy, xx = np.mgrid[:H, :W]
    head[((xx - 240) / 60.0) ** 2 + ((yy - 210) / 90.0) ** 2 <= 1] = True
    # the pieces carry the other side's colours: ear_l (picture right, root at its left end) is painted dark
    ear_l = _ear_rgba(dark, dark_in)
    ear_r = _ear_rgba(pink, pink_in)
    items = {"ear_l": (ear_l, (8.0, 22.0)), "ear_r": (ear_r, (81.0, 22.0))}
    got = rig_place.match_headgear(frame, items, 1.0, head, head.copy())
    assert set(got) == {"ear_l", "ear_r"}
    for n, (img, root) in items.items():
        m = got[n]
        assert (m["cx"] > frame.mid_x) == (n == "ear_l"), (n, m["cx"])       # stays on its annotated side
        off = rig_place._rot(((root[0] - img.shape[1] / 2) * m["scale"], (root[1] - img.shape[0] / 2) * m["scale"]),
                             m["angle"])
        rx, ry = np.round(np.array([m["cx"], m["cy"]]) + off).astype(int)
        assert head[ry, rx], (n, rx, ry)                                     # its root on the head
        want = 309 if n == "ear_l" else 171
        assert abs(m["cx"] - want) < 12 and abs(m["cy"] - 180) < 12, (n, m["cx"], m["cy"], m["angle"])


def _world_deg(world, bone):
    a_, _, c_, *_ = world[bone]
    return math.degrees(math.atan2(c_, a_))


@pytest.mark.slow
def test_hand_continues_the_forearm_at_holds(synth_rig):
    """Ruling 5: at every gesture's hold the hand's world angle is the forearm's (the line rig_hands assumes)."""
    import spine_qa
    _, out = synth_rig
    rig = spine_qa.Rig(out / "synth.json")
    for anim, t in (("thumbs_up", 1.2), ("point", 1.2), ("hold_card", 1.2), ("cheer_jump", 0.95), ("wave", 1.0333)):
        world, _ = rig.pose(anim, t)
        for s in ("l", "r") if anim == "cheer_jump" else ("l",):
            d = (_world_deg(world, f"hand_{s}") - _world_deg(world, f"forearm_{s}") + 180) % 360 - 180
            assert abs(d) < 0.5, (anim, s, d)
    world, _ = rig.pose(None, 0.0)                                     # the rest pose keeps the master's bent wrist
    assert abs((_world_deg(world, "hand_l") - _world_deg(world, "forearm_l") + 180) % 360 - 180) > 2


@pytest.mark.slow
def test_shoulder_outside_torso_moves_only_the_origin(tmp_path):
    """A master shoulder annotated above the torso's shoulder line: the upper arm's art still hangs from it, but the
    bone's origin moves onto the torso/upper-arm overlap, recorded as the shoulder's push-in and a doubt."""
    import rig_place
    ann = ra.load(make_character(tmp_path))
    W, H = rig_place._master_size(ann)
    x, y = ann.master.points["shoulder_l"]
    ann.master.points["shoulder_l"] = (x, y - 40.0 / H)                 # 10 px above the torso's top edge
    frame, g, (pieces, joints, bone_dir, doubts, info) = _place(ann)
    S = _master_px(ann, "shoulder_l")
    J = joints["upperarm_l"]
    xi, yi = np.round(J).astype(int)
    assert pieces["torso"]["mask"][yi, xi] and pieces["upperarm_l"]["mask"][yi, xi], J
    moved = float(np.linalg.norm(J - S))
    assert moved > 5
    assert info["upperarm_l"]["push"]["shoulder"] == pytest.approx(moved, abs=1e-6)
    d = [d_ for d_ in doubts if d_["reason"] == "shoulder_outside_torso"]
    assert [d_["part"] for d_ in d] == ["upperarm_l"] and d[0]["moved_px"] == pytest.approx(moved, abs=0.05)
    assert info["upperarm_r"]["push"] == {"shoulder": 0.0}                # the other side sits on its torso
    xf = rig_place.Placement(pieces["upperarm_l"]["img"].size, pieces["upperarm_l"]["cx"], pieces["upperarm_l"]["cy"],
                             pieces["upperarm_l"]["unit"] * g / frame.k, pieces["upperarm_l"]["unit_y"] * g / frame.k,
                             pieces["upperarm_l"]["angle"])
    o = next(o for p in ann.pieces.values() for o in p.outputs if o.name == "upperarm_l")
    assert np.linalg.norm(xf.world(o.points["shoulder"]) - S) < 0.5      # the art still on the master's shoulder


@pytest.mark.slow
def test_wave_falls_back_when_nothing_clears_the_head(tmp_path):
    """Annotations: when no forearm angle keeps the paw clear of the head, the wave uses WAVE_FA_FALLBACK (the most
    outward angle searched), not the upright one, and the hand still continues the forearm."""
    import spine_qa
    import spine_rig
    clear = lambda f: False
    assert spine_rig.wave_forearm(clear, "l", True) == (spine_rig.WAVE_FA_FALLBACK, False)
    assert spine_rig.wave_forearm(clear, "r", True) == (180 - spine_rig.WAVE_FA_FALLBACK, False)
    assert spine_rig.wave_forearm(clear, "l", False) == (85.0, False)        # legacy keeps the upright forearm
    assert spine_rig.wave_forearm(lambda f: True, "l", True) == (85.0, True)
    ann_path = make_character(tmp_path)
    out = tmp_path / "rig"
    argv = ["spine_rig.py", "--master", str(tmp_path / "master.png"), "--annotations", str(ann_path),
            "--name", "synth", "--out", str(out)]
    code = (f"import sys\nsys.path.insert(0, {str(SCRIPTS)!r})\nimport rig_anim\nimport spine_rig\n"
            "orig = rig_anim.wave_forearm\n"
            "rig_anim.wave_forearm = lambda clear, side, annotated: orig(lambda f: False, side, annotated)\n"
            f"sys.argv = {argv!r}\nraise SystemExit(spine_rig.main())\n")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert "nothing clears the head" in r.stdout
    rig = spine_qa.Rig(out / "synth.json")
    world, _ = rig.pose("wave", 1.35)                                       # the wave's swing passes zero here
    assert abs(_world_deg(world, "forearm_l") - spine_rig.WAVE_FA_FALLBACK) < 0.5
    world, _ = rig.pose("wave", 1.0333)                                     # the hand's lagged swing passes zero
    d = (_world_deg(world, "hand_l") - _world_deg(world, "forearm_l") + 180) % 360 - 180
    assert abs(d) < 0.5, d


def _back_point_rig(tmp_path, **kw):
    """The synthetic character with its point hand labelled as showing its back, normalised and built."""
    ann = ra.load(make_character(tmp_path, **kw))
    key = next(k for k, p in ann.pieces.items() if p.variant == "point")
    ann.pieces[key].facing = "back"
    ra.snap_all(ann)
    ra.normalise(ann)
    ra.save(ann)
    out = tmp_path / "rig"
    r = _build(ann.path, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return out


def test_across_hold_search():
    """The across hold: the highest paw among the head-clear angles that sit far enough above the hold_card paw;
    else the highest clear paw still above hold_card's ("low"); else the fallback ("none")."""
    import spine_rig
    paw_y = lambda ua, fa: 300.0 - (ua + 85.0) - (190.0 - fa)       # higher (smaller y) toward ua -45, fa 160
    fb = rh.GESTURE_ARM_DEG_ACROSS["point"]
    assert spine_rig.across_hold(lambda u, f: True, paw_y, 400.0, 10.0, fb) == (-45.0, 160.0, "ok")
    assert spine_rig.across_hold(lambda u, f: u <= -60, paw_y, 400.0, 10.0, fb) == (-60.0, 160.0, "ok")
    # (-60, 160) is at 245: a card at 250 needs 240 - only "low" is left, the highest clear paw above 250
    assert spine_rig.across_hold(lambda u, f: u <= -60, paw_y, 250.0, 10.0, fb) == (-60.0, 160.0, "low")
    assert spine_rig.across_hold(lambda u, f: u <= -60, paw_y, 240.0, 10.0, fb) == (*fb, "none")   # none above it
    assert spine_rig.across_hold(lambda u, f: False, paw_y, 400.0, 10.0, fb) == (*fb, "none")
    for ua, fa in [(u, f) for u in (-85.0, -45.0) for f in (160.0, 190.0)]:      # the search range's corners
        assert spine_rig.across_hold(lambda u, f, a=ua, b=fa: (u, f) == (a, b), paw_y, 400.0, 0.0, fb) == (ua, fa, "ok")


@pytest.mark.slow
def test_back_facing_point_hand_points_across(tmp_path):
    """T17b: a point hand painted showing its back is mirrored by anatomy, so pointing outward would hang its thumb
    down; the rig points it across the body instead (nothing in the way on the synth: the highest pose searched),
    and QA judges the thumb at that pose."""
    import spine_qa
    out = _back_point_rig(tmp_path)
    rig = spine_qa.Rig(out / "synth.json")
    world, _ = rig.pose("point", 1.2)
    ua, fa = -45.0, 160.0                                                   # the top of the search: the highest paw
    for bone, want in (("upperarm_l", ua), ("forearm_l", fa), ("hand_l", fa)):
        assert abs((_world_deg(world, bone) - want + 180) % 360 - 180) < 0.5, (bone, _world_deg(world, bone))
    world, _ = rig.pose("thumbs_up", 1.2)                                   # the palm-facing thumbs-up stays outward
    assert abs((_world_deg(world, "forearm_l") - rh.GESTURE_ARM_DEG["thumbs_up"][1] + 180) % 360 - 180) < 0.5
    res = json.loads((out / "annotations.resolved.json").read_text())
    assert res["holds"]["point"]["pose"] == "across" and res["holds"]["thumbs_up"]["pose"] == "outward"
    report = json.loads((out / "report.json").read_text())
    g = report["gestures"]["point"]["l"]
    assert g["pose"] == "across" and g["across_search"] == "ok"
    assert (g["upperarm_deg"], g["forearm_deg"]) == (ua, fa)
    assert not [d for d in report["doubts"] if d["reason"].startswith("gesture")], report["doubts"]
    qa = spine_qa.check_thumbs(rig, res)
    assert qa["pass"] is True and qa["thumbs"]["point"] < 30, qa


def _alpha_rows(alpha):
    ys = np.nonzero(alpha.any(1))[0]
    return ys.min(), ys.max(), float(np.nonzero(alpha)[0].mean())


def test_apply_layers_arm_over_neckwear():
    """Annotations, a character with neckwear: forearm and hand go just above it (an arm crossing the chest passes in
    front of a hanging scarf), still under the head; the upper arm stays under it (a scarf wraps the shoulders)."""
    import rig_place
    import spine_rig
    base = list(spine_rig.LAYERS)
    assert rig_place.apply_layers({}, base, has_neckwear=True) == \
        ["back", "leg", "foot", "hips", "torso", "arm", "neckwear", "hand", "forearm", "head", "hat", "front"]
    both = rig_place.apply_layers({"upperarm": "under_torso", "hand": "over_forearm"}, base, has_neckwear=True)
    assert both == ["back", "leg", "foot", "hips", "arm", "torso", "neckwear", "forearm", "hand", "head", "hat", "front"]
    assert rig_place.apply_layers({}, base) == base                       # no neckwear: nothing moves
    assert base == spine_rig.LAYERS


@pytest.mark.slow
def test_across_point_in_front_of_neckwear(tmp_path):
    """Fix round 2: with annotations the forearm and hand are drawn above the neckwear, so a scarf is no obstacle:
    the across hold is the head rule's (the same as without the scarf), the arm passes in front of the scarf, and
    the paw stays clearly above hold_card's."""
    import spine_qa
    out = _back_point_rig(tmp_path, neckwear=True)
    report = json.loads((out / "report.json").read_text())
    g = report["gestures"]["point"]["l"]
    assert g["pose"] == "across" and g["across_search"] == "ok", g
    assert (g["upperarm_deg"], g["forearm_deg"]) == (-45.0, 160.0)         # as without the scarf
    assert not [d for d in report["doubts"] if d["reason"].startswith("gesture")], report["doubts"]
    skel = json.loads((out / "synth.json").read_text())
    order = [s_["name"] for s_ in skel["slots"]]
    scarf = next(s_["name"] for s_ in skel["slots"] if "scarf" in (s_.get("attachment") or ""))
    for s_ in ("l", "r"):
        assert order.index(f"upperarm_{s_}") < order.index(scarf) < order.index(f"forearm_{s_}"), order
        assert order.index(scarf) < order.index(f"hand_{s_}") < order.index("head"), order
    rig = spine_qa.Rig(out / "synth.json")
    canvas = spine_qa.Canvas(rig, 600)
    _, _, _, alphas = spine_qa.render(rig, canvas, "point", 1.2)
    assert (alphas["hand_l"] & alphas[scarf]).any() or (alphas["forearm_l"] & alphas[scarf]).any()   # crosses it, in front
    _, _, _, card = spine_qa.render(rig, canvas, "hold_card", 1.2)
    _, _, _, setup = spine_qa.render(rig, canvas, None, 0.0)
    top, bottom, _ = _alpha_rows(np.any(list(setup.values()), axis=0))
    assert _alpha_rows(card["hand_l"])[2] - _alpha_rows(alphas["hand_l"])[2] >= 0.04 * (bottom - top)


# ------------------------------------------------------------------ final review: annotated roles, not name tokens

@pytest.fixture(scope="module")
def renamed_rig(tmp_path_factory):
    """The synthetic character with free-form names where the old name tokens guessed wrong: neckwear named
    `neckwear` (was a prop over the head), a hat named `beanie` (was a prop on the torso), feet named `sneaker` (were
    props: no foot layer, no tiptoe swap)."""
    root = tmp_path_factory.mktemp("renamed")
    ann = make_character(root, pose_variants=True, neckwear=True, hat=True,
                         names={"neckwear": "neckwear", "hat": "beanie", "foot": "sneaker"})
    out = root / "rig"
    r = _build(ann, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return root, out


@pytest.mark.slow
def test_renamed_neckwear_is_drawn_under_the_head(renamed_rig):
    _, out = renamed_rig
    skel = json.loads((out / "synth.json").read_text())
    order = [s_["name"] for s_ in skel["slots"]]
    assert order.index("torso") < order.index("neckwear") < order.index("head"), order
    assert {b["name"]: b for b in skel["bones"]}["neckwear"]["parent"] == "torso"


@pytest.mark.slow
def test_renamed_hat_hangs_from_the_head(renamed_rig):
    _, out = renamed_rig
    skel = json.loads((out / "synth.json").read_text())
    bones = {b["name"]: b for b in skel["bones"]}
    assert bones["beanie"]["parent"] == "head_base"
    order = [s_["name"] for s_ in skel["slots"]]
    assert order.index("head") < order.index("beanie"), order
    report = json.loads((out / "report.json").read_text())
    assert not [d for d in report["doubts"] if d["reason"] == "not_placed"], report["doubts"]


@pytest.mark.slow
def test_renamed_feet_are_feet(renamed_rig):
    _, out = renamed_rig
    skel = json.loads((out / "synth.json").read_text())
    bones = {b["name"]: b for b in skel["bones"]}
    order = [s_["name"] for s_ in skel["slots"]]
    for s in "lr":
        assert bones[f"sneaker_{s}"]["parent"] == f"leg_{s}"
        assert order.index(f"leg_{s}") < order.index(f"sneaker_{s}") < order.index("hips"), order
        keys = skel["animations"]["cheer_jump"]["slots"][f"sneaker_{s}"]["attachment"]
        assert f"synth_sneaker_{s}_tiptoe" in {k["name"] for k in keys}


@pytest.mark.slow
def test_variant_on_the_guessed_path_is_a_doubt(tmp_path):
    """A variant the annotations can't place (here: no wrist width on the open hand's left output) falls back to the
    guessed joint path: report.json says so per variant, and lists a variant_guessed doubt."""
    ann_path = make_character(tmp_path)
    ann = ra.load(ann_path)
    o = next(o for p in ann.pieces.values() for o in p.outputs if o.name == "hand_l_open")
    o.widths = {}
    ra.save(ann)
    r = _build(ann_path, tmp_path / "rig")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    report = json.loads((tmp_path / "rig" / "report.json").read_text())
    assert report["variants"]["synth_hand_l_open"]["joint"] == "guessed"
    guessed = [d for d in report["doubts"] if d["reason"] == "variant_guessed"]
    assert guessed == [{"part": "hand_l_open", "reason": "variant_guessed", "attachment": "synth_hand_l_open"}], guessed


def test_hands_need_their_structural_name(tmp_path):
    ann_path = make_character(tmp_path)
    raw = json.loads(ann_path.read_text())
    key = next(k for k, p in raw["pieces"].items() if p["role"] == "hand" and "variant" not in p)
    raw["pieces"][key]["name"] = "paw"
    ann_path.write_text(json.dumps(raw))
    r = _build(ann_path, tmp_path / "rig")
    assert r.returncode != 0 and "Traceback" not in r.stderr, r.stderr[-2000:]
    assert f"{key} (hand): name 'paw' must be 'hand'" in r.stderr, r.stderr[-2000:]
