import rig_hands as rh


def test_target_deg_sides():
    assert rh.target_deg("up", "l") == 90 and rh.target_deg("up", "r") == 90
    assert rh.target_deg("down", "l") == -90
    assert rh.target_deg("lateral", "l") == 0 and rh.target_deg("lateral", "r") == 180
    assert rh.target_deg("medial", "l") == 180 and rh.target_deg("medial", "r") == 0
    assert rh.side_deg(5.0, "l") == 5.0 and rh.side_deg(5.0, "r") == 175.0


def test_point_left_thumb_up():
    w = rh.thumb_world_deg((1, 0), rh.HOLD_FOREARM_DEG["point"])
    assert rh.ang_diff(w, 90) < 10
    mirror, m = rh.choose_mirror((1, 0), "point", "l")
    assert mirror is False and m > 90


def test_point_moose_regression():
    assert rh.choose_mirror((-1, 0), "point", "l")[0] is True


def test_right_side_mirrors():
    for var in rh.THUMB_TARGET:
        v = (1, 0.2)
        assert rh.choose_mirror(v, var, "r")[0] != rh.choose_mirror(v, var, "l")[0], var


def test_choose_mirror_ambiguous_is_flagged():
    _, m = rh.choose_mirror((0, 1), "point", "l")
    assert m < rh.MIRROR_AMBIGUOUS


def test_rest_uses_master_target():
    assert rh.choose_mirror((-1, 0), "rest", "l", rest_target="lateral")[0] is True
    assert rh.choose_mirror((-1, 0), None, "l", rest_target="lateral")[0] is True


# --- T3b: the thumb's side is judged across the hand's axis ---

LONG_HAND = dict(wrist=(176, 22), thumb_tip=(311, 358), fingertip=(185, 600))   # fox point hand, output px


def test_thumb_vector_is_perpendicular_to_the_hand_axis():
    vx, vy = rh.thumb_vector(**LONG_HAND)
    ax, ay = 185 - 176, 600 - 22
    assert abs(vx * ax + vy * ay) < 1e-6 * (ax * ax + ay * ay)       # across the axis
    assert vx > 100 and abs(vy) < 5                                   # the thumb is on the image's right


def test_thumb_vector_without_fingertip_uses_image_down():
    assert rh.thumb_vector((10, 10), (40, 90)) == (30.0, 0.0)
    assert rh.thumb_vector((10, 10), (40, 90), fingertip=(10, 10)) == (30.0, 0.0)   # no axis: image-down


def test_thumb_on_the_hand_axis_has_no_side():
    v = rh.thumb_vector((0, 0), (5, 100), (0, 200))          # 3 degrees off the axis: noise, not a side
    assert v == (0.0, 0.0)
    assert rh.choose_mirror(v, "point", "l") == (False, 0.0)
    assert rh.choose_mirror(v, "point", "l")[1] < rh.MIRROR_AMBIGUOUS
    assert rh.thumb_vector((0, 0), (30, 100), (0, 200)) == (30.0, 0.0)   # 17 degrees off: a side


def test_long_hand_mirror_is_decisive():
    v = rh.thumb_vector(**LONG_HAND)
    mirror, margin = rh.choose_mirror(v, "point", "l")
    assert mirror is False and margin > 120
    mirror, margin = rh.choose_mirror(v, "point", "r")
    assert mirror is True and margin > 120


def test_constants():
    assert rh.THUMB_TOL == 45.0 and rh.MIRROR_AMBIGUOUS == 30.0
    assert rh.GESTURE_ARM_DEG == {"thumbs_up": (-55.0, 10.0), "point": (5.0, 5.0), "hold_card": (-95.0, 170.0)}
    assert rh.HOLD_FOREARM_DEG == {"rest": -90.0, "open": 85.0, "fist": 65.0, "point": 5.0, "thumbsup": 10.0, "grip": 170.0}


# --- T17b: the mirror follows anatomy (which side of the hand is painted), the gesture picks a pose that works ---

def test_anatomy_table():
    """Joint end up, seen from the front: a left hand showing its palm has the thumb on image +x (lateral), showing
    its back on -x (medial); the right hand is the mirror image. mirror flips the painted thumb onto that side."""
    want_plus_x = {("l", "palm"): True, ("l", "back"): False, ("r", "palm"): False, ("r", "back"): True}
    for (side, facing), plus in want_plus_x.items():
        assert rh.anatomical_thumb_sign(side, facing) == (1 if plus else -1), (side, facing)
        mirror, margin = rh.anatomical_mirror((1.0, 0.0), facing, side)      # thumb painted on image +x
        assert mirror is (not plus), (side, facing)
        assert margin == 1.0
        assert rh.anatomical_mirror((-1.0, 0.0), facing, side)[0] is plus, (side, facing)


