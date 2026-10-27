"""rig_anim.py - the rig's animations (spine_rig.py stage 5): idle, blink, wave, cheer_jump, the gestures
(thumbs_up, point, hold_card), emotions, and the body moves walk, run, squat, jump_hurdle and wave_flag (the last two
only with the props they use, rig_props); with garden props (`use`: water / grow) plant_seed, water and grow_0..N, the
last on their own track: each holds one plant stage after a squash-and-stretch pop. plant_seed fires the event `seed`
and water the event `pour`, for a game to grow the plant on.

Targets are world angles in degrees (0 = out to the character's left, the picture's right; 90 = up), turned into bone
rotations against the rest pose, sampled at FPS_KEYS, eased and velocity-continuous. Arms keep clear of the head zone.
With annotations each gesture's hold pose is chosen by the painted thumb (rig_hands.hold_pose), the across hold is
searched per character (across_hold), and a sleeve mesh whose forearm crosses the body changes layer with drawOrder
keys while the forearm is clear of the torso (crossing_offsets, crossing_times).

  anim = rig_anim.build(geo, export, expr, doubts)   # anim.anims, anim.gesture_info, anim.crossing
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

import rig_hands
from rig_frame import grow
from rig_roles import ann_roles, foot_of, headgear, is_role, role, soft_kind

FPS_KEYS = 30
CROSS_EDGE = 3   # px: a sleeve crossing the body changes layer while its forearm is clear of the torso eroded this much
WAVE_FA_FALLBACK = 40.0   # annotations: the wave's forearm (left side) when no angle keeps the paw clear of the head

# Annotations: the "across" hold of point / thumbs_up is searched per character (character's left, world degrees):
ACROSS_UA_RANGE = (-85.0, -45.0)   # upper arm: down and a little out, the elbow at the side
ACROSS_FA_RANGE = (160.0, 190.0)   # forearm: across the chest toward the character's other side
ACROSS_STEP = 5.0
GESTURE_RAISE = (0.0, 0.7)          # s: a gesture's raise and lower windows, 0.7 s each (the old 0.6 s raise and 0.55 s
GESTURE_LOWER = (1.7, 2.4)          # lower jerked the beaver's long arm to and from across the chest: jerky_bones); the
GESTURE_SWAPS = (sum(GESTURE_RAISE) / 2, sum(GESTURE_LOWER) / 2)   # hand and face swap halfway through each
ACROSS_ABOVE_CARD = 0.04           # x body height: the across hand sits at least this far above the hold_card hand
# Whole legs (rig_variants.add_legs; experiments/2026-10-16-keypose-refs): the tail lies out flat behind in a full
# crouch by up to TAIL_OUT_DEG (the beaver's key poses: 30); in a crouch the arms hang down beside the knees
# (CROUCH_ARMS: upper arm, forearm, world degrees, character's left)
TAIL_OUT_DEG = 30.0
CROUCH_ARMS = (-56.0, -80.0)
LEGS_AIR_SHEETS = ("jump",)        # legs sheets whose fold happens in the air (leg_track)
LEGS_FADE = 2 / FPS_KEYS           # s: at a legs swap the incoming drawing fades in over this, then the outgoing out


def wave_forearm(clear, side: str, annotated: bool) -> tuple:
    """(world forearm angle, cleared) for the wave: upright (85 deg on the left) unless that puts the paw behind the
    head, then tilted outwards in 2.5-degree steps down to 40; clear(forearm_deg) says whether a forearm angle keeps
    the paw clear, tested at both ends of the +-18 degree wave. When nothing clears, annotation mode uses
    WAVE_FA_FALLBACK (the most outward angle searched; the fox's wide cheeks need it) and legacy keeps the upright
    angle, as it always did. Right-side angles are mirrored (180 - left)."""
    sgn = 1 if side == "l" else -1
    for f_deg in np.arange(85.0, 39.9, -2.5):
        w_ = f_deg if side == "l" else 180 - f_deg
        if clear(w_ - 18 * sgn) and clear(w_ + 18 * sgn):
            return w_, True
    if annotated:
        return (WAVE_FA_FALLBACK if side == "l" else 180 - WAVE_FA_FALLBACK), False
    return (85.0 if side == "l" else 95.0), False


def across_hold(clear, paw_y, card_y: float, min_gap: float, fallback: tuple) -> tuple:
    """(upper arm, forearm, status) world angles (character's left) for an across-the-chest gesture hold, searched over
    ACROSS_UA_RANGE x ACROSS_FA_RANGE (ACROSS_STEP apart) among the angles whose arm clear(ua, fa) keeps clear of the
    head (spine_rig passes the head zone; neckwear is drawn under the forearm and hand). paw_y(ua, fa) and card_y (the
    hold_card paw) are image y, down. status "ok": the highest paw at least min_gap above hold_card's (the first one
    on a tie). "low": none is that high, so the highest clear paw that is still above hold_card's (the two poses may
    read alike: a doubt). "none": no clear paw above hold_card's, (*fallback, "none")."""
    best = low = None
    for ua in np.arange(ACROSS_UA_RANGE[0], ACROSS_UA_RANGE[1] + 0.01, ACROSS_STEP):
        for fa in np.arange(ACROSS_FA_RANGE[0], ACROSS_FA_RANGE[1] + 0.01, ACROSS_STEP):
            ua_, fa_ = float(ua), float(fa)
            if not clear(ua_, fa_):
                continue
            y = paw_y(ua_, fa_)
            if y < card_y and (low is None or y < low[0]):
                low = (y, ua_, fa_)
            if y <= card_y - min_gap and (best is None or y < best[0]):
                best = (y, ua_, fa_)
    if best:
        return best[1], best[2], "ok"
    if low:
        return low[1], low[2], "low"
    return float(fallback[0]), float(fallback[1]), "none"


# ------------------------------------------------------------------ curves

def wrap(x):
    return (x + 180) % 360 - 180


def track(fn, dur):
    """fn(t) sampled every 1/FPS_KEYS s over [0, dur] as Spine timeline keys."""
    n_ = int(round(dur * FPS_KEYS))
    return [{"time": round(i / FPS_KEYS, 4), "value": round(fn(i / FPS_KEYS), 3)} for i in range(n_ + 1)]


def smooth(t, t0, t1):
    u = min(1.0, max(0.0, (t - t0) / (t1 - t0)))
    return u * u * u * (u * (6 * u - 15) + 10)   # smootherstep: zero velocity and acceleration at ends


def hermite(points):
    """Smooth curve through (time, value, slope) points; C1 continuous."""
    def f(t):
        if t <= points[0][0]:
            return points[0][1]
        for (t0, v0, m0), (t1, v1, m1) in zip(points, points[1:]):
            if t0 <= t <= t1:
                h = t1 - t0
                u = (t - t0) / h
                h00, h10, h01, h11 = 2*u**3 - 3*u**2 + 1, u**3 - 2*u**2 + u, -2*u**3 + 3*u**2, u**3 - u**2
                return h00 * v0 + h10 * h * m0 + h01 * v1 + h11 * h * m1
        return points[-1][1]
    return f


def catmull(knots, flat_ends: bool = True):
    """Smooth curve through (time, value) knots with Catmull-Rom slopes, flat wherever the value turns (a hold or a
    peak reads as a pose and never overshoots) and at the ends, or there along the end segment (flat_ends=False:
    a curve driven by an eased parameter, which is flat there already); C1 continuous."""
    slopes = []
    last = len(knots) - 1
    for i, (t_, v_) in enumerate(knots):
        if 0 < i < last and (knots[i + 1][1] - v_) * (v_ - knots[i - 1][1]) > 0:
            slopes.append((knots[i + 1][1] - knots[i - 1][1]) / (knots[i + 1][0] - knots[i - 1][0]))
        elif not flat_ends and last and i in (0, last):
            a, b = (knots[0], knots[1]) if i == 0 else (knots[-2], knots[-1])
            slopes.append((b[1] - a[1]) / (b[0] - a[0]))
        else:
            slopes.append(0.0)
    return hermite([(t_, v_, m_) for (t_, v_), m_ in zip(knots, slopes)])


# ------------------------------------------------------------------ geometry

@dataclass
class Geometry:
    """The placed rig as the animations see it (spine_rig stages 3-4): full-resolution master px, y down."""
    pieces: dict                    # name -> {"img", "cx", "cy", "unit", "angle", "mask", ...} (spine_rig.main)
    joints: dict                    # bone -> pivot (x, y)
    bone_dir: dict                  # bone -> pivot to the far end of its piece
    rest: dict                      # bone -> world angle at rest, degrees (y up)
    head_zone: np.ndarray | None    # the whole head assembly, grown: what the arms keep clear of
    fg: np.ndarray                  # the master's silhouette
    unit: float                     # Spine units per master px
    ann: object | None = None       # the resolved annotations (rig_annotations.load); None for a legacy build
    parents: dict | None = None     # bone -> parent bone (the locomotion animations move feet in their parent's frame)
    props: dict | None = None       # rig_props.add's result: held / ground props not in the master
    legs: dict | None = None        # rig_variants.add_legs' result: whole-legs drawings (squat, jumps); None: squash_hips


def head_zone(head_any: np.ndarray | None, pieces: dict, parent_of, r: int, roles: dict | None = None) -> np.ndarray | None:
    """The head (head_any: the expression heads' or head_base's mask) with its ears, antlers, horns and hats,
    grown by r px; None without a head. roles: the annotated roles (rig_roles.ann_roles; None: from the names)."""
    if head_any is None:
        return None
    for n_ in pieces:
        if parent_of(n_) in ("head_base",) or role(n_, roles)[1] == "hat" or (role(n_, roles)[1] == "back" and role(n_, roles)[0] == "head"):
            head_any |= pieces[n_]["mask"]
    return grow(head_any, r)


