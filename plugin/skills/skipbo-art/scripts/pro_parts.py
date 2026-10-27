"""pro_parts.py - the structural stages of spine_pro.py (bones, meshes, constraints, slots).

Each stage takes the skeleton dict (valid Spine 4.2 JSON) plus the output folder (images are read from and written
to <folder>/images) and returns a short report dict. Research references are to
docs/research/armanimation-spine/README.md.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

import pro_common as pc
import pro_mesh as pm

FOOT_WORDS = ("boot", "hoof", "foot", "shoe")


def _setup(data, folder):
    rig = pc.DataRig(data, folder)
    world, active = rig.pose(None, 0)
    return rig, world, active


def body_height(data) -> float:
    return float(data["skeleton"]["height"])


def foot_bones(data) -> list:
    """Foot bones that carry a slot, side suffix _l / _r: named boot / hoof / foot / shoe, or (free-form names such as
    clog) any sided bone hanging off the hips or a leg whose pivot lies in the lowest 30% of the body."""
    slotted = {s["bone"] for s in data["slots"] if s.get("attachment")}
    H = float(data["skeleton"]["height"])
    y0 = float(data["skeleton"].get("y", 0.0))
    world = None
    out = []
    for b in data["bones"]:
        n = b["name"]
        if n not in slotted or not n.endswith(("_l", "_r")):
            continue
        if n.rsplit("_", 1)[0] in FOOT_WORDS:
            out.append(n)
            continue
        if b.get("parent") not in ("hips", "leg_l", "leg_r") or n.startswith(("leg", "tail", "upperarm", "hand")):
            continue
        if world is None:
            import spine_qa
            world = _world_setup(data)
        if world[n][5] - y0 < 0.3 * H:
            out.append(n)
    return out


def _world_setup(data) -> dict:
    """Setup-pose world matrices without images (bones only)."""
    import qa_constraints
    import spine_qa
    return qa_constraints.pose_world({**data, "ik": [], "transform": []}, None, 0, spine_qa.interp)


# ------------------------------------------------------------------ 1. container + shadow

def container(data, folder, legacy_world_fn) -> dict:
    """`character` container under root (§2.4: root never animated; the first bone is a container). Hips translate
    keys move onto `character` in animations where every foot leaves the ground together (a jump), else stay on the
    hips (a squat or a walk keeps its feet down). Root keys, if any, move to `character` too."""
    if pc.has_bone(data, "character"):
        return {"skipped": "already has character"}
    pc.add_bone(data, {"name": "character", "parent": "root", "length": 0, "color": pc.RED}, after="root")
    for b in data["bones"]:
        if b.get("parent") == "root" and b["name"] in ("hips",):
            b["parent"] = "character"
    pc.set_bones(data, data["bones"])
    H = body_height(data)
    feet = foot_bones(data)
    moved = []
    for anim, A in data["animations"].items():
        bt = A.get("bones", {})
        if "root" in bt:
            bt["character"] = bt.pop("root")
            moved.append(f"{anim}: root -> character")
        if "translate" not in bt.get("hips", {}) or not feet:
            continue
        ts = pc.frames(pc.duration(data, anim))
        lifts = []
        for f in feet:
            y0 = legacy_world_fn(None, 0)[f][5]
            lifts.append(np.array([legacy_world_fn(anim, t)[f][5] - y0 for t in ts]))
        if (np.min(lifts, axis=0) > 0.02 * H).any():
            bt.setdefault("character", {})["translate"] = bt["hips"].pop("translate")
            if not bt["hips"]:
                del bt["hips"]
            moved.append(f"{anim}: hips translate -> character (jump)")
    return {"moved": moved}


def shadow_image(path: Path, w: int = 96, h: int = 28):
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx + 0.5 - w / 2) / (w / 2)) ** 2 + ((yy + 0.5 - h / 2) / (h / 2)) ** 2)
    a = np.clip(1 - r, 0, 1) ** 0.8 * 0.42                     # max alpha 107/255: never counted as a part
    img = np.zeros((h, w, 4), np.uint8)
    img[..., :3] = (52, 44, 50)
    img[..., 3] = np.round(a * 255).astype(np.uint8)
    Image.fromarray(img, "RGBA").save(path)


def shadow(data, folder) -> dict:
    """A soft ground shadow (§3: shadow bone outside the container), first in the draw order."""
    if any(s["name"] == "shadow" for s in data["slots"]):
        return {"skipped": "already has shadow"}
    rig, world, _ = _setup(data, folder)
    feet = foot_bones(data)
    xs = [world[f][4] for f in feet] or [0.0]
    sk = data["skeleton"]
    width = max(0.5 * sk["width"], 1.6 * (max(xs) - min(xs)) + 0.25 * sk["width"]) if feet else 0.6 * sk["width"]
    height = 0.07 * sk["height"]
    name = "shadow"
    shadow_image(Path(folder) / "images" / f"{name}.png")
    pc.add_bone(data, {"name": "shadow", "parent": "root", "x": round(float(np.mean(xs)), 2), "y": 0.0, "length": 0,
                       "color": pc.YELLOW}, after="root")
    data["slots"].insert(0, {"name": "shadow", "bone": "shadow", "color": "ffffffff", "attachment": name})
    data["skins"][0]["attachments"]["shadow"] = {name: {"x": 0.0, "y": round(height * 0.12, 2), "scaleX": round(width / 96, 4),
                                                        "scaleY": round(height / 28, 4), "width": 96, "height": 28}}
    return {"width": round(width, 1), "height": round(height, 1)}


def shadow_keys(data, folder) -> list:
    """In animations where `character` leaves the ground, the shadow shrinks and fades with the height."""
    H = body_height(data)
    done = []
    for anim, A in data["animations"].items():
        tr = A.get("bones", {}).get("character", {}).get("translate")
        if not tr:
            continue
        ts = pc.frames(pc.duration(data, anim))
        y = pc.sample(tr, ts, "y", 0.0)
        x = pc.sample(tr, ts, "x", 0.0)
        h = np.clip(y / (0.18 * H), 0, 1)
        pc.put(data, anim, "shadow", "scale", ts, x=1 - 0.45 * h, y=1 - 0.35 * h)
        if np.abs(x).max() > 0.5:
            pc.put(data, anim, "shadow", "translate", ts, x=x, y=np.zeros_like(x))
        alpha = 1 - 0.6 * h
        A.setdefault("slots", {}).setdefault("shadow", {})["rgba"] = [
            {"time": round(float(t), 4), "color": "ffffff%02x" % int(round(255 * a))} for t, a in zip(ts, alpha)]
        done.append(anim)
    return done


# ------------------------------------------------------------------ region -> weighted mesh

def to_mesh(data, folder, slot: str, att: str, lattice_px: np.ndarray, weight_fn, M=None) -> dict:
    """Replace a region attachment by a weighted mesh on the lattice (attachment px). weight_fn(world points (n, 2),
    lattice row/col index (n, 2)) -> list of {bone: weight}. The image is padded if the lattice leaves it. M: the
    region's image px -> world matrix, when it was taken before its bone moved."""
    rig, world, _ = _setup(data, folder)
    if M is None:
        M = rig.att_matrix(slot, att, world)
    R, C = lattice_px.shape[:2]
    rc = np.array([[i, j] for i in range(R) for j in range(C)])
    rc_grid = rc.reshape(R, C, 2).astype(float)
    pts, tris, hull = pm.lattice(lattice_px)
    rcs, _, _ = pm.lattice(rc_grid)
    wpts = (M @ np.hstack([pts, np.ones((len(pts), 1))]).T).T[:, :2]
    img_path = Path(folder) / "images" / f"{att}.png"
    img = Image.open(img_path).convert("RGBA")
    img2, (dx, dy) = pm.pad_image(img, pts)
    if (dx, dy) != (0, 0) or img2.size != img.size:
        img2.save(img_path)
    uv = pts + np.array([dx, dy])
    weights = weight_fn(wpts, rcs.astype(int))
    vertices = pc.encode_weighted(wpts, weights, world, {b["name"]: i for i, b in enumerate(data["bones"])})
    A = pc.mesh_attachment(uv, img2.size, tris, hull, vertices)
    data["skins"][0]["attachments"][slot][att] = A
    return {"vertices": len(pts), "triangles": len(tris), "padded": [dx, dy]}


