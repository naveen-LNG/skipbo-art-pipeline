#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "pillow"]
# ///
"""rig_hands.py - mirror a painted hand the way anatomy says, and pick a gesture pose the drawing can do.

Hand images are "joint end up": wrist at the top, fingers down, +y down. The hand continues its
forearm, so the image's +y maps to the world direction `forearm_deg` (degrees, 0 = picture right,
90 = up, y up).

The mirror is fixed by anatomy, not by the gesture: seen from the front, a left hand (the picture's right) showing
its palm has the thumb on image +x (lateral), showing its back on image -x (medial); the right hand is the mirror
image (anatomical_mirror). Turning a hand in the picture plane keeps that side, so a gesture can only choose a
pose: a palm-facing hand pointing outward has its thumb up, a back-facing one has it down and must point ACROSS
the body to show its thumb up (hold_pose). choose_mirror, the old rule that mirrored for the gesture's thumb
target whatever side was painted (and so could show an impossible hand), is legacy: hands without a `facing` only.

The thumb's direction is NOT wrist -> thumb_tip: on painted hands the thumb tip sits well down the hand,
so that vector mostly follows the hand's own axis and says little about which side the thumb is on.
Every judgement of a thumb uses thumb_vector(): the component of (thumb_tip - wrist) perpendicular to the
hand's axis (wrist -> fingertip, or image-down when there is no fingertip). Anything else that checks a
thumb (overlays, QA on the built rig) must use the same definition, taken relative to the hand bone's
direction rather than to the image or the forearm.
"""
import math

THUMB_TOL = 45.0          # a thumb further than this from its target is a doubt
MIRROR_AMBIGUOUS = 30.0   # candidates' errors closer than this make the mirror choice a doubt
THUMB_SIDE_MIN = 0.15     # a thumb tip less than this x its distance from the wrist off the hand's axis
                          # (about 9 degrees) has no side (thumb_vector returns zero)

# Forearm world angle at each variant's hold, for the character's left side.
HOLD_FOREARM_DEG = {"rest": -90.0, "open": 85.0, "fist": 65.0, "point": 5.0, "thumbsup": 10.0, "grip": 170.0}

# (upper arm, forearm) world angles used by rig_anim (Animator.gesture), for the character's left side.
GESTURE_ARM_DEG = {"thumbs_up": (-55.0, 10.0), "point": (5.0, 5.0), "hold_card": (-95.0, 170.0)}

# The other pose of the gestures that have a choice: elbow at the side, forearm across the chest toward the
# character's other side, the hand in front of the chest below the chin (character's left; side_deg mirrors).
# The fallback: rig_anim.across_hold searches the real hold per character (clear of the head - neckwear is drawn
# under the forearm and hand - above the hold_card hand, forearm within 15 degrees of this one); the worn strip
# judges the thumb at this one.
GESTURE_ARM_DEG_ACROSS = {"thumbs_up": (-75.0, 175.0), "point": (-75.0, 175.0)}
# Hand variant -> the gesture holding it, for the gestures with an outward/across choice ...
POSE_GESTURE = {"point": "point", "thumbsup": "thumbs_up"}
# ... and for every gesture whose thumb must point up (hold_card keeps its one pose).
UP_GESTURE = dict(POSE_GESTURE, grip="hold_card")

# Where the thumb should point at each hold, for the legacy choose_mirror (hands without a `facing`); "up" for
# UP_GESTURE's variants either way. With a `facing`, the open and fist hands' thumbs go where anatomy puts them
# (anatomical_thumb_deg), not here. The rest hand's legacy target comes from the master's thumb_side.
THUMB_TARGET = {"open": "medial", "fist": "medial", "point": "up", "thumbsup": "up", "grip": "up"}


def side_deg(deg_left, side):
    """World angle for the character's right side given the left-side angle (mirror about vertical)."""
    return 180.0 - deg_left if side == "r" else deg_left


def target_deg(target, side):
    """World angle of a named thumb direction; lateral = away from the body, medial = toward it."""
    if target == "up":
        return 90.0
    if target == "down":
        return -90.0
    if target == "lateral":
        return 0.0 if side == "l" else 180.0
    if target == "medial":
        return 180.0 if side == "l" else 0.0
    raise ValueError(f"unknown thumb target {target!r}")


def thumb_vector(wrist, thumb_tip, fingertip=None):
    """The thumb's direction (dx, dy) in image coordinates (y down): the part of thumb_tip - wrist that runs
    across the hand's axis. The axis is fingertip - wrist, or image-down (0, 1) without a fingertip (or when
    the fingertip sits on the wrist); outputs are joint end up, so image-down is the hand's own direction.

    A thumb tip that lies (nearly) on the axis has no side: when the across part is under THUMB_SIDE_MIN of
    |thumb_tip - wrist| this returns (0.0, 0.0), which choose_mirror reports as ambiguous (margin 0)."""
    vx, vy = thumb_tip[0] - wrist[0], thumb_tip[1] - wrist[1]
    ax, ay = 0.0, 1.0
    if fingertip is not None:
        fx, fy = fingertip[0] - wrist[0], fingertip[1] - wrist[1]
        n = math.hypot(fx, fy)
        if n > 1e-9:
            ax, ay = fx / n, fy / n
    along = vx * ax + vy * ay
    px, py = float(vx - along * ax), float(vy - along * ay)
    if math.hypot(px, py) < THUMB_SIDE_MIN * math.hypot(vx, vy) or math.hypot(px, py) < 1e-9:
        return (0.0, 0.0)
    return (px, py)


