"""pro_motion.py - the animation stages of spine_pro.py.

  new_idle      2 s loop: chest breathing, hips bob and weight shift over planted feet, offset limb sways, a look
                through the face helper, a blink (§2.9: idle = breathing + offset limb rotations + face turn + blink)
  look_around   the face helper carries the gaze left and right (fake 3D turn), the head tilts after it
  talk          talking-head swaps with a jaw-like head squash on every open mouth, a nod and one arm beat
  breathing     gentle chest scale added to every animation that has none
  secondary     follow-through on the tail chain and ears for every animation: a damped spring per segment driven
                by its pivot's acceleration and its parent's rotation (delayed, damped overlap), plus an idle sway
                with phase lag down the chain

All keys are dense linear keys at 30 fps (as spine_rig writes them), so spine_qa's jerk check sees exactly what
the runtime plays.
"""
from __future__ import annotations

import math

import numpy as np

import pro_common as pc


def _skin(data):
    return data["skins"][0]["attachments"]


def head_atts(data) -> tuple:
    """(head slot name, rest attachment, {expression: attachment})."""
    slot = next((s for s in data["slots"] if s["bone"] == "head_base" and s.get("attachment")), None)
    if slot is None:
        return None, None, {}
    atts = {a.rsplit("head_", 1)[-1]: a for a in _skin(data)[slot["name"]]}
    return slot["name"], slot["attachment"], atts


def parent_delta(data, folder, bone: str, dx: float, dy: float) -> tuple:
    """A world-space offset (setup pose) as the bone's translate key (parent's local axes, scale ignored)."""
    w, _ = pc.DataRig(data, folder).pose(None, 0)
    p = pc.bone(data, bone).get("parent")
    if not p:
        return dx, dy
    r = math.radians(pc.angle(w[p]))
    return dx * math.cos(r) + dy * math.sin(r), -dx * math.sin(r) + dy * math.cos(r)


def _side_sign(data, folder, bone: str) -> float:
    """+1 if a positive local rotation swings this hanging limb outward (away from the body's centre line)."""
    w, _ = pc.DataRig(data, folder).pose(None, 0)
    b = w[bone]
    cx = w["hips"][4] if "hips" in w else 0.0
    # direction of motion of the bone's tip for a small CCW rotation
    tip = np.array([b[0], b[2]])
    motion = np.array([-tip[1], tip[0]])
    return 1.0 if motion[0] * (b[4] - cx) > 0 else -1.0


def _blink_keys(data, t_blink: float, length: float = 0.12) -> list | None:
    slot, rest, atts = head_atts(data)
    if not slot or "blink" not in atts:
        return None
    return [{"time": 0.0, "name": rest}, {"time": round(t_blink, 4), "name": atts["blink"]},
            {"time": round(t_blink + length, 4), "name": rest}]


def new_idle(data, folder, dur: float = 2.0) -> dict:
    H = float(data["skeleton"]["height"])
    ts = pc.frames(dur)
    ph = 2 * math.pi * ts / dur
    data["animations"]["idle"] = {}
    breath = 0.5 - 0.5 * np.cos(ph)
    if pc.has_bone(data, "chest"):
        pc.put(data, "idle", "chest", "scale", ts, x=1 + 0.012 * breath, y=1 + 0.022 * breath)
    if pc.has_bone(data, "hips"):
        dx, dy = parent_delta(data, folder, "hips", 0.0025 * H, 0)
        sx = np.sin(ph)
        bob = -0.004 * H * breath
        pc.put(data, "idle", "hips", "translate", ts, x=dx * sx + parent_delta(data, folder, "hips", 0, 1)[0] * bob,
               y=dy * sx + parent_delta(data, folder, "hips", 0, 1)[1] * bob)
        pc.put(data, "idle", "hips", "rotate", ts, value=0.5 * np.sin(ph))
    if pc.has_bone(data, "torso"):
        pc.put(data, "idle", "torso", "rotate", ts, value=-0.7 * np.sin(ph - 0.6))
    if pc.has_bone(data, "head_base"):
        pc.put(data, "idle", "head_base", "rotate", ts, value=1.2 * np.sin(ph - 1.2))
    for side in ("l", "r"):
        for b, amp, lag in ((f"upperarm_{side}", 2.2, 0.5), (f"forearm_{side}", 2.0, 1.3), (f"hand_{side}", 3.0, 2.0)):
            if pc.has_bone(data, b):
                sg = _side_sign(data, folder, b)
                pc.put(data, "idle", b, "rotate", ts, value=sg * amp * (0.5 - 0.5 * np.cos(ph - lag)))
    if pc.has_bone(data, "face"):
        fx, fy = parent_delta(data, folder, "face", 1, 0)
        look = 0.007 * H * np.sin(ph - 0.3)
        pc.put(data, "idle", "face", "translate", ts, x=fx * look, y=fy * look)
    bk = _blink_keys(data, 1.25)
    if bk:
        data["animations"]["idle"]["slots"] = {head_atts(data)[0]: {"attachment": bk}}
    return {"duration": dur}