def crossing_offsets(ua: str, ex) -> list | None:
    """drawOrder offsets (Spine 4.2) that draw sleeve mesh `ua` where a two-piece forearm is drawn - above the
    torso, and above the neckwear when there is one (rig_place.apply_layers) - with its hand just above (over_forearm)
    or below it, for a hold whose forearm crosses the body. None when that changes nothing. ex: rig_slots.Export."""
    pieces = ex.pieces
    names = [s_["name"] for s_ in ex.slots]
    hand = f"hand_{ua[-1]}"
    moved = ([ua, hand] if ex.hand_over else [hand, ua]) if hand in names else [ua]
    alt = [("head" if n == "head_base" else n) for n in sorted(pieces, key=lambda n: ex.layer_key(n, "forearm"))
           if "mesh_of" not in pieces[n]]
    sleeves_ = [n for n in alt if "mesh" in pieces.get(n, {})]
    followers = set(sleeves_) | {f"hand_{n[-1]}" for n in sleeves_}
    after = alt[alt.index(ua) + 1:]
    anchor = next((n for n in after if n not in followers and n in names), None)   # the next fixed slot
    target = [n for n in names if n not in moved]
    at = target.index(anchor) if anchor else len(target)
    target[at:at] = moved
    off = [{"slot": n, "offset": target.index(n) - i} for i, n in enumerate(names) if target.index(n) != i]
    return off or None


# ------------------------------------------------------------------ animations

