"""Skeleton-driven legs (kp_rig, KP_LEGS=bones): the key-pose drawings give only joint targets; real leg bones bend
the rig's own trousers painting to reach them. No drawing swaps, so the legs move continuously at any frame rate.

* Joints (legs/joints.json, scripts/leg_joints.py): per drawing and leg the hip, knee, ankle and sole, mapped to the
  rig by the drawing's sheet scale (kp_rig.Bridge.legs) and hung from the rig's own hip joints.
* Bones, appended (weighted meshes index bones): thigh_<s> (hip -> knee) and shin_<s> (knee -> ankle), both hung on
  the hips, so neither inherits the other's stretch; the shin is moved to the knee by translate keys.
* The trousers: the rig's own `beaver_hips` painting as a weighted mesh (a grid, MESH_STEP px), skinned by its
  position along each leg (hips above the hip joint, thigh to the knee, shin below, smoothstep bands) and by side
  (a soft band down the middle, so the crotch stretches between the two thighs). At rest it reproduces the region
  attachment exactly, so swapping it in at frame 0 changes nothing on screen.
* The boots keep their own bones and follow the ankle, turned by the change of the ankle -> sole direction.
* The joints run through the drawings' joint sets along the same progress curve as the drawing swaps (Catmull-Rom
  over p per coordinate); the hips drop by the legs' lost height, so the soles stay on the ground.
* Hybrid (HYBRID): near a held key pose (the end of a sheet's sequence: the deep crouch, the tuck) that pose's
  painted drawing fades in over the mesh (legs_a, HOLD_IN), stretched to the bones' leg height so its soles sit on
  the ground; once it is opaque the mesh and the rig's boots fade out beneath it (MESH_OUT); leaving the hold, the
  reverse. The bones' targets came from that drawing, so the two silhouettes match at the hold: real folds at the
  poses, continuous motion between them.
"""
from __future__ import annotations

import os

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import Delaunay

EXP = Path(__file__).resolve().parent.parent
MESH_STEP = 36                 # px between mesh vertices on the trousers painting
HIP_BAND = (-0.8, 0.5)       # along the thigh (0 hip, 1 knee): hips -> thigh weight ramps over this
KNEE_BAND = (0.3, 1.7)         # thigh -> shin around the knee
MID_BAND = 0.08                # belt widths either side of the middle: left / right blend
MORPH = bool(os.environ.get("KP_MORPH"))  # trousers mesh morphs toward the held painting's outline (deform keys)
MORPH_P = (0.25, 0.84)         # progress over which the morph ramps in (done before the painting starts to fade in)
MORPH_ALONG = 1.8             # control points from the hip (0) down to this far along the leg (2: the ankle)
TPS_SMOOTH = 50.0              # thin-plate spline smoothing (control points: belt, joints, outline both sides)
SKIN = bool(os.environ.get("KP_SKIN"))   # the held painting skinned to the same bones (key_mesh), else a plain region
HOLD_IN = (0.62, 0.76) if SKIN else (0.84, 0.95)   # progress over which a held key pose's painting fades in over the mesh
MESH_OUT = (0.76, 0.88) if SKIN else (0.95, 0.995) # then the trousers mesh (and the rig's boots) fade out beneath it


def smoothstep(a, b, x):
    u = np.clip((np.asarray(x, float) - a) / (b - a), 0, 1)
    return u * u * (3 - 2 * u)


def rot(deg):
    r = math.radians(deg)
    return np.array([[math.cos(r), -math.sin(r)], [math.sin(r), math.cos(r)]])


def ang(v):
    return math.degrees(math.atan2(v[1], v[0]))


def wrap(x):
    return (x + 180) % 360 - 180


def world_matrices(rig: dict) -> dict:
    """Setup world matrices (2x2, origin) per bone; rotation, translation and scale (setup scales are 1 here)."""
    out = {}
    for b in rig["bones"]:
        R = rot(b.get("rotation", 0.0)) @ np.diag([b.get("scaleX", 1.0), b.get("scaleY", 1.0)])
        o = np.array([b.get("x", 0.0), b.get("y", 0.0)])
        if "parent" in b:
            PR, Po = out[b["parent"]]
            out[b["name"]] = (PR @ R, PR @ o + Po)
        else:
            out[b["name"]] = (R, o)
    return out