def look_around(data, folder, dur: float = 3.2) -> dict | None:
    if not pc.has_bone(data, "face"):
        return None
    H = float(data["skeleton"]["height"])
    ts = pc.frames(dur)
    A = 0.03 * H
    x = -A * pc.ease(ts, 0.25, 0.7) + 2 * A * pc.ease(ts, 1.45, 1.95) - A * pc.ease(ts, 2.55, 3.0)
    data["animations"]["look_around"] = {}
    fx, fy = parent_delta(data, folder, "face", 1, 0)
    pc.put(data, "look_around", "face", "translate", ts, x=fx * x, y=fy * x)
    lagged = np.interp(ts - 0.12, ts, x, left=0.0)
    pc.put(data, "look_around", "head_base", "rotate", ts, value=-3.0 * lagged / A)
    if pc.has_bone(data, "torso"):
        pc.put(data, "look_around", "torso", "rotate", ts, value=-0.9 * np.interp(ts - 0.25, ts, x, left=0.0) / A)
    bk = _blink_keys(data, 1.62)
    if bk:
        data["animations"]["look_around"]["slots"] = {head_atts(data)[0]: {"attachment": bk}}
    return {"duration": dur}


TALK_OPEN = [(0.10, 0.26), (0.38, 0.52), (0.66, 0.92), (1.06, 1.18), (1.32, 1.58), (1.76, 1.90), (2.02, 2.16)]


def talk(data, folder, dur: float = 2.4) -> dict | None:
    slot, rest, atts = head_atts(data)
    if not slot or not pc.has_bone(data, "head_base"):
        return None
    mouth = atts.get("talking") or atts.get("laugh") or atts.get("happy")
    ts = pc.frames(dur)
    data["animations"]["talk"] = {}
    if mouth:
        keys = [{"time": 0.0, "name": rest}]
        for a, b in TALK_OPEN:
            keys += [{"time": a, "name": mouth}, {"time": b, "name": rest}]
        data["animations"]["talk"]["slots"] = {slot: {"attachment": keys}}
    openness = np.zeros(len(ts))
    for a, b in TALK_OPEN:
        openness = np.maximum(openness, pc.ease(ts, a - 0.03, a + 0.04) * (1 - pc.ease(ts, b - 0.02, b + 0.06)))
    openness = pc.gauss_smooth(openness, 1.2, periodic=False)
    # jaw-ish squash: the head stretches along its axis while the mouth is open (head_base points up: x = along)
    pc.put(data, "talk", "head_base", "scale", ts, x=1 + 0.028 * openness, y=1 - 0.012 * openness)
    nod = 1.6 * np.sin(2 * math.pi * ts / (dur / 2)) * (0.6 + 0.4 * np.sin(2 * math.pi * ts / dur))
    pc.put(data, "talk", "head_base", "rotate", ts, value=nod)
    beat = pc.ease(ts, 0.5, 0.9) * (1 - pc.ease(ts, 1.5, 2.0))
    for b, amp in (("upperarm_l", 9.0), ("forearm_l", 14.0), ("hand_l", 8.0)):
        if pc.has_bone(data, b):
            pc.put(data, "talk", b, "rotate", ts, value=_side_sign(data, folder, b) * amp * beat)
    if pc.has_bone(data, "face"):
        H = float(data["skeleton"]["height"])
        fx, fy = parent_delta(data, folder, "face", 1, 0)
        look = 0.008 * H * np.sin(2 * math.pi * ts / dur)
        pc.put(data, "talk", "face", "translate", ts, x=fx * look, y=fy * look)
    return {"duration": dur, "mouth": mouth}


def breathing(data, period: float = 2.0, amp: float = 0.012) -> list:
    if not pc.has_bone(data, "chest"):
        return []
    done = []
    for anim, A in data["animations"].items():
        if "scale" in A.get("bones", {}).get("chest", {}):
            continue
        dur = pc.duration(data, anim)
        if dur < 0.5:
            continue
        ts = pc.frames(dur)
        T = dur / max(1, round(dur / period))
        b = 0.5 - 0.5 * np.cos(2 * math.pi * ts / T)
        pc.add_to(data, anim, "chest", "scale", ts, x=1 + amp * 0.6 * b, y=1 + amp * b)
        done.append(anim)
    return done


