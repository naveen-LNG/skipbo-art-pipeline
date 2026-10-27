"""pro_common.py - shared helpers for spine_pro.py: evaluating a skeleton dict, bone surgery, timelines, meshes.

The skeleton is kept as valid Spine 4.2 JSON at every step (a dict); bone insertions remap the bone indices of
every weighted mesh, so spine_qa's renderer (DataRig) can pose it at any time.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

import numpy as np
from PIL import Image

import qa_constraints
import spine_qa

FPS = 30
# bone colours the animator sees in the tree (Spine "color", RRGGBBAA)
RED, YELLOW, GREEN = "ff3b3bff", "ffd21fff", "35d94aff"


class _Images(dict):
    def __init__(self, folder: Path):
        super().__init__()
        self.folder = folder

    def __missing__(self, name):
        im = Image.open(self.folder / f"{name}.png").convert("RGBA")
        self[name] = im
        return im


class DataRig(spine_qa.Rig):
    """spine_qa.Rig over an in-memory skeleton dict (images loaded lazily from folder)."""
    def __init__(self, data: dict, folder: Path):
        self.path = Path(folder) / "_in_memory.json"
        self.data = data
        self.bones = data["bones"]
        self.index = {b["name"]: i for i, b in enumerate(self.bones)}
        self.slots = data["slots"]
        self.skin = data["skins"][0]["attachments"]
        self.extended = qa_constraints.extended(data)
        self.images = _Images(Path(folder) / data["skeleton"].get("images", "./images/"))


# ------------------------------------------------------------------ matrices

def mat(w) -> np.ndarray:
    a, b, c, d, x, y = w
    return np.array([[a, b, x], [c, d, y], [0, 0, 1.0]])


def angle(w) -> float:
    return math.degrees(math.atan2(w[2], w[0]))


def to_local(parent_w, p) -> np.ndarray:
    """World point p in the parent bone's local frame."""
    return (np.linalg.inv(mat(parent_w)) @ np.array([p[0], p[1], 1.0]))[:2]


def to_world(w, p) -> np.ndarray:
    return (mat(w) @ np.array([p[0], p[1], 1.0]))[:2]


# ------------------------------------------------------------------ bones

def bone(data: dict, name: str) -> dict:
    return next(b for b in data["bones"] if b["name"] == name)


def has_bone(data: dict, name: str) -> bool:
    return any(b["name"] == name for b in data["bones"])


def set_bones(data: dict, new_bones: list) -> None:
    """Replace the bone list (parents before children: sorted here, stable) and remap every weighted mesh's bone
    indices by name."""
    old = [b["name"] for b in data["bones"]]
    by = {b["name"]: b for b in new_bones}
    order, seen = [], set()

    def visit(n):
        if n in seen:
            return
        p = by[n].get("parent")
        if p:
            visit(p)
        seen.add(n)
        order.append(by[n])
    for b in new_bones:
        visit(b["name"])
    idx = {b["name"]: i for i, b in enumerate(order)}
    for atts in data["skins"][0]["attachments"].values():
        for A in atts.values():
            if A.get("type") == "mesh" and len(A["vertices"]) != len(A["uvs"]):
                v, k, out = A["vertices"], 0, []
                while k < len(v):
                    cnt = int(v[k])
                    out.append(cnt)
                    k += 1
                    for _ in range(cnt):
                        out += [idx[old[int(v[k])]], v[k + 1], v[k + 2], v[k + 3]]
                        k += 4
                A["vertices"] = out
    data["bones"] = order


def add_bone(data: dict, b: dict, after: str | None = None) -> None:
    bones = list(data["bones"])
    if after is None:
        bones.append(b)
    else:
        i = next(i for i, x in enumerate(bones) if x["name"] == after)
        bones.insert(i + 1, b)
    set_bones(data, bones)


def place_bone(data: dict, folder: Path, name: str, parent: str, world_xy, world_rot: float, length: float,
               after: str | None = None, **extra) -> dict:
    """Add a bone at a world position / rotation (setup pose) under parent."""
    w = DataRig(data, folder).pose(None, 0)[0]
    pw = w[parent]
    lx, ly = to_local(pw, world_xy)
    b = {"name": name, "parent": parent, "x": round(float(lx), 2), "y": round(float(ly), 2),
         "rotation": round(float(world_rot - angle(pw)), 2), "length": round(float(length), 1), **extra}
    add_bone(data, b, after or parent)
    return b


def reparent(data: dict, folder: Path, name: str, new_parent: str) -> None:
    """Move a bone under new_parent keeping its setup world transform (parents here carry no scale or shear)."""
    w = DataRig(data, folder).pose(None, 0)[0]
    b = bone(data, name)
    lx, ly = to_local(w[new_parent], (w[name][4], w[name][5]))
    b["parent"] = new_parent
    b["x"], b["y"] = round(float(lx), 2), round(float(ly), 2)
    b["rotation"] = round(float(angle(w[name]) - angle(w[new_parent])), 2)
    set_bones(data, data["bones"])