class LegBones:
    def __init__(self, br, sheet_scales: dict):
        """br: kp_rig.Bridge after legs(); sheet_scales: sheet -> (sx, sy) world units per drawing px."""
        self.br = br
        rig = br.rig
        J = json.loads((EXP / "legs/joints.json").read_text())
        rest = json.loads((EXP / "legs/rig_rest.json").read_text())
        S, (bpx, bpy) = rest["ppu"], rest["buckle_px"]
        self.buckle = np.array(rest["buckle_world"])
        W = world_matrices(rig)
        self.HR, self.Ho = W["hips"]
        self.Hinv = np.linalg.inv(self.HR)
        to_local = lambda p_world: self.Hinv @ (np.asarray(p_world) - self.Ho)

        def rel_rest(p):                                  # rig_rest px -> world, relative to the buckle
            return np.array([(p[0] - bpx) / S, -(p[1] - bpy) / S])

        def rel_draw(name, p):
            sheet = name.split("_")[0]
            sx, sy = sheet_scales[sheet]
            bx, by = J[name]["belt"]
            return np.array([(p[0] - bx) * sx, -(p[1] - by) * sy])

        # rest joints, world (relative to the buckle) and hips-local
        self.rest = {s: {k: rel_rest(J["rig_rest"][s][k]) for k in ("hip", "knee", "ankle", "sole")} for s in ("l", "r")}
        # each drawing's joints hung from the rest hip: rest hip + (joint - the drawing's own hip)
        self.keys = {"rig": self.rest}
        for name in J:
            if name == "rig_rest":
                continue
            v = f"{name[0]}{name.split('_')[1]}"                 # squat_34 -> s34, jump_5 -> j5
            self.keys[v] = {s: {k: self.rest[s]["hip"] + rel_draw(name, J[name][s][k]) - rel_draw(name, J[name][s]["hip"])
                                for k in ("hip", "knee", "ankle", "sole")} for s in ("l", "r")}
        self.to_local = lambda rel: to_local(self.buckle + rel)
        # bones: thigh and shin per side, hung on the hips, appended
        self.bone_rest = {}
        for s in ("l", "r"):
            H, K, A = (self.to_local(self.rest[s][k]) for k in ("hip", "knee", "ankle"))
            for name, o, e in ((f"thigh_{s}", H, K), (f"shin_{s}", K, A)):
                rig["bones"].append({"name": name, "parent": "hips", "x": round(float(o[0]), 3), "y": round(float(o[1]), 3),
                                     "rotation": round(ang(e - o), 4), "length": round(float(np.linalg.norm(e - o)), 2)})
                self.bone_rest[name] = (o, ang(e - o), float(np.linalg.norm(e - o)))
        self.mesh()
        self.key_meshes = {}
        self._targets = {}
        self._boots = {}
        fp = EXP / "legs/hold_fit.json"
        self.fix = json.loads(fp.read_text()) if fp.exists() and os.environ.get("KP_FIT") else {}   # the size fit: tried, off

    FIX0 = {"thigh_sy": 1.0, "shin_sy": 1.0, "shin_len": 1.0, "kdx": 0.0, "kdy": 0.0}

    def corrected(self, J: dict, v: str, p: float) -> dict:
        """The joints and part sizes near a held key pose v, corrected toward its painted drawing (fit_holds.py): the
        knee nudged out (kdx, along the leg's side) and up (kdy), the shin's length scaled about the knee (the ankle and
        sole move with it), and the thigh's and shin's thickness; all ramp in with smoothstep(0.5, 1, p)."""
        f = dict(self.FIX0, **self.fix.get(v, {}))
        w = float(smoothstep(0.5, 1.0, p))
        out, thick = {}, {}
        for s in ("l", "r"):
            sg = 1 if s == "l" else -1
            H, K, A, S_ = (np.array(J[s][k], float) for k in ("hip", "knee", "ankle", "sole"))
            K2 = K + w * np.array([sg * f["kdx"], f["kdy"]])
            fl = 1 + w * (f["shin_len"] - 1)
            A2 = K2 + fl * (A - K)
            out[s] = {"hip": H, "knee": K2, "ankle": A2, "sole": A2 + (S_ - A)}
            thick[f"thigh_{s}"] = 1 + w * (f["thigh_sy"] - 1)
            thick[f"shin_{s}"] = 1 + w * (f["shin_sy"] - 1)
        return out, thick

    # ---- the trousers mesh
    def mesh(self):
        rig, br = self.br.rig, self.br
        att = br.skin["hips"]["beaver_hips"]
        img = Image.open(br.out / "images/beaver_hips.png").convert("RGBA")
        al = np.asarray(img)[..., 3]
        w, h = img.size
        grow = ndi.binary_dilation(al > 8, iterations=MESH_STEP // 2 + 2)
        gx, gy = np.meshgrid(np.arange(0, w + MESH_STEP, MESH_STEP).clip(0, w), np.arange(0, h + MESH_STEP, MESH_STEP).clip(0, h))
        pts = np.stack([gx.ravel(), gy.ravel()], 1).astype(float)
        pts = np.unique(pts, axis=0)
        keep = grow[pts[:, 1].clip(0, h - 1).astype(int), pts[:, 0].clip(0, w - 1).astype(int)]
        pts = pts[keep]
        tri = Delaunay(pts).simplices
        cen = pts[tri].mean(1)
        inside = ndi.binary_dilation(al > 8, iterations=3)[cen[:, 1].clip(0, h - 1).astype(int), cen[:, 0].clip(0, w - 1).astype(int)]
        tri = tri[inside]
        used = np.unique(tri)
        remap = -np.ones(len(pts), int)
        remap[used] = np.arange(len(used))
        pts, tri = pts[used], remap[tri]
        # image px -> hips-local (the region attachment's placement)
        R = rot(att.get("rotation", 0.0))
        loc = (R @ np.stack([(pts[:, 0] - w / 2) * att.get("scaleX", 1), (h / 2 - pts[:, 1]) * att.get("scaleY", 1)])).T + [att["x"], att["y"]]
        world = (self.HR @ loc.T).T + self.Ho
        # weights
        bw = self.br.leg_h and json.loads((EXP / "legs/rig_rest.json").read_text())["belt_w"]
        side_l = smoothstep(-MID_BAND * bw, MID_BAND * bw, world[:, 0] - self.buckle[0])
        names = [b["name"] for b in rig["bones"]]
        Wts = {"hips": np.zeros(len(pts))}
        for s, ws in (("l", side_l), ("r", 1 - side_l)):
            H, K, A = (self.to_local(self.rest[s][k]) for k in ("hip", "knee", "ankle"))
            # position along the leg: 0 hip, 1 knee, 2 ankle (projections on each segment)
            t1 = (loc - H) @ (K - H) / max(np.dot(K - H, K - H), 1e-9)
            t2 = (loc - K) @ (A - K) / max(np.dot(A - K, A - K), 1e-9)
            sp = np.where(t1 < 1, t1, 1 + t2)
            w_thigh_on = smoothstep(*HIP_BAND, sp)
            w_shin = smoothstep(*KNEE_BAND, sp)
            Wts["hips"] += ws * (1 - w_thigh_on)
            Wts[f"thigh_{s}"] = ws * (w_thigh_on - w_shin)
            Wts[f"shin_{s}"] = ws * w_shin
        Wm = world_matrices(rig)
        verts = []
        for i in range(len(pts)):
            entries = [(b, Wts[b][i]) for b in Wts if Wts[b][i] > 1e-3]
            tot = sum(x for _, x in entries)
            verts.append(len(entries))
            for b, x in entries:
                BR, Bo = Wm[b]
                bind = np.linalg.inv(BR) @ (world[i] - Bo)
                verts += [names.index(b), round(float(bind[0]), 3), round(float(bind[1]), 3), round(x / tot, 4)]
        self.mv_world = world                              # setup positions (world), and per vertex its weights
        self.mv_entries = []
        k_ = 0
        for i in range(len(pts)):
            cnt = verts[k_]; k_ += 1
            ent = []
            for _ in range(cnt):
                ent.append((names[verts[k_]], verts[k_ + 3], np.array([verts[k_ + 1], verts[k_ + 2]], float))); k_ += 4
            self.mv_entries.append(ent)
        uvs = np.stack([pts[:, 0] / w, pts[:, 1] / h], 1).ravel()
        br.skin["hips"]["beaver_hips_mesh"] = {"type": "mesh", "path": "beaver_hips", "uvs": [round(float(u), 6) for u in uvs],
                                              "triangles": [int(x) for x in tri.ravel()], "vertices": verts, "hull": 0,
                                              "width": w, "height": h}
        import shutil
        shutil.copy(br.out / "images/beaver_hips.png", br.out / "images/beaver_hips_mesh.png")   # spine_qa loads by name
        print(f"trousers mesh: {len(pts)} vertices, {len(tri)} triangles")

    # ---- the morph: trousers mesh points to the held painting, by skeleton coordinates
    @staticmethod
    def chain_coords(P, H, K, A, outward):
        """Skeleton coordinates of points P on a leg chain H -> K -> A (world): along (0 hip, 1 knee, 2 ankle; < 0
        above the hip) and across (signed distance from the chain, + toward `outward`, the leg's outer side)."""
        def seg(o, e):
            u = (e - o) / max(np.linalg.norm(e - o), 1e-9)
            n = np.array([-u[1], u[0]])
            if n @ outward < 0:
                n = -n
            t = (P - o) @ (e - o) / max(np.dot(e - o, e - o), 1e-9)
            return t, (P - o) @ n
        t1, d1 = seg(H, K)
        t2, d2 = seg(K, A)
        along = np.where(t1 < 1, t1, 1 + t2)
        across = np.where(t1 < 1, d1, d2)
        return along, across

    @staticmethod
    def chain_point(a, H, K, A, outward):
        """The chain's point and outward normal at `along` a (clamped to 0 .. 2.2)."""
        a = np.clip(a, -0.5, 2.2)
        o, e, t = (H, K, a) if a < 1 else (K, A, a - 1)

        def nrm(o_, e_):
            u = (e_ - o_) / max(np.linalg.norm(e_ - o_), 1e-9)
            n_ = np.array([-u[1], u[0]])
            return n_ if n_ @ outward >= 0 else -n_
        n1, n2 = nrm(H, K), nrm(K, A)
        b = float(smoothstep(0.75, 1.25, a))                   # the normal turns smoothly round the knee
        n = (1 - b) * n1 + b * n2
        n = n / max(np.linalg.norm(n), 1e-9)
        return o + t * (e - o), n

    def half_widths(self, mask, w2px, H, K, A, outward, grid):
        """Per `along` in grid: how far the outline lies from the chain, outward and inward (world units)."""
        hh, ww = mask.shape
        out = []
        for a in grid:
            c, n = self.chain_point(a, H, K, A, outward)
            res = []
            for sg in (1, -1):
                r = 0.0
                for step in range(1, 400):
                    q_ = c + sg * step * n
                    x, y = w2px(q_)
                    if not (0 <= x < ww and 0 <= y < hh) or not mask[int(y), int(x)]:
                        break
                    r = step
                res.append(max(r, 1.0))
            out.append(res)
        return np.array(out)

    def morph_targets(self, v: str):
        """Per trousers-mesh vertex: its correction at the hold of v, a displacement (world) from where the bones put
        it at v's pose to the painting's outline, from a thin-plate spline through control points on both outlines
        (the bent mesh's: v's joints and the standing legs' widths; the painting's: its joints and its widths) and the
        belt. The bones do the bending; the spline only the remaining shape, so it never has to fold."""
        if v in self._targets:
            return self._targets[v]
        br = self.br
        rest = json.loads((EXP / "legs/rig_rest.json").read_text())
        S, (bpx, bpy) = rest["ppu"], rest["buckle_px"]
        def cloth(a_):                                       # the trousers only: the boots (red) are not cloth
            hh, ss_, vv = __import__("cut_legs").hsv(a_[..., :3].astype(np.float32))
            red = ((hh < 14) | (hh > 340)) & (ss_ > 0.4)
            return (a_[..., 3] > 127) & ~ndi.binary_dilation(red, iterations=3)
        rm = cloth(np.asarray(Image.open(EXP / "legs/rig_rest.png").convert("RGBA")))
        r_w2px = lambda q_: ((q_[0] - self.buckle[0]) * S + bpx, (self.buckle[1] - q_[1]) * S + bpy)
        # the painting, placed as the hybrid shows it at the hold
        name = f"beaver_legs_{v}"
        att = br.skin["legs_a"][name]
        im = Image.open(br.out / f"images/{name}.png")
        pm = cloth(np.asarray(im.convert("RGBA")))
        w, h = im.size
        J = self.keys[v]
        s0 = -0.5 * (J["l"]["sole"][1] + J["r"]["sole"][1]) / br.leg_h[v]
        lb = next(b for b in br.rig["bones"] if b["name"] == "legs_a")
        bo = self.HR @ np.array([lb["x"], lb["y"]]) + self.Ho
        sx, sy = att["scaleX"], att["scaleY"]
        p2w = lambda u, vv: np.array([bo[0] + att["x"] + (u - w / 2) * sx, bo[1] + s0 * (att["y"] + (h / 2 - vv) * sy)])
        p_w2px = lambda q_: ((q_[0] - bo[0] - att["x"]) / sx + w / 2, h / 2 - ((q_[1] - bo[1]) / s0 - att["y"]) / sy)
        PJ = json.loads((EXP / "legs/joints.json").read_text())
        sheet, num = ("squat" if v[0] == "s" else "jump"), v[1:]
        pj = PJ[f"{sheet}_{num}"]
        grid = np.linspace(-0.5, 2.2, 55)
        # the trousers mesh with the bones at v's pose (hips at setup): where the morph starts from at the hold
        M = {"hips": (self.HR, self.Ho)}
        for side in ("l", "r"):
            H, K, A = (self.to_local(J[side][k]) for k in ("hip", "knee", "ankle"))
            for bn, o, e in ((f"thigh_{side}", H, K), (f"shin_{side}", K, A)):
                _, _, l0 = self.bone_rest[bn]
                M[bn] = (self.HR @ rot(ang(e - o)) @ np.diag([float(np.linalg.norm(e - o)) / l0, 1.0]), self.HR @ o + self.Ho)
        Pk = np.array([sum(wt * (M[b][0] @ bind + M[b][1]) for b, wt, bind in ent) for ent in self.mv_entries])
        # control points along both outlines: the bent mesh (key joints, the standing legs' widths: the bones keep a
        # leg's thickness) -> the painting (its joints and its own widths); the belt keeps its place
        src, dst = [], []
        for side, outward in (("l", np.array([1.0, 0.0])), ("r", np.array([-1.0, 0.0]))):
            Hr, Kr, Ar = (self.buckle + self.rest[side][k] for k in ("hip", "knee", "ankle"))
            Hk, Kk, Ak = (self.buckle + J[side][k] for k in ("hip", "knee", "ankle"))
            Hp, Kp, Ap = (p2w(*pj[side][k]) for k in ("hip", "knee", "ankle"))
            wr = self.half_widths(rm, r_w2px, Hr, Kr, Ar, outward, grid)
            wp = self.half_widths(pm, p_w2px, Hp, Kp, Ap, outward, grid)
            for a in np.linspace(0.0, MORPH_ALONG, 11):            # above the cuffs' lower edge
                ck, nk = self.chain_point(a, Hk, Kk, Ak, outward)
                cp, np_ = self.chain_point(a, Hp, Kp, Ap, outward)
                for c in (-1.0, 0.0, 1.0):
                    src.append(ck + c * np.interp(a, grid, wr[:, 0 if c > 0 else 1]) * nk)
                    dst.append(cp + c * np.interp(a, grid, wp[:, 0 if c > 0 else 1]) * np_)
        bw = rest["belt_w"]
        for dx in (-0.5, -0.25, 0.0, 0.25, 0.5):
            for dy in (0.0, -0.12):
                q_ = self.buckle + np.array([dx * bw, dy * bw])
                src.append(q_); dst.append(q_)
        from scipy.interpolate import RBFInterpolator
        tps = RBFInterpolator(np.array(src), np.array(dst) - np.array(src), kernel="thin_plate_spline", smoothing=TPS_SMOOTH)
        target = tps(Pk)                                     # the correction at the hold (a displacement, world)
        amount = np.ones(len(Pk))
        self._targets[v] = (target, amount)
        return target, amount

    def boot_fit(self, v: str):
        """Per side, the boot's correction at the hold of v: from the rig's boot (its bone at v's pose) to the
        painting's boot (its red shape), as a similarity about the boot's centre: the centre's shift and the boot's
        centre in its own frame (hips-local), an extra turn (principal axes) and a scale (areas)."""
        if v in self._boots:
            return self._boots[v]
        br = self.br
        name = f"beaver_legs_{v}"
        att = br.skin["legs_a"][name]
        im = Image.open(br.out / f"images/{name}.png").convert("RGBA")
        a_ = np.asarray(im)
        w, h = im.size
        J = self.keys[v]
        s0 = -0.5 * (J["l"]["sole"][1] + J["r"]["sole"][1]) / br.leg_h[v]
        lb = next(b for b in br.rig["bones"] if b["name"] == "legs_a")
        bo = self.HR @ np.array([lb["x"], lb["y"]]) + self.Ho
        hh, ss_, _ = __import__("cut_legs").hsv(a_[..., :3].astype(np.float32))
        red = ((hh < 14) | (hh > 340)) & (ss_ > 0.4) & (a_[..., 3] > 127)
        ys, xs = np.nonzero(red)
        pw = np.stack([bo[0] + att["x"] + (xs - w / 2) * att["scaleX"], bo[1] + s0 * (att["y"] + (h / 2 - ys) * att["scaleY"])], 1)
        pl = (self.Hinv @ (pw - self.Ho).T).T                 # painting boot pixels, hips-local

        def shape(P):
            c = P.mean(0)
            ev, evec = np.linalg.eigh(np.cov((P - c).T))
            return c, evec[:, 1], len(P)
        out = {}
        for side in ("l", "r"):
            sel = (pw[:, 0] - self.buckle[0]) * (1 if side == "l" else -1) > 0
            cp, ap, np_ = shape(pl[sel])
            # the rig's boot at v's pose: its region's opaque pixels through the boot bone
            A, S_ = (self.to_local(J[side][k]) for k in ("ankle", "sole"))
            O0, O1, dth, r0 = self.boot_pose(side, A, S_)
            ra_ = br.skin[f"boot_{side}"][f"beaver_boot_{side}"]
            bi = Image.open(br.out / f"images/beaver_boot_{side}.png").convert("RGBA")
            by_, bx_ = np.nonzero(np.asarray(bi)[..., 3] > 127)
            loc_att = (rot(ra_.get("rotation", 0)) @ np.stack([(bx_ - bi.width / 2) * ra_["scaleX"], (bi.height / 2 - by_) * ra_["scaleY"]])).T + [ra_["x"], ra_["y"]]
            bl = (rot(r0 + dth) @ loc_att.T).T + O1               # hips-local (the boot bone's rotation is relative to hips)
            ck, ak, nk = shape(bl)
            dr = math.degrees(math.atan2(ak[0] * ap[1] - ak[1] * ap[0], ak @ ap))
            dr = (dr + 90) % 180 - 90                            # an axis has no direction
            sc = math.sqrt((np_ * (abs(att["scaleX"] * att["scaleY"] * s0))) / max(nk * abs(ra_["scaleX"] * ra_["scaleY"]), 1e-9))
            crel = rot(-(dth)) @ (ck - O1)                       # the centre in the boot's frame at v's pose
            out[side] = (cp - ck, crel, dr, sc)
        self._boots[v] = out
        return out

    def morph_frame(self, v: str, m: float, HRt, Hot, local: dict) -> list:
        """Deform offsets for the trousers mesh at one frame: each vertex moved by m x its correction at the hold
        (where the bones put it at v's pose -> the painting's outline), as offsets in each influencing bone's bind
        space. local: bone -> (origin, rotation, scaleX, scaleY) in the hips' frame."""
        target, amount = self.morph_targets(v)
        M = {"hips": (HRt, Hot)}
        for b, (o, r_, sx_, sy_) in local.items():
            M[b] = (HRt @ rot(r_) @ np.diag([sx_, sy_]), HRt @ o + Hot)
        out = []
        for i, ent in enumerate(self.mv_entries):
            D = m * amount[i] * target[i]
            for b, wt, bind in ent:
                off = np.linalg.solve(M[b][0], D)
                out += [round(float(off[0]), 3), round(float(off[1]), 3)]
        return out

    # ---- the hybrid: painted key drawings at the holds
    def hybrid(self, an: dict, ts: list, at_p, height):
        def ss(a, b, x):
            return float(smoothstep(a, b, x))
        att, a_d, a_m, sc = [], [], [], []
        for t in ts:
            seq, p = at_p(t)
            v = seq[-1]                                   # the held key pose of this stretch
            d = ss(*HOLD_IN, p)
            m = 1 - ss(*MESH_OUT, p)
            if SKIN and v not in self.key_meshes:
                self.key_meshes[v] = self.key_mesh(v)
            att.append((self.key_meshes[v] if SKIN else f"beaver_legs_{v}") if d > 0 else None)
            a_d.append(d); a_m.append(m)
            sc.append(height(t) / self.br.leg_h[v] if d > 0 else 1.0)
        slots, bones = an.setdefault("slots", {}), an.setdefault("bones", {})
        keys = [{"time": round(ts[0], 4), "name": att[0]}] + [{"time": round(t, 4), "name": n} for i, (t, n) in enumerate(zip(ts, att)) if i and n != att[i - 1]]
        slots["legs_a"] = {"attachment": keys, "rgba": [{"time": round(t, 4), "color": "ffffff%02x" % round(255 * a)} for t, a in zip(ts, a_d)]}
        for s_ in ("hips", "boot_l", "boot_r"):
            slots.setdefault(s_, {})["rgba"] = [{"time": round(t, 4), "color": "ffffff%02x" % round(255 * a)} for t, a in zip(ts, a_m)]
        if not SKIN:                                       # a plain painting: stretched to the bones' leg height
            bones["legs_a"] = {"scale": [{"time": round(t, 4), "x": 1.0, "y": round(k, 4)} for t, k in zip(ts, sc)]}

    # ---- the animation
    def joints_at(self, seq: list, p: float) -> dict:
        """Joints (world, relative to the buckle) at progress p along seq: Catmull-Rom through the drawings' joints."""
        n = len(seq) - 1
        x = min(max(p, 0.0), 1.0) * n
        i = min(int(x), n - 1)
        u = x - i
        out = {}
        for s in ("l", "r"):
            out[s] = {}
            for k in ("hip", "knee", "ankle", "sole"):
                P = [self.keys[seq[max(0, min(n, j))]][s][k] for j in (i - 1, i, i + 1, i + 2)]
                m1 = 0.5 * (P[2] - P[0]) if i > 0 else P[2] - P[1]
                m2 = 0.5 * (P[3] - P[1]) if i + 1 < n else P[2] - P[1]
                if i == 0:
                    m1 = 0 * m1
                if i + 1 == n:
                    m2 = 0 * m2
                h00, h10, h01, h11 = 2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u, -2 * u**3 + 3 * u**2, u**3 - u**2
                out[s][k] = h00 * P[1] + h10 * m1 + h01 * P[2] + h11 * m2
        return out

    def boot_pose(self, s: str, A, S_):
        """The boot bone's local origin and rotation delta for ankle A and sole S_ (hips-local)."""
        Ar, Sr = (self.to_local(self.rest[s][k]) for k in ("ankle", "sole"))
        b = next(b for b in self.br.rig["bones"] if b["name"] == f"boot_{s}")
        O0 = np.array([b["x"], b["y"]])
        dth = wrap(ang(S_ - A) - ang(Sr - Ar))
        return O0, A + rot(dth) @ (O0 - Ar), dth, b.get("rotation", 0.0)

    def key_mesh(self, v: str):
        """The painting of held key pose v as a weighted mesh on the same bones, bound in its own pose: with the bones
        at v's joints it is exactly the painting; elsewhere it bends with them (toward standing as the legs straighten),
        like the trousers mesh bends toward v. Weights as the trousers' (along each leg in v's pose, a soft middle),
        the red boots on the boot bones."""
        br, rig = self.br, self.br.rig
        name = f"beaver_legs_{v}"
        att = br.skin["legs_a"][name]
        img = Image.open(br.out / f"images/{name}.png").convert("RGBA")
        a = np.asarray(img)
        al, w, h = a[..., 3], img.size[0], img.size[1]
        grow = ndi.binary_dilation(al > 8, iterations=MESH_STEP // 2 + 2)
        step = max(12, int(MESH_STEP * min(w, h) / 560))
        gx, gy = np.meshgrid(np.arange(0, w + step, step).clip(0, w), np.arange(0, h + step, step).clip(0, h))
        pts = np.unique(np.stack([gx.ravel(), gy.ravel()], 1).astype(float), axis=0)
        pts = pts[grow[pts[:, 1].clip(0, h - 1).astype(int), pts[:, 0].clip(0, w - 1).astype(int)]]
        tri = Delaunay(pts).simplices
        cen = pts[tri].mean(1)
        tri = tri[ndi.binary_dilation(al > 8, iterations=3)[cen[:, 1].clip(0, h - 1).astype(int), cen[:, 0].clip(0, w - 1).astype(int)]]
        used = np.unique(tri); remap = -np.ones(len(pts), int); remap[used] = np.arange(len(used)); pts, tri = pts[used], remap[tri]
        # v's pose with the hips at setup: joints, the drawing's placement (stretched to v's leg height)
        J = {s_: {k: self.keys[v][s_][k] for k in ("hip", "knee", "ankle", "sole")} for s_ in ("l", "r")}
        hgt = -0.5 * (J["l"]["sole"][1] + J["r"]["sole"][1])
        s0 = hgt / br.leg_h[v]
        lb = next(b for b in rig["bones"] if b["name"] == "legs_a")
        bone_o = self.HR @ np.array([lb["x"], lb["y"]]) + self.Ho
        world = np.stack([bone_o[0] + att["x"] + (pts[:, 0] - w / 2) * att["scaleX"],
                          bone_o[1] + s0 * (att["y"] + (h / 2 - pts[:, 1]) * att["scaleY"])], 1)
        loc = (self.Hinv @ (world - self.Ho).T).T
        # bone world matrices in v's pose (hips at setup)
        M = {"hips": (self.HR, self.Ho)}
        for s_ in ("l", "r"):
            H, K, A, S_ = (self.to_local(J[s_][k]) for k in ("hip", "knee", "ankle", "sole"))
            for bn, o, e in ((f"thigh_{s_}", H, K), (f"shin_{s_}", K, A)):
                _, _, l0 = self.bone_rest[bn]
                M[bn] = (self.HR @ rot(ang(e - o)) @ np.diag([float(np.linalg.norm(e - o)) / l0, 1.0]), self.HR @ o + self.Ho)
            O0, O1, dth, r0 = self.boot_pose(s_, A, S_)
            M[f"boot_{s_}"] = (self.HR @ rot(r0 + dth), self.HR @ O1 + self.Ho)
        # weights
        bw = json.loads((EXP / "legs/rig_rest.json").read_text())["belt_w"]
        side_l = smoothstep(-MID_BAND * bw, MID_BAND * bw, world[:, 0] - self.buckle[0])
        hh, ss_, vv = (lambda c: (c[0], c[1], c[2]))(__import__("cut_legs").hsv(a[..., :3].astype(np.float32)))
        red = ((hh < 14) | (hh > 340)) & (ss_ > 0.4) & (al > 127)
        soft = ndi.gaussian_filter(red.astype(np.float32), 0.25 * step)      # the boots blend into the cuffs
        is_boot = np.clip(soft[pts[:, 1].clip(0, h - 1).astype(int), pts[:, 0].clip(0, w - 1).astype(int)] * 1.6, 0, 1)
        Wts = {"hips": np.zeros(len(pts))}
        for s_, ws in (("l", side_l), ("r", 1 - side_l)):
            H, K, A = (self.to_local(J[s_][k]) for k in ("hip", "knee", "ankle"))
            t1 = (loc - H) @ (K - H) / max(np.dot(K - H, K - H), 1e-9)
            t2 = (loc - K) @ (A - K) / max(np.dot(A - K, A - K), 1e-9)
            sp = np.where(t1 < 1, t1, 1 + t2)
            on, shin = smoothstep(*HIP_BAND, sp), smoothstep(*KNEE_BAND, sp)
            Wts["hips"] += ws * (1 - on) * (1 - is_boot)
            Wts[f"thigh_{s_}"] = ws * (on - shin) * (1 - is_boot)
            Wts[f"shin_{s_}"] = ws * shin * (1 - is_boot)
            Wts[f"boot_{s_}"] = ws * is_boot
        names = [b["name"] for b in rig["bones"]]
        verts = []
        for i in range(len(pts)):
            entries = [(b, Wts[b][i]) for b in Wts if Wts[b][i] > 1e-3]
            tot = sum(x for _, x in entries)
            verts.append(len(entries))
            for b, x in entries:
                BR, Bo = M[b]
                bind = np.linalg.inv(BR) @ (world[i] - Bo)
                verts += [names.index(b), round(float(bind[0]), 3), round(float(bind[1]), 3), round(x / tot, 4)]
        mname = f"{name}_mesh"
        br.skin["legs_a"][mname] = {"type": "mesh", "path": name, "uvs": [round(float(u), 6) for u in np.stack([pts[:, 0] / w, pts[:, 1] / h], 1).ravel()],
                                    "triangles": [int(x) for x in tri.ravel()], "vertices": verts, "hull": 0, "width": w, "height": h}
        import shutil
        shutil.copy(br.out / f"images/{name}.png", br.out / f"images/{mname}.png")
        print(f"{mname}: {len(pts)} vertices")
        return mname

    def track(self, an: dict, T: float, segs: list, at_p, frames, lift, air, tail_out: float, tail_track):
        """Key the hips drop, thighs, shins and boots from the joints at every frame (at_p(t) -> (sheet, p))."""
        ts = frames(T)
        rest_h = -0.5 * (self.rest["l"]["sole"][1] + self.rest["r"]["sole"][1])
        crouch_h = -0.5 * (self.keys["s5"]["l"]["sole"][1] + self.keys["s5"]["r"]["sole"][1])
        B = {b: {"rotate": [], "scale": [], "translate": []} for b in ("thigh_l", "shin_l", "thigh_r", "shin_r", "boot_l", "boot_r")}
        hips_tr, heights = [], {}
        rig = self.br.rig
        boot_rest = {b["name"]: (np.array([b["x"], b["y"]]), b.get("rotation", 0.0)) for b in rig["bones"] if b["name"] in ("boot_l", "boot_r")}
        deform = []
        for t in ts:
            seq, p = at_p(t)
            J, thick = self.corrected(self.joints_at(seq, p), seq[-1], p)
            local = {}
            hgt = -0.5 * (J["l"]["sole"][1] + J["r"]["sole"][1])
            heights[round(t, 4)] = hgt
            hips_tr.append({"time": round(t, 4), "x": 0.0, "y": round((hgt - rest_h) * (1 - air(t)) + lift(t), 2)})
            for s in ("l", "r"):
                H, K, A, S_ = (self.to_local(J[s][k]) for k in ("hip", "knee", "ankle", "sole"))
                Kr, Ar, Sr = (self.to_local(self.rest[s][k]) for k in ("knee", "ankle", "sole"))
                for name, o, e in ((f"thigh_{s}", H, K), (f"shin_{s}", K, A)):
                    o0, a0, l0 = self.bone_rest[name]
                    B[name]["rotate"].append({"time": round(t, 4), "value": round(wrap(ang(e - o) - a0), 3)})
                    B[name]["scale"].append({"time": round(t, 4), "x": round(float(np.linalg.norm(e - o)) / l0, 4), "y": round(thick[name], 4)})
                    B[name]["translate"].append({"time": round(t, 4), "x": round(float(o[0] - o0[0]), 2), "y": round(float(o[1] - o0[1]), 2)})
                    local[name] = (o, ang(e - o), float(np.linalg.norm(e - o)) / l0, thick[name])
                dth = wrap(ang(S_ - A) - ang(Sr - Ar))
                O0, _ = boot_rest[f"boot_{s}"]
                O1 = A + rot(dth) @ (O0 - Ar)
                bsc = 1.0
                if MORPH:                                       # the boot eased onto the painting's boot near the hold
                    mb = float(smoothstep(*MORPH_P, p))
                    dc, crel, dr, sc_ = self.boot_fit(seq[-1])[s]
                    c = O1 + rot(dth) @ crel
                    bsc = 1 + mb * (sc_ - 1)
                    O1 = c + mb * dc + bsc * rot(mb * dr) @ (O1 - c)
                    dth = dth + mb * dr
                B[f"boot_{s}"]["rotate"].append({"time": round(t, 4), "value": round(dth, 3)})
                B[f"boot_{s}"]["translate"].append({"time": round(t, 4), "x": round(float(O1[0] - O0[0]), 2), "y": round(float(O1[1] - O0[1]), 2)})
                B[f"boot_{s}"]["scale"].append({"time": round(t, 4), "x": round(bsc, 4), "y": round(bsc, 4)})
            if MORPH:
                m = float(smoothstep(*MORPH_P, p))
                Hot = self.Ho + np.array([0.0, hips_tr[-1]["y"]])
                deform.append({"time": round(t, 4), "vertices": self.morph_frame(seq[-1], m, self.HR, Hot, local)} if m > 0 else {"time": round(t, 4)})
        bones = an.setdefault("bones", {})
        bones["hips"] = {"translate": hips_tr}
        if MORPH:
            an.setdefault("attachments", {}).setdefault("default", {}).setdefault("hips", {})["beaver_hips_mesh"] = {"deform": deform}
        for b, tl in B.items():
            bones[b] = {k: v for k, v in tl.items() if v}
        height = lambda t: heights[min(heights, key=lambda k: abs(k - t))]
        if os.environ.get("KP_HYBRID"):
            self.hybrid(an, ts, at_p, height)
        bones["tail"] = {"rotate": tail_track(lambda t: tail_out * min(1.0, max(0.0, rest_h - height(max(0.0, t - 0.06))) / (rest_h - crouch_h)), T)}
        an.setdefault("slots", {}).setdefault("hips", {})["attachment"] = [{"time": 0, "name": "beaver_hips_mesh"}, {"time": T, "name": "beaver_hips"}]   # keeps the hybrid's fade keys
        return height
