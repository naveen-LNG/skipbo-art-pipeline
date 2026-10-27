"""The synthetic test character: a drawn figure, its raw pieces and a confirmed annotations.json."""
import json

import numpy as np
from PIL import Image

import rig_annotations as ra
import rig_hands as rh
from synth_character import make_character

HAND_VARIANTS = ("open", "fist", "point", "thumbsup", "grip")


def _outputs(ann):
    return {o.name: (p, o) for p in ann.pieces.values() for o in p.outputs}


def test_make_character_valid(tmp_path):
    path = make_character(tmp_path)
    assert path == tmp_path / "annotations.json"
    ann = ra.load(path)                                   # raises on any validation error
    assert ra.validate(ann) == []
    assert ann.master.status == "confirmed"
    assert ann.pieces and all(p.status == "confirmed" for p in ann.pieces.values())
    assert ann.master.hands == {"l": {"thumb_side": "lateral", "facing": "palm"},
                                "r": {"thumb_side": "lateral", "facing": "palm"}}
    assert ann.master.layers == {}
    master = Image.open(tmp_path / ann.master.image)
    assert master.size == (600, 900)
    assert master.convert("RGB").getpixel((2, 2)) == (214, 214, 214)
    for key in ann.pieces:                                # every key resolves to exactly one raw piece
        assert ra.piece_image(ann, key).exists()
    roles = {p.role for p in ann.pieces.values()}
    assert {"torso", "hips", "upperarm", "forearm", "hand", "leg", "foot", "head", "tail"} <= roles


def test_outputs_written_and_recorded(tmp_path):
    ann = ra.load(make_character(tmp_path))
    outs = _outputs(ann)
    for name in ("torso", "hips", "upperarm_l", "upperarm_r", "forearm_l", "forearm_r",
                 "hand_l", "hand_r", "leg_l", "leg_r", "boot_l", "boot_r", "head_base", "tail"):
        assert name in outs, name
        assert outs[name][1].file == f"body/synth_{name}.png"
    for expr in ("neutral", "happy"):
        assert outs[f"head_{expr}"][1].file == f"face-heads/synth_head_{expr}.png"
    for piece, o in outs.values():
        img = Image.open(tmp_path / o.file)
        assert img.mode == "RGBA"
        w, h = img.size
        for name in ra._required_points(piece):
            x, y = o.points[name]
            assert 0 <= x <= w and 0 <= y <= h, (o.name, name)
            kind = piece.points[name].kind
            if kind == "opening":
                assert o.widths[name] > 0 and abs(o.depths[name] - 0.35 * o.widths[name]) < 0.02
            elif kind == "round_end":
                assert o.widths[name] > 0
        # joint end up: the proximal point sits above the distal one
        names = ra.ROLES[piece.role]
        if piece.role in ("upperarm", "forearm", "leg", "foot", "hand"):
            assert o.points[names[0]][1] < o.points[names[1]][1], o.name
    # the opening rim of a boot is darker than the boot below it
    p, o = outs["boot_l"]
    img = np.asarray(Image.open(tmp_path / o.file).convert("RGBA")).astype(int)
    ax, ay = o.points["ankle"]
    below = img[int(ay + o.depths["ankle"] * 2), int(ax)]
    assert img[int(ay), int(ax), :3].sum() < below[:3].sum()


def test_variants_present(tmp_path):
    ann = ra.load(make_character(tmp_path))
    outs = _outputs(ann)
    hand_pieces = [p for p in ann.pieces.values() if p.key.startswith("synth-hands-parts/")]
    assert sorted(p.variant for p in hand_pieces) == sorted(HAND_VARIANTS)
    for v in HAND_VARIANTS:
        for side in "lr":
            name = f"hand_{side}_{v}"
            piece, o = outs[name]
            assert o.file == f"variants/synth_{name}.png"
            assert (tmp_path / o.file).exists()
            assert ("fingertip" in piece.points) == (v not in ra.NO_FINGERTIP_VARIANTS)


def _thumb_vec(o):
    (wx, wy), (tx, ty) = o.points["wrist"], o.points["thumb_tip"]
    return tx - wx, ty - wy


def test_hand_outputs_have_the_thumb_right(tmp_path):
    ann = ra.load(make_character(tmp_path))
    for piece, o in _outputs(ann).values():
        if piece.role != "hand":
            continue
        side = o.name.split("_")[1]
        vec = _thumb_vec(o)
        assert rh.choose_mirror(vec, piece.variant, side, rest_target="lateral")[0] is False, o.name
        variant = piece.variant or "rest"
        target = "lateral" if variant == "rest" else rh.THUMB_TARGET[variant]
        world = rh.thumb_world_deg(vec, rh.side_deg(rh.HOLD_FOREARM_DEG[variant], side))
        assert rh.ang_diff(world, rh.target_deg(target, side)) < rh.THUMB_TOL, o.name