# ------------------------------------------------------------------ follow-through

def _periodic(rig, anim, dur) -> bool:
    w0, _ = rig.pose(anim, 0.0)
    w1, _ = rig.pose(anim, dur)
    return all(np.allclose(w0[n], w1[n], atol=1e-3) for n in w0)


def _deriv2(x: np.ndarray, dt: float, periodic: bool) -> np.ndarray:
    if periodic:
        core = x[:-1]
        d2 = (np.roll(core, -1) - 2 * core + np.roll(core, 1)) / dt ** 2
        return np.append(d2, d2[0])
    xp = np.concatenate([[x[0]], x, [x[-1]]])
    return (xp[2:] - 2 * xp[1:-1] + xp[:-2]) / dt ** 2


def _spring(drive: np.ndarray, dt: float, f: float, zeta: float, periodic: bool, sub: int = 6) -> np.ndarray:
    """theta'' = drive - w^2 theta - 2 zeta w theta' (semi-implicit Euler, sub-stepped). Periodic (the last frame
    repeats the first): three passes over the cycle, the last one kept, then a linear ramp closes the residual seam."""
    w = 2 * math.pi * f
    n = len(drive)
    passes = 3 if periodic else 1
    th, om = 0.0, 0.0
    out = np.zeros(n)
    for _ in range(passes):
        for i in range(n - 1):
            out[i] = th
            d0, d1 = drive[i], drive[i + 1]
            for k in range(sub):
                d = d0 + (d1 - d0) * k / sub
                om += (d - w * w * th - 2 * zeta * w * om) * dt / sub
                th += om * dt / sub
        out[n - 1] = th
    if periodic:
        out -= (out[-1] - out[0]) * np.linspace(0, 1, n)
    return out


def chain_overlap(world_seq: list, chain: list, lengths: list, dt: float, periodic: bool, f: float, zeta: float,
                  gain: float, inertia: float, limit: float) -> list:
    """Relative rotation offsets (degrees per frame) for each bone of a chain, from the rigid motion world_seq
    (list of world dicts per frame)."""
    n = len(world_seq)
    offsets = []
    acc_theta = np.zeros(n)                               # sum of the earlier segments' offsets (radians)
    for i, b in enumerate(chain):
        P = np.array([[w[b][4], w[b][5]] for w in world_seq])
        A = np.unwrap(np.radians([pc.angle(w[b]) for w in world_seq])) + acc_theta
        ax = pc.gauss_smooth(_deriv2(P[:, 0], dt, periodic), 3.0, periodic)
        ay = pc.gauss_smooth(_deriv2(P[:, 1], dt, periodic), 3.0, periodic)
        alpha_p = pc.gauss_smooth(_deriv2(A, dt, periodic), 3.0, periodic)
        nx, ny = -np.sin(A), np.cos(A)
        drive = -gain * 1.5 / max(1.0, lengths[i]) * (ax * nx + ay * ny) - inertia * alpha_p
        th = _spring(drive, dt, f, zeta, periodic)
        lim = math.radians(limit)
        th = lim * np.tanh(th / lim)
        th = pc.gauss_smooth(th, 2.0, periodic)
        if not periodic:                                  # fade out so a one-shot ends on its own pose
            th = th * (1 - pc.ease(np.arange(n) * dt, n * dt - min(0.45, 0.3 * n * dt), n * dt - dt))
        acc_theta = acc_theta + th
        offsets.append(np.degrees(th))
    return offsets


JERK_BUDGET = 1.6