def _band_weights(s: float, pivots: list, bones: list, band: float) -> dict:
    """Weights along a chain: 100% on the segment's bone, a smoothstep blend of width 2*band centred on each pivot
    (0.5 / 0.5 exactly on the pivot row)."""
    w = {bones[0]: 1.0}
    for i in range(1, len(pivots)):
        u = float(pc.smoothstep((s - (pivots[i] - band)) / (2 * band)))
        if u <= 0:
            break
        prev = max(w, key=w.get)
        w = {k: v * (1 - u) for k, v in w.items()}
        w[bones[i]] = w.get(bones[i], 0) + u
        w = {k: v for k, v in w.items() if v > 1e-4}
        del prev
    return w


def _rows(lo: float, hi: float, n: int, pivots: list, band: float) -> list:
    """Row arc positions: uniform from lo to hi plus three rows per inner pivot (pivot - band, pivot, pivot + band)."""
    forced = sorted({round(p + k * band, 3) for p in pivots[1:] for k in (-1, 0, 1)} | {round(pivots[0], 3)})
    uni = [x for x in np.linspace(lo, hi, n) if all(abs(x - f) > 0.45 * band for f in forced)]
    return sorted(set(uni) | set(f for f in forced if lo < f < hi) | {lo, hi})


# ------------------------------------------------------------------ 3. tail chain

