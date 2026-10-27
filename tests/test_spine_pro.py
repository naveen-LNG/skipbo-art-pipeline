"""spine_pro.py: upgrading a built rig with container, underfill, tail chain, chest, face/ears, planted feet, colours
and secondary motion, on the synthetic character; plus spine_qa's evaluation of the new constructs."""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from conftest import ROOT, SCRIPTS
from synth_character import make_character

import pro_common as pc
import qa_constraints
import spine_qa


def _build_legacy(root: Path) -> Path:
    ann = make_character(root, pose_variants=True)
    out = root / "rig"
    r = subprocess.run([sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(root / "master.png"),
                        "--annotations", str(ann), "--name", "synth", "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return out / "synth.json"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("pro")
    legacy = _build_legacy(root)
    before = legacy.read_bytes()
    import spine_pro
    rep = spine_pro.build(legacy, root / "pro")
    return root, legacy, root / "pro" / "synth.json", rep, before


def _data(p):
    return json.loads(Path(p).read_text())


def test_legacy_rig_untouched(built):
    root, legacy, pro, rep, before = built
    assert legacy.read_bytes() == before
    assert (root / "pro" / "synth.atlas").exists() and (root / "pro" / "preview.html").exists()
    assert "spine-player@4.2." in (root / "pro" / "preview.html").read_text()
    assert not spine_qa.Rig(legacy).extended                      # legacy rigs never take the extended path


def test_container_and_shadow(built):
    _, _, pro, rep, _ = built
    d = _data(pro)
    by = {b["name"]: b for b in d["bones"]}
    assert by["character"]["parent"] == "root" and by["hips"]["parent"] == "character"
    assert all("root" not in a.get("bones", {}) for a in d["animations"].values())
    assert d["slots"][0]["name"] == "shadow" and by["shadow"]["parent"] == "root"
    jump = d["animations"]["cheer_jump"]
    assert "translate" in jump["bones"]["character"] and "rgba" in jump["slots"]["shadow"]
    alpha = [int(k["color"][6:], 16) for k in jump["slots"]["shadow"]["rgba"]]
    assert min(alpha) < 200 and alpha[0] == 255                  # fades in the air, opaque on the ground


def _weights(d, att):
    bones = d["bones"]
    v, k, out = att["vertices"], 0, []
    while k < len(v):
        c = int(v[k])
        k += 1
        w = {}
        for _ in range(c):
            w[bones[int(v[k])]["name"]] = v[k + 3]
            k += 4
        out.append(w)
    return out


def test_tail_chain_weighted_mesh(built):
    _, _, pro, rep, _ = built
    d = _data(pro)
    chain = rep["stages"]["tail"]["bones"]
    assert chain[0] == "tail" and len(chain) >= 3
    for b in chain[1:]:
        assert pc.bone(d, b)["parent"] == chain[chain.index(b) - 1]
    rest = next(s_ for s_ in d["slots"] if s_["name"] == "tail")["attachment"]
    for name, att in d["skins"][0]["attachments"]["tail"].items():
        if name != rest:                                               # pose variants stay rigid regions on `tail`
            assert att.get("type", "region") == "region"
            continue
        assert att["type"] == "mesh"
        ws = _weights(d, att)
        assert len(ws) == len(att["uvs"]) // 2
        assert all(abs(sum(w.values()) - 1) < 1e-3 for w in ws)
        assert all(len(w) <= 2 for w in ws)                            # narrow blend bands: two bones at most
        assert any(w == {chain[-1]: 1.0} for w in ws)                  # rigid tip
        assert set().union(*ws) == set(chain)


def test_chest_breathing_and_inherit(built):
    _, _, pro, _, _ = built
    d = _data(pro)
    for n in ("upperarm_l", "upperarm_r", "head_base"):
        b = pc.bone(d, n)
        assert b["parent"] == "chest" and b["inherit"] == "noScale"
    torso = d["skins"][0]["attachments"]["torso"]
    att = next(iter(torso.values()))
    assert att["type"] == "mesh" and set().union(*_weights(d, att)) == {"torso", "chest"}
    assert "scale" in d["animations"]["idle"]["bones"]["chest"]
    # breathing scales the chest, not the arms: the upper arm's world scale stays 1 at the breath's peak
    rig = spine_qa.Rig(pro)
    w, _ = rig.pose("idle", 1.0)
    a, b, c, dd, _, _ = w["upperarm_l"]
    assert abs(math.hypot(a, c) - 1) < 1e-6 and abs(math.hypot(b, dd) - 1) < 1e-6
    a, b, c, dd, _, _ = w["chest"]
    assert math.hypot(b, dd) > 1.01


def test_head_face_meshes(built):
    _, _, pro, rep, _ = built
    d = _data(pro)
    heads = d["skins"][0]["attachments"]["head"]
    assert heads and all(a["type"] == "mesh" for a in heads.values())
    for a in heads.values():
        ws = _weights(d, a)
        assert max(w.get("face", 0) for w in ws) > 0.3
        assert all(w.get("face", 0) <= 0.45 + 1e-3 for w in ws)
    look = d["animations"]["look_around"]["bones"]["face"]["translate"]
    assert max(abs(k["x"]) + abs(k["y"]) for k in look) > 5


def test_feet_planted_in_idle(built):
    _, _, pro, rep, _ = built
    rig = spine_qa.Rig(pro)
    assert rig.extended
    names = [c["name"] for c in rig.data.get("ik", [])] + [c["name"] for c in rig.data.get("transform", [])]
    assert names
    for c in rig.data.get("transform", []):
        assert c["mixScaleX"] == 0 and c["mixScaleY"] == 0 and c["mixShearY"] == 0
    hips, boots = [], []
    for t in np.linspace(0, 2.0, 9):
        w, _ = rig.pose("idle", float(t))
        hips.append((w["hips"][4], w["hips"][5]))
        boots.append([(w[f][4], w[f][5], pc.angle(w[f])) for f in ("boot_l", "boot_r")])
    hips, boots = np.array(hips), np.array(boots)
    assert np.ptp(hips, axis=0).max() > 1.0                          # the hips bob ...
    assert np.ptp(boots[..., :2], axis=0).max() < 0.05                # ... over planted feet
    assert np.ptp(boots[..., 2], axis=0).max() < 0.05


def test_feet_reproduce_legacy_motion(built):
    """Baked targets: in walk and cheer_jump each foot's world pose equals the legacy rig's."""
    _, legacy, pro, _, _ = built
    L, P = spine_qa.Rig(legacy), spine_qa.Rig(pro)
    for anim in ("walk", "cheer_jump", "squat"):
        for t in np.linspace(0, L.duration(anim), 7):
            wl, _ = L.pose(anim, float(t))
            wp, _ = P.pose(anim, float(t))
            for f in ("boot_l", "boot_r"):
                assert math.hypot(wl[f][4] - wp[f][4], wl[f][5] - wp[f][5]) < 0.6, (anim, t, f)
                dr = (pc.angle(wl[f]) - pc.angle(wp[f]) + 180) % 360 - 180
                assert abs(dr) < 0.3, (anim, t, f, dr)


def test_underfill_slots(built):
    _, _, pro, rep, _ = built
    d = _data(pro)
    names = [s["name"] for s in d["slots"]]
    made = rep["stages"]["underfill"]["slots"]
    assert {"head", "hips", "hand_l", "tail"} <= set(made)
    first_part = min(names.index(p_) for p_ in names if p_ != "shadow" and not p_.endswith("_under"))
    for part in made:
        i = names.index(f"{part}_under")
        assert 0 < i < first_part                                      # one block behind every part, above the shadow
        sk = d["skins"][0]["attachments"]
        assert set(sk[f"{part}_under"]) == {f"{a}_under" for a in sk[part]}
    for anim, A in d["animations"].items():
        for slot, tl in A.get("slots", {}).items():
            if slot in made and "attachment" in tl:
                mirror = A["slots"][f"{slot}_under"]["attachment"]
                assert [k.get("name") and k["name"][:-6] for k in mirror] == [k.get("name") for k in tl["attachment"]]
        for key in A.get("drawOrder", []):                             # every key keeps the underfills at the back
            order = spine_qa.apply_offsets(names, key.get("offsets", []))
            parts_at = [order.index(p_) for p_ in order if p_ != "shadow" and not p_.endswith("_under")]
            assert all(order.index(f"{part}_under") < min(parts_at) for part in made)


def test_bone_colours(built):
    _, _, pro, _, _ = built
    d = _data(pro)
    col = {b["name"]: b.get("color") for b in d["bones"]}
    assert col["boot_l_ik"] == pc.GREEN and col["chest"] == pc.YELLOW and col["face"] == pc.YELLOW
    assert col["character"] == pc.RED and col["tail2"] == pc.RED


def test_new_animations_and_secondary(built):
    _, legacy, pro, rep, _ = built
    d = _data(pro)
    for a in ("idle", "look_around", "talk"):
        assert a in d["animations"]
    assert abs(pc.duration(d, "idle") - 2.0) < 1e-6
    talk = d["animations"]["talk"]
    assert len(talk["slots"]["head"]["attachment"]) > 6 and "scale" in talk["bones"]["head_base"]
    # every legacy animation got breathing and tail overlap on top
    for a in _data(legacy)["animations"]:
        if pc.duration(d, a) >= 0.5:
            assert "rotate" in d["animations"][a]["bones"].get("tail2", {}), a
    sec = rep["stages"]["secondary"]
    assert sec["cheer_jump"]["tail"] > 3                              # the jump throws the tail
    # loops stay loops
    rig = spine_qa.Rig(pro)
    for a in ("idle", "walk"):
        w0, _ = rig.pose(a, 0.0)
        w1, _ = rig.pose(a, rig.duration(a))
        assert all(np.allclose(w0[n], w1[n], atol=1e-2) for n in w0), a


def test_skip_stages(tmp_path, built):
    root, legacy, _, _, _ = built
    import spine_pro
    rep = spine_pro.build(legacy, tmp_path / "p", skip=("tail", "torso", "head", "feet", "anims", "secondary", "underfill"))
    d = _data(tmp_path / "p" / "synth.json")
    assert pc.has_bone(d, "character") and not pc.has_bone(d, "chest") and not pc.has_bone(d, "tail2")
    assert "transform" not in d and "ik" not in d
    assert set(rep["stages"]) == {"container", "organise"}


@pytest.mark.slow
def test_qa_adds_no_failures(built):
    """spine_qa on the pro rig: no check fails that passes on the legacy synthetic rig (the synthetic tail is a
    known legacy failure), for structure and three animations."""
    _, legacy, pro, _, _ = built
    L, P = spine_qa.Rig(legacy), spine_qa.Rig(pro)
    cl, cp = spine_qa.Canvas(L, 380), spine_qa.Canvas(P, 380)
    sl, sp = spine_qa.check_structure(L, cl), spine_qa.check_structure(P, cp)
    for k in ("pivot_off_joint", "reversed_bones", "weak_joints", "slivers", "fragments", "draw_order", "mesh_fold"):
        new = set(sp[k]) - set(sl[k])
        assert not new, (k, sp[k])
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        for anim in ("walk", "cheer_jump"):
            rl = spine_qa.check_anim(L, cl, anim, 30, Path(td))
            rp = spine_qa.check_anim(P, cp, anim, 30, Path(td))
            for k in ("detached", "joint_holes", "unstitched", "jerky_bones", "occluded", "mesh_fold"):
                new = set(rp[k]) - set(rl[k])
                assert not new, (anim, k, rp[k])


# ------------------------------------------------------------------ qa_constraints on hand-made skeletons

def _skel(bones, **extra):
    return {"skeleton": {"height": 100, "images": "./"}, "bones": bones, "slots": [], "skins": [{"name": "default", "attachments": {}}],
            "animations": {}, **extra}


def test_inherit_noscale_matches_spine():
    bones = [{"name": "root"}, {"name": "p", "parent": "root", "rotation": 30, "scaleX": 2, "scaleY": 2},
             {"name": "n", "parent": "p", "x": 10, "rotation": 15},
             {"name": "s", "parent": "p", "x": 10, "rotation": 15, "inherit": "noScale"},
             {"name": "t", "parent": "p", "x": 10, "rotation": 15, "inherit": "onlyTranslation"}]
    w = qa_constraints.pose_world(_skel(bones), None, 0, spine_qa.interp)
    # same position for all three (the parent's full matrix carries the offset)
    assert np.allclose(w["n"][4:], w["s"][4:]) and np.allclose(w["n"][4:], w["t"][4:])
    a, b, c, d = w["s"][:4]
    assert abs(math.hypot(a, c) - 1) < 1e-9 and abs(math.hypot(b, d) - 1) < 1e-9
    assert abs(math.degrees(math.atan2(c, a)) - 45) < 1e-6                 # rotation still inherited
    a, b, c, d = w["t"][:4]
    assert abs(math.degrees(math.atan2(c, a)) - 15) < 1e-6                 # onlyTranslation: own rotation only


def test_normal_inherit_matches_legacy_pose(tmp_path):
    bones = [{"name": "root"}, {"name": "a", "parent": "root", "x": 5, "y": 2, "rotation": 40, "scaleX": 1.2},
             {"name": "b", "parent": "a", "x": 30, "rotation": -70, "scaleY": 0.8}]
    data = _skel(bones)
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data))
    legacy = spine_qa.Rig(p).pose(None, 0)[0]
    ext = qa_constraints.pose_world(data, None, 0, spine_qa.interp)
    for n in legacy:
        assert np.allclose(legacy[n], ext[n])


