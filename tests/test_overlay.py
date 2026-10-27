"""Checkpoint pictures: master overlay, sheet overlay, as-worn strip."""
import numpy as np
from PIL import Image

import rig_annotations as ra
import rig_overlay as ro
from synth_character import make_character

BODY = "synth-body-parts"
HANDS = "synth-hands-parts"
HEADS = "synth-heads-parts"


def _load(tmp_path, **kw):
    return ra.load(make_character(tmp_path, **kw))


def test_sheet_overlay_writes_png(tmp_path):
    ann = _load(tmp_path)
    n = len([k for k in ann.pieces if k.startswith(BODY + "/")])
    out = ro.render_sheet_overlay(ann, BODY, tmp_path / "ann" / "body_overlay.png", cell=200)
    assert out.exists() and out.stat().st_size > 0
    img = Image.open(out).convert("RGB")
    cols, rows, w, h = ro.layout_size(n, 200)
    assert img.width >= w and img.height > h                 # grid plus a legend line
    a = np.asarray(img)
    for i in range(n):                                       # one cell per piece, each holds a drawn piece
        x0 = (i % cols) * 200
        y0 = (i // cols) * (200 + ro.HEADER_H) + ro.HEADER_H
        cell = a[y0 + 20:y0 + 180, x0 + 20:x0 + 180].reshape(-1, 3)
        assert (np.abs(cell.astype(int) - np.array(ro.BG)).sum(axis=1) > 30).any(), i


def test_sheet_overlay_frames_doubtful_piece_in_red(tmp_path):
    ann = _load(tmp_path)
    key = f"{BODY}/02"
    ann.pieces[key].confidence = 0.3
    out = ro.render_sheet_overlay(ann, BODY, tmp_path / "o.png", cell=200)
    a = np.asarray(Image.open(out).convert("RGB"))
    cols = ro.layout_size(len([k for k in ann.pieces if k.startswith(BODY + "/")]), 200)[0]
    i = 2
    x0, y0 = (i % cols) * 200, (i // cols) * (200 + ro.HEADER_H)
    assert tuple(a[y0 + 100, x0 + 1]) == ro.FAILED           # frame on the cell's left edge
    j = 3
    assert tuple(a[(j // cols) * (200 + ro.HEADER_H) + 100, (j % cols) * 200 + 1]) != ro.FAILED


def test_sheet_overlay_hands_sheet(tmp_path):
    ann = _load(tmp_path)
    out = ro.render_sheet_overlay(ann, HANDS, tmp_path / "hands_overlay.png")
    assert Image.open(out).width >= 260 * 4 or Image.open(out).width >= 640


def test_master_overlay_writes_png(tmp_path):
    ann = _load(tmp_path)
    out = ro.render_master_overlay(ann, tmp_path / "ann" / "master_overlay.png")
    assert out.exists() and out.stat().st_size > 0
    img = Image.open(out)
    assert img.height >= 900                                  # master plus a legend
    a = np.asarray(img.convert("RGB")).reshape(-1, 3)
    assert (np.abs(a.astype(int) - np.array(ro.THUMB)).sum(axis=1) < 10).any()   # a thumb arrow was drawn


def test_worn_strip_marks_wrong_thumb(tmp_path):
    ann = _load(tmp_path, hand_thumb_wrong=True)
    out, labels = ro.render_worn_strip(ann, HANDS, tmp_path / "ann" / "hands_worn.png")
    assert out.exists() and out.stat().st_size > 0
    assert ("hand_l_point", False) in labels
    # the fixture paints the point variant's thumb on the wrong side for both hands; nothing else is wrong
    assert sorted(n for n, ok in labels if not ok) == ["hand_l_point", "hand_r_point"]


def test_master_overlay_frames_a_master_doubt_in_red(tmp_path):
    def red_frame(path):
        a = np.asarray(Image.open(path).convert("RGB")).astype(int)
        return (np.abs(a[2, :, :] - np.array(ro.FAILED)).sum(axis=1) < 10).sum() > 100     # along the top edge
    ann = _load(tmp_path)
    assert not red_frame(ro.render_master_overlay(ann, tmp_path / "ok.png"))
    ann.master.status = "proposed"
    ann.master.hands["l"] = {"thumb_side": "medial", "facing": "palm"}          # anatomy: a palm's thumb is lateral
    assert [x for x in ra.doubts(ann) if x["key"] == "master"]
    assert red_frame(ro.render_master_overlay(ann, tmp_path / "doubt.png"))


def test_worn_strip_wrong_thumb_names_the_painted_side(tmp_path):
    ann = _load(tmp_path, hand_thumb_wrong=True)
    piece, out = _hand_output(ann, "hand_l_point")
    _, lines, ok, _ = ro._worn_item(ann, piece, out)
    assert ok is False and lines[1].startswith("palm") and "wrong side" in lines[1]


def test_worn_strip_draws_each_hand_at_its_gestures_pose(tmp_path):
    import math
    import rig_hands as rh
    ann = _load(tmp_path)
    key = next(k for k, p in ann.pieces.items() if p.variant == "point")
    ann.pieces[key].facing = "back"
    ra.snap_all(ann)
    ra.normalise(ann)                                         # mirrored for a back: the point goes across
    piece, out = _hand_output(ann, "hand_l_point")
    _, lines, ok, geom = ro._worn_item(ann, piece, out)
    assert ok is True and lines[1] == "back · across · up"
    (cx, cy), (dx, dy) = geom["wrist"], geom["thumb_dot"]
    assert rh.ang_diff(math.degrees(math.atan2(-(dy - cy), dx - cx)), 90) < rh.THUMB_TOL     # thumb drawn up
    piece, out = _hand_output(ann, "hand_l_thumbsup")         # still a palm: outward
    assert ro._worn_item(ann, piece, out)[1][1] == "palm · outward · up"
    piece, out = _hand_output(ann, "hand_l_open")
    assert ro._worn_item(ann, piece, out)[1][1] == "palm · anatomy"


def test_worn_strip_all_right_when_thumbs_right(tmp_path):
    ann = _load(tmp_path)
    _, labels = ro.render_worn_strip(ann, HANDS, tmp_path / "w.png")
    assert len(labels) == 10                                  # five variants, both hands
    assert all(ok for _, ok in labels), labels


def test_worn_strip_body_run_shows_hands_feet_and_upper_arms(tmp_path):
    ann = _load(tmp_path)
    out, labels = ro.render_worn_strip(ann, BODY, tmp_path / "b.png", h=240)
    names = [n for n, _ in labels]
    assert {"hand_l", "hand_r", "boot_l", "boot_r", "upperarm_l", "upperarm_r"} == set(names)
    assert all(ok for _, ok in labels)                        # rest thumbs are lateral on the fixture
    assert Image.open(out).height >= 240


def test_worn_strip_puts_characters_left_on_the_right(tmp_path):
    ann = _load(tmp_path)
    cells = {o.name: (row, col) for _, o, row, col in ro.worn_cells(ann, HANDS)}
    for v in ("open", "fist", "point", "thumbsup", "grip"):
        r, l = cells[f"hand_r_{v}"], cells[f"hand_l_{v}"]
        assert r[0] == l[0] and r[1] < l[1], v                # same row, the right hand on the picture's left
    body = {o.name: c for _, o, _r, c in ro.worn_cells(ann, BODY)}
    assert body["boot_r"] < body["boot_l"] and body["upperarm_r"] < body["upperarm_l"]


def test_worn_strip_shows_whole_sleeves(tmp_path):
    """A whole sleeve (role arm) hangs from its shoulder like an upper arm, the character's right on the left, so
    its mirror per side can be checked; no forearm stub (it is the forearm)."""
    ann = _load(tmp_path, sleeves=True)
    body = {o.name: (r, c) for _, o, r, c in ro.worn_cells(ann, BODY)}
    assert body["arm_r"][0] == body["arm_l"][0] and body["arm_r"][1] < body["arm_l"][1], body
    _, labels = ro.render_worn_strip(ann, BODY, tmp_path / "b.png", h=240)
    assert {"arm_l", "arm_r"} <= {n for n, _ in labels}
    p, o = _hand_output(ann, "arm_l")
    content, _, ok, geom = ro._worn_item(ann, p, o)
    assert ok is True
    a = np.asarray(content)
    stub = (np.abs(a[..., :3].astype(int) - (120, 120, 126)).sum(-1) < 6) & (a[..., 3] == 255)
    assert not stub.any()                                     # no grey forearm stub drawn


def _hand_output(ann, name):
    for p in ann.pieces.values():
        for o in p.outputs:
            if o.name == name:
                return p, o
    raise KeyError(name)


def test_worn_picture_and_verdict_share_one_rotation(tmp_path):
    import math
    import rig_hands as rh
    ann = _load(tmp_path)
    piece, out = _hand_output(ann, "hand_l_point")
    wx, wy = out.points["wrist"]
    # fingertip 40 degrees off image-down: the picture must still follow the verdict's convention
    out.points["fingertip"] = (wx + 50 * math.sin(math.radians(40)), wy + 50 * math.cos(math.radians(40)))
    _, _, ok, geom = ro._worn_item(ann, piece, out)
    thumb = rh.thumb_vector(out.points["wrist"], out.points["thumb_tip"], out.points["fingertip"])
    forearm = rh.side_deg(rh.HOLD_FOREARM_DEG["point"], "l")
    want = rh.thumb_world_deg(thumb, forearm)
    (cx, cy), (dx, dy) = geom["wrist"], geom["thumb_dot"]
    got = math.degrees(math.atan2(-(dy - cy), dx - cx))
    assert rh.ang_diff(got, want) < 1.0
    assert ok is (rh.ang_diff(want, rh.target_deg("up", "l")) <= rh.THUMB_TOL)


def test_worn_thumb_far_down_the_hand_is_judged_across_its_axis(tmp_path):
    import math
    import rig_hands as rh
    ann = _load(tmp_path)
    piece, out = _hand_output(ann, "hand_l_point")
    wx, wy = out.points["wrist"]
    out.points["fingertip"] = (wx, wy + 200)
    out.points["thumb_tip"] = (wx + 40, wy + 120)        # beside the knuckles, far down the hand (real art)
    _, _, ok, geom = ro._worn_item(ann, piece, out)
    assert ok is True
    (cx, cy), (dx, dy) = geom["wrist"], geom["thumb_dot"]
    got = math.degrees(math.atan2(-(dy - cy), dx - cx))
    assert rh.ang_diff(got, rh.side_deg(rh.HOLD_FOREARM_DEG["point"], "l") + 90) < 1.0   # straight across the stub
    assert math.hypot(dx - cx, dy - cy) == __import__("pytest").approx(40, abs=1)


def test_failed_snap_on_a_confident_piece_is_labelled_but_not_framed(tmp_path):
    ann = _load(tmp_path)
    ra.snap_all(ann)
    ra.normalise(ann)
    arm = next(k for k, p in ann.pieces.items() if p.role == "upperarm")
    ann.pieces[arm].points["elbow"].snap = "failed"          # as if its snap had failed
    ann.pieces[arm].points["elbow"].snapped = None
    assert not ro._is_doubt(ann.pieces[arm])
    out = ro.render_sheet_overlay(ann, BODY, tmp_path / "o.png", cell=200)
    a = np.asarray(Image.open(out).convert("RGB"))
    keys = sorted(k for k in ann.pieces if k.startswith(BODY + "/"))
    cols = ro.layout_size(len(keys), 200)[0]
    i = keys.index(arm)
    x0, y0 = (i % cols) * 200, (i // cols) * (200 + ro.HEADER_H)
    assert tuple(a[y0 + 100, x0 + 1]) != ro.FAILED                       # no red frame
    cell = a[y0 + ro.HEADER_H:y0 + ro.HEADER_H + 200, x0 + 6:x0 + 194].reshape(-1, 3)
    assert (cell == np.array(ro.FAILED)).all(axis=1).any()               # the red "(snap failed)" mark is there


def test_worn_strip_unchecked_hand_is_none(tmp_path):
    ann = _load(tmp_path)
    _, out = _hand_output(ann, "hand_l_point")
    del out.points["thumb_tip"]
    path, labels = ro.render_worn_strip(ann, HANDS, tmp_path / "w.png")
    d = dict(labels)
    assert d["hand_l_point"] is None
    assert d["hand_r_grip"] is True and path.exists()
    assert all(v is True for n, v in labels if n not in ("hand_l_point",))
    # a rest hand whose master thumb_side is missing cannot be checked either
    ann2 = _load(tmp_path / "b")
    ann2.master.hands = {}
    _, labels2 = ro.render_worn_strip(ann2, BODY, tmp_path / "w2.png")
    assert dict(labels2)["hand_l"] is None and dict(labels2)["boot_l"] is True


def test_thumb_label_either_says_what_is_painted_and_sided_says_at_rest(tmp_path):
    ann = _load(tmp_path)
    either = ann.pieces[f"{HANDS}/00"]
    assert either.side == "either"
    label = ro._piece_label(either)
    assert "thumb image-left" in label or "thumb image-right" in label
    assert "lateral" not in label and "medial" not in label
    sided = ra.load(make_character(tmp_path / "s")).pieces[f"{BODY}/06"]
    sided.side = "l"
    label = ro._piece_label(sided)
    assert "thumb lateral at rest" in label or "thumb medial at rest" in label
    assert "image-" not in label


def test_long_cell_label_is_not_cut(tmp_path):
    ann = _load(tmp_path)
    piece = ann.pieces[f"{BODY}/06"]
    piece.variant = "extraordinarily_long_variant_name_that_must_wrap"
    d = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(Image.new("RGB", (4, 4)))
    lines, _ = ro._header_lines(d, "06  " + ro._piece_label(piece), 252)
    assert len(lines) <= 3 and "thumb" in " ".join(lines) and "..." not in " ".join(lines)


def test_ignored_piece_is_labelled_ignored_and_not_framed(tmp_path):
    ann = _load(tmp_path)
    key = f"{BODY}/02"
    piece = ann.pieces[key]
    piece.status, piece.confidence, piece.outputs = "ignored", 0.1, []
    assert ro._piece_label(piece).startswith("ignored")
    assert not ro._is_doubt(piece)
    out = ro.render_sheet_overlay(ann, BODY, tmp_path / "o.png", cell=200)
    a = np.asarray(Image.open(out).convert("RGB"))
    cols = ro.layout_size(len([k for k in ann.pieces if k.startswith(BODY + "/")]), 200)[0]
    assert tuple(a[(2 // cols) * (200 + ro.HEADER_H) + 100, (2 % cols) * 200 + 1]) != ro.FAILED
    ro.render_worn_strip(ann, BODY, tmp_path / "w.png")     # an ignored worn-role piece has no outputs: no error