def tail_chain(data, folder, segments: int | None = None) -> dict:
    """The tail as a chain of 3-4 bones along its medial axis (§3 quadruped: tail1 > tail2 > ..., tip rigid), the tail
    image(s) as a weighted mesh with rows on every pivot and narrow blend bands."""
    if not pc.has_bone(data, "tail") or pc.has_bone(data, "tail2"):
        return {"skipped": "no tail bone (or already chained)"}
    slot = next((s for s in data["slots"] if s["bone"] == "tail"), None)
    if slot is None or not slot.get("attachment"):
        return {"skipped": "tail has no slot"}
    rig, world, _ = _setup(data, folder)
    rest = slot["attachment"]
    A = data["skins"][0]["attachments"][slot["name"]][rest]
    if A.get("type", "region") != "region":
        return {"skipped": "tail is not a region"}
    M = rig.att_matrix(slot["name"], rest, world)
    Minv = np.linalg.inv(M)
    alpha = np.asarray(rig.images[rest])[..., 3]
    root_w = np.array([world["tail"][4], world["tail"][5]])
    root_px = (Minv @ np.array([*root_w, 1]))[:2]
    pts = pm.alpha_points(alpha)
    tip_px = pts[np.argmax(np.linalg.norm(pts - root_px, axis=1))]
    P = pm.medial_axis(alpha, root_px, tip_px)
    Pw = (M @ np.hstack([P, np.ones((len(P), 1))]).T).T[:, :2]
    Lw = float(np.sum(np.linalg.norm(np.diff(Pw, axis=0), axis=1)))
    H = body_height(data)
    n = segments or (4 if Lw > 0.28 * H else 3)
    fr = {3: [0.0, 0.4, 0.72], 4: [0.0, 0.3, 0.56, 0.8]}[n]
    names = ["tail"] + [f"tail{i}" for i in range(2, n + 1)]
    S = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(Pw, axis=0), axis=1))])

    def at_w(s):
        k = int(np.clip(np.searchsorted(S, s) - 1, 0, len(Pw) - 2))
        seg = Pw[k + 1] - Pw[k]
        return Pw[k] + seg / max(1e-9, np.linalg.norm(seg)) * (s - S[k]), math.degrees(math.atan2(seg[1], seg[0]))
    piv = [f * Lw for f in fr]
    regions = [a for a, A_ in data["skins"][0]["attachments"][slot["name"]].items() if A_.get("type", "region") == "region"]
    M_att = {a: rig.att_matrix(slot["name"], a, world) for a in regions}      # before the tail bone is re-aimed
    # re-aim the root bone along the axis; children placed on the axis
    tb = pc.bone(data, "tail")
    _, a0 = at_w(piv[0] + 1e-3)
    parent_w = world[tb["parent"]]
    tb["rotation"] = round(a0 - pc.angle(parent_w), 2)
    tb["length"] = round(piv[1] - piv[0], 1)
    tb["color"] = pc.RED
    prev = "tail"
    for i in range(1, n):
        p, a = at_w(piv[i] + 1e-3)
        L = (piv[i + 1] if i + 1 < n else Lw) - piv[i]
        pc.place_bone(data, folder, names[i], prev, p, a, L, after=prev, color=pc.RED)
        prev = names[i]
    band = 0.06 * Lw
    report = {"bones": names, "length": round(Lw, 1), "fractions": fr, "attachments": {}}
    # the rest drawing: a strip mesh on the straight root -> tip axis (regular quads that never fold), with a vertex
    # row through each pivot's projection (the pivots themselves sit on the curved medial axis, on those rows)
    Ma = M_att[rest]
    Mi = np.linalg.inv(Ma)
    Ps = np.stack([P[0], P[-1]])
    apts = pm.alpha_points(alpha)
    s_, _ = pm.project(Ps, apts)
    piv_px = [float(pm.project(Ps, (Mi @ np.array([*at_w(pv)[0], 1]))[:2][None])[0][0]) for pv in piv]
    piv_px[0] = 0.0
    k_px = float(np.linalg.norm(Ps[1] - Ps[0])) / max(1e-6, Lw)
    band_px = band * k_px
    margin = 0.04 * float(np.linalg.norm(Ps[1] - Ps[0]))
    rows = _rows(min(s_.min(), 0) - margin, s_.max() + margin, 9, piv_px, band_px)
    lat, ok = pm.strip(alpha, Ps, rows, 4, margin)
    row_s = np.array(rows)

    def wfn(wpts, rc):
        return [_band_weights(float(row_s[r]), piv_px, names, band_px) for r, _ in rc]
    report["attachments"][rest] = {**to_mesh(data, folder, slot["name"], rest, lat, wfn, M=Ma), "fold_free": ok}
    # pose variants (a raised tail) stay rigid regions on the root bone, re-expressed for its new aim: their drawing
    # does not follow the rest tail's medial axis, so the chain's pivots would sit outside them
    rig2, world2, _ = _setup(data, folder)
    for att in regions:
        if att != rest:
            _region_on_bone(data["skins"][0]["attachments"][slot["name"]][att], M_att[att], world2["tail"],
                            rig2.images[att])
            report["attachments"][att] = "region, rigid on tail"
    return report