def test_transform_constraint_absolute():
    bones = [{"name": "root"}, {"name": "hips", "parent": "root", "y": 50},
             {"name": "foot", "parent": "hips", "x": 10, "y": -40, "rotation": 5},
             {"name": "foot_ik", "parent": "root", "x": 12, "y": 8, "rotation": 20}]
    con = [{"name": "plant", "bones": ["foot"], "target": "foot_ik", "mixScaleX": 0, "mixScaleY": 0, "mixShearY": 0}]
    data = _skel(bones, transform=con)
    data["animations"]["bob"] = {"bones": {"hips": {"translate": [{"time": 0, "y": 0}, {"time": 1, "y": -9}]}}}
    for t in (0.0, 0.5, 1.0):
        w = qa_constraints.pose_world(data, "bob", t, spine_qa.interp)
        assert np.allclose(w["foot"][4:], (12, 8))
        assert abs(pc.angle(w["foot"]) - 20) < 1e-6
    half = dict(con[0], mixRotate=0.5, mixX=0.5)
    w = qa_constraints.pose_world(_skel(bones, transform=[half]), None, 0, spine_qa.interp)
    assert np.allclose(w["foot"][4:], ((10 + 12) / 2, (10 + 8) / 2)) and abs(pc.angle(w["foot"]) - 12.5) < 1e-6