def thumb_world_deg(thumb_vec, forearm_deg):
    """World angle (y up) of a thumb vector (dx, dy) from a joint-end-up image (y down); pass thumb_vector()."""
    dx, dy = thumb_vec
    a = math.degrees(math.atan2(-dy, dx))
    # image-down is -90 deg in y-up and must land on forearm_deg, so rotate by forearm_deg + 90
    return (a + forearm_deg + 90.0 + 180.0) % 360.0 - 180.0


def ang_diff(a, b):
    """Absolute angle difference in [0, 180]."""
    d = abs(a - b) % 360.0
    return 360.0 - d if d > 180.0 else d


def choose_mirror(thumb_vec, variant, side, rest_target=None):
    """LEGACY, for a hand without a `facing` only (rig_annotations doubts it): mirrors for the gesture's thumb
    target whatever side of the hand is painted, which can show an impossible hand; use anatomical_mirror.
    Return (mirror, margin) for thumb_vec = thumb_vector(...) of a joint-end-up hand.
    mirror=True flips the image horizontally (dx -> -dx);
    margin = |error(unmirrored) - error(mirrored)| in degrees. variant None or "rest" uses rest_target.
    A zero vector (the thumb has no side) gives (False, 0.0)."""
    if variant is None or variant == "rest":
        variant = "rest"
        target = rest_target
        if target is None:
            raise ValueError("the rest variant needs rest_target")
    else:
        target = THUMB_TARGET[variant]
    forearm = side_deg(HOLD_FOREARM_DEG[variant], side)
    goal = target_deg(target, side)
    dx, dy = thumb_vec
    if math.hypot(dx, dy) < 1e-9:
        return False, 0.0
    e_plain = ang_diff(thumb_world_deg((dx, dy), forearm), goal)
    e_flip = ang_diff(thumb_world_deg((-dx, dy), forearm), goal)
    return e_flip < e_plain, abs(e_plain - e_flip)


def anatomical_thumb_sign(side, facing):
    """+1 when the thumb belongs on image +x of a joint-end-up hand seen from the front, else -1: +1 for the left
    hand (the picture's right) showing its palm and for the right hand showing its back."""
    return 1 if (side == "l") == (facing == "palm") else -1


def anatomical_mirror(thumb_vec, facing, side):
    """(mirror, margin) for thumb_vec = thumb_vector(...) of a joint-end-up hand painted showing `facing`
    (palm | back) and worn on `side`. mirror=True when the thumb is painted on the other image side than anatomy
    puts it (anatomical_thumb_sign). margin = |dx| / |thumb_vec|, the share of the thumb that runs sideways; under
    THUMB_SIDE_MIN the thumb's side is unclear (a doubt). A zero vector (no side) gives (False, 0.0)."""
    dx, dy = thumb_vec
    n = math.hypot(dx, dy)
    if n < 1e-9:
        return False, 0.0
    return (dx > 0) != (anatomical_thumb_sign(side, facing) > 0), abs(dx) / n


def anatomical_thumb_deg(hand_deg, side, facing):
    """World angle of the thumb that anatomy gives a hand pointing at hand_deg (world, y up): square to the hand, on
    the side anatomical_thumb_sign says - what thumb_world_deg gives an anatomically mirrored, sideways thumb."""
    return (hand_deg + 90.0 * anatomical_thumb_sign(side, facing) + 180.0) % 360.0 - 180.0


def hold_pose(variant, thumb_vec, side, across=None):
    """The pose a gesture holds this hand at so its thumb points up, or None for a variant with no such gesture
    (open, fist, rest: their thumb goes wherever anatomy puts it). thumb_vec: the WORN (mirrored) hand's
    thumb_vector.

    point and thumbsup have two candidates, "outward" (GESTURE_ARM_DEG) and "across" (GESTURE_ARM_DEG_ACROSS):
    outward when its thumb lands within THUMB_TOL of up, else across when that does; when neither does, outward is
    kept and ok is False. grip has its one pose, "hold_card". A thumb without a side keeps the first pose, ok None.
    Returns {"gesture", "pose", "upperarm_deg", "forearm_deg", "thumb_deg", "error", "errors": {pose: error},
    "ok"}; angles are world degrees for `side`, with the hand continuing the forearm's line. across: (upper arm,
    forearm) for the character's left replacing GESTURE_ARM_DEG_ACROSS (the fallback): rig_anim searches it per
    character (clear of the head - neckwear is drawn under the arm - above the hold_card hand)."""
    gesture = UP_GESTURE.get(variant)
    if gesture is None:
        return None
    if variant in POSE_GESTURE:
        cands = {"outward": GESTURE_ARM_DEG[gesture], "across": tuple(across or GESTURE_ARM_DEG_ACROSS[gesture])}
    else:
        cands = {"hold_card": GESTURE_ARM_DEG[gesture]}
    sided = math.hypot(*thumb_vec) > 1e-9
    thumbs = {k: thumb_world_deg(thumb_vec, side_deg(fa, side)) for k, (_, fa) in cands.items()} if sided else {}
    errors = {k: ang_diff(t, target_deg("up", side)) for k, t in thumbs.items()}
    passing = [k for k in cands if k in errors and errors[k] <= THUMB_TOL]
    pose = passing[0] if passing else next(iter(cands))
    ua, fa = cands[pose]
    return {"gesture": gesture, "pose": pose, "upperarm_deg": side_deg(ua, side), "forearm_deg": side_deg(fa, side),
            "thumb_deg": thumbs.get(pose), "error": errors.get(pose), "errors": errors,
            "ok": bool(passing) if sided else None}