def _region_on_bone(A: dict, M: np.ndarray, bone_w, img) -> None:
    """Rewrite a region attachment's x / y / rotation / scale so that it maps image px -> world by M on a bone whose
    world matrix is bone_w (no shear: M is a similarity, possibly mirrored)."""
    B = pc.mat(bone_w)
    L = np.linalg.inv(B) @ M                                   # image px -> bone local
    w, h = A.get("width", img.width), A.get("height", img.height)
    kx, ky = w / img.width, h / img.height
    # L = R(rot) . diag(sx*kx, -sy*ky) . [[1,0,-W/2],[0,1,-H/2]]  (spine_qa.att_matrix)
    cx, cy = (L @ np.array([img.width / 2, img.height / 2, 1.0]))[:2]
    col0, col1 = L[:2, 0], L[:2, 1]
    rot = math.degrees(math.atan2(col0[1], col0[0]))
    sx = float(np.linalg.norm(col0)) / kx
    # the y column is -(sy*ky) along the rotated y axis
    r = math.radians(rot)
    yaxis = np.array([-math.sin(r), math.cos(r)])
    sy = -float(col1 @ yaxis) / ky
    A.update({"x": round(float(cx), 2), "y": round(float(cy), 2), "rotation": round(rot, 2),
              "scaleX": round(sx, 4), "scaleY": round(sy, 4)})


# ------------------------------------------------------------------ 4. torso: chest helper + breathing mesh

def torso_chest(data, folder) -> dict:
    """A `chest` helper bone (§2.5 hip/chest split) and the torso as a mesh weighted torso -> chest. Arms, head and
    neckwear move under the chest with inherit noScale, so a breathing scale on the chest does not scale them
    (§2.5: inherit-scale off on shoulders and neck for breathing)."""
    if not pc.has_bone(data, "torso") or pc.has_bone(data, "chest"):
        return {"skipped": "no torso (or already has chest)"}
    slot = next((s for s in data["slots"] if s["bone"] == "torso" and s.get("attachment")), None)
    if slot is None:
        return {"skipped": "torso has no slot"}
    rig, world, _ = _setup(data, folder)
    tw = world["torso"]
    root = np.array([tw[4], tw[5]])
    u = np.array([tw[0], tw[2]]) / math.hypot(tw[0], tw[2])
    kids = [b["name"] for b in data["bones"] if b.get("parent") == "torso"]
    s_k = {k: float((np.array([world[k][4], world[k][5]]) - root) @ u) for k in kids}
    arms = [k for k in kids if k.startswith("upperarm")]
    s_sh = float(np.mean([s_k[k] for k in arms])) if arms else 0.75 * pc.bone(data, "torso").get("length", 300)
    s_c = 0.5 * s_sh
    band = 0.14 * s_sh
    pc.place_bone(data, folder, "chest", "torso", root + u * s_c, pc.angle(tw), s_sh - s_c, after="torso",
                  color=pc.YELLOW)
    moved = []
    for k in kids:
        if s_k[k] > s_c + band:
            pc.reparent(data, folder, k, "chest")
            pc.bone(data, k)["inherit"] = "noScale"
            moved.append(k)
    rig, world, _ = _setup(data, folder)
    att = slot["attachment"]
    M = rig.att_matrix(slot["name"], att, world)
    Minv = np.linalg.inv(M)
    al = np.asarray(rig.images[att])[..., 3]
    r_px = (Minv @ np.array([*root, 1]))[:2]
    far_px = (Minv @ np.array([*(root + u * 10 * s_sh), 1]))[:2]
    P = np.stack([r_px, far_px])
    k_px = np.linalg.norm(far_px - r_px) / (10 * s_sh)
    apts = pm.alpha_points(al)
    s_, _ = pm.project(P, apts)
    margin = 0.03 * (s_.max() - s_.min())
    piv_px = [0.0, s_c * k_px]
    chain = ["torso", "chest"]
    doubts = []
    # each bone must keep a part on its own side of its pivot (spine_qa: a bone points into its own part). A torso
    # drawing that reaches far below the waist (dungarees, a long coat) would leave the torso bone owning mostly the
    # area behind its pivot; then the part below the waist is weighted to the hips (it moves with them anyway)
    u_px = (far_px - r_px) / max(1e-9, float(np.linalg.norm(far_px - r_px)))

    def own_cos(lo, hi):
        sel = (s_ >= lo) & (s_ < hi)
        if not sel.any():
            return -1.0
        v = apts[sel].mean(0) - r_px
        return float(v @ u_px / max(1e-9, np.linalg.norm(v)))
    cos0 = own_cos(-np.inf, s_c * k_px)
    parent = pc.bone(data, "torso").get("parent")
    if cos0 < TORSO_OWN_COS:
        if parent and any(sl["bone"] == parent for sl in data["slots"]):
            piv_px = [float(s_.min()) - margin, 0.0, s_c * k_px]
            chain = [parent, "torso", "chest"]
            doubts.append({"reason": "torso_below_waist", "detail": f"the torso drawing reaches {round(-float(s_.min()) / k_px, 1)} "
                           f"units below the waist (the torso bone's own part pointed {round(cos0, 2)} along it); "
                           f"the part below the waist is weighted to {parent}", "own_cos_after": round(own_cos(0.0, s_c * k_px), 2)})
        else:
            doubts.append({"reason": "torso_below_waist", "detail": f"own-part direction {round(cos0, 2)}, no parent part to take it"})
    rows = _rows(s_.min() - margin, s_.max() + margin, 7, piv_px, band * k_px)
    lat, ok = pm.strip(al, P, rows, 5, margin)
    row_s = np.array(rows)

    def wfn(wpts, rc):
        return [_band_weights(float(row_s[r]), piv_px, chain, band * k_px) for r, _ in rc]
    rep = to_mesh(data, folder, slot["name"], att, lat, wfn)
    out = {"chest_at": round(s_c, 1), "moved_under_chest": moved, "weights": chain, "mesh": rep, "fold_free": ok}
    if doubts:
        out["doubts"] = doubts
    return out