def test_one_bone_ik_stretch_and_compress():
    bones = [{"name": "root"}, {"name": "hips", "parent": "root", "y": 100},
             {"name": "leg", "parent": "hips", "rotation": -90, "length": 80},
             {"name": "boot", "parent": "leg", "x": 80},
             {"name": "t", "parent": "root", "x": 30, "y": 10}]
    ik = [{"name": "leg_ik", "bones": ["leg"], "target": "t", "compress": True, "stretch": True}]
    w = qa_constraints.pose_world(_skel(bones, ik=ik), None, 0, spine_qa.interp)
    assert np.allclose(w["boot"][4:], (30, 10), atol=1e-6)                  # the leg reaches the target exactly
    ik[0]["stretch"] = ik[0]["compress"] = False
    w = qa_constraints.pose_world(_skel(bones, ik=ik), None, 0, spine_qa.interp)
    d = np.array(w["boot"][4:]) - np.array(w["leg"][4:])
    assert abs(np.linalg.norm(d) - 80) < 1e-6 and abs(d[1] / d[0] - (10 - 100) / 30) < 1e-6


def test_slot_colour_and_decor(tmp_path):
    keys = [{"time": 0, "color": "ffffffff"}, {"time": 1, "color": "ffffff00"}]
    data = {"animations": {"a": {"slots": {"shadow": {"rgba": keys}}}}}
    c = qa_constraints.slot_color(data, {"name": "shadow", "color": "ffffffff"}, "a", 0.5)
    assert abs(c[3] - 0.5) < 0.01
    assert qa_constraints.slot_color(data, {"name": "x"}, "a", 0.5) is None


