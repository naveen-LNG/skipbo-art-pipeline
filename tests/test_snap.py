import math

import numpy as np
import pytest
from PIL import Image, ImageDraw

import rig_snap
import spine_rig


def _mask(draw_fn, size=(220, 260)):
    im = Image.new("L", size, 0)
    draw_fn(ImageDraw.Draw(im))
    return np.asarray(im) > 127


def _capsule():
    def draw(d):
        d.rectangle([70, 60, 130, 200], fill=255)
        d.ellipse([70, 30, 130, 90], fill=255)   # round end: centre (100, 60), radius 30
    return _mask(draw)


def _rot(pt, deg, c):
    a = math.radians(deg)
    x, y = pt[0] - c[0], pt[1] - c[1]
    return (c[0] + x * math.cos(a) - y * math.sin(a), c[1] + x * math.sin(a) + y * math.cos(a))


def test_round_end_capsule():
    r = rig_snap.snap_round_end(_capsule(), (110, 50), 45)
    assert r is not None
    assert math.hypot(r.at[0] - 100, r.at[1] - 60) <= 1.0
    assert abs(r.width - 60) <= 3


def test_round_end_rejects_far_point():
    assert rig_snap.snap_round_end(_capsule(), (110, 250), 45) is None
    assert rig_snap.snap_round_end(_capsule(), (310, 50), 45) is None


def test_opening_boot():
    alpha = _mask(lambda d: d.rectangle([50, 40, 120, 200], fill=255))
    r = rig_snap.snap_opening(alpha, (90, 45), (0, 1), 40)
    assert r is not None
    assert abs(r.at[0] - 85) <= 2 and abs(r.at[1] - 42) <= 2
    assert abs(r.width - 71) <= 0.5
    assert abs(r.depth - 0.35 * r.width) <= 1


def test_opening_rejects_far_point():
    alpha = _mask(lambda d: d.rectangle([50, 40, 120, 200], fill=255))
    assert rig_snap.snap_opening(alpha, (90, 5), (0, 1), 20) is None


def test_opening_tilted():
    c = (85, 120)
    corners = [_rot(p, 20, c) for p in [(50, 40), (120, 40), (120, 200), (50, 200)]]
    alpha = _mask(lambda d: d.polygon(corners, fill=255))
    a = math.radians(20)
    inward = (-math.sin(a), math.cos(a))
    p = _rot((90, 45), 20, c)
    r = rig_snap.snap_opening(alpha, p, inward, 40)
    assert r is not None
    assert abs(r.width - 70) <= 3
    exp = _rot((85, 42), 20, c)
    assert math.hypot(r.at[0] - exp[0], r.at[1] - exp[1]) <= 3


def test_inward_axis_and_boundary():
    alpha = _mask(lambda d: d.rectangle([50, 40, 120, 200], fill=255))
    v = rig_snap.inward_axis(alpha, (85, 45))
    assert abs(math.hypot(*v) - 1) < 1e-6 and v[1] > 0.99
    b = rig_snap.boundary(alpha)
    assert b.shape[1] == 2
    assert (b[:, 0] == 50).sum() == 161            # the left edge column
    assert not any((x == 80 and y == 100) for x, y in b)   # interior pixel


def test_axis_ends_matches_spine_rig():
    rng = np.random.default_rng(0)
    pts = rng.normal(size=(300, 2)) * [30, 8] + [50, 60]
    a0, a1, w = rig_snap.axis_ends(pts)
    b0, b1, v = spine_rig.axis_ends(pts)
    assert np.allclose(a0, b0) and np.allclose(a1, b1) and w == v


# ---- fit-quality gate, None branches, search radius ----

def _tube_flared():
    """Round-ended tube (end radius 30, centre (100, 60)) that flares to a wide cuff 45 px below the end."""
    def draw(d):
        d.ellipse([70, 30, 130, 90], fill=255)
        d.rectangle([70, 60, 130, 105], fill=255)
        d.polygon([(70, 105), (130, 105), (160, 125), (160, 200), (40, 200), (40, 125)], fill=255)
    return _mask(draw)


@pytest.mark.parametrize("radius", [50, 60, 80])
def test_round_end_flared_cuff_never_confidently_wrong(radius):
    r = rig_snap.snap_round_end(_tube_flared(), (100, 50), radius)
    assert r is None or math.hypot(r.at[0] - 100, r.at[1] - 60) <= 2.0


def test_round_end_flat_square_end_is_none():
    alpha = _mask(lambda d: d.rectangle([70, 40, 130, 200], fill=255))
    assert rig_snap.snap_round_end(alpha, (100, 45), 40) is None


def test_round_end_triangle_apex_is_none():
    alpha = _mask(lambda d: d.polygon([(100, 30), (160, 180), (40, 180)], fill=255))
    assert rig_snap.snap_round_end(alpha, (100, 40), 40) is None