TORSO_OWN_COS = 0.3     # the torso bone's own share of the torso drawing must lie at least this much along the bone


# ------------------------------------------------------------------ 5. head: face helper + ears

def detect_ears(alpha: np.ndarray) -> list:
    """Ear lobes on an upright head image: the topmost point in each outer half with a valley between it and the
    crown at least 4% of the head's height deep. Returns [(side, base_px, tip_px, half_width_px)] (side l = the
    picture's right)."""
    H, W = alpha.shape
    m = alpha > 127
    cols = np.nonzero(m.any(0))[0]
    if not len(cols):
        return []
    top = np.where(m.any(0), m.argmax(0), H).astype(float)
    ys = np.nonzero(m.any(1))[0]
    hh = ys.max() - ys.min()
    x0, x1 = cols.min(), cols.max()
    cx = 0.5 * (x0 + x1)
    out = []
    for side, lo, hi in (("r", x0, cx - 0.08 * (x1 - x0)), ("l", cx + 0.08 * (x1 - x0), x1)):
        xs = np.arange(int(lo), int(hi) + 1)
        if not len(xs):
            continue
        # a lobe: a column whose top lies at least 4% of the head's height above the deepest point between it
        # and the centre line (the crown itself has no such valley); the highest such column is the tip
        depth = np.array([top[min(x, int(cx)):max(x, int(cx)) + 1].max() - top[x] for x in xs])
        cand = xs[depth >= 0.04 * hh]
        if not len(cand):
            continue
        tx = cand[np.argmin(top[cand])]
        ty = top[tx]
        between = np.arange(min(tx, int(cx)), max(tx, int(cx)) + 1)
        valley_x = between[np.argmax(top[between])]
        vy = top[valley_x]
        # columns whose top lies above the valley level, contiguous around the tip: the ear's span
        span = [tx]
        for step in (-1, 1):
            x = tx + step
            while 0 <= x < W and top[x] < vy:
                span.append(x)
                x += step
        sx0, sx1 = min(span), max(span)
        base = np.array([0.5 * (sx0 + sx1), vy + 0.1 * (vy - ty)])
        tip = np.array([float(tx), float(ty)])
        out.append((side, base, tip, 0.5 * (sx1 - sx0 + 1)))
    return out