def test_torso_reaching_below_the_waist(built, tmp_path):
    """A torso drawing that hangs far below the waist (dungarees): the part below the waist is weighted to the hips,
    so the torso bone still points into its own part (spine_qa structure), and pro_report records the doubt."""
    import shutil
    import spine_pro
    root, legacy, _, _, _ = built
    src = tmp_path / "rig"
    shutil.copytree(legacy.parent, src)
    d = _data(src / "synth.json")
    torso = d["skins"][0]["attachments"]["torso"]
    att = next(iter(torso.values()))
    att["x"] = att.get("x", 0.0) - 0.45 * pc.bone(d, "torso").get("length", 200)     # slide the drawing down the bone
    (src / "synth.json").write_text(json.dumps(d))
    rep = spine_pro.build(src / "synth.json", tmp_path / "pro")
    st = rep["stages"]["torso"]
    assert st["weights"][0] == "hips" and st["doubts"][0]["reason"] == "torso_below_waist"
    rig = spine_qa.Rig(tmp_path / "pro" / "synth.json")
    res = spine_qa.check_structure(rig, spine_qa.Canvas(rig, 380))
    assert "torso" not in res["reversed_bones"] and "chest" not in res["reversed_bones"]
    assert rep["stages"]["torso"]["doubts"][0]["own_cos_after"] > 0.3