def secondary(data, folder) -> dict:
    """Tail, ear and chest follow-through (+ tail / ear sway) on every animation, added to whatever is keyed."""
    chains = []
    tail = [b for b in ("tail", "tail2", "tail3", "tail4", "tail5") if pc.has_bone(data, b)]
    if len(tail) >= 2:
        chains.append(("tail", tail, dict(f=1.5, zeta=0.35, gain=0.6, inertia=0.6, limit=11.0),
                       [1.4, 2.4, 3.2, 3.8, 4.2]))
    if pc.has_bone(data, "chest"):                      # torso bend: the chest lags the hips a little
        chains.append(("chest", ["chest"], dict(f=2.2, zeta=0.5, gain=0.3, inertia=0.35, limit=4.0), [0.0]))
    for e in ("ear_l", "ear_r"):
        if pc.has_bone(data, e):
            chains.append((e, [e], dict(f=2.6, zeta=0.28, gain=0.8, inertia=0.8, limit=10.0), [1.2]))
    if not chains:
        return {}
    rep = {}
    dt = 1 / pc.FPS
    # a long chain shows at its far pivots the jerk a single rigid tail hid at its tip: where the primary motion
    # already breaks spine_qa's limits on the chain, smooth the root's keyed rotation first
    smoothed = []
    if len(tail) >= 2:
        for anim in data["animations"]:
            dur = pc.duration(data, anim)
            tl = data["animations"][anim].get("bones", {}).get("tail", {}).get("rotate")
            if dur < 0.3 or not tl:
                continue
            ts = pc.frames(dur)
            for sigma in (1.5, 2.5, 4.0):
                if _chain_jerk_ok(data, folder, anim, ts, tail, margin=0.8):
                    break
                v = pc.sample(tl, ts, "value", 0.0)
                periodic = abs(v[0] - v[-1]) < 1e-6
                pc.put(data, anim, "tail", "rotate", ts, value=pc.gauss_smooth(v, sigma, periodic))
                smoothed.append(f"{anim}: sigma {sigma}")
    if smoothed:
        rep["tail_root_smoothed"] = smoothed
    snapshot = pc.deepcopy(data)                          # primary motion only: offsets don't feed each other
    rig = pc.DataRig(snapshot, folder)
    for anim in list(data["animations"]):
        dur = pc.duration(data, anim)
        if dur < 0.3:
            continue
        ts = pc.frames(dur)
        seq = [rig.pose(anim, float(t))[0] for t in ts]
        periodic = _periodic(rig, anim, dur)
        T = dur / max(1, round(dur / 1.8))
        rep[anim] = {"periodic": periodic}
        for cname, chain, prm, sway in chains:
            lengths = [pc.bone(data, b).get("length", 50.0) for b in chain]
            offs = chain_overlap(seq, chain, lengths, dt, periodic, **prm)
            sw = [sway[i] * np.sin(2 * math.pi * ts / T - 0.7 * i) for i in range(len(chain))]
            # keep the added world-angle acceleration of every segment under JERK_BUDGET deg/frame^2 (spine_qa's
            # jerk check allows 4 on top of whatever the primary motion already has)
            cum = np.cumsum([o + s_ for o, s_ in zip(offs, sw)], axis=0)
            j = float(np.abs(np.diff(cum, 2, axis=1)).max()) if cum.shape[1] > 2 else 0.0
            k = min(1.0, JERK_BUDGET / j) if j > 0 else 1.0
            saved = {b: pc.deepcopy(data["animations"][anim].get("bones", {}).get(b, {}).get("rotate")) for b in chain}
            for _ in range(8):                            # measured check: shrink until the chain passes spine_qa's
                for i, b in enumerate(chain):             # jerk limits with a margin (positions included)
                    tl = data["animations"][anim].setdefault("bones", {}).setdefault(b, {})
                    if saved[b] is None:
                        tl.pop("rotate", None)
                    else:
                        tl["rotate"] = pc.deepcopy(saved[b])
                    pc.add_to(data, anim, b, "rotate", ts, value=k * (offs[i] + sw[i]))
                if _chain_jerk_ok(data, folder, anim, ts, chain):
                    break
                k *= 0.75
            peak = max(float(np.abs(k * o).max()) for o in offs)
            rep[anim][cname] = round(peak, 1)
            if k < 1:
                rep[anim][cname + "_damped"] = round(k, 2)
    return rep


def _chain_jerk_ok(data, folder, anim, ts, chain, margin: float = 0.85) -> bool:
    """spine_qa's smoothness measure on the chain bones (angular and positional velocity change per frame)."""
    import spine_qa
    rig = pc.DataRig(data, folder)
    H = float(data["skeleton"]["height"])
    tr = {b: [] for b in chain}
    for t in ts:
        w, _ = rig.pose(anim, float(t))
        for b in chain:
            tr[b].append((w[b][4], w[b][5], pc.angle(w[b])))
    for b, v in tr.items():
        v = np.array(v)
        if len(v) < 3:
            continue
        ang = np.unwrap(np.radians(v[:, 2])) * 180 / math.pi
        ja = float(np.abs(np.diff(ang, 2)).max())
        jp = float(np.linalg.norm(np.diff(v[:, :2], 2, axis=0) / H, axis=1).max())
        if ja > margin * spine_qa.MAX_ANG_JUMP or jp > margin * spine_qa.MAX_POS_JUMP:
            return False
    return True