def head_face(data, folder, ears: bool = True) -> dict:
    """Every head attachment as a mesh weighted to `head_base` (rim) and a `face` helper (centre, at most 45%), so
    moving `face` a few units fakes a 3D head turn (§2.5 `face` bone; Arman's face3D). Ear lobes found on the rest
    head get short `ear_l` / `ear_r` bones (§3 ear chains) and their vertices weighted to them."""
    if not pc.has_bone(data, "head_base") or pc.has_bone(data, "face"):
        return {"skipped": "no head_base (or already has face)"}
    slot = next((s for s in data["slots"] if s["bone"] == "head_base" and s.get("attachment")), None)
    if slot is None:
        return {"skipped": "head has no slot"}
    rig, world, _ = _setup(data, folder)
    rest = slot["attachment"]
    M = rig.att_matrix(slot["name"], rest, world)
    al = np.asarray(rig.images[rest])[..., 3]
    ys, xs = np.nonzero(al > 127)
    corners = (M @ np.array([[xs.min(), xs.max()], [ys.min(), ys.max()], [1, 1]]))[:2].T
    up = (M @ np.array([0, -1, 0]))[:2]
    upright = up[1] > 0.85 * np.linalg.norm(up)
    hw = world["head_base"]
    cx, cy = corners[:, 0].mean(), corners[:, 1].mean()
    rx, ry = abs(corners[1, 0] - corners[0, 0]) / 2, abs(corners[1, 1] - corners[0, 1]) / 2
    centre = np.array([cx, cy - 0.08 * ry])
    pc.place_bone(data, folder, "face", "head_base", centre, pc.angle(hw), 0.3 * ry, after="head_base",
                  color=pc.YELLOW)
    ear_info = []
    has_ear_parts = any(pc.has_bone(data, n) for n in ("ear_l", "ear_r"))
    if ears and upright and not has_ear_parts:
        for side, base, tip, half in detect_ears(al):
            bw = (M @ np.array([*base, 1]))[:2]
            tw_ = (M @ np.array([*tip, 1]))[:2]
            k = np.linalg.norm((M @ np.array([1, 0, 0]))[:2])
            ear_info.append({"side": side, "base": bw, "tip": tw_, "half": half * k})
    snapped = []
    for e in ear_info:
        name = f"ear_{e['side']}"
        d = e["tip"] - e["base"]
        pc.place_bone(data, folder, name, "head_base", e["base"], math.degrees(math.atan2(d[1], d[0])),
                      float(np.linalg.norm(d)), after="face", color=pc.RED)
        snapped.append(name)
    rx_, ry_ = rx, ry

    def wfn(wpts, rc):
        out = []
        for q in wpts:
            w = {}
            ear_sum = 0.0
            for e in ear_info:
                d = e["tip"] - e["base"]
                L = float(np.linalg.norm(d))
                uu = d / max(1e-9, L)
                v = q - e["base"]
                along = float(v @ uu)
                lat = abs(float(uu[0] * v[1] - uu[1] * v[0]))
                b = 0.2 * L
                wl = 1.4 * e["half"] + 0.15 * L
                we = float(pc.smoothstep((along + b) / (2 * b))) * float(1 - pc.smoothstep((lat - wl) / (0.6 * wl)))
                we *= float(1 - pc.smoothstep((along - 1.6 * L) / (0.3 * L)))
                if we > 0:
                    w[f"ear_{e['side']}"] = we
                    ear_sum += we
            ear_sum = min(ear_sum, 1.0)
            r = math.hypot((q[0] - centre[0]) / rx_, (q[1] - centre[1]) / ry_)
            wf = 0.45 * float(1 - pc.smoothstep((r - 0.3) / 0.55)) * (1 - ear_sum)
            if wf > 0:
                w["face"] = wf
            w["head_base"] = max(0.0, 1.0 - ear_sum - wf)
            out.append(w)
        return out
    report = {"face_at": [round(float(centre[0]), 1), round(float(centre[1]), 1)], "ears": snapped,
              "ear_parts": has_ear_parts, "attachments": {}}
    for att in list(data["skins"][0]["attachments"][slot["name"]]):
        if data["skins"][0]["attachments"][slot["name"]][att].get("type", "region") != "region":
            continue
        rig, world, _ = _setup(data, folder)
        Ma = rig.att_matrix(slot["name"], att, world)
        Mi = np.linalg.inv(Ma)
        a_ = np.asarray(rig.images[att])[..., 3]
        force = [tuple((Mi @ np.array([*e["base"], 1]))[:2]) for e in ear_info]
        k = np.linalg.norm((Ma @ np.array([1, 0, 0]))[:2])
        lat = pm.grid(a_, 9, 9, max(3.0, 6.0 / max(k, 1e-6)), force)
        report["attachments"][att] = to_mesh(data, folder, slot["name"], att, lat, wfn)
    return report


# ------------------------------------------------------------------ 6. planted feet

def feet(data, folder, legacy_world_fn) -> dict:
    """IK-style foot controls (§2.7, §3: targets built from the container, outside the chains). For each foot a green
    `<foot>_ik` bone under `character`; the foot follows it through a transform constraint (translate + rotate, no
    scale), or, when the foot hangs off a leg bone, a one-bone IK (compress + stretch) aims the leg at the target and
    a rotate-only transform constraint turns the foot. Every animation's foot motion is baked onto the targets from
    the legacy rig's world pose, so walks and jumps are unchanged while the hips are free to bob over planted feet."""
    fbs = foot_bones(data)
    if not fbs or not pc.has_bone(data, "character"):
        return {"skipped": "no feet or no container"}
    rig, world, _ = _setup(data, folder)
    data.setdefault("transform", [])
    data.setdefault("ik", [])
    order = len(data["transform"]) + len(data["ik"])
    report = {}
    for f in fbs:
        fb = pc.bone(data, f)
        leg = fb["parent"] if fb["parent"].startswith("leg") else None
        tgt = f"{f}_ik"
        pc.place_bone(data, folder, tgt, "character", (world[f][4], world[f][5]), pc.angle(world[f]),
                      0.5 * fb.get("length", 50), color=pc.GREEN)
        if leg:
            lb = pc.bone(data, leg)
            lb["length"] = round(math.hypot(fb.get("x", 0), fb.get("y", 0)), 2)
            data["ik"].append({"name": f"{leg}_ik", "order": order, "bones": [leg], "target": tgt,
                               "compress": True, "stretch": True})
            order += 1
            data["transform"].append({"name": f"{f}_rotate", "order": order, "bones": [f], "target": tgt,
                                      "mixRotate": 1, "mixX": 0, "mixY": 0, "mixScaleX": 0, "mixScaleY": 0,
                                      "mixShearY": 0})
        else:
            data["transform"].append({"name": f"{f}_plant", "order": order, "bones": [f], "target": tgt,
                                      "mixRotate": 1, "mixX": 1, "mixY": 1, "mixScaleX": 0, "mixScaleY": 0,
                                      "mixShearY": 0})
        order += 1
        report[f] = {"target": tgt, "leg_ik": leg}
    # bake: target(t) = legacy foot world(t) in the container's frame
    rig, world, _ = _setup(data, folder)
    baked = {}
    for anim in data["animations"]:
        ts = pc.frames(pc.duration(data, anim))
        ctl = data["animations"][anim].get("bones", {}).get("character", {}).get("translate", [])
        cx = pc.sample(ctl, ts, "x", 0.0) if ctl else np.zeros(len(ts))
        cy = pc.sample(ctl, ts, "y", 0.0) if ctl else np.zeros(len(ts))
        for f in fbs:
            w0 = legacy_world_fn(None, 0)[f]
            lw = [legacy_world_fn(anim, t)[f] for t in ts]
            dx = np.array([w[4] for w in lw]) - w0[4] - cx
            dy = np.array([w[5] for w in lw]) - w0[5] - cy
            ang = np.unwrap(np.radians([pc.angle(w) for w in lw])) * 180 / math.pi
            dr = ang - pc.angle(w0)
            dr -= 360 * np.round(dr[0] / 360)
            if np.abs(dx).max() < 0.05 and np.abs(dy).max() < 0.05 and np.abs(dr).max() < 0.05:
                continue
            pc.put(data, anim, f"{f}_ik", "translate", ts, x=dx, y=dy)
            if np.abs(dr).max() >= 0.05:
                pc.put(data, anim, f"{f}_ik", "rotate", ts, value=dr)
            baked.setdefault(anim, []).append(f)
            # the foot's own rotate / translate keys are now carried by the target
            fbt = data["animations"][anim].get("bones", {}).get(f, {})
            fbt.pop("rotate", None)
            fbt.pop("translate", None)
            if not fbt and f in data["animations"][anim].get("bones", {}):
                del data["animations"][anim]["bones"][f]
    for anim in data["animations"]:
        for f in fbs:
            fbt = data["animations"][anim].get("bones", {}).get(f, {})
            for k in ("rotate", "translate"):
                if k in fbt:            # not baked (no motion in character space), so these keys did nothing new
                    fbt.pop(k)
            if f in data["animations"][anim].get("bones", {}) and not fbt:
                del data["animations"][anim]["bones"][f]
    return {"feet": report, "baked": baked}