class Animator:
    """Builds the animations of one rig into `anims`; `gesture_info` holds each annotated hold (report.json) and
    `crossing` the holds that move a sleeve mesh over the torso. Doubts are appended to `doubts`."""

    def __init__(self, geo: Geometry, ex, expr: list, doubts: list):
        self.geo, self.ex, self.expr, self.doubts = geo, ex, expr, doubts
        self.prefix = ex.prefix
        self.anims, self.gesture_info, self.crossing = {}, {}, {}
        pieces, joints, bone_dir = geo.pieces, geo.joints, geo.bone_dir
        self.Hf, self.Wf = geo.fg.shape
        self.torso_core = ~grow(~pieces["torso"]["mask"], CROSS_EDGE) \
            if "torso" in pieces and any("mesh" in p_ for p_ in pieces.values()) else None
        self.paw = {}                                                # side -> (hand length, half its breadth), master px
        for side_ in (("l", "r") if geo.ann is not None else ()):
            hd_ = f"hand_{side_}"
            if hd_ in pieces and hd_ in bone_dir and pieces[hd_]["mask"].any():
                d_ = bone_dir[hd_] / (np.linalg.norm(bone_dir[hd_]) + 1e-9)
                ys_, xs_ = np.nonzero(pieces[hd_]["mask"])
                across = (xs_ - joints[hd_][0]) * -d_[1] + (ys_ - joints[hd_][1]) * d_[0]
                self.paw[side_] = (float(np.linalg.norm(bone_dir[hd_])), float(np.percentile(across, 95) - np.percentile(across, 5)) / 2)
        self.neutral = f"{self.prefix}head_neutral" if f"{self.prefix}head_neutral" in expr else None
        # Annotations: each hold's pose and thumb, by (animation, side), for report.json and the resolved holds. The
        # mirror is anatomy's (the painted side); a gesture can only choose its pose (rig_hands.hold_pose).
        self.hand_outputs = {o.name: (p_, o) for p_ in geo.ann.pieces.values() for o in p_.outputs if p_.role == "hand"} \
            if geo.ann is not None else {}
        self.roles = ann_roles(geo.ann)                              # annotated roles (None: from the names)
        self.tail_n = next((n for n in pieces if is_role(n, self.roles, "tail", ("tail",))), None)

    # ---- slots

    def var(self, slot: str, v: str | None) -> str | None:
        """Attachment name of a slot's variant (None = its rest attachment); None if the rig doesn't have it."""
        name = f"{self.prefix}{slot}_{v}" if v else f"{self.prefix}{slot}"
        return name if name in self.ex.skin.get(slot, {}) else None

    def swaps(self, anim: dict, slot: str, keys: list):
        """Key attachment swaps [(time, variant or None)] on a slot, skipping variants this character lacks."""
        var = self.var
        if not var(slot, None) or not any(var(slot, v) for _, v in keys if v):
            return
        anim.setdefault("slots", {}).setdefault(slot, {})["attachment"] = [{"time": round(t, 3), "name": var(slot, v) or var(slot, None)} for t, v in keys]

    # ---- drawOrder crossing

    def forearm_on_torso(self, side: str, ua_deg: float, fa_deg: float) -> bool:
        """Would the forearm (elbow to wrist, its painted width; rest-pose geometry) lie over the torso, eroded by
        CROSS_EDGE px, with these world angles?"""
        joints, bone_dir, torso_core = self.geo.joints, self.geo.bone_dir, self.torso_core
        fa_, ua_ = f"forearm_{side}", f"upperarm_{side}"
        if torso_core is None or fa_ not in joints or ua_ not in joints:
            return False
        L1, L2 = float(np.linalg.norm(joints[fa_] - joints[ua_])), float(np.linalg.norm(bone_dir[fa_]))
        half = 0.5 * self.geo.pieces[fa_]["mask"].sum() / max(L2, 1.0)
        dirn = lambda a: np.array([math.cos(math.radians(a)), -math.sin(math.radians(a))])    # noqa: E731
        e = joints[ua_] + L1 * dirn(ua_deg)
        u_, n_ = dirn(fa_deg), dirn(fa_deg + 90)
        for f in np.linspace(0.1, 1.0, 10):
            for k in (-1.0, 0.0, 1.0):
                q = e + u_ * f * L2 + n_ * k * half
                x_, y_ = int(q[0]), int(q[1])
                if 0 <= x_ < self.Wf and 0 <= y_ < self.Hf and torso_core[y_, x_]:
                    return True
        return False

    def crossing_times(self, side: str, angles, raise_: tuple, lower: tuple) -> tuple:
        """(in, out) times of a crossing hold's drawOrder keys: the last frame of the raise before the forearm first
        lies over the torso, and the first frame of the lower after it last does (forearm_on_torso; angles(t) ->
        (upper arm, forearm) world degrees), so the sleeve changes layer while clear of the torso. Midpoints of the
        raise / lower when it never clears there (already over the torso at rest, or never over it)."""
        def frames(a, b):                              # frame indices (keys land on sampled frames, as track's)
            return range(int(round(a * FPS_KEYS)), int(round(b * FPS_KEYS)) + 1)
        up = [i for i in frames(*raise_) if self.forearm_on_torso(side, *angles(i / FPS_KEYS))]
        down = [i for i in frames(*lower) if self.forearm_on_torso(side, *angles(i / FPS_KEYS))]
        t_in, t_out = round(sum(raise_) / 2, 3), round(sum(lower) / 2, 3)
        if up and up[0] > frames(*raise_)[0]:
            t_in = round((up[0] - 1) / FPS_KEYS, 4)
        if down and down[-1] < frames(*lower)[-1]:
            t_out = round((down[-1] + 1) / FPS_KEYS, 4)
        return t_in, t_out

    # ---- clear of the head

    def arm_probes(self, side: str, ua_deg: float, fa_deg: float):
        """(probe points, paw centre) in master px with these world angles (rest-pose geometry): elbow, forearm
        midpoint, hand end, and with annotations both sides of the paw; the paw centre is the hand end without them.
        None when the arm is missing."""
        joints, bone_dir = self.geo.joints, self.geo.bone_dir
        ua, fa = f"upperarm_{side}", f"forearm_{side}"
        if ua not in joints or fa not in joints:
            return None
        S_, E_ = joints[ua], joints[fa]
        L1 = float(np.linalg.norm(E_ - S_))
        L2 = float(np.linalg.norm(bone_dir[fa])) + float(np.linalg.norm(bone_dir.get(f"hand_{side}", np.zeros(2))))
        e = S_ + L1 * np.array([math.cos(math.radians(ua_deg)), -math.sin(math.radians(ua_deg))])
        h_ = e + L2 * np.array([math.cos(math.radians(fa_deg)), -math.sin(math.radians(fa_deg))])
        probes, centre = [e, (e + h_) / 2, h_], h_
        if side in self.paw:                                     # annotations: the paw's breadth, not only its axis
            lh, rh = self.paw[side]
            u_ = (h_ - e) / (np.linalg.norm(h_ - e) + 1e-9)
            c_, n_ = h_ - u_ * lh / 2, np.array([-u_[1], u_[0]])
            probes += [c_ + n_ * rh, c_ - n_ * rh]
            centre = c_
        return probes, centre

    def clear_of(self, zone, side: str, ua_deg: float, fa_deg: float) -> bool:
        """Would the arm's probes (arm_probes) sit outside `zone` with these world angles?"""
        ap = self.arm_probes(side, ua_deg, fa_deg) if zone is not None else None
        for q in (ap[0] if ap else ()):
            x_, y_ = int(q[0]), int(q[1])
            if 0 <= x_ < self.Wf and 0 <= y_ < self.Hf and zone[y_, x_]:
                return False
        return True

    def clear_of_head(self, side: str, ua_deg: float, fa_deg: float) -> bool:
        """Would the elbow and hand sit outside the head zone with these world angles (rest-pose geometry)?"""
        return self.clear_of(self.geo.head_zone, side, ua_deg, fa_deg)

    def best_across(self, side: str, gesture_name: str) -> tuple:
        """Annotations: (upper arm, forearm, found) world angles, character's LEFT convention, of the across hold
        (across_hold): clear of the head zone, paw above the hold_card paw. Neckwear is no obstacle: with
        annotations the forearm and hand are drawn above it (rig_place.apply_layers)."""
        fb = rig_hands.GESTURE_ARM_DEG_ACROSS[gesture_name]
        card = self.arm_probes(side, *(rig_hands.side_deg(d_, side) for d_ in rig_hands.GESTURE_ARM_DEG["hold_card"]))
        if card is None:
            return float(fb[0]), float(fb[1]), False

        def w(u_, f_):
            return rig_hands.side_deg(u_, side), rig_hands.side_deg(f_, side)
        return across_hold(lambda u_, f_: self.clear_of(self.geo.head_zone, side, *w(u_, f_)),
                           lambda u_, f_: float(self.arm_probes(side, *w(u_, f_))[1][1]), float(card[1][1]),
                           ACROSS_ABOVE_CARD * float(np.ptp(np.nonzero(self.geo.fg)[0])), fb)

    def best_raise(self, lo: float = 10.0, hi: float = 70.0):
        """Shoulder and forearm angles (character's left, degrees above +x) that put the paw highest while elbow
        and paw stay clear of the head on BOTH sides; the right side uses the mirror image."""
        best, best_h = (lo, lo + 10.0), -1e9
        for ua_deg in np.arange(lo, hi + 0.1, 5.0):
            for off in np.arange(0.0, 70.1, 10.0):
                fa_deg = min(100.0, ua_deg + off)
                if not (self.clear_of_head("l", ua_deg, fa_deg) and self.clear_of_head("r", 180 - ua_deg, 180 - fa_deg)):
                    continue
                h_ = math.sin(math.radians(ua_deg)) + 1.4 * math.sin(math.radians(fa_deg))   # paw height, roughly
                if h_ > best_h:
                    best, best_h = (float(ua_deg), float(fa_deg)), h_
        return best

    # ---- hands

    def straighten(self, fa: str, hd: str) -> float:
        """Annotations: the hand's rotation that makes its world angle the forearm's once the arm's turn is fully
        applied - at a hold the hand continues the forearm's line, the convention rig_hands' mirror rule assumes."""
        return wrap(self.geo.rest[fa] - self.geo.rest[hd])

    def hand_thumb(self, hd: str, v: str):
        """(worn thumb vector, facing) of the hand output `<slot>_<variant>`, or (None, None)."""
        rec = self.hand_outputs.get(f"{hd}_{v}")
        if rec is None or "wrist" not in rec[1].points or "thumb_tip" not in rec[1].points:
            return None, (rec[0].facing if rec else None)
        pts_ = rec[1].points
        return rig_hands.thumb_vector(pts_["wrist"], pts_["thumb_tip"], pts_.get("fingertip")), rec[0].facing

    def note_hold(self, anim: str, side: str, v: str, pose: str, ua_deg, fa_deg: float, target):
        """Record a hold: its pose, arm angles, the thumb's world angle and its target (up for the gestures that
        need it, else where anatomy puts the thumb; None without a facing)."""
        tv, facing = self.hand_thumb(f"hand_{side}", v)
        if target is None and facing in ("palm", "back"):
            target = rig_hands.anatomical_thumb_deg(fa_deg, side, facing)
        th = rig_hands.thumb_world_deg(tv, fa_deg) if tv is not None and tv != (0.0, 0.0) else None
        self.gesture_info[(anim, side)] = {
            "variant": v, "facing": facing, "pose": pose, "upperarm_deg": None if ua_deg is None else round(ua_deg, 1),
            "forearm_deg": round(fa_deg, 1), "thumb_deg": None if th is None else round(th, 1),
            "thumb_target_deg": None if target is None else round(target, 1),
            "thumb_error_deg": None if th is None or target is None else round(rig_hands.ang_diff(th, target), 1)}
        if th is not None and target is not None:
            print(f"  {anim} ({side}): {v} hand, {facing or 'facing ?'}, {pose} pose, thumb at {th:.0f} deg "
                  f"(target {target:.0f}, off {rig_hands.ang_diff(th, target):.0f})")

    # ---- the animations

    def idle(self):
        """idle: a 2.4 s seamless loop (breathing torso, head and arm sway, antlers / ears); blink."""
        pieces, expr, prefix, neutral = self.geo.pieces, self.expr, self.prefix, self.neutral
        T = 2.4
        w0 = 2 * math.pi / T
        idle = {"bones": {}}
        if "torso" in pieces:
            idle["bones"]["torso"] = {"scale": [{"time": k_["time"], "x": 1, "y": round(1 + 0.012 * (1 - math.cos(w0 * k_["time"])), 4)} for k_ in track(lambda t: 0, T)]}
        if "head_base" in pieces:
            idle["bones"]["head_base"] = {"rotate": track(lambda t: 2.0 * math.sin(w0 * t), T)}
        for side, sgn in (("l", 1), ("r", -1)):
            if f"upperarm_{side}" in pieces:
                idle["bones"][f"upperarm_{side}"] = {"rotate": track(lambda t, sg=sgn: 2.5 * sg * math.sin(w0 * t), T)}
        for n in pieces:
            if headgear(n, self.roles):
                idle["bones"][n] = {"rotate": track(lambda t: 2.0 * math.sin(w0 * t + 0.8), T)}
        if neutral and f"{prefix}head_blink" in expr:
            idle["slots"] = {"head": {"attachment": [{"time": 0, "name": neutral}, {"time": 1.8, "name": f"{prefix}head_blink"}, {"time": 1.93, "name": neutral}]}}
            self.anims["blink"] = {"slots": {"head": {"attachment": [{"time": 0, "name": neutral}, {"time": 0.5, "name": f"{prefix}head_blink"}, {"time": 0.63, "name": neutral}, {"time": 1.0, "name": neutral}]}}}
        self.anims["idle"] = idle

    def wave(self):
        """wave: the character's left arm (picture right) rises, forearm waves twice, arm lowers."""
        pieces, rest, expr, prefix, neutral = self.geo.pieces, self.geo.rest, self.expr, self.prefix, self.neutral
        ann = self.geo.ann
        side = "l" if f"upperarm_l" in pieces else ("r" if f"upperarm_r" in pieces else None)
        if not (side and f"forearm_{side}" in pieces):
            return
        ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
        mirror = 1 if side == "l" else -1
        tgt_ua = 20.0 if side == "l" else 160.0          # out to the side, a little above horizontal
        tgt_fa, cleared = wave_forearm(lambda f_: self.clear_of_head(side, tgt_ua, f_), side, ann is not None)
        if not cleared and ann is not None:
            print(f"  wave: nothing clears the head; forearm at the fallback {tgt_fa}")
        print(f"  wave forearm angle (clear of the head through the wave): {tgt_fa}")
        d_ua = wrap(tgt_ua - rest[ua])
        d_fa = wrap(tgt_fa - rest[fa]) - d_ua              # forearm is a child: subtract the parent's turn
        d_hd = wrap((tgt_fa + 5 * mirror) - rest.get(hd, tgt_fa)) - d_ua - d_fa if hd in pieces else 0
        if ann is not None and hd in pieces:
            d_hd = self.straighten(fa, hd)
            self.note_hold("wave", side, "open", "wave", tgt_ua, tgt_fa, None)     # no choice: the thumb is anatomy's
        T, up, down = 3.0, (0.0, 0.7), (2.35, 3.0)

        def env(t):
            return smooth(t, *up) * (1 - smooth(t, *down))

        def osc(t):  # two waves between the raise and the lower, faded in and out
            ramp = smooth(t, 0.55, 0.95) * (1 - smooth(t, 1.9, 2.35))
            return ramp * math.sin(2 * math.pi * 1.25 * (t - 0.55))

        bones_w = {ua: {"rotate": track(lambda t: d_ua * env(t), T)},
                   fa: {"rotate": track(lambda t: d_fa * env(t) + 18 * mirror * osc(t), T)}}
        if hd in pieces:
            bones_w[hd] = {"rotate": track(lambda t: d_hd * env(t) + 8 * mirror * osc(t - 0.08), T)}
        if "head_base" in pieces:
            bones_w["head_base"] = {"rotate": track(lambda t: 4 * mirror * env(t), T)}
        self.anims["wave"] = {"bones": bones_w}
        if f"{prefix}head_happy" in expr:
            self.anims["wave"]["slots"] = {"head": {"attachment": [{"time": 0, "name": neutral or expr[0]}, {"time": 0.3, "name": f"{prefix}head_happy"},
                                                                   {"time": 2.7, "name": neutral or expr[0]}, {"time": T, "name": neutral or expr[0]}]}}
        self.swaps(self.anims["wave"], hd, [(0, None), (0.35, "open"), (2.6, None), (T, None)])      # swap mid-motion, open palm to wave

    def cheer_jump(self):
        """cheer_jump: squash, jump with both arms flung up into a V, fist pumps at the top, soft landing, recover."""
        pieces, rest, expr, prefix, neutral = self.geo.pieces, self.geo.rest, self.expr, self.prefix, self.neutral
        ann, swaps = self.geo.ann, self.swaps
        if not ("hips" in pieces and "torso" in pieces):
            return
        T = 1.9
        Hsk = float(np.ptp(np.nonzero(self.geo.fg)[0])) * self.geo.unit   # skeleton height in units
        JUMP = 0.12 * Hsk                                        # apex height; flight 0.30-1.16 s keeps hand accel under the QA limit
        hips_y = hermite([(0, 0, 0), (0.30, 0, 0), (0.73, JUMP, 0), (1.16, 0, 0), (T, 0, 0)])
        sq_y = hermite([(0, 1, 0), (0.28, 0.92, 0), (0.48, 1.06, 0), (0.75, 1.0, 0), (1.08, 1.0, 0), (1.24, 0.91, 0), (1.58, 1.0, 0), (T, 1.0, 0)])
        cj = {"bones": {}}
        cj["bones"]["hips"] = {"translate": [{"time": k_["time"], "x": 0, "y": round(hips_y(k_["time"]), 2)} for k_ in track(lambda t: 0, T)]}
        cj["bones"]["torso"] = {"scale": [{"time": k_["time"], "x": round(1 / math.sqrt(sq_y(k_["time"])), 4), "y": round(sq_y(k_["time"]), 4)}
                                          for k_ in track(lambda t: 0, T)]}
        arm_env = hermite([(0, 0, 0), (0.66, 1, 0), (1.15, 1, 0), (1.85, 0, 0), (T, 0, 0)])   # ~180 deg each way: keep >= 0.65 s
        pump_env = hermite([(0, 0, 0), (0.74, 0, 0), (0.86, 1, 0), (1.02, 1, 0), (1.14, 0, 0), (T, 0, 0)])   # after the apex
        ua_up, fa_up = self.best_raise()
        print(f"  cheer_jump pose (clear of the head, mirrored): upper arm {ua_up} deg, forearm {fa_up} deg")
        for side, tgt in (("l", ua_up), ("r", 180 - ua_up)):            # arms up as high as the head allows
            ua, fa = f"upperarm_{side}", f"forearm_{side}"
            if ua not in pieces:
                continue
            mirror = 1 if side == "l" else -1
            d_ua = wrap(tgt - rest[ua])
            cj["bones"][ua] = {"rotate": track(lambda t, d=d_ua, m=mirror: d * arm_env(t) + 5 * m * pump_env(t) * math.sin(2 * math.pi * 2 * (t - 0.74)), T)}
            if fa in pieces:                                         # forearms bend up beside the head
                fa_tgt = fa_up if side == "l" else 180 - fa_up
                d_fa = wrap(fa_tgt - rest[fa]) - d_ua
                cj["bones"][fa] = {"rotate": track(lambda t, d=d_fa: d * arm_env(t), T)}
                hd_cj = f"hand_{side}"
                if ann is not None and hd_cj in pieces:
                    cj["bones"][hd_cj] = {"rotate": track(lambda t, d=self.straighten(fa, hd_cj): d * arm_env(t), T)}
                    self.note_hold("cheer_jump", side, "fist", "cheer", tgt, fa_tgt, None)   # the thumb is anatomy's
        if "head_base" in pieces:
            cj["bones"]["head_base"] = {"rotate": track(lambda t: 4 * math.sin(math.pi * min(1, max(0, (t - 0.3) / 0.9))) ** 2, T)}
        for n in pieces:                                             # follow-through on soft appendages
            base = soft_kind(n, self.roles)
            if base in ("tail", "ear"):
                amp = 12.0 if base == "tail" else 6.0
                lag = 0.10
                cj["bones"][n] = {"rotate": track(lambda t, a_=amp, l_=lag: -a_ * (hips_y(max(0.0, t - l_)) - hips_y(max(0.0, t - l_ - 1 / 30))) * 30 / (JUMP * 3.5), T)}
        face = next((f"{prefix}head_{e}" for e in ("laugh", "happy") if f"{prefix}head_{e}" in expr), None)
        if face and neutral:
            cj["slots"] = {"head": {"attachment": [{"time": 0, "name": neutral}, {"time": 0.25, "name": face}, {"time": 1.6, "name": neutral}, {"time": T, "name": neutral}]}}
        for side in ("l", "r"):                                       # swaps keyed mid-motion so they read as one move
            swaps(cj, f"upperarm_{side}", [(0, None), (0.33, "raised"), (1.5, None), (T, None)])
            swaps(cj, f"hand_{side}", [(0, None), (0.45, "fist"), (1.4, None), (T, None)])
            foot = foot_of(side, pieces, self.roles)
            if foot:
                swaps(cj, foot, [(0, None), (0.34, "tiptoe"), (1.12, None), (T, None)])
        if self.tail_n:
            swaps(cj, self.tail_n, [(0, None), (0.36, "up"), (1.25, None), (T, None)])
        self.anims["cheer_jump"] = cj

    def gesture(self, name: str, ua_w: float, fa_w: float, hand_v: str, face_e: str | None, side: str = "l", T: float = 2.4):
        """A gesture pose on one arm (the character's left by default): raise, hold, lower, with the hand swapped
        mid-motion. ua_w, fa_w: world angles for the character's left side (0 = out to the side, 90 = up, -90 =
        hanging); with annotations the hold may change to the pose that shows the painted thumb up."""
        pieces, rest, expr, prefix, neutral = self.geo.pieces, self.geo.rest, self.expr, self.prefix, self.neutral
        ann, doubts, gesture_info = self.geo.ann, self.doubts, self.gesture_info
        ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
        if not (ua in pieces and fa in pieces and self.var(hd, hand_v)):
            return
        if side == "r":
            ua_w, fa_w = 180 - ua_w, 180 - fa_w
        tv, facing = self.hand_thumb(hd, hand_v)
        hold, across = None, None
        if ann is not None and tv is not None:
            if hand_v in rig_hands.POSE_GESTURE:   # the across candidate, searched for this character
                across = self.best_across(side, name)
            hold = rig_hands.hold_pose(hand_v, tv, side, across=across[:2] if across else None)
        if hold is not None:                   # annotations: the pose this drawing can show its thumb up in
            ua_w, fa_w = hold["upperarm_deg"], hold["forearm_deg"]
            self.note_hold(name, side, hand_v, hold["pose"], ua_w, fa_w, rig_hands.target_deg("up", side))
            gesture_info[(name, side)]["errors"] = {k: round(e, 1) for k, e in hold["errors"].items()}
            if hold["ok"] is not True:
                why = "the thumb has no side" if hold["ok"] is None else \
                    f"no pose shows the thumb up ({', '.join(f'{k} {e:.0f} deg off' for k, e in hold['errors'].items())})"
                doubts.append({"part": hd, "reason": "gesture_thumb", "gesture": name, "facing": facing,
                               "pose": hold["pose"], "detail": f"{why}; kept the {hold['pose']} pose"})
                print(f"  ? doubt: {name}: {why}; kept the {hold['pose']} pose")
            if hold["pose"] == "across":
                gesture_info[(name, side)]["across_search"] = across[2]
                if across[2] != "ok":
                    why = (f"no across pose clear of the head lifts the paw {ACROSS_ABOVE_CARD:.0%} of body height "
                           f"above hold_card's; used the highest clear one {list(across[:2])}, the two holds may read "
                           "alike") if across[2] == "low" else \
                        f"no across pose clear of the head has the paw above hold_card's; kept {list(across[:2])}"
                    doubts.append({"part": hd, "reason": "gesture_across", "gesture": name, "pose": "across",
                                   "search": across[2], "detail": why})
                    print(f"  ? doubt: {name}: {why}")
        d_ua = wrap(ua_w - rest[ua])
        d_fa = wrap(fa_w - rest[fa]) - d_ua

        def env(t):
            return smooth(t, *GESTURE_RAISE) * (1 - smooth(t, *GESTURE_LOWER))
        g_ = {"bones": {ua: {"rotate": track(lambda t: d_ua * env(t), T)}, fa: {"rotate": track(lambda t: d_fa * env(t), T)}}}
        if ann is not None and hd in pieces:
            d_hd = self.straighten(fa, hd)
            g_["bones"][hd] = {"rotate": track(lambda t: d_hd * env(t), T)}
        if "head_base" in pieces:
            g_["bones"]["head_base"] = {"rotate": track(lambda t: 3 * (1 if side == "l" else -1) * env(t), T)}
        if face_e and neutral and f"{prefix}head_{face_e}" in expr:
            g_["slots"] = {"head": {"attachment": [{"time": 0, "name": neutral},
                                                   {"time": GESTURE_SWAPS[0], "name": f"{prefix}head_{face_e}"},
                                                   {"time": GESTURE_SWAPS[1], "name": neutral}, {"time": T, "name": neutral}]}}
        self.swaps(g_, hd, [(0, None), (GESTURE_SWAPS[0], hand_v), (GESTURE_SWAPS[1], None), (T, None)])
        if "mesh" in pieces.get(ua, {}) and (name == "hold_card" or (hold is not None and hold["pose"] == "across")):
            off = crossing_offsets(ua, self.ex)        # the forearm crosses the body: the sleeve goes over the torso
            if off:                                    # while it is clear of the torso (crossing_times)
                t_in, t_out = self.crossing_times(side, lambda t: (rest[ua] + d_ua * env(t), rest[fa] + (d_ua + d_fa) * env(t)),
                                                  GESTURE_RAISE, GESTURE_LOWER)
                g_["drawOrder"] = [{"time": t_in, "offsets": off}, {"time": t_out}]
                self.crossing.setdefault(ua, []).append(name)
        self.anims[name] = g_

    def emotions(self):
        """emotions: every expression head in turn, 0.8 s each."""
        expr = self.expr
        if expr:
            self.anims["emotions"] = {"slots": {"head": {"attachment": [{"time": round(i * 0.8, 2), "name": e} for i, e in enumerate(expr)]
                                                         + [{"time": round(len(expr) * 0.8, 2), "name": expr[-1]}]}}}


    # ---- body moves: walk, run, squat, jump_hurdle, wave_flag (front view, in place)

    def body_h(self) -> float:
        """Body height in Spine units."""
        return float(np.ptp(np.nonzero(self.geo.fg)[0])) * self.geo.unit

    def local(self, bone: str, dx: float, dy: float) -> tuple:
        """A world offset (Spine units, y up) in `bone`'s parent's frame at rest: translate keys are parent-local."""
        par = (self.geo.parents or {}).get(bone)
        a = math.radians(self.geo.rest.get(par, 0.0)) if par else 0.0
        return dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)

    def along_hips(self, bone: str) -> float:
        """How far below the hips' origin, along the hips bone, `bone`'s pivot sits (Spine units)."""
        j, rest = self.geo.joints, self.geo.rest
        a = math.radians(rest["hips"])
        d = (np.asarray(j[bone], float) - np.asarray(j["hips"], float))
        return float(d[0] * math.cos(a) - d[1] * math.sin(a)) * self.geo.unit     # master px are y down

    def hips_children(self) -> list:
        """The bones hanging straight off the hips and lying along its axis (within 25 deg): the torso, the feet or
        legs. Scaling the hips along its axis squashes them too; they get the inverse scale."""
        par, rest = self.geo.parents or {}, self.geo.rest
        out = []
        for b, p_ in par.items():
            if p_ == "hips" and b in self.geo.pieces:
                rel = abs(((rest[b] - rest["hips"]) + 90) % 180 - 90)
                if rel <= 25:
                    out.append(b)
        return out

    def loose_foot(self, f: str) -> bool:
        """A foot that may move on its own: hung straight off the hips and not worn over the trousers. A boot worn
        over the trouser leg, or hung on a leg piece, must ride with them or the leg leaves the boot."""
        return f not in self.ex.worn and (self.geo.parents or {}).get(f) == "hips"

    def feet(self) -> list:
        return [f for f in (foot_of(s_, self.geo.pieces, self.roles) for s_ in ("l", "r")) if f]

    def tr(self, fn, T):
        return [{"time": k_["time"], "x": round(fn(k_["time"])[0], 2), "y": round(fn(k_["time"])[1], 2)} for k_ in track(lambda t: 0, T)]

    def sc(self, fn, T):
        return [{"time": k_["time"], "x": round(fn(k_["time"])[0], 4), "y": round(fn(k_["time"])[1], 4)} for k_ in track(lambda t: 0, T)]

    def locomotion(self, name: str, run: bool):
        """walk / run in place, a seamless loop of two steps: the hips bob (lowest at each contact) and sway over the
        standing foot, the feet stay planted (counter to the hips) and take turns stepping toward the viewer (a small
        lift, a little bigger), the torso and head counter-tilt, the arms swing (run: bent, fists, pumping)."""
        pieces, rest, ann = self.geo.pieces, self.geo.rest, self.geo.ann
        if "hips" not in pieces or not self.feet():
            return
        H = self.body_h()
        T = 0.64 if run else 1.0
        bob, lift, grow_, sway = (0.022, 0.03, 0.08, 0.004) if run else (0.012, 0.025, 0.07, 0.005)
        w = 2 * math.pi / T

        def hip(t):
            return sway * H * math.sin(w * t), bob * H * math.sin(w * t) ** 2
        an = {"bones": {"hips": {"translate": self.tr(hip, T)}}}
        for f in self.feet():
            sgn = 1 if f == foot_of("l", pieces, self.roles) else -1
            step = (lambda t, g=sgn: max(0.0, g * math.sin(w * t)) ** 2)
            an["bones"][f] = {"scale": self.sc(lambda t, st=step: (1 + grow_ * st(t), 1 + grow_ * st(t)), T)}
            # a foot under the trousers stays planted while the hips bob and lifts as it steps; a boot worn over the
            # trouser leg (or hung on a leg piece) rides with the hips instead, or the leg would leave the boot
            if self.loose_foot(f):
                an["bones"][f]["translate"] = self.tr(lambda t, st=step, f_=f: self.local(f_, -0.5 * hip(t)[0], -hip(t)[1] + lift * H * st(t)), T)
        if "torso" in pieces:
            an["bones"]["torso"] = {"rotate": track(lambda t: (3.0 if run else 1.5) * math.sin(w * t), T)}
        if "head_base" in pieces:
            an["bones"]["head_base"] = {"rotate": track(lambda t: -(2.0 if run else 1.0) * math.sin(w * t), T)}
        for side, m in (("l", 1), ("r", -1)):
            ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
            if ua not in pieces:
                continue
            if run:                                      # bent arms, fists up at the sides, pumping against the feet
                ua_t, fa_t = (-65.0, 10.0) if side == "l" else (-115.0, 170.0)    # fists at the waist, beside the body
                d_ua, pump = wrap(ua_t - rest[ua]), (lambda t, mm=m: 10 * mm * math.sin(w * t))
                an["bones"][ua] = {"rotate": track(lambda t, d=d_ua, pp=pump: d + pp(t), T)}
                if fa in pieces:
                    d_fa = wrap(fa_t - rest[fa]) - d_ua
                    an["bones"][fa] = {"rotate": track(lambda t, d=d_fa, pp=pump: d + 0.5 * pp(t), T)}
                    if ann is not None and hd in pieces:
                        an["bones"][hd] = {"rotate": track(lambda t, d=self.straighten(fa, hd): d, T)}
                self.swaps(an, hd, [(0, "fist"), (T, "fist")])
            else:
                an["bones"][ua] = {"rotate": track(lambda t, mm=m: 9 * mm * math.sin(w * t), T)}
                if fa in pieces:
                    an["bones"][fa] = {"rotate": track(lambda t, mm=m: 4 * mm * max(0.0, mm * math.sin(w * t)), T)}
        if self.tail_n:
            an["bones"][self.tail_n] = {"rotate": track(lambda t: (8 if run else 5) * math.sin(w * t - 0.6), T)}
        face = next((f"{self.prefix}head_{e}" for e in (("happy", "laugh") if run else ()) if f"{self.prefix}head_{e}" in self.expr), None)
        if face:
            an["slots"] = {"head": {"attachment": [{"time": 0, "name": face}, {"time": T, "name": face}]}}
        self.anims[name] = an

    def walk(self):
        self.locomotion("walk", run=False)

    def run(self):
        self.locomotion("run", run=True)

    # ---- whole legs (rig_variants.add_legs): drawings swapped in for the trousers and feet

    def has_legs(self, *sheets: str) -> bool:
        """Whether the rig has whole-legs drawings from these sheets (rig_variants.add_legs: squat, jump)."""
        legs = self.geo.legs
        return bool(legs) and all(s_ in legs["seq"] for s_ in sheets)

    def tail_out(self) -> float:
        """Signed degrees that lay the tail out flat behind, toward the horizontal on its own side (at most
        TAIL_OUT_DEG): what the key poses show it doing as the body sinks into a crouch. 0 without a tail."""
        d = self.geo.bone_dir.get(self.tail_n) if self.tail_n else None
        if d is None or not np.any(d):
            return 0.0
        a = math.degrees(math.atan2(-d[1], d[0]))              # world angle of root -> tip (master px are y down)
        to_flat = wrap((0.0 if d[0] >= 0 else 180.0) - a)
        return math.copysign(min(TAIL_OUT_DEG, abs(to_flat)), to_flat)

    def leg_track(self, an: dict, T: float, segs: list, lift=None, air=None, tail: bool = True):
        """Frame-by-frame legs driven by progress. segs: [(sheet, [(t, p), ...])], consecutive, each starting where
        the last ends, at p = 0 at the joins (every sheet starts from the rig's own rest legs). Per sheet, p(t) runs
        smoothly through its keys (flat at each key: holds read as poses); the drawing shown is the nearest in
        progress along the sheet's sequence ("rig", drawing 2, 3, ..., in-betweens in their places; legs_spacing),
        and the rig's own trousers and feet show until the first one. Swaps cross-fade (cross_fade). The legs' height follows a Catmull-Rom curve over p through
        the drawings' heights, and the shown drawing is squashed or stretched to it. On the ground the hips drop by
        the height lost, so the soles stay put; in the air (air(t) -> 1) the body rides lift(t) (Spine units) alone
        and the legs fold under it. A sheet that folds the legs only in the air (LEGS_AIR_SHEETS: the jump's tuck)
        never lowers the hips; it lifts them with a stretched push-off, on the way up only. Its fold, and the
        push-off drawing passing again on the way down, moving the hips while the body lands jerked a rig whose legs
        are half its height (kp_rig's beaver got away with it). The tail lies out flat as the body sinks (tail=False:
        keyed by the caller). Returns height(t)."""
        legs = self.geo.legs
        h = legs["height"]
        lift, air = lift or (lambda t: 0.0), air or (lambda t: 0.0)
        rest_h = h["rig"]
        curves = []
        for sheet, keys in segs:
            seq = legs["seq"][sheet]
            pos = self.legs_spacing([h[v] for v in seq])
            top = next(t_ for t_, p_ in keys if p_ == max(p__ for _, p__ in keys))   # an air sheet's take-off
            curves.append((keys[-1][0], seq, hermite([(t_, p_, 0.0) for t_, p_ in keys]),     # ends at its top
                           catmull([(q_, h[v]) for q_, v in zip(pos, seq)], flat_ends=False),
                           top if sheet in LEGS_AIR_SHEETS else None, pos))

        def at(t):
            for t1, seq, p, hp, top, pos in curves:
                if t <= t1 + 1e-9 or t1 == curves[-1][0]:
                    pp = min(1.0, max(0.0, p(t)))
                    return seq[min(range(len(seq)), key=lambda i: abs(pos[i] - pp))], hp(pp), top

        def height(t):
            return at(t)[1]

        k = 0.02 * rest_h

        def sink(t):                         # how far the hips sit below rest on the ground; an air sheet only
            _, h_, top = at(t)               # lifts them, while pushing off (a smooth max with 0: a kink jerks)
            x = h_ - rest_h
            if top is None:
                return x
            return 0.5 * (x + math.sqrt(x * x + k * k) - k) if t < top else 0.0
        an["bones"].setdefault("hips", {})["translate"] = self.tr(lambda t: (0.0, sink(t) * (1 - air(t)) + lift(t)), T)
        if tail and self.tail_n and "squat" in legs["seq"]:
            out, drop = self.tail_out(), max(rest_h - h[legs["seq"]["squat"][-1]], 1e-6)
            an["bones"][self.tail_n] = {"rotate": track(
                lambda t: out * min(1.0, max(0.0, rest_h - height(max(0.0, t - 0.06))) / drop), T)}
        shown = [(k_["time"], at(k_["time"])[0]) for k_ in track(lambda t: 0, T)]
        self.cross_fade(an, T, [(t_, v) for i, (t_, v) in enumerate(shown) if i == 0 or v != shown[i - 1][1]], height)
        return height

    def cross_fade(self, an: dict, T: float, plan: list, height):
        """Show plan's drawings [(t_swap, variant or "rig")] with a cross-fade at every swap: the incoming one (in
        the other legs slot, or the rig's own trousers and feet for "rig") fades in over LEGS_FADE before the swap,
        then the outgoing one fades out over LEGS_FADE after it (Spine rgba slot keys), so one drawing is always
        opaque and nothing pops (fades shorten when swaps come close together). Each legs slot's bone is scaled so
        its drawing has the legs' height at every frame."""
        legs = self.geo.legs
        h = legs["height"]
        slot_a, slot_b = legs["slots"]
        groups = {"rig": list(legs["hide"]), slot_a: [slot_a], slot_b: [slot_b]}
        shows, nxt = [], slot_a                        # [group, drawing, shown from, to]
        for i, (t0, v) in enumerate(plan):
            g = "rig" if v == "rig" else nxt
            if g != "rig":
                nxt = slot_b if g == slot_a else slot_a
            shows.append((g, v, t0, plan[i + 1][0] if i + 1 < len(plan) else T))
        windows, alpha = {g: [] for g in groups}, {g: [] for g in groups}
        for i, (g, v, t0, t1) in enumerate(shows):
            d_in = 0.0 if i == 0 else min(LEGS_FADE, 0.5 * (t0 - shows[i - 1][2]))
            d_out = 0.0 if i == len(shows) - 1 else min(LEGS_FADE, 0.5 * (shows[i + 1][3] - t1))
            a0, a1 = max(0.0, t0 - d_in), min(T, t1 + d_out)
            windows[g].append((a0, a1, v))
            alpha[g] += [(a0, 0.0 if d_in else 1.0), (t0, 1.0), (t1, 1.0), (a1, 0.0 if d_out else 1.0)]
        slots = an.setdefault("slots", {})
        for g, names in groups.items():
            ws, keys = windows[g], []
            for (a0, a1, v), w_next in zip(ws, ws[1:] + [None]):
                keys.append((a0, v))
                if w_next is None or w_next[0] > a1 + 1e-6:
                    keys.append((a1, None))
            if not ws or ws[0][0] > 0:
                keys.insert(0, (0.0, None))
            rgba = []
            for t_, a_ in sorted(alpha[g]):
                if not rgba or abs(rgba[-1][0] - t_) > 1e-6 or rgba[-1][1] != a_:
                    rgba.append((t_, a_))
            for n in names:
                if g == "rig":                                 # the rig's own part, back at the end
                    att = legs["hide"][n]
                    ak = [{"time": round(t_, 4), "name": att if v else None} for t_, v in keys] + [{"time": T, "name": att}]
                    rk = rgba + [(T, 1.0)]
                else:
                    ak = [{"time": round(t_, 4), "name": legs["atts"][v] if v else None} for t_, v in keys]
                    rk = rgba
                slots[n] = {"attachment": ak,
                            "rgba": [{"time": round(t_, 4), "color": "ffffff%02x" % round(255 * a_)} for t_, a_ in rk]
                            or [{"time": 0, "color": "ffffffff"}]}
            if g != "rig":                                     # this slot's bone: its drawing at the legs' height

                def own(t_, ws=ws):                            # where two windows touch, the incoming drawing
                    return next((v for a0, a1, v in reversed(ws) if a0 - 1e-3 <= t_ <= a1 + 1e-3), None)   # keys: 1e-4
                an["bones"].setdefault(g, {})["scale"] = self.sc(
                    lambda t_, own=own: (1.0, height(t_) / h[own(t_)] if own(t_) else 1.0), T)

    @staticmethod
    def legs_spacing(heights: list) -> list:
        """Where each drawing of a sequence sits in progress (0 .. 1): halfway between evenly spaced and spaced by
        height change. Evenly spaced alone, an in-between (half a step in height) halves the legs' speed in its
        interval and jerks the body; by height alone, two drawings of about the same height (a drawing that only
        bends the knees) would flash past in a frame."""
        n = max(len(heights) - 1, 1)
        steps = [abs(b - a) for a, b in zip(heights, heights[1:])]
        total = sum(steps) or 1.0
        pos, acc = [0.0], 0.0
        for i, d in enumerate(steps, 1):
            acc += d
            pos.append(0.5 * (i / n + acc / total))
        return pos

    def crouch_legs(self, an: dict, T: float, down: float, low: float, hold: float, up: float):
        """A crouch on the squat sheet (leg_track): standing until `down` s, all the way down at `low`, held until
        `hold`, standing again at `up`. Returns height(t)."""
        return self.leg_track(an, T, [("squat", [(0, 0), (down, 0), (low, 1), (hold, 1), (up, 0), (T, 0)])])

    def arm_keys(self, an: dict, side: str, ua_keys: list, fa_keys: list):
        """Arm poses held at keyed times: [(t, world angle, character's left convention, or None = rest)] for the
        upper arm and the forearm (the right side mirrored), eased through each key (flat at the keys: holds read
        as poses). Rotations are deltas against the rest pose, the forearm's relative to its upper arm's."""
        pieces, rest = self.geo.pieces, self.geo.rest
        ua, fa = f"upperarm_{side}", f"forearm_{side}"
        if ua not in pieces:
            return

        def curve(keys, bone):
            return hermite([(t, 0.0 if a is None else wrap(rig_hands.side_deg(a, side) - rest[bone]), 0.0) for t, a in keys])
        T = max(t for t, _ in ua_keys)
        du = curve(ua_keys, ua)
        an["bones"][ua] = {"rotate": track(du, T)}
        if fa in pieces:
            dfw = curve(fa_keys, fa)
            an["bones"][fa] = {"rotate": track(lambda t: dfw(t) - du(t), T)}

    def squash_hips(self, an: dict, k, s, up, T: float):
        """Key the hips as a front-view squat / jump: squashed along its axis by k(t) (no knees: the trousers
        shorten), scaled uniformly by s(t) (nearer the viewer), the feet held on the ground raised by up(t) (Spine
        units); the bones lying along the hips' axis get the inverse squash."""
        par = self.geo.parents or {}

        def on_hips(b):                          # the bone carrying b that hangs straight off the hips (a leg, or b)
            while par.get(b) not in (None, "hips"):
                b = par[b]
            return b
        # what shortens is only the span from the hips' origin to where the feet (or their legs) hang: those are
        # counter-scaled and keep their length
        feet = self.feet()
        d = float(np.mean([self.along_hips(on_hips(f)) for f in feet])) if feet else 0.0
        an["bones"]["hips"] = {"scale": self.sc(lambda t: (k(t) * s(t), s(t)), T),
                               "translate": self.tr(lambda t: (0.0, up(t) + (k(t) * s(t) - 1) * d), T)}
        for b in self.hips_children():
            an["bones"].setdefault(b, {})["scale"] = self.sc(lambda t: (1 / k(t), 1.0), T)

    def squat(self):
        """squat: down and back up (2 s). With whole legs (has_legs): the knees bend out (half), the body sinks into
        the crouch and holds, comes back up; the arms hang down beside the knees, the head tips down a little.
        Without: the trousers shorten (no knees to bend) while the feet stay on the ground, arms out to the sides
        for balance."""
        pieces, rest = self.geo.pieces, self.geo.rest
        if self.has_legs("squat"):
            self.squat_legs()
            return
        if "hips" not in pieces or not self.feet():
            return
        T = 2.0

        def env(t):
            return smooth(t, 0.1, 0.75) * (1 - smooth(t, 1.25, 1.9))
        an = {"bones": {}}
        self.squash_hips(an, lambda t: 1 - 0.3 * env(t), lambda t: 1.0, lambda t: 0.0, T)
        for side in ("l", "r"):
            ua, fa = f"upperarm_{side}", f"forearm_{side}"
            if ua in pieces:
                d_ua = wrap((-20.0 if side == "l" else -160.0) - rest[ua])
                an["bones"][ua] = {"rotate": track(lambda t, d=d_ua: d * env(t), T)}
                if fa in pieces:
                    d_fa = wrap((-5.0 if side == "l" else -175.0) - rest[fa]) - d_ua
                    an["bones"][fa] = {"rotate": track(lambda t, d=d_fa: d * env(t), T)}
        if "head_base" in pieces:
            an["bones"]["head_base"] = {"rotate": track(lambda t: -3 * env(t), T)}
        self.anims["squat"] = an

    def squat_legs(self):
        T = 2.0
        an = {"bones": {}}
        self.crouch_legs(an, T, 0.08, 0.7, 1.3, 1.9)
        ua_, fa_ = CROUCH_ARMS
        for side in ("l", "r"):
            self.arm_keys(an, side, [(0, None), (0.35, None), (0.75, ua_), (1.3, ua_), (1.75, None), (T, None)],
                          [(0, None), (0.35, None), (0.75, fa_), (1.3, fa_), (1.75, None), (T, None)])
        if "head_base" in self.geo.pieces:
            an["bones"]["head_base"] = {"rotate": track(hermite([(0, 0, 0), (0.7, -2.5, 0), (1.35, -2.5, 0), (1.9, 0, 0), (T, 0, 0)]), T)}
        self.anims["squat"] = an

    def jump_hurdle(self):
        """jump_hurdle (one-shot, 2.2 s): with a ground prop (rig_props) standing in front of the legs: crouch, leap
        toward the viewer over it (it goes behind at the top of the jump, a drawOrder key), land a little nearer
        (lower and bigger), absorb, recover. Arms out to the sides for balance, feet on tiptoe and tucked."""
        pieces, rest, props = self.geo.pieces, self.geo.rest, self.geo.props or {}
        prop = next((p for p in props.values() if p["kind"] == "ground" and not p.get("use")), None)
        if prop is None or "hips" not in pieces or not self.feet():
            return
        if self.has_legs("squat", "jump"):
            self.jump_hurdle_legs(prop)
            return
        H, T, apex = self.body_h(), 2.2, 0.8
        k = hermite([(0, 1, 0), (0.06, 1, 0), (0.34, 0.88, 0), (0.62, 1.0, 0), (1.22, 1.0, 0), (1.46, 0.88, 0), (1.98, 1.0, 0), (T, 1.0, 0)])   # crouch, push off over 0.28 s
        jump = hermite([(0, 0, 0), (0.34, 0, 0), (apex, 0.18 * H, 0), (1.3, 0, 0), (T, 0, 0)])   # spine_qa's canvas has 25% headroom
        near = hermite([(0, 0, 0), (0.4, 0, 0), (1.24, 1, 0), (T, 1, 0)])
        an = {"bones": {}}
        self.squash_hips(an, k, lambda t: 1 + 0.08 * near(t), lambda t: jump(t) - prop["front"] * 1.6 * near(t), T)
        tuck = hermite([(0, 0, 0), (0.45, 0, 0), (apex, 1, 0), (1.15, 0, 0), (T, 0, 0)])
        for f in [f_ for f_ in self.feet() if self.loose_foot(f_)]:
            an["bones"].setdefault(f, {})["translate"] = self.tr(lambda t, f_=f: self.local(f_, 0.0, 0.04 * H * tuck(t)), T)
        def arm(t):                              # smootherstep: no kick in acceleration at either end
            return smooth(t, 0.0, 0.75) * (1 - smooth(t, 1.35, 2.2))      # still at the apex: no added jerk
        for side in ("l", "r"):
            ua, fa = f"upperarm_{side}", f"forearm_{side}"
            if ua in pieces:
                tu = 15.0 if side == "l" else 165.0          # arms out to the sides for balance, not up
                d_ua = wrap(tu - rest[ua])
                an["bones"][ua] = {"rotate": track(lambda t, d=d_ua: d * arm(t), T)}
                if fa in pieces:
                    tf = 35.0 if side == "l" else 145.0
                    d_fa = wrap(tf - rest[fa]) - d_ua
                    an["bones"][fa] = {"rotate": track(lambda t, d=d_fa: d * arm(t), T)}
            foot = foot_of(side, pieces, self.roles)
            if foot:
                self.swaps(an, foot, [(0, None), (0.42, "tiptoe"), (1.18, None), (T, None)])
        if self.tail_n:
            an["bones"][self.tail_n] = {"rotate": track(lambda t: -10 * (jump(max(0.0, t - 0.1)) - jump(max(0.0, t - 0.1 - 1 / 30))) * 30 / (0.18 * H * 3.5), T)}
        faces = [(0, self.neutral), (0.3, f"{self.prefix}head_surprised"), (1.24, f"{self.prefix}head_laugh"), (2.0, self.neutral)]
        if self.neutral and all(n_ in self.expr for _, n_ in faces):
            an["slots"] = {"head": {"attachment": [{"time": t_, "name": n_} for t_, n_ in faces] + [{"time": T, "name": self.neutral}]}}
        an.setdefault("slots", {})[prop["slot"]] = {"attachment": [{"time": 0, "name": prop["attachment"]}]}
        order = [s_["name"] for s_ in self.ex.slots]
        an["drawOrder"] = [{"time": 0}, {"time": apex, "offsets": [{"slot": prop["slot"], "offset": -order.index(prop["slot"])}]}]
        self.anims["jump_hurdle"] = an

    def jump_hurdle_legs(self, prop: dict):
        """jump_hurdle with whole legs (2.9 s, the key poses hurdle_crouch / hurdle_air / hurdle_land): sink into a
        crouch behind the hurdle (the squat sheet), the arms down, and hold it a beat; rise to straight legs and push
        off, tuck the knees up over the bar (the jump sheet) with the arms flung up; reach the legs down and land in a
        deep crouch on the near side (the squat sheet again; a little lower and bigger), the arms out at shoulder
        height; recover. The sheets meet at p = 0, where both show the rig's own legs. The held crouch, the longer
        landing absorb and the arm swing spread a little past the apex keep spine_qa's jerk checks quiet; in the air
        the body rides its own arc, not the legs' height, or tucking the legs would pull it down."""
        pieces = self.geo.pieces
        H, T, apex = self.body_h(), 2.9, 1.32
        jump = hermite([(0, 0, 0), (0.8, 0, 0), (apex, 0.2 * H, 0), (1.82, 0, 0), (T, 0, 0)])
        near = hermite([(0, 0, 0), (0.85, 0, 0), (1.82, 1, 0), (T, 1, 0)])
        segs = [("squat", [(0, 0), (0.06, 0), (0.5, 1), (0.6, 1), (1.02, 0)]),           # sink, hold, rise to straight
                ("jump", [(1.02, 0), (apex, 1), (1.4, 1), (1.74, 0)]),                    # push off, tuck; reach down
                ("squat", [(1.74, 0), (2.3, 1), (2.4, 1), (2.84, 0), (T, 0)])]           # land, absorb, recover

        def air(t):
            return smooth(t, 0.8, 1.22) * (1 - smooth(t, 1.56, 1.94))
        an = {"bones": {}}
        self.leg_track(an, T, segs, lift=lambda t: jump(t) - prop["front"] * 1.6 * near(t), air=air, tail=False)
        # nearer the viewer: the whole character a little bigger about the ground (the root), the hurdle not
        an["bones"]["root"] = {"scale": self.sc(lambda t: (1 + 0.08 * near(t), 1 + 0.08 * near(t)), T)}
        an["bones"][prop["bone"]] = {"scale": self.sc(lambda t: (1 / (1 + 0.08 * near(t)), 1 / (1 + 0.08 * near(t))), T)}
        # arms: down beside the knees in the crouch, flung up at the apex (as high as the head allows), out at
        # shoulder height on landing
        up = (45.0, 62.0)
        if not (self.clear_of_head("l", *up) and self.clear_of_head("r", 180 - up[0], 180 - up[1])):
            up = self.best_raise()
        cu, cf = CROUCH_ARMS
        ua = [(0, None), (0.36, cu - 2), (0.72, cu - 1), (apex + 0.16, up[0]), (1.76, 35.0), (2.16, 12.0), (2.8, None), (T, None)]
        fa = [(0, None), (0.36, cf - 2), (0.72, cf - 1), (apex + 0.16, up[1]), (1.76, 50.0), (2.16, 22.0), (2.8, None), (T, None)]
        for side in ("l", "r"):
            self.arm_keys(an, side, ua, fa)
            self.swaps(an, f"hand_{side}", [(0, None), (0.88, "open"), (2.35, None), (T, None)])
        if "head_base" in pieces:
            an["bones"]["head_base"] = {"rotate": track(hermite([(0, 0, 0), (0.55, 3.0, 0), (apex, -2.0, 0), (1.7, 2.0, 0), (2.2, 0, 0), (T, 0, 0)]), T)}
        if self.tail_n:                          # out flat in the crouches, trailing low on the way up, a flick at the apex
            o = self.tail_out()
            an["bones"][self.tail_n] = {"rotate": track(hermite([(t_, k_ * o, 0) for t_, k_ in (
                (0, 0), (0.55, 1), (0.9, 0.27), (apex, -0.47), (1.55, 0), (1.85, 1), (2.05, 0.6), (2.45, 0), (T, 0))]), T)}
        faces = [(0, self.neutral), (0.3, f"{self.prefix}head_surprised"), (0.95, f"{self.prefix}head_laugh"), (2.4, f"{self.prefix}head_happy")]
        if self.neutral and all(n_ in self.expr for _, n_ in faces):
            an["slots"]["head"] = {"attachment": [{"time": t_, "name": n_} for t_, n_ in faces] + [{"time": T, "name": self.neutral}]}
        an["slots"][prop["slot"]] = {"attachment": [{"time": 0, "name": prop["attachment"]}]}
        order = [s_["name"] for s_ in self.ex.slots]
        an["drawOrder"] = [{"time": 0}, {"time": apex, "offsets": [{"slot": prop["slot"], "offset": -order.index(prop["slot"])}]}]
        self.anims["jump_hurdle"] = an

    def wave_flag(self):
        """wave_flag (3.2 s): with a held prop (rig_props), the fist closes on the stick (held upright at rest), the
        arm rises like the wave and swings the flag from side to side, the cloth flutters, the arm comes down."""
        pieces, rest, props, ann = self.geo.pieces, self.geo.rest, self.geo.props or {}, self.geo.ann
        prop = next((p for p in props.values() if p["kind"] == "held" and not p.get("use")), None)
        if prop is None:
            return
        side = prop["side"]
        ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
        if not (ua in pieces and fa in pieces and hd in pieces):
            return
        m = 1 if side == "l" else -1
        T = 3.2
        tgt_ua = 20.0 if side == "l" else 160.0
        tgt_fa, _ = wave_forearm(lambda f_: self.clear_of_head(side, tgt_ua, f_), side, ann is not None)
        d_ua = wrap(tgt_ua - rest[ua])
        d_fa = wrap(tgt_fa - rest[fa]) - d_ua
        d_hd = self.straighten(fa, hd) if ann is not None else 0.0

        def env(t):                              # 0.9 s raise / lower: the fist (and the flag's bone) lies beyond
            return smooth(t, 0.0, 0.9) * (1 - smooth(t, 2.3, 3.2))   # the hand, so a 0.7 s raise jerked it

        def osc(t):
            return smooth(t, 0.8, 1.3) * (1 - smooth(t, 1.8, 2.3)) * math.sin(2 * math.pi * 1.0 * (t - 0.8))
        r_ua, r_fa, r_hd = (lambda t: d_ua * env(t)), (lambda t: d_fa * env(t) + 18 * m * osc(t)), (lambda t: d_hd * env(t))
        an = {"bones": {ua: {"rotate": track(r_ua, T)}, fa: {"rotate": track(r_fa, T)}, hd: {"rotate": track(r_hd, T)}}}
        # the stick: upright beside the hanging fist at rest; at the hold rigid in the fist, upright (tilted 8 deg out)
        # with the forearm still, so the wave swings it; the wrist turns it from one to the other during the raise
        c_rest = 90.0 - rest[hd]
        c_hold = (90.0 - 8 * m) - tgt_fa
        an["bones"][prop["bone"]] = {
            "rotate": track(lambda t: wrap(c_rest + wrap(c_hold - c_rest) * env(t)), T),
            "scale": self.sc(lambda t: (1.0, 1 - 0.08 * (0.5 - 0.5 * math.cos(2 * math.pi * 2.2 * t))), T)}
        if "head_base" in pieces:
            an["bones"]["head_base"] = {"rotate": track(lambda t: 4 * m * env(t), T)}
        an["slots"] = {prop["slot"]: {"attachment": [{"time": 0, "name": prop["attachment"]}]}}
        if f"{self.prefix}head_happy" in self.expr and self.neutral:
            an["slots"]["head"] = {"attachment": [{"time": 0, "name": self.neutral}, {"time": 0.35, "name": f"{self.prefix}head_happy"},
                                                  {"time": 2.85, "name": self.neutral}, {"time": T, "name": self.neutral}]}
        self.swaps(an, hd, [(0, "fist"), (T, "fist")])
        self.anims["wave_flag"] = an

    # ---- garden: plant_seed, water, grow_<n> (props with `use`, rig_props)

    def _use(self, use: str, kind: str):
        return next((p for p in (self.geo.props or {}).values() if p.get("use") == use and p["kind"] == kind), None)

    def plant_seed(self):
        """plant_seed (2.6 s): squat and lean toward the plant's spot, eyes on it, the arm on its side reaching down
        and out with a pinch, the paw lets go at the bottom (event `seed`: the game shows the first stage), stand back
        up, delighted."""
        pieces, rest, ann = self.geo.pieces, self.geo.rest, self.geo.ann
        plant = self._use("grow", "ground")
        if plant is None or "hips" not in pieces or not self.feet():
            return
        side = "l" if plant["x"] >= 0 else "r"
        ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
        T, drop = 2.6, 1.2

        def env(t):
            return smooth(t, 0.1, 0.95) * (1 - smooth(t, 1.55, 2.4))
        an = {"bones": {}}
        if self.has_legs("squat"):                                            # knees bend: the squat sheet (leg_track)
            self.crouch_legs(an, T, 0.1, 0.85, 1.6, 2.4)
        else:                                                                 # no knees: the trousers shorten
            self.squash_hips(an, lambda t: 1 - 0.32 * env(t), lambda t: 1.0, lambda t: 0.0, T)
        m = 1 if side == "l" else -1
        if "torso" in pieces:                                                 # lean toward the spot
            an["bones"]["torso"] = {"rotate": track(lambda t: -4 * m * env(t), T)}
        if ua in pieces:
            tu, tf = (-30.0, -42.0) if side == "l" else (-150.0, -138.0)       # down and out toward the spot
            d_ua = wrap(tu - rest[ua])
            an["bones"][ua] = {"rotate": track(lambda t, d=d_ua: d * env(t), T)}
            if fa in pieces:
                d_fa = wrap(tf - rest[fa]) - d_ua
                an["bones"][fa] = {"rotate": track(lambda t, d=d_fa: d * env(t), T)}
                if ann is not None and hd in pieces:
                    d_hd = self.straighten(fa, hd)
                    an["bones"][hd] = {"rotate": track(lambda t, d=d_hd: d * env(t), T)}
            self.swaps(an, hd, [(0, None), (0.25, "grip"), (2.35, None), (T, None)])   # pinches the seed (lets go at `seed`)
        other = "r" if side == "l" else "l"
        oua, ofa = f"upperarm_{other}", f"forearm_{other}"
        if oua in pieces:                                                     # the other arm out for balance, as squat's
            d_o = wrap((-20.0 if other == "l" else -160.0) - rest[oua])
            an["bones"][oua] = {"rotate": track(lambda t, d=d_o: d * env(t), T)}
            if ofa in pieces:
                d_of = wrap((-5.0 if other == "l" else -175.0) - rest[ofa]) - d_o
                an["bones"][ofa] = {"rotate": track(lambda t, d=d_of: d * env(t), T)}
        if "head_base" in pieces:
            an["bones"]["head_base"] = {"rotate": track(lambda t: -8 * m * env(t), T)}
        faces = [(0, self.neutral), (0.3, self.look()), (drop + 0.1, self.look(True)), (2.3, self.neutral)]
        if self.neutral and all(faces):
            an.setdefault("slots", {})["head"] = {"attachment": [{"time": t_, "name": n_} for t_, n_ in faces] + [{"time": T, "name": self.neutral}]}
        an["events"] = [{"time": drop, "name": "seed"}]
        self.anims["plant_seed"] = an

    def look(self, happy: bool = False) -> str | None:
        """The head that looks down at the plant (garden heads `look` / `look_happy`), else happy / neutral."""
        for e in (("look_happy", "happy") if happy else ("look", "neutral")):
            if f"{self.prefix}head_{e}" in self.expr:
                return f"{self.prefix}head_{e}"
        return self.neutral

    def front_of_body(self, side: str, extra: list) -> list:
        """drawOrder offsets bringing the arm on `side` (its slots in their own order) and `extra` slots (drawn just
        behind the hand: what it holds) in front of the torso, below the head: a held can tipping toward the body
        stays in front of the sweater and trousers. An arm already drawn over the torso keeps its place."""
        names = [s_["name"] for s_ in self.ex.slots]
        ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
        arm = [n for n in names if n in (ua, fa, hd)]
        props = [n for n in extra if n in names]
        if hd in arm:
            h = names.index(hd)
            group = [n for n in arm if names.index(n) < h] + props + [n for n in arm if names.index(n) >= h]
        else:
            group = props + arm
        target = [n for n in names if n not in group]
        first = min(names.index(n) for n in group)
        if "torso" in names and first > names.index("torso"):
            at = sum(1 for n in names[:first] if n not in group)          # already over the torso: stays there
        else:
            at = target.index("torso") + 1 if "torso" in target else len(target)
        target[at:at] = group
        return [{"slot": n, "offset": target.index(n) - i} for i, n in enumerate(names) if target.index(n) != i]

    def water(self):
        """water (3.8 s): the arm on the plant's side comes out to the side, the forearm angled down and the paw
        straight on it, closed round the can's handle (the handle runs across the fist), the can upright below it; the head turns to the plant and
        the eyes look at it; the can tips forward and the stream pours straight down onto the soil (event `pour` as
        it starts; the forearm rolls with it), wobbles a little, tips back, the arm comes down. Arm, can and stream are drawn in front of the
        body throughout. The can is shown only here."""
        pieces, rest, ann = self.geo.pieces, self.geo.rest, self.geo.ann
        can, stream = self._use("water", "held"), self._use("water", "attached")
        if can is None:
            return
        side = can["side"]
        ua, fa, hd = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
        if not (ua in pieces and fa in pieces and hd in pieces):
            return
        m = 1 if side == "l" else -1
        T, pour0, pour1, tilt = 3.8, 1.25, 2.85, 72.0
        tgt_ua, tgt_fa = (-6.0, -30.0) if side == "l" else (-174.0, -150.0)  # out to the side, the forearm angled down
        d_ua = wrap(tgt_ua - rest[ua])
        d_fa = wrap(tgt_fa - rest[fa]) - d_ua
        d_hd = self.straighten(fa, hd) if ann is not None else 0.0          # the paw straight on the forearm: the
        hw_hold = rest[hd] + d_ua + d_fa + d_hd                               # cuff covers the wrist; the handle
                                                                              # runs across the closed fingers

        def env(t):
            return smooth(t, 0.0, 1.0) * (1 - smooth(t, 3.0, 3.8))

        def tip(t):                                  # 0 upright .. 1 poured
            return smooth(t, 0.8, pour0 + 0.25) * (1 - smooth(t, pour1 - 0.15, pour1 + 0.4))

        def wob(t):
            return smooth(t, pour0, pour0 + 0.3) * (1 - smooth(t, pour1 - 0.4, pour1)) * math.sin(2 * math.pi * 1.6 * (t - pour0))
        # pouring rolls the wrist: the forearm and paw turn with the can for part of its tilt, so the handle stays
        # across the fist; the can turns the rest relative to the paw
        roll_fa, roll_hd = 0.55 * tilt, 0.0
        an = {"bones": {ua: {"rotate": track(lambda t: d_ua * env(t), T)},
                        fa: {"rotate": track(lambda t: d_fa * env(t) - roll_fa * m * tip(t) + 3 * m * wob(t), T)},
                        hd: {"rotate": track(lambda t: d_hd * env(t) - roll_hd * m * tip(t), T)}}}
        # the can, relative to the hand: hanging upright below the fist (its grip-to-spout line at its painted
        # angle) all the way, then tipped forward to pour (toward the side it is held on)
        painted = can["img_deg"] if side == "l" else 180 - can["img_deg"]
        up_rest = painted - rest[hd]
        up_hold = painted - hw_hold
        an["bones"][can["bone"]] = {"rotate": track(
            lambda t: wrap(up_rest + wrap(up_hold - up_rest) * env(t)) - (tilt - roll_fa - roll_hd) * m * tip(t) - 3 * m * wob(t), T)}
        if side == "r":
            an["bones"][can["bone"]]["scale"] = self.sc(lambda t: (1.0, -1.0), T)  # the spout to the outside
        an["slots"] = {can["slot"]: {"attachment": [{"time": 0, "name": can["attachment"]}]}}
        extra = [can["slot"]]
        if stream is not None:
            extra.insert(0, stream["slot"])
            an["slots"][stream["slot"]] = {"attachment": [{"time": 0, "name": None}, {"time": pour0, "name": stream["attachment"]},
                                                          {"time": pour1, "name": None}]}
            fall = stream["spec"].get("fall", 1.0)                         # ends on the soil (rig_props)
            an["bones"][stream["bone"]] = {"scale": self.sc(lambda t: (1.0 + 0.04 * math.sin(2 * math.pi * 3.1 * t),
                                                                      fall * (0.2 + 0.8 * smooth(t, pour0, pour0 + 0.3)) * (1 + 0.03 * math.sin(2 * math.pi * 4.3 * t))), T)}
        order = self.front_of_body(side, extra)
        if order:
            an["drawOrder"] = [{"time": 0, "offsets": order}]
        def look(t):                                 # head turned down toward the plant while watering
            return smooth(t, 0.4, 1.2) * (1 - smooth(t, 2.9, 3.6))
        if "head_base" in pieces:
            an["bones"]["head_base"] = {"rotate": track(lambda t: -9 * m * look(t), T)}
        if "torso" in pieces:
            an["bones"]["torso"] = {"rotate": track(lambda t: -3 * m * look(t), T)}
        if self.neutral:
            heads = [(0, self.neutral), (0.6, self.look()), (pour0 + 0.15, self.look(True)), (3.15, self.neutral)]
            an["slots"]["head"] = {"attachment": [{"time": t_, "name": n_} for t_, n_ in heads if n_] + [{"time": T, "name": self.neutral}]}
        self.swaps(an, hd, [(0, "fist"), (T, "fist")])
        an["events"] = [{"time": pour0, "name": "pour"}]
        self.anims["water"] = an

    def grow(self):
        """grow_<n> (0.9 s each, one per stage, for a track of their own): the plant's slot shows stage n, which
        pops up from 0.6 of its height with a squash and stretch and settles; it holds that stage when it ends."""
        plant = self._use("grow", "ground")
        if plant is None:
            return
        T = 0.9
        pop = hermite([(0, 0.6, 0), (0.28, 1.14, 0), (0.48, 0.94, 0), (0.66, 1.03, 0), (T, 1.0, 0)])
        for i, att in enumerate(plant["stages"]):
            self.anims[f"grow_{i}"] = {
                "slots": {plant["slot"]: {"attachment": [{"time": 0, "name": att}]}},
                "bones": {plant["bone"]: {"scale": self.sc(lambda t: (1 / math.sqrt(max(pop(t), 0.3)), pop(t)), T)}}}

