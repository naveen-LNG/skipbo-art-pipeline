"""Task M2: the `arm` role (one whole sleeve per side) exported by spine_rig.py --annotations as a two-bone weighted
mesh in the upper arm's slot (rig_mesh.py), so the elbow bends one drawing instead of showing two pieces' round caps."""
import json
import math
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image, ImageDraw

import rig_annotations as ra
from conftest import ROOT, SCRIPTS
from synth_character import BG, C, make_character


# ------------------------------------------------------------------ the arm role

def test_arm_role_points_and_kinds():
    assert ra.ROLES["arm"] == ("shoulder", "elbow", "wrist")
    assert ra.default_kind("arm", "shoulder") == "round_end"
    assert ra.default_kind("arm", "elbow") == "point"            # where it bends: nothing to snap to
    assert ra.default_kind("arm", "wrist") == "opening"
    assert ra.opening_inward("arm", "wrist", (10.0, 100.0), {"elbow": (10.0, 50.0)}) == pytest.approx((0.0, -1.0))
    assert ra.ROTATE_AXIS["arm"] == ("shoulder", "wrist")


def _arm_key(ann):
    return next(k for k, p in ann.pieces.items() if p.role == "arm")


def test_arm_needs_its_points(tmp_path):
    ann = ra.load(make_character(tmp_path, sleeves=True))
    assert ra.validate(ann) == []
    del ann.pieces[_arm_key(ann)].points["elbow"]
    assert any("missing required point 'elbow'" in e for e in ra.validate(ann))


def test_normalise_turns_a_sleeve_joint_end_up(tmp_path):
    """A sleeve painted lying down (shoulder on the left) comes out shoulder up, wrist straight below; the right
    side's output is the left's mirror (painted_as l)."""
    ann = ra.load(make_character(tmp_path, sleeves=True))
    key = _arm_key(ann)
    path = ra.piece_image(ann, key)
    Image.open(path).rotate(90, expand=True).save(path)        # top to the left
    for pt in ann.pieces[key].points.values():
        pt.at = (pt.at[1], 1.0 - pt.at[0])
        pt.snapped, pt.snap = None, "none"
    ra.snap_all(ann)
    ra.normalise(ann)
    outs = {o.name: o for o in ann.pieces[key].outputs}
    assert set(outs) == {"arm_l", "arm_r"}
    assert not outs["arm_l"].mirrored and outs["arm_r"].mirrored
    for o in outs.values():
        S, E, W = (np.array(o.points[n]) for n in ("shoulder", "elbow", "wrist"))
        assert W[1] - S[1] > 100 and abs(W[0] - S[0]) < 2.0, (o.name, S, W)
        assert S[1] < E[1] < W[1]
        assert o.widths["shoulder"] > 0 and o.widths["wrist"] > 0 and o.depths["wrist"] > 0
        assert (tmp_path / o.file).exists()


# ------------------------------------------------------------------ rig_mesh geometry

