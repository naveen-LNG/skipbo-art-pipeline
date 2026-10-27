"""spine_qa renders Spine mesh attachments (weighted and unweighted) and flags folded triangles (mesh_fold).

A hand-built rig: root -> upper (shoulder at (0, 200), pointing down) -> lower (elbow at (0, 100), pointing down).
One slot "arm" on the upper bone carries a 60 x 200 image spanning shoulder to wrist, as a region attachment or
as a 2 x 3-vertex strip mesh: top row on the upper bone, middle row 50/50, bottom row on the lower bone."""
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

import spine_qa

W_IMG, H_IMG = 60, 200
SHOULDER, ELBOW = (0.0, 200.0), (0.0, 100.0)
GRID = [(i, j) for j in range(3) for i in range(2)]           # (column, row); vertex k = 2 * row + column
HULL = [0, 1, 3, 5, 4, 2]                                     # outline order of the grid vertices


def _world(i: int, j: int):
    """Setup-pose world position of grid vertex (column i, row j): image px (60 i, 100 j), top at the shoulder."""
    return -W_IMG / 2 + W_IMG * i, SHOULDER[1] - 100.0 * j


def _local(origin, p):
    """Bone-local coordinates of world point p for a bone at origin pointing straight down (rotation -90)."""
    return -(p[1] - origin[1]), p[0]