def build(geo: Geometry, ex, expr: list, doubts: list) -> Animator:
    """Every animation of the rig, in spine_rig's order. ex: the rig_slots.Export with the slots and skin written so
    far (swaps only key attachments the skin has; crossing keys reorder its slots); expr: the expression head
    attachment names; doubts: appended to."""
    an = Animator(geo, ex, expr, doubts)
    an.idle()
    an.wave()
    an.cheer_jump()
    # (upper arm, forearm), shared with rig_hands; with annotations point and thumbs_up may go across the body instead
    # (rig_hands.GESTURE_ARM_DEG_ACROSS) when only that shows the painted hand's thumb up
    arm_deg = rig_hands.GESTURE_ARM_DEG
    an.gesture("thumbs_up", *arm_deg["thumbs_up"], "thumbsup", "happy")   # forearm out to the side, thumb up
    an.gesture("point", *arm_deg["point"], "point", "talking")            # whole arm straight out, finger along it
    an.gesture("hold_card", *arm_deg["hold_card"], "grip", "neutral")     # forearm across the belly, below any scarf, paw pinching
    an.emotions()
    an.walk()
    an.run()
    an.squat()
    an.jump_hurdle()
    an.wave_flag()
    an.plant_seed()
    an.water()
    an.grow()
    return an