def test_anatomical_mirror_ambiguous_without_a_side():
    assert rh.anatomical_mirror((0.0, 0.0), "palm", "l") == (False, 0.0)
    _, margin = rh.anatomical_mirror((0.05, 1.0), "palm", "l")              # (almost) along the image's vertical
    assert margin < rh.THUMB_SIDE_MIN


def test_anatomical_thumb_deg_matches_thumb_world_deg():
    # a hand mirrored by the anatomy rule has its thumb where anatomical_thumb_deg says, at any hand angle
    for side in "lr":
        for facing in ("palm", "back"):
            v = (rh.anatomical_thumb_sign(side, facing) * 1.0, 0.0)
            for hand in (-90.0, 5.0, 85.0, 175.0):
                assert rh.ang_diff(rh.thumb_world_deg(v, hand), rh.anatomical_thumb_deg(hand, side, facing)) < 1e-6
    assert rh.ang_diff(rh.anatomical_thumb_deg(-90.0, "l", "palm"), rh.target_deg("lateral", "l")) < 1e-6
    assert rh.ang_diff(rh.anatomical_thumb_deg(-90.0, "r", "back"), rh.target_deg("medial", "r")) < 1e-6


def test_point_palm_goes_outward_back_goes_across():
    for side in "lr":
        palm = (rh.anatomical_thumb_sign(side, "palm") * 1.0, 0.0)
        back = (rh.anatomical_thumb_sign(side, "back") * 1.0, 0.0)
        for variant in ("point", "thumbsup"):
            h = rh.hold_pose(variant, palm, side)
            assert h["pose"] == "outward" and h["ok"] is True and h["error"] < 15, (side, variant, h)
            assert h["forearm_deg"] == rh.side_deg(rh.GESTURE_ARM_DEG[rh.POSE_GESTURE[variant]][1], side)
            h = rh.hold_pose(variant, back, side)
            assert h["pose"] == "across" and h["ok"] is True and h["error"] < 25, (side, variant, h)
            assert h["forearm_deg"] == rh.side_deg(rh.GESTURE_ARM_DEG_ACROSS[rh.POSE_GESTURE[variant]][1], side)


def test_hold_pose_prefers_outward_and_flags_neither():
    h = rh.hold_pose("point", (0.0, 0.0), "l")              # the thumb has no side: nothing to choose by
    assert h["pose"] == "outward" and h["ok"] is None
    h = rh.hold_pose("point", (0.0, -1.0), "l")             # thumb back toward the wrist: along the arm both ways
    assert h["pose"] == "outward" and h["ok"] is False
    assert set(h["errors"]) == {"outward", "across"}


def test_hold_card_and_wave_have_no_choice():
    back_l = (rh.anatomical_thumb_sign("l", "back") * 1.0, 0.0)
    h = rh.hold_pose("grip", back_l, "l")
    assert h["pose"] == "hold_card" and h["ok"] is True                    # across the belly, thumb up
    assert rh.hold_pose("grip", (-back_l[0], 0.0), "l")["ok"] is False
    assert rh.hold_pose("open", back_l, "l") is None
    assert rh.hold_pose("fist", back_l, "l") is None


def test_across_pose_constants():
    assert set(rh.GESTURE_ARM_DEG_ACROSS) == {"point", "thumbs_up"}
    for ua, fa in rh.GESTURE_ARM_DEG_ACROSS.values():
        assert -90.0 < ua < 0.0                     # upper arm down and a little out, elbow at the side
        assert 135.0 <= fa <= 225.0                 # forearm across the chest toward the other side


def test_hold_pose_takes_a_searched_across_pose():
    back_l = (rh.anatomical_thumb_sign("l", "back") * 1.0, 0.0)
    h = rh.hold_pose("point", back_l, "l", across=(-60.0, 165.0))
    assert h["pose"] == "across" and (h["upperarm_deg"], h["forearm_deg"]) == (-60.0, 165.0)
    back_r = (rh.anatomical_thumb_sign("r", "back") * 1.0, 0.0)
    h = rh.hold_pose("point", back_r, "r", across=(-60.0, 165.0))             # given for the left, mirrored
    assert (h["upperarm_deg"], h["forearm_deg"]) == (rh.side_deg(-60.0, "r"), rh.side_deg(165.0, "r"))