def _sleeve_image(w=60, lu=150, lf=140, pad=12):
    """A straight vertical sleeve, round shoulder end, flat cuff: (image, S, E, W) in image px."""
    h = int(lu + lf + w / 2 + 2 * pad)
    im = Image.new("RGBA", (w + 2 * pad, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, top = pad + w / 2, pad + w / 2
    d.ellipse((cx - w / 2, top - w / 2, cx + w / 2, top + w / 2), fill=(170, 50, 120, 255))
    d.rectangle((cx - w / 2, top, cx + w / 2 - 1, top + lu + lf - 1), fill=(170, 50, 120, 255))
    return im, (cx, top), (cx, top + lu), (cx, top + lu + lf)


def test_strip_covers_the_sleeve_with_dense_rows_at_the_elbow():
    import rig_mesh
    im, S, E, W = _sleeve_image()
    alpha = np.asarray(im)[..., 3] > 0
    st = rig_mesh.strip(alpha, S, E, W)
    n = len(st.ts)
    assert st.uv.shape == (2 * n, 2) and len(st.triangles) == 3 * 2 * (n - 1)
    assert st.width == pytest.approx(60, abs=2)
    assert ((np.abs(st.ts) <= 0.6 * st.width + 1e-6).sum()) >= 8      # dense around the elbow
    assert 0.0 in [round(t, 6) for t in st.ts]                         # a row through the elbow itself
    hull = Image.new("1", im.size, 0)                                  # every painted pixel lies inside the hull
    ImageDraw.Draw(hull).polygon([tuple(p) for p in st.uv], fill=1)
    inside = np.asarray(hull, dtype=bool)
    assert not (alpha & ~inside).any()
    # the hull follows the outline (no slack beyond the 1 px margin) along the straight part
    left, right = st.uv[:n], st.uv[n:][::-1]
    mid = (st.ts > -100) & (st.ts < 100)
    assert np.all(np.abs(left[mid, 0] - (S[0] - 30)) <= 1.5) and np.all(np.abs(right[mid, 0] - (S[0] + 30)) <= 1.5)
    tri = st.uv[np.array(st.triangles).reshape(-1, 3)]                  # one orientation, none degenerate
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    cross = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    assert (np.sign(cross) == np.sign(cross[0])).all() and (np.abs(cross) > 1e-6).all()


def _straight(st, S, E, scale=1.0):
    """Setup positions (Spine units, y up) of a straight sleeve hanging down from the origin: both bones carry it
    the same way."""
    def f(p):
        p = np.asarray(p, float)
        return np.stack([(p[..., 0] - S[0]) * scale, -(p[..., 1] - S[1]) * scale], -1)
    O = f(np.array(E))
    return f, f, O


def _bend(P0, u, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    R = np.array([[c, -s], [s, c]])
    return P0 + u @ (R - np.eye(2)).T


def _flipped(P, P0, tris):
    def area(Q):
        a, b, c = Q[tris[:, 0]], Q[tris[:, 1]], Q[tris[:, 2]]
        e1, e2 = b - a, c - a
        return e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    return int((area(P) * np.sign(area(P0)) <= 0).sum())


@pytest.mark.parametrize("need", [(-60.0, 60.0), (-105.0, 93.0), (-155.0, 80.0), (-80.0, 150.0)])
def test_design_is_fold_free_over_the_needed_bend(need):
    """The chosen weights keep every triangle's orientation through the whole needed elbow range (both ways)."""
    import rig_mesh
    im, S, E, W = _sleeve_image()
    st = rig_mesh.strip(np.asarray(im)[..., 3] > 0, S, E, W)
    to_u, to_f, O = _straight(st, S, E)
    m = rig_mesh.choose(st, to_u(st.uv), to_f(st.uv), O, need)
    assert m.ok, m.covered
    tris = np.array(st.triangles).reshape(-1, 3)
    for deg in np.arange(need[0], need[1] + 0.01, 1.0):
        assert _flipped(_bend(m.P0, m.u, deg), m.P0, tris) == 0, deg
    assert m.covered[0] <= need[0] and m.covered[1] >= need[1]


def test_small_bends_keep_the_spec_default():
    """When the default (forearm weight = smoothstep over +-0.5 sleeve width around the elbow) suffices, it is used."""
    import rig_mesh
    im, S, E, W = _sleeve_image()
    st = rig_mesh.strip(np.asarray(im)[..., 3] > 0, S, E, W)
    to_u, to_f, O = _straight(st, S, E)
    m = rig_mesh.choose(st, to_u(st.uv), to_f(st.uv), O, (-40.0, 40.0))
    assert m.design == rig_mesh.DEFAULT
    n = len(st.ts)
    w = m.w[:n]
    assert w[st.ts <= -0.5 * st.width - 1e-6].max() == 0.0 and w[st.ts >= 0.5 * st.width + 1e-6].min() == 1.0
    assert w[np.isclose(st.ts, 0.0)][0] == pytest.approx(0.5)
    assert np.allclose(m.u, m.w[:, None] * (m.P0 - O))                # plain linear blend skinning about the elbow


def _two_bone_rig(tmp_path, im, att, bones_rot=(-90.0, 0.0), O_local=150.0):
    """A hand-built Spine rig: root -> upper (at the origin, pointing down) -> fore (at O_local along it), one slot
    `arm` on the upper bone carrying `att` (image `arm`); animation `bend` turns the forearm 0 -> 100 deg (`unbend` -100)."""
    import spine_qa
    data = {"skeleton": {"x": -150, "y": -320, "width": 300, "height": 340, "images": "./images/"},
            "bones": [{"name": "root"},
                      {"name": "upper", "parent": "root", "rotation": bones_rot[0], "length": O_local},
                      {"name": "fore", "parent": "upper", "x": O_local, "rotation": bones_rot[1], "length": 140}],
            "slots": [{"name": "arm", "bone": "upper", "attachment": "arm"}],
            "skins": [{"name": "default", "attachments": {"arm": {"arm": att}}}],
            "animations": {"bend": {"bones": {"fore": {"rotate": [{"time": 0, "value": 0}, {"time": 1, "value": 100}]}}},
                           "unbend": {"bones": {"fore": {"rotate": [{"time": 0, "value": 0}, {"time": 1, "value": -100}]}}}}}
    (tmp_path / "images").mkdir(exist_ok=True)
    im.save(tmp_path / "images" / "arm.png")
    (tmp_path / "rig.json").write_text(json.dumps(data))
    return spine_qa.Rig(tmp_path / "rig.json")


def test_spine_vertices_reproduce_the_designed_motion(tmp_path):
    """The weighted vertices (bind positions per bone, weights) give exactly P0 at the setup pose and P0 + (R - I) u
    at any elbow angle, as spine_qa (Spine's formula) evaluates them; hull = every vertex, in outline order."""
    import rig_mesh
    import spine_qa
    im, S, E, W = _sleeve_image()
    st = rig_mesh.strip(np.asarray(im)[..., 3] > 0, S, E, W)
    to_u, to_f, O = _straight(st, S, E)
    m = rig_mesh.choose(st, to_u(st.uv), to_f(st.uv), O, (-110.0, 110.0))
    assert m.ok, m.covered
    upper = ((0.0, 0.0), -90.0)
    fore = ((float(O[0]), float(O[1])), -90.0)
    att = rig_mesh.attachment(st, m, upper, fore, 1, 2, im.size)
    assert att["type"] == "mesh" and att["hull"] == len(att["uvs"]) // 2 and (att["width"], att["height"]) == im.size
    rig = _two_bone_rig(tmp_path, im, att, O_local=float(-O[1]))
    tris = np.array(att["triangles"]).reshape(-1, 3)
    for anim, t, deg in ((None, 0.0, 0.0), ("bend", 0.5, 50.0), ("bend", 1.0, 100.0), ("unbend", 0.75, -75.0)):
        world, _ = rig.pose(anim, t)
        got = rig.mesh_world("arm", "arm", world)
        assert np.allclose(got, _bend(m.P0, m.u, deg), atol=0.02), (anim, t)
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    assert spine_qa.mesh_fold_setup(rig) == {}
    for anim in ("bend", "unbend"):
        out = spine_qa.check_anim(rig, canvas, anim, 30, tmp_path / "qa")
        assert out["mesh_fold"] == {}, out["mesh_fold"]
    # each triangle belongs to the bone on its side of the elbow row (the elbow pivot lies on both parts)
    bones = rig.mesh_tri_bones("arm", "arm")
    rows = st.uv[tris].mean(1)[:, 1] - E[1]
    assert all(b == "upper" for b, r in zip(bones, rows) if r < -1) and all(b == "fore" for b, r in zip(bones, rows) if r > 1)


# ------------------------------------------------------------------ building the synthetic sleeve rig

def _build(ann_path, out, *extra):
    root = ann_path.parent
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(root / "master.png"),
           "--annotations", str(ann_path), "--name", "synth", "--out", str(out), *extra]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


@pytest.fixture(scope="module")
def sleeve_rig(tmp_path_factory):
    root = tmp_path_factory.mktemp("sleeves")
    # no tail: the synthetic tail does not touch the hips (spine_qa's attached check fails on it with or without sleeves)
    ann = make_character(root, sleeves=True, pose_variants=True, tail=False)
    out = root / "rig"
    r = _build(ann, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return root, out


def _skel(out):
    return json.loads((out / "synth.json").read_text())


@pytest.mark.slow
def test_sleeve_rig_writes_one_mesh_per_arm(sleeve_rig):
    _, out = sleeve_rig
    skel = _skel(out)
    slots = {s["name"]: s for s in skel["slots"]}
    skin = skel["skins"][0]["attachments"]
    bones = {b["name"]: b for b in skel["bones"]}
    for s in "lr":
        assert f"forearm_{s}" not in slots and f"forearm_{s}" not in skin    # the mesh draws the forearm too
        assert bones[f"forearm_{s}"]["parent"] == f"upperarm_{s}" and bones[f"hand_{s}"]["parent"] == f"forearm_{s}"
        assert slots[f"upperarm_{s}"]["attachment"] == f"synth_arm_{s}"
        assert list(skin[f"upperarm_{s}"]) == [f"synth_arm_{s}"]          # no raised-sleeve swap for a mesh arm
        att = skin[f"upperarm_{s}"][f"synth_arm_{s}"]
        assert att["type"] == "mesh" and att["hull"] == len(att["uvs"]) // 2
        assert len(att["vertices"]) > len(att["uvs"])                     # weighted
        assert (out / "images" / f"synth_arm_{s}.png").exists()
    for anim in skel["animations"].values():                              # nothing keys the missing raised sleeve
        for s in "lr":
            assert f"upperarm_{s}" not in anim.get("slots", {})
    report = json.loads((out / "report.json").read_text())
    for s in "lr":
        m = report["meshes"][f"upperarm_{s}"]
        assert m["arm"] == f"arm_{s}" and m["fold_free"] is True
        assert m["covered_deg"][0] <= m["need_deg"][0] and m["covered_deg"][1] >= m["need_deg"][1]
        assert report["parts"][f"upperarm_{s}"]["method"] == "mesh" and report["parts"][f"forearm_{s}"]["method"] == "mesh"
    assert "synth_upperarm_l_raised" in report["mesh_skipped_variants"]
    assert not [d for d in report["doubts"] if d["reason"] in ("not_placed", "matcher_disagreement", "stretch")], \
        report["doubts"]


def _canvas_master_mask(rig, canvas, root, out):
    """The master's sleeve pixels (by colour) in QA canvas px, through the master frame recorded in report.json."""
    m = np.asarray(Image.open(root / "master.png").convert("RGB")).astype(int)
    sleeve = np.abs(m - np.array(C["sleeve"])).sum(2) < 40
    fr = json.loads((out / "report.json").read_text())["master_frame"]
    k = fr["units_per_px"]
    x0, y0 = canvas.point(-fr["mid_x"] * k, fr["ground_y"] * k)
    im = Image.fromarray(sleeve).resize((round(m.shape[1] * k * canvas.S), round(m.shape[0] * k * canvas.S)), Image.NEAREST)
    t = np.asarray(im)
    mm = np.zeros((canvas.H, canvas.W), bool)
    X0, Y0 = int(round(x0)), int(round(y0))
    xs, ys = slice(max(0, X0), min(canvas.W, X0 + t.shape[1])), slice(max(0, Y0), min(canvas.H, Y0 + t.shape[0]))
    mm[ys, xs] = t[ys.start - Y0: ys.stop - Y0, xs.start - X0: xs.stop - X0]
    return mm


@pytest.mark.slow
def test_setup_mesh_matches_the_straight_sleeve(sleeve_rig):
    import spine_qa
    root, out = sleeve_rig
    rig = spine_qa.Rig(out / "synth.json")
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    _, _, _, alphas = spine_qa.render(rig, canvas, None, 0.0)
    want = _canvas_master_mask(rig, canvas, root, out)
    for s in "lr":
        got = alphas[f"upperarm_{s}"]
        side = np.zeros_like(want)
        ys, xs = np.nonzero(got)
        side[:, max(0, xs.min() - 20): xs.max() + 20] = True
        w = want & side
        iou = (got & w).sum() / max(1, (got | w).sum())
        assert iou >= 0.9, (s, iou)


def _elbow_range(skel, s):
    vals = [k["value"] for a in skel["animations"].values() for k in a.get("bones", {}).get(f"forearm_{s}", {}).get("rotate", [])]
    return min(vals + [0.0]), max(vals + [0.0])


@pytest.mark.slow
def test_elbow_sweep_never_folds(sleeve_rig, tmp_path):
    """From the setup pose to the largest elbow bend any animation uses + 10 deg, both ways: no triangle flips."""
    import spine_qa
    _, out = sleeve_rig
    skel = _skel(out)
    for s in "lr":
        lo, hi = _elbow_range(skel, s)
        assert hi - lo > (80 if s == "l" else 20)              # hold_card and wave bend the left elbow both ways
        skel["animations"][f"sweep_{s}"] = {"bones": {f"forearm_{s}": {"rotate": [
            {"time": 0, "value": 0.0}, {"time": 1, "value": lo - 10}, {"time": 2, "value": 0.0},
            {"time": 3, "value": hi + 10}]}}}
    (out / "sweep.json").write_text(json.dumps(skel))
    rig = spine_qa.Rig(out / "sweep.json")
    canvas = spine_qa.Canvas(rig, 400)
    for s in "lr":
        res = spine_qa.check_anim(rig, canvas, f"sweep_{s}", 30, tmp_path / "qa")
        assert res["mesh_fold"] == {}, (s, res["mesh_fold"])


# What the synthetic character fails with or without sleeves (its two-piece build fails the same, a little worse): the
# head's overlap with the torso is under 3% of the smaller part, and the arms' fast cheer/wave sweeps move the hand
# just past MAX_POS_JUMP (0.0126 two-piece). Nothing else may fail.
FIXTURE_FAILS = {("structure", "weak_joints"): {"head_base"}, ("cheer_jump", "jerky_bones"): {"hand_l", "hand_r"},
                 ("wave", "jerky_bones"): {"hand_l"}}


@pytest.mark.slow
def test_sleeve_rig_passes_spine_qa(sleeve_rig):
    root, out = sleeve_rig
    r = subprocess.run([sys.executable, str(SCRIPTS / "spine_qa.py"), str(out / "synth.json"), "--master",
                        str(root / "master.png")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode in (0, 1), r.stderr[-3000:]
    rep = json.loads((out / "qa" / "report.json").read_text())
    for check, res in rep.items():
        for key, val in res.items():
            if key in ("pass", "frames", "duration", "silhouette_iou", "seams", "thumbs", "sockets", "landmarks",
                       "unchecked", "draw_order") or not val or not isinstance(val, dict):
                continue
            assert set(val) <= FIXTURE_FAILS.get((check, key), set()), (check, key, val)
        for k in ("setup", "seams", "thumbs", "sockets", "landmarks", "idle", "point", "thumbs_up", "hold_card",
                  "emotions"):
            assert rep[k]["pass"], (k, rep[k])
    assert rep["structure"]["mesh_fold"] == {} and not rep["structure"]["pivot_off_joint"]
    for anim in ("hold_card", "cheer_jump", "wave", "point", "thumbs_up"):
        assert rep[anim]["mesh_fold"] == {} and not rep[anim]["detached"] and not rep[anim]["joint_holes"], rep[anim]
        assert not rep[anim]["unstitched"] and not rep[anim]["occluded"], rep[anim]
    assert "synth_hand_l/synth_arm_l" in rep["sockets"]["sockets"]


@pytest.mark.slow
def test_forearm_bone_owns_the_lower_sleeve(sleeve_rig):
    """The forearm bone has a part (the mesh's lower triangles), so the hand's joint checks run against it."""
    import spine_qa
    _, out = sleeve_rig
    rig = spine_qa.Rig(out / "synth.json")
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    _, world, _, alphas = spine_qa.render(rig, canvas, "hold_card", 1.2)
    masks = spine_qa.bone_masks(rig, alphas)
    for s in "lr":
        assert masks[f"forearm_{s}"].sum() > 0.3 * masks[f"upperarm_{s}"].sum()
        jx, jy = canvas.point(world[f"hand_{s}"][4], world[f"hand_{s}"][5])        # the wrist on the forearm part
        assert spine_qa.dilate(masks[f"forearm_{s}"], 3)[int(jy), int(jx)]
    res = spine_qa.check_anim(rig, canvas, "hold_card", 30, out / "qa_hold")
    assert not res["detached"] and not res["joint_holes"] and not res["unstitched"], res


@pytest.mark.slow
def test_resolved_with_sleeves(sleeve_rig):
    root, out = sleeve_rig
    res = json.loads((out / "annotations.resolved.json").read_text())
    ann = ra.load(root / "annotations.json")
    outs = {o.name: o for p in ann.pieces.values() for o in p.outputs}
    for s in "lr":
        a = res["attachments"][f"synth_arm_{s}"]
        assert a["slot"] == f"upperarm_{s}" and a["variant"] is None and a["side"] == s
        for n in ("shoulder", "elbow", "wrist"):                 # bind image px = the output image's px
            assert a["points"][n] == pytest.approx(list(outs[f"arm_{s}"].points[n]), abs=0.01)
        assert f"synth_forearm_{s}" not in res["attachments"] and f"synth_upperarm_{s}" not in res["attachments"]
    socks = {(x["child"], x["child_point"], x["parent"], x["parent_point"]): x["width"] for x in res["sockets"]}
    for s in "lr":
        assert socks[(f"synth_hand_{s}", "wrist", f"synth_arm_{s}", "wrist")] == pytest.approx(37 * 0.8)
    pb = {}
    for s in "lr":
        pb.update({f"shoulder_{s}": f"upperarm_{s}", f"elbow_{s}": f"forearm_{s}", f"wrist_{s}": f"hand_{s}",
                   f"hip_{s}": f"leg_{s}", f"ankle_{s}": f"boot_{s}"})
    assert res["point_bones"] == pb


@pytest.mark.slow
def test_sleeve_trimmed_at_the_wrist(tmp_path):
    """The sleeve loses its hand-coloured pixels past its wrist rim like a forearm (a fur tuft painted on the cuff),
    its rim inset is recorded for the socket check (on the sleeve's attachment), and with hand over_forearm the hand
    is drawn over the mesh."""
    ann = ra.load(make_character(tmp_path, sleeves=True))
    ann.master.layers["hand"] = "over_forearm"
    ra.save(ann)
    o = next(o for p in ann.pieces.values() for o in p.outputs if o.name == "arm_l")
    im = Image.open(tmp_path / o.file).convert("RGBA")
    wx, wy = o.points["wrist"]
    ImageDraw.Draw(im).ellipse((wx - 10, wy - 2, wx + 10, wy + 6), fill=C["hand"] + (255,))   # a tuft over the cuff
    im.save(tmp_path / o.file)
    out = tmp_path / "rig"
    r = _build(ann.path, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    trim = json.loads((out / "report.json").read_text())["parts"]["forearm_l"]["wrist_trim"]
    assert trim["trimmed_px"] > 20, trim
    a = np.asarray(Image.open(out / "images" / "synth_arm_l.png").convert("RGBA")).astype(int)
    white = (np.abs(a[..., :3] - np.array(C["hand"])).sum(2) < 30) & (a[..., 3] > 127)
    assert white[int(wy) + 1:].sum() == 0                                  # nothing hand-coloured left past the rim
    res = json.loads((out / "annotations.resolved.json").read_text())
    assert res["attachments"]["synth_arm_l"]["rim_inset"]["wrist"] > 0
    assert "rim_inset" not in res["attachments"]["synth_arm_r"]            # untouched on the other side
    order = [s["name"] for s in _skel(out)["slots"]]
    assert order.index("upperarm_l") < order.index("hand_l")


@pytest.mark.slow
def test_sleeve_sheet_at_its_own_scale(tmp_path):
    """A sleeve sheet generated on its own paints at its own scale (the real fox's: ~1.8x the body sheet's). The
    sleeve is scaled by its shoulder -> elbow -> wrist length against the master's, so it still lands on the master's
    joints without stretch doubts."""
    import spine_qa
    ann = ra.load(make_character(tmp_path, sleeves=True, tail=False))
    p = ann.pieces[_arm_key(ann)]
    for o in p.outputs:
        im = Image.open(tmp_path / o.file)
        im.resize((round(im.width * 1.6), round(im.height * 1.6)), Image.LANCZOS).save(tmp_path / o.file)
        o.points = {n: (x * 1.6, y * 1.6) for n, (x, y) in o.points.items()}
        o.widths = {n: w * 1.6 for n, w in o.widths.items()}
        o.depths = {n: d * 1.6 for n, d in o.depths.items()}
    ra.save(ann)
    out = tmp_path / "rig"
    r = _build(ann.path, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    report = json.loads((out / "report.json").read_text())
    assert not [d for d in report["doubts"] if d["reason"] == "stretch"], report["doubts"]
    assert report["meshes"]["upperarm_l"]["scale_vs_sheet"] == pytest.approx(1 / 1.6, abs=0.01)
    rig = spine_qa.Rig(out / "synth.json")
    res = json.loads((out / "annotations.resolved.json").read_text())
    assert spine_qa.check_landmarks(rig, res)["pass"], spine_qa.check_landmarks(rig, res)


@pytest.mark.slow
def _under_torso_rig(tmp_path, back_point=False, **kw):
    ann = ra.load(make_character(tmp_path, sleeves=True, tail=False, **kw))
    ann.master.layers["upperarm"] = "under_torso"
    if back_point:                      # a point hand showing its back: the point hold goes across the body
        ann.pieces[next(k for k, p in ann.pieces.items() if p.variant == "point")].facing = "back"
        ra.snap_all(ann)
        ra.normalise(ann)
    ra.save(ann)
    out = tmp_path / "rig"
    r = _build(ann.path, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return out


@pytest.mark.slow
def test_sleeve_under_the_torso_crosses_in_front_while_holding(tmp_path):
    """upperarm under_torso: the sleeve mesh sits under the torso at rest (the straps over its top); while the forearm
    crosses the belly (hold_card) a drawOrder key moves the sleeve just above the torso: during the raise, on the last
    frame before the forearm reaches the torso, back during the lower on the first frame after it has left (so the
    layer changes while the forearm is clear of the torso). Holds out to the side (synth palm-facing point,
    thumbs_up) and wave / cheer keep the rest order."""
    import spine_qa
    out = _under_torso_rig(tmp_path)
    skel = _skel(out)
    order = [s["name"] for s in skel["slots"]]
    assert order.index("upperarm_l") < order.index("torso") and order.index("upperarm_r") < order.index("torso")
    keys = skel["animations"]["hold_card"]["drawOrder"]
    t_in, t_out = keys[0]["time"], keys[1]["time"]
    assert 0.0 < t_in < 0.6 and 1.8 < t_out < 2.35 and "offsets" not in keys[1], keys
    for anim in ("point", "thumbs_up", "wave", "cheer_jump", "idle"):
        assert "drawOrder" not in skel["animations"][anim], anim
    rig = spine_qa.Rig(out / "synth.json")
    for t, above in ((0.0, False), (t_in - 0.02, False), (t_in, True), (1.2, True), (t_out - 0.02, True),
                     (t_out, False), (2.4, False)):
        o = rig.draw_order("hold_card", t)
        assert (o.index("upperarm_l") > o.index("torso")) == above, (t, o)
        assert o.index("upperarm_r") < o.index("torso")                   # only the holding arm moves
    _hands_hug_their_sleeves(rig, "below")                                # hand under_forearm: tucked under the cuff
    assert t_in == round(round(t_in * 30) / 30, 4)                        # the key lands on a sampled frame
    res_ = json.loads((out / "annotations.resolved.json").read_text())
    assert spine_qa.check_layer_order(rig, res_)["pass"]
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    res = spine_qa.check_anim(rig, canvas, "hold_card", 30, out / "qa")
    assert res["mesh_fold"] == {} and not res["occluded"] and not res["detached"], res
    _, _, _, al = spine_qa.render(rig, canvas, "hold_card", 1.2)
    lower = spine_qa.bone_masks(rig, al)["forearm_l"]
    assert (lower & al["torso"]).sum() > 0.3 * lower.sum()               # the forearm really lies over the belly


@pytest.mark.slow
def test_across_point_moves_the_sleeve_too(tmp_path):
    out = _under_torso_rig(tmp_path, back_point=True)
    skel = _skel(out)
    assert json.loads((out / "report.json").read_text())["gestures"]["point"]["l"]["pose"] == "across"
    assert "drawOrder" in skel["animations"]["point"] and "drawOrder" in skel["animations"]["hold_card"]
    assert "drawOrder" not in skel["animations"]["thumbs_up"]


@pytest.mark.slow
def test_glove_over_the_sleeve_follows_it(tmp_path):
    """hand over_forearm with a sleeve mesh: the hand is drawn just above the sleeve at rest and moves with it while
    holding (both slots in the drawOrder key)."""
    import spine_qa
    ann = ra.load(make_character(tmp_path, sleeves=True, tail=False))
    ann.master.layers.update({"upperarm": "under_torso", "hand": "over_forearm"})
    ra.save(ann)
    out = tmp_path / "rig"
    r = _build(ann.path, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    order = [s["name"] for s in _skel(out)["slots"]]
    assert order.index("hand_l") == order.index("upperarm_l") + 1 and order.index("hand_l") < order.index("torso")
    rig = spine_qa.Rig(out / "synth.json")
    o = rig.draw_order("hold_card", 1.2)
    assert o.index("hand_l") == o.index("upperarm_l") + 1 and o.index("upperarm_l") > o.index("torso")
    _hands_hug_their_sleeves(rig, "above")
    res = json.loads((out / "annotations.resolved.json").read_text())
    assert {(x["slot"], x["over"], x["relation"]) for x in res["layer_order"]} == \
        {("hand_l", "upperarm_l", "above"), ("hand_r", "upperarm_r", "above")}
    assert spine_qa.check_layer_order(rig, res)["pass"]


def _hands_hug_their_sleeves(rig, relation):
    """In the setup pose and every frame of every animation, each hand is drawn directly below (under_forearm) or
    directly above (over_forearm) its sleeve mesh's slot."""
    step = -1 if relation == "below" else 1
    for anim in [None] + list(rig.data["animations"]):
        n = 1 if anim is None else int(round(rig.duration(anim) * 30)) + 1
        for i in range(n):
            o = rig.draw_order(anim, i / 30)
            for s in "lr":
                assert o.index(f"hand_{s}") == o.index(f"upperarm_{s}") + step, (anim, i, s, o)


@pytest.mark.slow
def test_layer_order_check_catches_a_glove_over_the_cuff(tmp_path):
    """spine_qa layer_order: a hand drawn on the wrong side of its forearm / sleeve slot (against master.layers.hand)
    in any frame fails, naming the pair and the frames; the two-piece rig passes too."""
    import spine_qa
    out = _under_torso_rig(tmp_path)
    res = json.loads((out / "annotations.resolved.json").read_text())
    assert {(x["slot"], x["over"], x["relation"]) for x in res["layer_order"]} == \
        {("hand_l", "upperarm_l", "below"), ("hand_r", "upperarm_r", "below")}
    skel = _skel(out)
    names = [x["name"] for x in skel["slots"]]
    i, j = names.index("hand_l"), names.index("upperarm_l")
    skel["slots"][i], skel["slots"][j] = skel["slots"][j], skel["slots"][i]           # the glove over the cuff
    skel["animations"]["hold_card"].pop("drawOrder")
    (out / "bad.json").write_text(json.dumps(skel))
    bad = spine_qa.check_layer_order(spine_qa.Rig(out / "bad.json"), res)
    assert bad["pass"] is False and "hand_l/upperarm_l" in bad["wrong"] and "hand_r/upperarm_r" not in bad["wrong"]
    two = tmp_path / "two"
    two.mkdir()
    ann = ra.load(make_character(two, tail=False))
    ra.save(ann)
    r = _build(ann.path, two / "rig")
    assert r.returncode == 0, r.stderr[-2000:]
    res2 = json.loads((two / "rig" / "annotations.resolved.json").read_text())
    assert {(x["slot"], x["over"], x["relation"]) for x in res2["layer_order"]} == \
        {("hand_l", "forearm_l", "below"), ("hand_r", "forearm_r", "below")}
    assert spine_qa.check_layer_order(spine_qa.Rig(two / "rig" / "synth.json"), res2)["pass"]


@pytest.mark.slow
def test_two_piece_arms_get_no_draw_order(tmp_path):
    ann = ra.load(make_character(tmp_path, tail=False))
    ann.master.layers["upperarm"] = "under_torso"
    ra.save(ann)
    out = tmp_path / "rig"
    r = _build(ann.path, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert not any("drawOrder" in a for a in _skel(out)["animations"].values())


# ------------------------------------------------------------------ T20: width fit and a round elbow

def _tube_master(width=40.0, above_x=None):
    """A plain master: one vertical sleeve-coloured tube (x centre 100, the given width) on the background, from
    y 20 to 380; above_x: a darker part drawn over the tube's left side, up to that x (a vest edge)."""
    im = Image.new("RGB", (200, 400), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((100 - width / 2, 20, 100 + width / 2 - 1, 380), fill=C["sleeve"])
    above = np.zeros((400, 200), bool)
    if above_x is not None:
        d.rectangle((0, 0, above_x - 1, 399), fill=(40, 50, 90))
        above[:, :above_x] = True
    rgb = np.asarray(im, dtype=np.float32) / 255
    fg = np.abs(np.asarray(im, int) - np.array(BG)).sum(2) > 30
    return rgb, fg, above


def _sleeve_alpha(width=60.0):
    """A sleeve drawing at the master's scale (S, E, W at x 50; y 20, 200, 380), `width` wide."""
    a = np.zeros((400, 100), bool)
    a[20:381, int(round(50 - width / 2)):int(round(50 + width / 2))] = True
    return a, (50.0, 20.0), (50.0, 200.0), (50.0, 380.0)


def test_width_fit_matches_the_masters_sleeve():
    """A sleeve painted 1.5x as wide as the master's: each half is narrowed across its axis to the master's width
    (factor 2/3), centred on the master's tube; nothing moves along the axis."""
    import rig_mesh
    rgb, fg, _ = _tube_master(40.0)
    alpha, S, E, W = _sleeve_alpha(60.0)
    M = ((100.0, 20.0), (100.0, 200.0), (100.0, 380.0))
    fit = rig_mesh.width_fit(rgb, fg, M, alpha, (S, E, W), 1.0)
    for half in ("upper", "lower"):
        h = fit[half]
        assert h["raw"] == pytest.approx(40 / 60, abs=0.03), h
        assert h["factor"] == pytest.approx(40 / 60, abs=0.03) and abs(h["offset_px"]) < 1.5, h
    P = rig_mesh.fitted(np.array([[20.0, 100.0], [80.0, 100.0], [20.0, 300.0], [80.0, 300.0], [20.0, 200.0]]), fit)
    assert P[1, 0] - P[0, 0] == pytest.approx(40, abs=1.5) and P[3, 0] - P[2, 0] == pytest.approx(40, abs=1.5)
    assert np.allclose(P[:, 1], [100, 100, 300, 300, 200])


def test_width_fit_never_widens_and_clamps():
    import rig_mesh
    rgb, fg, _ = _tube_master(40.0)
    M = ((100.0, 20.0), (100.0, 200.0), (100.0, 380.0))
    alpha, S, E, W = _sleeve_alpha(30.0)                                   # thinner than the master's: left alone
    fit = rig_mesh.width_fit(rgb, fg, M, alpha, (S, E, W), 1.0)
    assert fit["upper"]["factor"] == 1.0 and abs(fit["upper"]["offset_px"]) < 1.5 and fit["upper"]["raw"] > 1.0
    alpha, S, E, W = _sleeve_alpha(90.0)                                   # 2.25x: clamped
    fit = rig_mesh.width_fit(rgb, fg, M, alpha, (S, E, W), 1.0)
    assert fit["upper"]["factor"] == pytest.approx(rig_mesh.WIDTH_FIT_MIN) and fit["upper"]["raw"] < 0.5


def test_width_fit_skips_a_sleeve_edge_hidden_under_another_part():
    """The moose's upper sleeve runs under its vest: an edge whose far side is a part drawn over the sleeve is not the
    sleeve's edge, so that half is not measured (factor 1); a part the sleeve is drawn over does not hide it."""
    import rig_mesh
    rgb, fg, above = _tube_master(40.0, above_x=95)
    alpha, S, E, W = _sleeve_alpha(60.0)
    M = ((100.0, 20.0), (100.0, 200.0), (100.0, 380.0))
    hidden = rig_mesh.width_fit(rgb, fg, M, alpha, (S, E, W), 1.0, above=above)
    assert hidden["upper"]["factor"] == 1.0 and hidden["upper"]["raw"] is None
    shown = rig_mesh.width_fit(rgb, fg, M, alpha, (S, E, W), 1.0, above=None)    # the vest under the sleeve
    assert shown["upper"]["raw"] == pytest.approx(25 / 60, abs=0.04)        # what shows of it: 95..120


def _knit(rgb, x0, x1, amp=0.06):
    """Knit ripple across columns x0..x1: alternate 3-px bands lightened / darkened by amp (a step over EDGE_JUMP
    whose far side is still the same cloth)."""
    for x in range(x0, x1, 3):
        rgb[:, x:x + 3] = np.clip(rgb[:, x:x + 3] + (amp if (x // 3) % 2 else -amp), 0, 1)


def test_width_fit_reads_a_knit_ripple_as_cloth_not_an_edge():
    """The beaver's knit sleeve: ripples inside the sleeve step by more than EDGE_JUMP back into the same cloth; the
    edges are where the background starts, so the master's tube is measured whole and centred."""
    import rig_mesh
    rgb, fg, _ = _tube_master(40.0)
    rgb = rgb.copy()
    _knit(rgb, 80, 120)
    alpha, S, E, W = _sleeve_alpha(60.0)
    M = ((100.0, 20.0), (100.0, 200.0), (100.0, 380.0))
    fit = rig_mesh.width_fit(rgb, fg, M, alpha, (S, E, W), 1.0)
    for half in ("upper", "lower"):
        assert fit[half]["raw"] == pytest.approx(40 / 60, abs=0.03) and abs(fit[half]["offset_px"]) < 1.5, fit[half]


def test_width_fit_does_not_find_an_edge_deep_under_a_part_of_the_same_yarn():
    """The beaver's sweater body is drawn over its sleeves in the same yarn: a walk that goes in under it finds no
    crease at its outline, then a ripple well inside it - the body's own shading, not the sleeve's edge - so the
    sleeve's edge on that side is hidden (as on the mirrored side, where no ripple happens to lie in reach)."""
    import rig_mesh
    rgb, fg, above = _tube_master(40.0, above_x=95)
    rgb = rgb.copy()
    rgb[:, 40:95] = rgb[:, 100:101]                                         # the body: the sleeve's own colour
    fg[:, 40:95] = True
    rgb[:, 70:76] = np.clip(rgb[:, 70:76] + 0.1, 0, 1)                      # a ripple 20 px in under the body
    alpha, S, E, W = _sleeve_alpha(60.0)
    M = ((100.0, 20.0), (100.0, 200.0), (100.0, 380.0))
    fit = rig_mesh.width_fit(rgb, fg, M, alpha, (S, E, W), 1.0, above=above)
    for half in ("upper", "lower"):
        assert fit[half]["raw"] is None and fit[half]["factor"] == 1.0 and fit[half]["offset_px"] == 0.0, fit[half]


def test_width_fit_recentres_only_when_both_halves_are_measured():
    """No sideways jog at the elbow at setup: with both halves measured, each is centred on the master's tube; with
    one hidden, neither moves sideways - the measured half narrows about the drawing's own centre."""
    import rig_mesh
    rgb, fg, _ = _tube_master(40.0)
    rgb_v, fg_v, above = _tube_master(40.0, above_x=95)                   # a vest over the upper sleeve only
    rgb, fg = rgb.copy(), fg.copy()
    rgb[:200], fg[:200], above[200:] = rgb_v[:200], fg_v[:200], False
    alpha, S, E, W = _sleeve_alpha(60.0)
    S, E, W = ((x + 6.0, y) for x, y in (S, E, W))                       # the drawing's joint line off its tube centre
    M = ((100.0, 20.0), (100.0, 200.0), (100.0, 380.0))
    both = rig_mesh.width_fit(*_tube_master(40.0)[:2], M, alpha, (S, E, W), 1.0)
    for half in ("upper", "lower"):
        assert both[half]["raw"] is not None and both[half]["offset_px"] != 0.0
    one = rig_mesh.width_fit(rgb, fg, M, alpha, (S, E, W), 1.0, above=above)
    assert one["upper"]["raw"] is None and one["lower"]["raw"] is not None
    P = np.array([[x, y] for y in (60.0, 200.0, 340.0) for x in (20.0, 80.0)])     # left / right edges, 3 rows
    Q = rig_mesh.fitted(P, one)
    centres = (Q[0::2, 0] + Q[1::2, 0]) / 2
    assert np.allclose(centres, (P[0, 0] + P[1, 0]) / 2, atol=0.5), centres  # the tube's centre stays put
    assert Q[5, 0] - Q[4, 0] == pytest.approx(40, abs=1.5)                  # the forearm still narrowed


def _widen_sleeve(ann, root, k=1.5):
    """Paint the whole-sleeve outputs k x as wide (across their axis, x), length unchanged."""
    p = ann.pieces[_arm_key(ann)]
    for o in p.outputs:
        im = Image.open(root / o.file)
        im.resize((round(im.width * k), im.height), Image.LANCZOS).save(root / o.file)
        o.points = {n: (x * k, y) for n, (x, y) in o.points.items()}
        o.widths = {n: w * k for n, w in o.widths.items()}


def _setup_width(canvas, alpha, out, P, d):
    """Width (master px) of the rendered setup-pose mask `alpha` across direction d (master px, image y down)
    through master point P."""
    fr = json.loads((out / "report.json").read_text())["master_frame"]
    k = fr["units_per_px"]
    c = np.array(canvas.point((P[0] - fr["mid_x"]) * k, (fr["ground_y"] - P[1]) * k))
    n = np.array([d[1], -d[0]]) / math.hypot(*d)
    run = [0, 0]
    for i, sgn in enumerate((1, -1)):
        for s in range(1, 800):
            x, y = (c + sgn * s * n).astype(int)
            if not alpha[y, x]:
                break
            run[i] = s
    return (run[0] + run[1] + 1) / (k * canvas.S)


@pytest.mark.slow
def test_sleeve_painted_too_wide_is_fitted_to_the_master(tmp_path):
    """A sleeve sheet painted 1.5x too wide: at the setup pose the mesh is as wide as the master's sleeve (within 5%)
    across the upper arm and the forearm; report.json records the factors."""
    import spine_qa
    from synth_character import TRUTH
    ann = ra.load(make_character(tmp_path, sleeves=True, tail=False))
    master = {k: np.array(v) for k, v in TRUTH["master"].items()}
    _widen_sleeve(ann, tmp_path)
    ra.save(ann)
    out = tmp_path / "rig"
    r = _build(ann.path, out)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    rig = spine_qa.Rig(out / "synth.json")
    canvas = spine_qa.Canvas(rig, 2400)
    _, _, _, alphas = spine_qa.render(rig, canvas, None, 0.0)
    for s in "lr":
        S, E, W = master[f"shoulder_{s}"], master[f"elbow_{s}"], master[f"wrist_{s}"]
        up = _setup_width(canvas, alphas[f"upperarm_{s}"], out, (S + E) / 2, E - S)
        lo = _setup_width(canvas, alphas[f"upperarm_{s}"], out, E + 0.35 * (W - E), W - E)
        assert up == pytest.approx(42.0, rel=0.05) and lo == pytest.approx(2 * (20 - 1.5 * 0.35), rel=0.05), (s, up, lo)
    report = json.loads((out / "report.json").read_text())
    wf = report["parts"]["upperarm_l"]["width_fit"]
    assert wf["upper"]["factor"] == pytest.approx(1 / 1.5, abs=0.05) and wf["lower"]["factor"] == pytest.approx(1 / 1.5, abs=0.05)
    assert not [d for d in report["doubts"] if d["reason"] == "sleeve_too_wide"]


def test_smooth_binds_survive_the_files_rounding(tmp_path):
    """A smooth design's lever u is not proportional to its weight: a vertex with a tiny forearm weight and a real
    lever must still be reproduced by the written (rounded) binds, as spine_qa evaluates them."""
    import rig_mesh
    im, S, E, W = _sleeve_image()
    st = rig_mesh.strip(np.asarray(im)[..., 3] > 0, S, E, W)
    to_u, to_f, O = _straight(st, S, E)
    m = rig_mesh.choose(st, to_u(st.uv), to_f(st.uv), O, (-105.0, 93.0))
    assert m.design[0] == "smooth"
    w = m.w.copy()
    w[(st.ts[st.row()] < 0) & (np.linalg.norm(m.u, axis=1) > 1)] = 1.3e-4   # rounds to 1e-4 in the file: 23% off
    m = rig_mesh.Motion(m.design, m.P0, m.u, w, m.q, m.covered, m.ok)
    att = rig_mesh.attachment(st, m, ((0.0, 0.0), -90.0), ((float(O[0]), float(O[1])), -90.0), 1, 2, im.size)
    rig = _two_bone_rig(tmp_path, im, att, O_local=float(-O[1]))
    for anim, t, deg in (("bend", 0.9, 90.0), ("unbend", 1.0, -100.0)):
        world, _ = rig.pose(anim, t)
        assert np.abs(rig.mesh_world("arm", "arm", world) - _bend(m.P0, m.u, deg)).max() < 0.05, anim


def _polylines(st, P):
    n = len(st.ts)
    return P[:n], P[n:][::-1]


def _turns(poly):
    """Signed turning angle (deg) at each interior vertex of a polyline, skipping zero-length segments."""
    seg = np.diff(poly, axis=0)
    seg = seg[np.linalg.norm(seg, axis=1) > 1e-6]
    ang = np.degrees(np.arctan2(seg[:, 1], seg[:, 0]))
    return (np.diff(ang) + 180) % 360 - 180


def _self_crossing(poly) -> bool:
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    for i in range(len(poly) - 1):
        for j in range(i + 2, len(poly) - 1):
            p, q, r_, s_ = poly[i], poly[i + 1], poly[j], poly[j + 1]
            if cross(p, q, r_) * cross(p, q, s_) < 0 and cross(r_, s_, p) * cross(r_, s_, q) < 0:
                return True
    return False


@pytest.mark.parametrize("w,lu,lf", [(60, 150, 140), (100, 160, 150)])     # a long forearm, and the fox's 1.5 widths
def test_elbow_stays_round_when_bent(w, lu, lf):
    """The fox's holds (hold_card -88 deg, thumbs_up +72; need -98..82 with the margin), and a 90 deg bend: the outer
    edge of the elbow is one convex curve without a corner (no vertex turns by more than 15 deg), the inner edge
    does not cross itself (a crease, not a fold), and the crease leaves no gap at its corner (notch)."""
    import rig_mesh
    im, S, E, W = _sleeve_image(w=w, lu=lu, lf=lf)
    st = rig_mesh.strip(np.asarray(im)[..., 3] > 0, S, E, W)
    to_u, to_f, O = _straight(st, S, E)
    m = rig_mesh.choose(st, to_u(st.uv), to_f(st.uv), O, (-98.0, 82.0))
    assert m.ok, m.covered
    near = np.abs(st.ts) <= 1.2 * st.width                                  # the elbow, not the shoulder cap or cuff
    for deg in (-90.0, -88.0, 72.0):
        left, right = (p[near] for p in _polylines(st, _bend(m.P0, m.u, deg)))
        lens = [np.linalg.norm(np.diff(p, axis=0), axis=1).sum() for p in (left, right)]
        outer, inner = (left, right) if lens[0] > lens[1] else (right, left)
        t = _turns(outer)
        sign = np.sign(t.sum())
        assert (t * sign >= -3.0).all(), (deg, np.round(t, 1))                # convex: it only turns one way
        assert np.abs(t).max() <= 15.0, (deg, np.round(t, 1))                  # round: no corner
        assert not _self_crossing(inner), deg
    assert m.design[0] == "smooth"                                          # the crease closes at its corner
    assert rig_mesh.notch(st, m.P0, m.u, m.design[1:3], (-88.0, 72.0)) <= rig_mesh.NOTCH_MAX


@pytest.mark.parametrize("w,lu,lf", [(60, 150, 140), (100, 160, 150)])
def test_smooth_design_is_scale_invariant_and_keeps_the_shoulder_rigid(w, lu, lf):
    """The band is in sleeve widths whatever the setup's units per image px (the fox's ~0.53, the moose's ~0.38): the
    same design at every scale, and the rows above the shoulder point never move with the elbow."""
    import rig_mesh
    im, S, E, W = _sleeve_image(w=w, lu=lu, lf=lf)
    st = rig_mesh.strip(np.asarray(im)[..., 3] > 0, S, E, W)
    designs = []
    for scale in (0.35, 0.5, 1.0):
        to_u, to_f, O = _straight(st, S, E, scale=scale)
        assert rig_mesh.units_per_px(st, to_u(st.uv)) == pytest.approx(scale, rel=1e-6)
        m = rig_mesh.choose(st, to_u(st.uv), to_f(st.uv), O, (-98.0, 82.0))
        assert m.ok and m.design[0] == "smooth", m.design
        designs.append(m.design)
        above = st.ts[st.row()] <= st.t_shoulder + 1e-6
        assert above.any() and np.abs(m.u[above]).max() < 1e-6 * scale * w
        assert m.design[1] * st.width >= st.t_shoulder - 1e-6               # the band never reaches above the shoulder
    assert designs[0] == designs[1] == designs[2], designs