def test_round_end_too_few_boundary_points():
    alpha = _mask(lambda d: d.rectangle([100, 100, 102, 102], fill=255))
    assert len(rig_snap.boundary(alpha)) < 12
    assert rig_snap.snap_round_end(alpha, (101, 101), 40) is None


def test_round_end_radius_out_of_range():
    alpha = _mask(lambda d: d.ellipse([97, 97, 103, 103], fill=255))      # r ~3 << 0.15 * 40
    assert rig_snap.snap_round_end(alpha, (100, 100), 40) is None
    big = _mask(lambda d: d.ellipse([10, 10, 210, 210], fill=255))        # r ~100 >> 1.5 * 20
    assert rig_snap.snap_round_end(big, (110, 12), 20) is None


def test_round_end_centre_not_in_alpha():
    # opaque plate with a round hole: the outline fits the hole well, but its centre is transparent.
    # (Without the centre-opaque check this returns a circle centred at ~(110, 120).)
    def draw(d):
        d.rectangle([20, 20, 200, 240], fill=255)
        d.ellipse([90, 100, 130, 140], fill=0)
    alpha = _mask(draw)
    assert not alpha[120, 110]
    assert rig_snap.snap_round_end(alpha, (110, 102), 30) is None


def test_round_end_arc_gate_rejects_rounded_corner():
    # a rounded corner (r=40) is a good circle fit but spans only ~90 degrees: not a limb end.
    # (With the 120-degree arc gate removed this returns a circle centred at ~(80, 80).)
    alpha = _mask(lambda d: d.rounded_rectangle([40, 40, 180, 220], radius=40, fill=255))
    assert rig_snap.snap_round_end(alpha, (52, 52), 30) is None
    assert rig_snap.snap_round_end(alpha, (52, 52), 40) is None


def test_round_end_empty_mask():
    assert rig_snap.snap_round_end(np.zeros((100, 100), dtype=bool), (50, 50), 40) is None


def test_round_end_mask_touching_border():
    def draw(d):
        d.rectangle([70, 30, 130, 200], fill=255)
        d.ellipse([70, 0, 130, 60], fill=255)         # cap reaches the top image row; centre (100, 30)
    r = rig_snap.snap_round_end(_mask(draw), (108, 22), 45)
    assert r is not None
    assert math.hypot(r.at[0] - 100, r.at[1] - 30) <= 2.0
    assert abs(r.width - 60) <= 3


def test_search_radius_and_realistic_capsule():
    assert rig_snap.SNAP_RADIUS_FRAC == 0.6
    def draw(d):
        d.rectangle([40, 70, 160, 330], fill=255)
        d.ellipse([40, 10, 160, 130], fill=255)       # 120 wide, end radius 60, centre (100, 70)
    alpha = _mask(draw, size=(200, 340))
    rad = rig_snap.search_radius(alpha)
    assert abs(rad - 0.6 * 121) <= 1.0
    r = rig_snap.snap_round_end(alpha, (112, 57), rad)     # rough point ~17 px off
    assert r is not None
    assert math.hypot(r.at[0] - 100, r.at[1] - 70) <= 2.0
    assert abs(r.width - 120) <= 4
    assert rig_snap.search_radius(np.zeros((10, 10), dtype=bool)) == 0.0


@pytest.mark.parametrize("deg", [20, 45, 71])
def test_search_radius_follows_the_pieces_own_width_when_tilted(deg):
    base = Image.new("L", (200, 340), 0)
    d = ImageDraw.Draw(base)
    d.rectangle([40, 70, 160, 330], fill=255)
    d.ellipse([40, 10, 160, 130], fill=255)          # 120 wide, round end centre (100, 70)
    tilted = np.asarray(base.rotate(deg, expand=True, resample=Image.BICUBIC)) > 127
    assert abs(rig_snap.piece_width(tilted) - 121) <= 3
    assert abs(rig_snap.search_radius(tilted) - 0.6 * 121) <= 2.0


def test_piece_width_falls_back_to_the_box_without_an_axis():
    tiny = np.zeros((10, 10), dtype=bool)
    tiny[2:4, 3:7] = True                            # 8 pixels
    assert rig_snap.piece_width(tiny) == 2.0
    square = np.zeros((60, 60), dtype=bool)
    square[10:50, 10:50] = True                      # no principal axis
    assert rig_snap.piece_width(square) == 40.0


def test_opening_window_width_capped_on_a_steep_cone():
    # a cone flaring 2 px per px from a 60 px rim: the window follows it inward but never beyond 1.6 x the rim
    w = rig_snap.opening_window_width(60.0, lambda t: 60.0 + 2.0 * t, lambda t: True)
    assert w <= 1.6 * 60.0 + 1e-9
    assert w > 60.0                                    # it did follow the round-off up to the cap
    # a gentle widening (below the slope) is not followed at all
    assert rig_snap.opening_window_width(60.0, lambda t: 60.0 + 0.2 * t, lambda t: True) == 60.0