def _image(kind: str) -> Image.Image:
    im = Image.new("RGBA", (W_IMG, H_IMG), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if kind == "solid":
        d.rectangle((0, 0, W_IMG - 1, H_IMG - 1), fill=(200, 80, 40, 255))
    else:                                                     # asymmetric: a wedge wide at the top left
        d.polygon([(2, 2), (W_IMG - 3, 10), (W_IMG // 2, H_IMG - 3), (4, H_IMG - 30)], fill=(40, 120, 200, 255))
    return im


def _mesh(weighted: bool) -> dict:
    tris = []
    for j in range(2):
        a, b, c, d = 2 * j, 2 * j + 1, 2 * j + 2, 2 * j + 3
        tris += [a, b, c, b, d, c]
    uvs, verts = [], []
    for i, j in GRID:
        uvs += [i * 1.0, j / 2]
        p = _world(i, j)
        if not weighted:
            verts += list(_local(SHOULDER, p))
        elif j == 0:
            verts += [1, 1, *_local(SHOULDER, p), 1.0]
        elif j == 1:
            verts += [2, 1, *_local(SHOULDER, p), 0.5, 2, *_local(ELBOW, p), 0.5]
        else:
            verts += [1, 2, *_local(ELBOW, p), 1.0]
    return {"type": "mesh", "uvs": uvs, "triangles": tris, "vertices": verts, "hull": 6, "width": W_IMG, "height": H_IMG}


def make_rig(tmp_path, kind: str = "weighted", image: str = "solid", hand_x: float | None = None):
    """kind: weighted | unweighted | region. hand_x: also a 50 x 50 hand (region) on a bone at the wrist, parented
    to the lower bone, its centre hand_x along the hand bone."""
    if kind == "region":
        att = {"x": 100, "y": 0, "rotation": 90, "width": W_IMG, "height": H_IMG}
    else:
        att = _mesh(kind == "weighted")
    rot = lambda v: [{"time": 0, "value": v}, {"time": 0.2, "value": v}]
    data = {
        "skeleton": {"x": -100, "y": 0, "width": 200, "height": 220, "images": "./images/"},
        "bones": [{"name": "root"},
                  {"name": "upper", "parent": "root", "x": SHOULDER[0], "y": SHOULDER[1], "rotation": -90, "length": 100},
                  {"name": "lower", "parent": "upper", "x": 100, "length": 100}],
        "slots": [{"name": "arm", "bone": "upper", "attachment": "arm"}],
        "skins": [{"name": "default", "attachments": {"arm": {"arm": att}}}],
        "animations": {"bend60": {"bones": {"lower": {"rotate": rot(60)}}},
                       "fold170": {"bones": {"lower": {"rotate": [{"time": 0, "value": 0}, {"time": 1, "value": 170}]}}}},
    }
    if hand_x is not None:
        data["bones"].append({"name": "hand", "parent": "lower", "x": 100, "length": 30})
        data["slots"].append({"name": "hand", "bone": "hand", "attachment": "hand"})
        data["skins"][0]["attachments"]["hand"] = {"hand": {"x": hand_x, "y": 0, "rotation": 90, "width": 50, "height": 50}}
    d = tmp_path / kind
    (d / "images").mkdir(parents=True)
    _image(image).save(d / "images" / "arm.png")
    Image.new("RGBA", (50, 50), (90, 60, 30, 255)).save(d / "images" / "hand.png")
    (d / "rig.json").write_text(json.dumps(data))
    return spine_qa.Rig(d / "rig.json")


def _alpha(rig, anim=None, t=0.0):
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    _, _, _, alphas = spine_qa.render(rig, canvas, anim, t)
    return alphas["arm"], canvas


def _iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


@pytest.mark.parametrize("image", ["solid", "wedge"])
def test_weighted_setup_matches_region(tmp_path, image):
    mesh, _ = _alpha(make_rig(tmp_path, "weighted", image))
    region, _ = _alpha(make_rig(tmp_path, "region", image))
    assert region.sum() > 1000
    assert (mesh ^ region).sum() <= 0.01 * region.sum(), ((mesh ^ region).sum(), region.sum())


@pytest.mark.parametrize("image", ["solid", "wedge"])
def test_unweighted_matches_region(tmp_path, image):
    mesh, _ = _alpha(make_rig(tmp_path, "unweighted", image))
    region, _ = _alpha(make_rig(tmp_path, "region", image))
    assert (mesh ^ region).sum() <= 0.01 * region.sum(), ((mesh ^ region).sum(), region.sum())


def test_mesh_colours_match_region(tmp_path):
    rigs = [make_rig(tmp_path, k, "wedge") for k in ("weighted", "region")]
    frames = []
    for rig in rigs:
        canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
        frames.append(np.asarray(spine_qa.render(rig, canvas, None, 0)[0].convert("RGB"), dtype=float))
    inner = _alpha(rigs[1])[0]
    inner = ~spine_qa.dilate(~inner, 2)                       # away from the anti-aliased edge
    assert np.abs(frames[0] - frames[1])[inner].mean() < 2.0


def _expected_bent(canvas, deg: float) -> np.ndarray:
    """The strip's outline with the lower bone rotated by deg: rows 0 / 1 / 2 on the upper bone / 50-50 / lower bone."""
    def place(origin, theta, loc):
        c, s = math.cos(math.radians(theta)), math.sin(math.radians(theta))
        return origin[0] + loc[0] * c - loc[1] * s, origin[1] + loc[0] * s + loc[1] * c
    pts = []
    for i, j in GRID:
        p = _world(i, j)
        up = place(SHOULDER, -90, _local(SHOULDER, p))
        lo = place(ELBOW, -90 + deg, _local(ELBOW, p))
        pts.append(up if j == 0 else lo if j == 2 else ((up[0] + lo[0]) / 2, (up[1] + lo[1]) / 2))
    im = Image.new("L", (canvas.W, canvas.H), 0)
    ImageDraw.Draw(im).polygon([canvas.point(*pts[k]) for k in HULL], fill=255)
    return np.asarray(im) > 127


def test_child_rotation_bends_the_strip(tmp_path):
    rig = make_rig(tmp_path, "weighted")
    bent, canvas = _alpha(rig, "bend60", 0.1)
    straight, _ = _alpha(rig)
    assert _iou(bent, _expected_bent(canvas, 60)) >= 0.98
    assert _iou(bent, straight) < 0.8                         # it really moved


def test_mesh_fold_quiet_on_a_bend(tmp_path):
    rig = make_rig(tmp_path, "weighted")
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    st = spine_qa.check_structure(rig, canvas)
    assert st["mesh_fold"] == {} and st["pass"], st
    out = spine_qa.check_anim(rig, canvas, "bend60", 30, tmp_path / "qa")
    assert out["mesh_fold"] == {} and out["pass"], out


def test_mesh_fold_flags_a_170_degree_fold(tmp_path):
    rig = make_rig(tmp_path, "weighted")
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    out = spine_qa.check_anim(rig, canvas, "fold170", 30, tmp_path / "qa")
    assert out["pass"] is False
    f = out["mesh_fold"]["arm"]
    assert f["frames"] >= 1 and f["worst"]["flipped"] >= 1
    assert f["worst"]["t"] == pytest.approx(1.0, abs=0.05)    # the deepest fold is at the end
    json.dumps(out)


def test_mesh_fold_flags_a_fold_baked_into_the_setup(tmp_path):
    rig = make_rig(tmp_path, "weighted")
    rig.bones[2]["rotation"] = 170                            # the setup pose itself is folded
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    st = spine_qa.check_structure(rig, canvas)
    assert "arm" in st["mesh_fold"] and st["pass"] is False, st["mesh_fold"]


def test_region_att_matrix_unchanged(tmp_path):
    rig = make_rig(tmp_path, "region")
    world, _ = rig.pose(None, 0)
    M = rig.att_matrix("arm", "arm", world)
    assert np.allclose(spine_qa._xy(M, (0, 0)), (-30, 200)) and np.allclose(spine_qa._xy(M, (60, 200)), (30, 0))


def test_mesh_att_matrix_fits_the_setup(tmp_path):
    """A mesh has no single matrix; att_matrix gives the best affine fit (sockets / thumbs keep working)."""
    rig = make_rig(tmp_path, "weighted")
    world, _ = rig.pose(None, 0)
    M = rig.att_matrix("arm", "arm", world)
    assert np.allclose(spine_qa._xy(M, (0, 0)), (-30, 200), atol=1e-6)
    assert np.allclose(spine_qa._xy(M, (60, 200)), (30, 0), atol=1e-6)


def test_weighted_mesh_splits_into_bone_masks(tmp_path):
    """Each triangle's pixels go to the bone with the highest mean weight: the strip's top band to the upper bone, the
    bottom band to the lower bone, split at the 50/50 row (the elbow)."""
    rig = make_rig(tmp_path, "weighted")
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    _, _, _, alphas = spine_qa.render(rig, canvas, None, 0)
    masks = spine_qa.bone_masks(rig, alphas)
    assert set(masks) == {"upper", "lower"}
    up, lo = np.nonzero(masks["upper"])[0], np.nonzero(masks["lower"])[0]
    elbow_y = canvas.point(*ELBOW)[1]
    assert abs(up.max() - elbow_y) <= 3 and abs(lo.min() - elbow_y) <= 3, (up.max(), lo.min(), elbow_y)   # px rows vs a continuous y
    assert abs(len(up) - len(lo)) <= 0.02 * len(up)
    assert ((masks["upper"] | masks["lower"]) == alphas["arm"]).all()


def test_hand_on_the_mesh_forearm_passes_its_joint_checks(tmp_path):
    rig = make_rig(tmp_path, "weighted", hand_x=15)           # the hand reaches 10 units up into the sleeve
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    st = spine_qa.check_structure(rig, canvas)
    assert st["pass"], st
    out = spine_qa.check_anim(rig, canvas, "bend60", 30, tmp_path / "qa")
    assert out["pass"], out
    assert not out["detached"] and not out["joint_holes"] and not out["unstitched"]


def test_hand_off_the_mesh_forearm_is_detached(tmp_path):
    """The joint checks really run against the forearm's share of the mesh: a hand 35 units past the wrist fails."""
    rig = make_rig(tmp_path, "weighted", hand_x=60)
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    out = spine_qa.check_anim(rig, canvas, "bend60", 30, tmp_path / "qa")
    assert "hand" in out["detached"] and "hand" in out["joint_holes"], out
    assert "hand" in spine_qa.check_structure(rig, canvas)["pivot_off_joint"]


def test_mesh_point_is_exact_in_the_bent_half(tmp_path):
    rig = make_rig(tmp_path, "weighted")
    world, _ = rig.pose("bend60", 0.1)
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    p = (10.0, 180.0)                                         # in triangle (2, 3, 4): rows 1 and 2, bent by 60 deg

    def place(origin, theta, loc):
        c, s = math.cos(math.radians(theta)), math.sin(math.radians(theta))
        return np.array([origin[0] + loc[0] * c - loc[1] * s, origin[1] + loc[0] * s + loc[1] * c])
    v = {}
    for k, (i, j) in enumerate(GRID):
        w = _world(i, j)
        up, lo = place(SHOULDER, -90, _local(SHOULDER, w)), place(ELBOW, -30, _local(ELBOW, w))
        v[k] = up if j == 0 else lo if j == 2 else (up + lo) / 2
    s_, t_ = p[0] / W_IMG, (p[1] - 100) / 100                 # p = v2 + s (v3 - v2) + t (v4 - v2)
    want = v[2] + s_ * (v[3] - v[2]) + t_ * (v[4] - v[2])
    got = spine_qa.mesh_point(rig, "arm", "arm", world, p)
    px = lambda q: np.array(canvas.point(*q))
    assert np.linalg.norm(px(got) - px(want)) <= 0.5
    assert np.allclose(spine_qa.att_point(rig, "arm", "arm", world, p), got)
    lsq = spine_qa._xy(rig.att_matrix("arm", "arm", world), p)
    assert np.linalg.norm(px(lsq) - px(want)) > 5             # the best-fit affine would be well off


GOLDEN = Path(__file__).resolve().parent / "golden" / "qa_region.json"


def _snapshot(rig, outdir) -> dict:
    """Everything spine_qa says about a region-only rig: per-frame hashes of each slot's alpha mask and of the composite,
    and the structure, seams and per-animation reports (json round-tripped)."""
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    frames = {}
    times = [(None, 0.0)] + [("bend60", i / 30) for i in range(7)] + [("fold170", i / 30) for i in range(0, 31, 5)]
    for anim, t in times:
        frame, _, _, alphas = spine_qa.render(rig, canvas, anim, t)
        frames[f"{anim or 'setup'}@{t:.3f}"] = {
            "frame": hashlib.sha256(frame.tobytes()).hexdigest(),
            **{k: [int(v.sum()), hashlib.sha256(np.packbits(v).tobytes()).hexdigest()] for k, v in alphas.items()}}
    rep = {"structure": spine_qa.check_structure(rig, canvas),
           "seams": spine_qa.check_seams(rig, canvas, [(None, 0.0), ("bend60", 0.1), ("fold170", 0.5)])}
    for anim in ("bend60", "fold170"):
        rep[anim] = spine_qa.check_anim(rig, canvas, anim, 30, outdir)
    return json.loads(json.dumps({"frames": frames, "reports": rep}))


def test_region_rig_golden(tmp_path):
    """Region-only rigs must keep rendering and reporting exactly as before mesh support (the golden matches 40997eb's
    spine_qa; regenerate with QA_GOLDEN_REGEN=1 only when a change to region behaviour is intended)."""
    got = _snapshot(make_rig(tmp_path, "region", "wedge", hand_x=15), tmp_path / "qa")
    if os.environ.get("QA_GOLDEN_REGEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
    want = json.loads(GOLDEN.read_text())
    assert got["frames"] == want["frames"]
    assert got["reports"] == want["reports"]


def test_draw_order_timeline_reorders_slots(tmp_path):
    """Spine 4.2 drawOrder keys: from 0.5 s the arm slot is drawn above the hand (offset +1), from 1.0 s (a key with
    no offsets) in the setup order again. render composites, and reports alphas, in the keyed order."""
    rig = make_rig(tmp_path, "weighted", hand_x=15)
    rig.data["animations"]["swap"] = {"drawOrder": [{"time": 0.5, "offsets": [{"slot": "arm", "offset": 1}]},
                                                    {"time": 1.0}]}
    assert [s["name"] for s in rig.slots] == ["arm", "hand"]
    assert rig.draw_order("swap", 0.2) == ["arm", "hand"]
    assert rig.draw_order("swap", 0.5) == ["hand", "arm"] and rig.draw_order("swap", 0.9) == ["hand", "arm"]
    assert rig.draw_order("swap", 1.0) == ["arm", "hand"] and rig.draw_order(None, 0.7) == ["arm", "hand"]
    assert rig.duration("swap") == 1.0
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    before, _, _, a0 = spine_qa.render(rig, canvas, "swap", 0.2)
    after, _, _, a1 = spine_qa.render(rig, canvas, "swap", 0.7)
    assert list(a0) == ["arm", "hand"] and list(a1) == ["hand", "arm"]
    both = a0["arm"] & a0["hand"]
    assert both.sum() > 50
    ys, xs = np.nonzero(both)
    y, x = int(np.median(ys)), int(np.median(xs))
    hand_rgb, arm_rgb = (90, 60, 30), (200, 80, 40)
    assert np.abs(np.asarray(before)[y, x, :3].astype(int) - hand_rgb).sum() < 10      # the hand on top
    assert np.abs(np.asarray(after)[y, x, :3].astype(int) - arm_rgb).sum() < 10        # the sleeve on top


def test_draw_order_offsets_follow_spine():
    """Spine's rule: each keyed slot goes to (setup index + offset); the others fill the free places in setup order."""
    assert spine_qa.apply_offsets(["a", "b", "c", "d", "e"], [{"slot": "b", "offset": 2}]) == ["a", "c", "d", "b", "e"]
    assert spine_qa.apply_offsets(["a", "b", "c", "d"], [{"slot": "d", "offset": -3}]) == ["d", "a", "b", "c"]
    assert spine_qa.apply_offsets(["a", "b", "c"], []) == ["a", "b", "c"]