# ------------------------------------------------------------------ 2. underfill

UNDER_ROLES = ("upperarm", "forearm", "leg", "hand", "head", "tail", "boot", "hoof", "foot", "shoe", "hips", "ear")


def _under_image(img: Image.Image, ring_px: float, pad: int, zone=None) -> Image.Image:
    """A flat silhouette of the part, dilated by ring_px only inside `zone` (image px -> bool, the joint areas where
    gaps open), coloured with the part's own colour bled outward and darkened: a gap that opens at a joint shows
    shaded part colour, not background, and the free silhouette keeps its painted edge (no outline)."""
    arr = np.asarray(img).astype(np.float32)
    W, H = img.size
    a = np.zeros((H + 2 * pad, W + 2 * pad), np.float32)
    rgb = np.zeros((H + 2 * pad, W + 2 * pad, 3), np.float32)
    a[pad:pad + H, pad:pad + W] = arr[..., 3] / 255
    rgb[pad:pad + H, pad:pad + W] = arr[..., :3]
    # colour bleed: premultiplied blur / alpha blur, a few times wider than the ring
    rb = max(2.0, 1.5 * ring_px)
    solid = (a > 0.95).astype(np.float32)                 # bleed from solid pixels only: soft edges carry the grey
    pm_ = Image.fromarray(np.clip(rgb * solid[..., None], 0, 255).astype(np.uint8), "RGB").filter(ImageFilter.GaussianBlur(rb))
    ab = Image.fromarray((solid * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(rb))
    col = np.asarray(pm_).astype(np.float32) / np.maximum(np.asarray(ab).astype(np.float32)[..., None] / 255, 1e-3)
    inside = a > 0.5
    col[inside] = rgb[inside]
    col = np.clip(col * 0.78, 0, 255)
    r = max(1, int(round(ring_px)))
    base = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8), "L")
    if r <= 12:
        big = base.filter(ImageFilter.MaxFilter(2 * r + 1))
    else:
        small = base.resize((max(1, base.width // 4), max(1, base.height // 4)))
        big = small.filter(ImageFilter.MaxFilter(2 * max(1, r // 4) + 1)).resize(base.size)
    big = np.asarray(big).astype(np.float32) / 255
    if zone is not None:
        yy, xx = np.mgrid[0:base.height, 0:base.width]
        z = zone(xx - pad + 0.5, yy - pad + 0.5).astype(np.float32)
        z = np.asarray(Image.fromarray((z * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(max(1.0, ring_px)))) / 255
        big = np.maximum(a, ((big * z) > 0.5).astype(np.float32))   # a hard edge: no faint halo (spine_qa slivers)
    out = np.zeros((base.height, base.width, 4), np.uint8)
    out[..., :3] = col.astype(np.uint8)
    out[..., 3] = np.clip(np.round(big * 255), 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _joint_zone(data, world, M: np.ndarray, slot_bone: str, att: dict, img: Image.Image, frac: float = 0.22):
    """image px -> bool: within reach of the joint where this part meets its parent (its own pivot), where a gap opens
    when it turns. Joints inside one mesh (an elbow) never open, and a child part's joint is its own underfill's job.
    Radius: frac x sqrt(the part's area in world units)."""
    a = np.asarray(img)[..., 3] > 127
    area_px = max(1, int(a.sum()))
    k = math.sqrt(abs(np.linalg.det(M[:2, :2])))
    Rpx = frac * math.sqrt(area_px)
    cx, cy = (np.linalg.inv(M) @ np.array([world[slot_bone][4], world[slot_bone][5], 1.0]))[:2]

    def zone(x, y):
        return (x - cx) ** 2 + (y - cy) ** 2 <= Rpx ** 2
    return zone


def underfill(data, folder, ring_frac: float = 0.004) -> dict:
    """Underfill (§6 rule 2): for each moving part a darker, slightly dilated flat silhouette in a slot <slot>_under
    on the same bone (regions) or with the same weights (meshes: an identical mesh), with the part's attachment swaps
    mirrored. The dilation is limited to the part's joints, where gaps open. The underfills are drawn as one block
    behind every part (above the shadow), not directly below each part: directly below, the ring showed as a dark
    hairline wherever a part's edge lies over another part (spine_qa seams, and visibly on the sleeves); at the back
    it only shows where a gap opens onto the background, which is its purpose."""
    H = body_height(data)
    ring_units = ring_frac * H
    rig, world, _ = _setup(data, folder)
    skin = data["skins"][0]["attachments"]
    made = {}
    new_slots, unders = [], []
    feet_ = set(foot_bones(data))
    for s in data["slots"]:
        name = s["name"]
        role = name.rsplit("_", 1)[0] if name.endswith(("_l", "_r")) else name
        if s["bone"] in feet_:
            role = "foot"
        if name.endswith(("_back", "_under")) or name == "shadow" or role not in UNDER_ROLES or not s.get("attachment"):
            new_slots.append(s)
            continue
        under = f"{name}_under"
        skin[under] = {}
        for att, A in skin[name].items():
            img = rig.images[att]
            M = rig.att_matrix(name, att, world)
            k = math.sqrt(abs(np.linalg.det(M[:2, :2])))
            ring_px = ring_units / max(k, 1e-6)
            zone = _joint_zone(data, world, M, s["bone"], A, img)
            if A.get("type", "region") == "region":
                pad = int(math.ceil(ring_px)) + 2
                uimg = _under_image(img, ring_px, pad, zone)
                skin[under][f"{att}_under"] = {**A, "width": uimg.width, "height": uimg.height}
            else:
                uimg = _under_image(img, ring_px, 0, zone)
                skin[under][f"{att}_under"] = {kk: vv for kk, vv in A.items()}
            uimg.save(Path(folder) / "images" / f"{att}_under.png")
        unders.append({"name": under, "bone": s["bone"], "attachment": f"{s['attachment']}_under"})
        new_slots.append(s)
        made[name] = len(skin[under])
    old_names = [s["name"] for s in data["slots"]]
    lead = 1 if new_slots and new_slots[0]["name"] == "shadow" else 0
    new_slots = new_slots[:lead] + unders + new_slots[lead:]          # behind every part, above the shadow
    data["slots"] = new_slots
    new_names = [s["name"] for s in new_slots]
    for anim, A in data["animations"].items():
        for slot, tl in list(A.get("slots", {}).items()):
            if slot in made and "attachment" in tl:
                A["slots"][f"{slot}_under"] = {"attachment": [{**k, "name": (f"{k['name']}_under" if k.get("name") else None)}
                                                              for k in tl["attachment"]]}
        if "drawOrder" in A:
            A["drawOrder"] = [_reencode(k, old_names, new_names, made) for k in A["drawOrder"]]
    return {"slots": made, "ring_units": round(ring_units, 2)}


def _reencode(key: dict, old: list, new: list, made: dict) -> dict:
    """A drawOrder key re-expressed for the new slot list: the legacy order at that key, with the underfills kept as
    one block behind every part (right above the shadow)."""
    import spine_qa
    order = spine_qa.apply_offsets(old, key.get("offsets", [])) if key.get("offsets") else list(old)
    lead = [n for n in order[:1] if n == "shadow"]
    full = lead + [n for n in new if n.endswith("_under") and n[:-6] in made] + [n for n in order if n not in lead]
    offs = [{"slot": n, "offset": full.index(n) - new.index(n)} for n in new if full.index(n) != new.index(n)]
    out = {k: v for k, v in key.items() if k != "offsets"}
    if offs:
        out["offsets"] = offs
    return out


# ------------------------------------------------------------------ 7. organise

def organise(data) -> dict:
    """Bone colours: controllers red, helpers yellow, IK targets green (§2.8). Animated bones without a colour are
    controllers."""
    animated = {b for A in data["animations"].values() for b in A.get("bones", {})}
    counts = {"red": 0, "yellow": 0, "green": 0}
    for b in data["bones"]:
        if b["name"] == "root":
            continue
        if b["name"].endswith("_ik"):
            b["color"] = pc.GREEN
        elif b["name"] in ("chest", "face", "shadow"):
            b["color"] = pc.YELLOW
        elif b["name"] in animated or b["name"] in ("character", "hips", "torso", "head_base") or "color" in b:
            b.setdefault("color", pc.RED)
        else:
            continue
        counts[{pc.RED: "red", pc.YELLOW: "yellow", pc.GREEN: "green"}[b["color"]]] += 1
    return counts