# ------------------------------------------------------------------ timelines

def duration(data: dict, anim: str) -> float:
    a = data["animations"][anim]
    times = [k.get("time", 0) for tl in a.get("bones", {}).values() for keys in tl.values() for k in keys]
    times += [k.get("time", 0) for tl in a.get("slots", {}).values() for keys in tl.values() for k in keys]
    times += [k.get("time", 0) for k in a.get("drawOrder", [])]
    return max(times or [0])


def frames(dur: float) -> np.ndarray:
    n = max(1, int(round(dur * FPS)))
    return np.arange(n + 1) / FPS * (dur / (n / FPS))


def sample(keys: list, ts, field: str, default: float) -> np.ndarray:
    """Values of one field of a (linear / stepped) timeline at times ts (spine_qa.interp semantics)."""
    return np.array([(spine_qa.interp(keys, float(t), (field,), (default,)) or (default,))[0] for t in ts])


def put(data: dict, anim: str, bone_name: str, kind: str, ts, **fields) -> None:
    """Write a dense linear timeline (one key per time) for a bone: kind rotate (value=) / translate / scale (x=, y=)."""
    keys = []
    for i, t in enumerate(ts):
        k = {"time": round(float(t), 4)}
        for f, arr in fields.items():
            k[f] = round(float(arr[i]), 4 if kind == "scale" else 3)
        keys.append(k)
    data["animations"][anim].setdefault("bones", {}).setdefault(bone_name, {})[kind] = keys


def add_to(data: dict, anim: str, bone_name: str, kind: str, ts, **fields) -> None:
    """Add offsets (rotate value / translate x, y) or multiply factors (scale x, y) onto a bone's existing timeline,
    resampled densely at ts."""
    tl = data["animations"][anim].get("bones", {}).get(bone_name, {}).get(kind, [])
    out = {}
    for f, arr in fields.items():
        base = sample(tl, ts, f, 1.0 if kind == "scale" else 0.0) if tl else np.full(len(ts), 1.0 if kind == "scale" else 0.0)
        out[f] = base * arr if kind == "scale" else base + arr
    if kind in ("translate", "scale"):
        for f in ("x", "y"):
            if f not in out:
                out[f] = sample(tl, ts, f, 1.0 if kind == "scale" else 0.0) if tl else np.full(len(ts), 1.0 if kind == "scale" else 0.0)
    put(data, anim, bone_name, kind, ts, **out)


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def ease(t, t0, t1):
    """0 before t0, 1 after t1, smoothstep between (vectorised)."""
    return smoothstep((np.asarray(t, dtype=float) - t0) / max(1e-6, t1 - t0))


def gauss_smooth(x: np.ndarray, sigma: float, periodic: bool) -> np.ndarray:
    if sigma <= 0 or len(x) < 3:
        return x
    r = int(math.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    if periodic:
        core = x[:-1]                                  # the last frame repeats the first
        ext = np.concatenate([core[-r:], core, core[:r]]) if len(core) > r else np.tile(core, 3)[len(core) - r:2 * len(core) + r]
        y = np.convolve(ext, k, mode="valid")
        return np.append(y, y[0])
    ext = np.concatenate([np.full(r, x[0]), x, np.full(r, x[-1])])
    return np.convolve(ext, k, mode="valid")


# ------------------------------------------------------------------ meshes

def encode_weighted(points_world: np.ndarray, weights: list, bone_world: dict, bone_index: dict) -> list:
    """Spine weighted vertices: per vertex [count, (boneIndex, bindX, bindY, weight) x count]. weights: per vertex
    {bone: w} (normalised here, tiny weights dropped)."""
    out = []
    inv = {n: np.linalg.inv(mat(w)) for n, w in bone_world.items()}
    for p, ws in zip(points_world, weights):
        ws = {n: w for n, w in ws.items() if w > 0.004}
        s = sum(ws.values())
        out.append(len(ws))
        for n, w in sorted(ws.items(), key=lambda kv: bone_index[kv[0]]):
            bx, by = (inv[n] @ np.array([p[0], p[1], 1.0]))[:2]
            out += [bone_index[n], round(float(bx), 2), round(float(by), 2), round(w / s, 4)]
    return out


def mesh_attachment(uv_px: np.ndarray, size: tuple, triangles: np.ndarray, hull: int, vertices: list) -> dict:
    W, H = size
    uvs = (uv_px / np.array([W, H], dtype=float)).ravel()
    return {"type": "mesh", "uvs": [round(float(u), 5) for u in uvs], "triangles": [int(i) for i in triangles.ravel()],
            "vertices": vertices, "hull": int(hull), "width": int(W), "height": int(H)}


def deepcopy(x):
    return copy.deepcopy(x)