def test_hand_thumb_wrong_flips_only_point(tmp_path):
    good = ra.load(make_character(tmp_path / "good"))
    bad = ra.load(make_character(tmp_path / "bad", hand_thumb_wrong=True))
    g, b = _outputs(good), _outputs(bad)
    for name, (piece, o) in b.items():
        if piece.role != "hand":
            continue
        side = name.split("_")[1]
        wrong = rh.choose_mirror(_thumb_vec(o), piece.variant, side, rest_target="lateral")[0]
        assert wrong is (piece.variant == "point"), name
        assert o.mirrored == g[name][1].mirrored            # same mirror applied, thumb painted the other way
    pk = next(k for k, p in bad.pieces.items() if p.variant == "point")
    gx = good.pieces[pk].points["thumb_tip"].at[0]
    bx = bad.pieces[pk].points["thumb_tip"].at[0]
    assert (gx - 0.5) * (bx - 0.5) < 0                     # raw thumb on the other side


def test_no_tail_option(tmp_path):
    ann = ra.load(make_character(tmp_path, tail=False))
    assert all(p.role != "tail" for p in ann.pieces.values())
    assert not (tmp_path / "body" / "synth_tail.png").exists()
    truth = json.loads((tmp_path / "truth.json").read_text())
    assert "tail_root" not in truth["master_extra"] and "tail" not in truth["placed"]
    make_character(tmp_path / "with-tail")
    with_tail = json.loads((tmp_path / "with-tail" / "truth.json").read_text())
    assert "tail_root" in with_tail["master_extra"]


def test_hoof_feet(tmp_path):
    ann = ra.load(make_character(tmp_path, feet="hoof"))
    feet = [p for p in ann.pieces.values() if p.role == "foot"]
    assert sorted(p.name for p in feet) == ["hoof", "hoof"]
    assert (tmp_path / "body" / "synth_hoof_l.png").exists()


def test_truth_matches_annotations(tmp_path):
    ann = ra.load(make_character(tmp_path))
    truth = json.loads((tmp_path / "truth.json").read_text())
    W, H = 600, 900
    assert set(truth["master"]) == set(ra.MASTER_POINTS)
    for name, (x, y) in truth["master"].items():
        ax, ay = ann.master.points[name]
        assert abs(ax * W - x) < 0.1 and abs(ay * H - y) < 0.1, name
    assert set(truth["pieces"]) == set(ann.pieces)
    for key, pts in truth["pieces"].items():
        w, h = Image.open(ra.piece_image(ann, key)).size
        assert set(pts) == set(ann.pieces[key].points)
        for name, (x, y) in pts.items():
            ax, ay = ann.pieces[key].points[name].at
            assert abs(ax * w - x) < 0.05 and abs(ay * h - y) < 0.05, (key, name)
    # the pieces are painted at 0.8 x the master's scale
    torso = next(k for k, p in ann.pieces.items() if p.role == "torso")
    piece_len = truth["pieces"][torso]["waist"][1] - truth["pieces"][torso]["neck"][1]
    master_len = truth["master"]["waist"][1] - truth["master"]["neck"][1]
    assert abs(piece_len / master_len - 0.8) < 1e-3


def test_master_colours_at_joints(tmp_path):
    """The master is drawn where the truth says: the parts' flat colours sit at their joints."""
    make_character(tmp_path)
    truth = json.loads((tmp_path / "truth.json").read_text())
    img = np.asarray(Image.open(tmp_path / "master.png").convert("RGB")).astype(int)
    bg = np.array([214, 214, 214])
    for name in ("neck", "waist", "shoulder_l", "elbow_r", "wrist_l", "hip_r", "ankle_l"):
        x, y = truth["master"][name]
        assert np.abs(img[int(y), int(x)] - bg).sum() > 30, name


def test_deterministic(tmp_path):
    make_character(tmp_path / "a")
    make_character(tmp_path / "b")
    assert (tmp_path / "a" / "annotations.json").read_text() == (tmp_path / "b" / "annotations.json").read_text()
    for f in ("master.png", "runs/synth-body-parts/synth_02.png", "variants/synth_hand_l_point.png"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()
