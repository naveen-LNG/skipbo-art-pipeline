#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""spine_diff.py - what an animator changed in our Spine project, as labelled corrections.

  uv run spine_diff.py generated.json edited.json [--out corrections.jsonl] [--character beaver]

The feedback loop (docs/research/armanimation-spine/README.md §4): we emit a first-pass rig; the animator opens it in
Spine, fixes pivots, bones, weights and constraints, and exports JSON. This compares the two skeletons and writes one
correction per change, tagged like the research learnings (bucket, stage, primitive) so corrections become
rule / training data, one bucket at a time:

  bone        added / removed / reparented / moved (x, y) / rotated / rescaled / lengthened / inherit changed /
              recoloured; a move reports the setup-pose world delta too, as a fraction of the skeleton's height
  slot        added / removed / rebound to another bone / setup attachment changed / blend or colour changed;
              draw order: each slot whose setup index changed
  attachment  added / removed / type changed (region <-> mesh); region placement changed; mesh re-meshed (vertex
              or triangle count), uvs moved, bind positions moved, weights changed (per bone: vertices gained / lost
              influence, mean and max weight change)
  constraint  ik / transform / path / physics constraint added / removed / any field changed
  animation   added / removed; per timeline a summary (keys added / removed / changed, largest value change)

Stages: skeleton, helper-bones, mesh-weights, constraints, organize, animate (the research's stage names).
Bucket: anthro-biped-animal (our cast) unless --bucket says otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

BUCKET = "anthro-biped-animal"
POS_EPS, ROT_EPS, SCALE_EPS, W_EPS = 0.05, 0.05, 1e-4, 0.005


# ------------------------------------------------------------------ helpers

def _world(bones: list) -> dict:
    """Setup-pose world matrices (a, b, c, d, x, y), inherit 'normal' only (good enough for reporting deltas)."""
    w = {}
    for b in bones:
        r = math.radians(b.get("rotation", 0.0))
        sx, sy = b.get("scaleX", 1.0), b.get("scaleY", 1.0)
        la, lb, lc, ld = math.cos(r) * sx, -math.sin(r) * sy, math.sin(r) * sx, math.cos(r) * sy
        x, y = b.get("x", 0.0), b.get("y", 0.0)
        p = w.get(b.get("parent"))
        if p is None:
            w[b["name"]] = (la, lb, lc, ld, x, y)
        else:
            pa, pb, pc, pd, px, py = p
            w[b["name"]] = (pa * la + pb * lc, pa * lb + pb * ld, pc * la + pd * lc, pc * lb + pd * ld,
                            pa * x + pb * y + px, pc * x + pd * y + py)
    return w


def _helper(name: str, slotted: set) -> bool:
    return name not in slotted and name not in ("root", "character") and not name.endswith("_ik")


def _bone_stage(name: str, slotted: set) -> str:
    if name.endswith("_ik") or name.endswith("_target"):
        return "constraints"
    return "helper-bones" if _helper(name, slotted) else "skeleton"


def weights_by_vertex(att: dict, bones: list) -> list | None:
    """Per vertex {bone name: weight} for a weighted mesh (None for regions / unweighted meshes)."""
    if att.get("type") not in ("mesh",) or len(att.get("vertices", [])) == len(att.get("uvs", [])):
        return None
    v, k, out = att["vertices"], 0, []
    while k < len(v):
        c = int(v[k])
        k += 1
        d = {}
        for _ in range(c):
            d[bones[int(v[k])]["name"]] = d.get(bones[int(v[k])]["name"], 0.0) + v[k + 3]
            k += 4
        out.append(d)
    return out


def bind_positions(att: dict, bones: list) -> list:
    """Per vertex setup-pose world position (weighted: sum w * bone world . bind; unweighted: raw local)."""
    n = len(att.get("uvs", [])) // 2
    v = att.get("vertices", [])
    if len(v) == 2 * n:
        return [(v[2 * i], v[2 * i + 1]) for i in range(n)]
    w = _world(bones)
    out, k = [], 0
    for _ in range(n):
        c = int(v[k])
        k += 1
        x = y = 0.0
        for _ in range(c):
            a, b_, c_, d, wx, wy = w[bones[int(v[k])]["name"]]
            bx, by, ww = v[k + 1], v[k + 2], v[k + 3]
            x += ww * (a * bx + b_ * by + wx)
            y += ww * (c_ * bx + d * by + wy)
            k += 4
        out.append((x, y))
    return out


# ------------------------------------------------------------------ the diff

class Diff:
    def __init__(self, gen: dict, edit: dict, character: str | None, bucket: str, sources: tuple):
        self.g, self.e = gen, edit
        self.character, self.bucket, self.sources = character, bucket, sources
        self.H = float(gen.get("skeleton", {}).get("height") or 1.0)
        self.out: list = []

    def add(self, stage: str, primitive: str, kind: str, target: str, before=None, after=None, **detail):
        rec = {"bucket": self.bucket, "stage": stage, "primitive": primitive, "kind": kind, "target": target,
               "before": before, "after": after}
        if detail:
            rec["detail"] = detail
        if self.character:
            rec["character"] = self.character
        rec["generated"], rec["edited"] = self.sources
        rec["id"] = hashlib.sha1(json.dumps([self.character, stage, kind, target, before, after], sort_keys=True,
                                            default=str).encode()).hexdigest()[:12]
        self.out.append(rec)

    # bones
    def bones(self):
        gb = {b["name"]: b for b in self.g["bones"]}
        eb = {b["name"]: b for b in self.e["bones"]}
        g_slotted = {s["bone"] for s in self.g.get("slots", [])}
        e_slotted = {s["bone"] for s in self.e.get("slots", [])}
        gw, ew = _world(self.g["bones"]), _world(self.e["bones"])
        for n in eb.keys() - gb.keys():
            b = eb[n]
            self.add(_bone_stage(n, e_slotted), "bone", "bone_added", n, None,
                     {k: b.get(k) for k in ("parent", "x", "y", "rotation", "length", "inherit", "color") if k in b},
                     world=[round(ew[n][4], 2), round(ew[n][5], 2)], helper=_helper(n, e_slotted))
        for n in gb.keys() - eb.keys():
            self.add(_bone_stage(n, g_slotted), "bone", "bone_removed", n, {"parent": gb[n].get("parent")}, None)
        for n in gb.keys() & eb.keys():
            a, b = gb[n], eb[n]
            st = _bone_stage(n, g_slotted)
            if a.get("parent") != b.get("parent"):
                self.add(st, "bone", "bone_reparented", n, a.get("parent"), b.get("parent"))
            dx, dy = b.get("x", 0.0) - a.get("x", 0.0), b.get("y", 0.0) - a.get("y", 0.0)
            wdx, wdy = ew[n][4] - gw[n][4], ew[n][5] - gw[n][5]
            if math.hypot(dx, dy) > POS_EPS and a.get("parent") == b.get("parent"):
                self.add(st, "bone", "bone_moved", n, [a.get("x", 0.0), a.get("y", 0.0)], [b.get("x", 0.0), b.get("y", 0.0)],
                         local_delta=[round(dx, 2), round(dy, 2)], world_delta=[round(wdx, 2), round(wdy, 2)],
                         world_delta_frac_height=round(math.hypot(wdx, wdy) / self.H, 4))
            dr = (b.get("rotation", 0.0) - a.get("rotation", 0.0) + 180) % 360 - 180
            if abs(dr) > ROT_EPS and a.get("parent") == b.get("parent"):
                self.add(st, "bone", "bone_rotated", n, a.get("rotation", 0.0), b.get("rotation", 0.0), delta=round(dr, 2))
            for f in ("scaleX", "scaleY", "shearX", "shearY"):
                d0 = 1.0 if f.startswith("scale") else 0.0
                if abs(b.get(f, d0) - a.get(f, d0)) > SCALE_EPS:
                    self.add(st, "bone", "bone_rescaled" if f.startswith("scale") else "bone_sheared", n,
                             a.get(f, d0), b.get(f, d0), field=f)
            if abs(b.get("length", 0.0) - a.get("length", 0.0)) > POS_EPS:
                self.add(st, "bone", "bone_lengthened", n, a.get("length", 0.0), b.get("length", 0.0))
            if a.get("inherit", "normal") != b.get("inherit", "normal"):
                self.add("helper-bones", "inherit", "bone_inherit_changed", n, a.get("inherit", "normal"),
                         b.get("inherit", "normal"))
            if a.get("color") != b.get("color"):
                self.add("organize", "bone", "bone_recoloured", n, a.get("color"), b.get("color"))

    # slots + draw order
    def slots(self):
        gs = {s["name"]: s for s in self.g.get("slots", [])}
        es = {s["name"]: s for s in self.e.get("slots", [])}
        for n in es.keys() - gs.keys():
            self.add("skeleton", "slot", "slot_added", n, None, {"bone": es[n]["bone"], "attachment": es[n].get("attachment")})
        for n in gs.keys() - es.keys():
            self.add("skeleton", "slot", "slot_removed", n, {"bone": gs[n]["bone"]}, None)
        for n in gs.keys() & es.keys():
            a, b = gs[n], es[n]
            if a["bone"] != b["bone"]:
                self.add("skeleton", "slot", "slot_rebound", n, a["bone"], b["bone"])
            if a.get("attachment") != b.get("attachment"):
                self.add("skeleton", "attachment", "slot_setup_attachment", n, a.get("attachment"), b.get("attachment"))
            for f in ("color", "dark", "blend"):
                if a.get(f) != b.get(f):
                    self.add("organize", "slot", f"slot_{f}_changed", n, a.get(f), b.get(f))
        go = [s["name"] for s in self.g.get("slots", []) if s["name"] in es]
        eo = [s["name"] for s in self.e.get("slots", []) if s["name"] in gs]
        if go != eo:
            for n in go:
                if go.index(n) != eo.index(n):
                    above_g = go[go.index(n) + 1] if go.index(n) + 1 < len(go) else None
                    above_e = eo[eo.index(n) + 1] if eo.index(n) + 1 < len(eo) else None
                    self.add("organize", "slot", "draw_order_changed", n, go.index(n), eo.index(n),
                             below_of_before=above_g, below_of_after=above_e)

    # attachments
    def attachments(self):
        gk = self.g["skins"][0]["attachments"] if self.g.get("skins") else {}
        ek = self.e["skins"][0]["attachments"] if self.e.get("skins") else {}
        for slot in sorted(set(gk) | set(ek)):
            ga, ea = gk.get(slot, {}), ek.get(slot, {})
            for att in sorted(set(ea) - set(ga)):
                self.add("mesh-weights" if ea[att].get("type") == "mesh" else "skeleton", "attachment",
                         "attachment_added", f"{slot}/{att}", None, ea[att].get("type", "region"))
            for att in sorted(set(ga) - set(ea)):
                self.add("skeleton", "attachment", "attachment_removed", f"{slot}/{att}", ga[att].get("type", "region"), None)
            for att in sorted(set(ga) & set(ea)):
                self.attachment(f"{slot}/{att}", ga[att], ea[att])

    def attachment(self, target: str, a: dict, b: dict):
        ta, tb = a.get("type", "region"), b.get("type", "region")
        if ta != tb:
            self.add("mesh-weights", "mesh", "attachment_type_changed", target, ta, tb)
            return
        if ta == "region":
            ch = {f: [a.get(f), b.get(f)] for f in ("x", "y", "rotation", "scaleX", "scaleY", "width", "height")
                  if abs((b.get(f) or 0) - (a.get(f) or 0)) > 1e-3}
            if ch:
                self.add("skeleton", "attachment", "region_placement_changed", target,
                         {f: v[0] for f, v in ch.items()}, {f: v[1] for f, v in ch.items()})
            return
        if ta != "mesh":
            if a != b:
                self.add("skeleton", "attachment", f"{ta}_changed", target)
            return
        na, nb = len(a["uvs"]) // 2, len(b["uvs"]) // 2
        if na != nb or len(a["triangles"]) != len(b["triangles"]):
            self.add("mesh-weights", "mesh", "mesh_remeshed", target, {"vertices": na, "triangles": len(a["triangles"]) // 3},
                     {"vertices": nb, "triangles": len(b["triangles"]) // 3}, hull=[a.get("hull"), b.get("hull")])
            self.weights_summary(target, a, b, same_topology=False)
            return
        duv = max((abs(x - y) for x, y in zip(a["uvs"], b["uvs"])), default=0.0)
        if duv > 1e-4:
            self.add("mesh-weights", "mesh", "mesh_uvs_moved", target, None, None, max_uv_delta=round(duv, 5))
        if a["triangles"] != b["triangles"]:
            self.add("mesh-weights", "mesh", "mesh_retriangulated", target)
        pa, pb = bind_positions(a, self.g["bones"]), bind_positions(b, self.e["bones"])
        moved = [i for i, (p, q) in enumerate(zip(pa, pb)) if math.hypot(p[0] - q[0], p[1] - q[1]) > POS_EPS * 4]
        if moved:
            dmax = max(math.hypot(pa[i][0] - pb[i][0], pa[i][1] - pb[i][1]) for i in moved)
            self.add("mesh-weights", "mesh", "mesh_vertices_moved", target, None, None, vertices=len(moved),
                     of=na, max_delta=round(dmax, 2), max_delta_frac_height=round(dmax / self.H, 4))
        self.weights_summary(target, a, b, same_topology=True)

    def weights_summary(self, target: str, a: dict, b: dict, same_topology: bool):
        wa, wb = weights_by_vertex(a, self.g["bones"]), weights_by_vertex(b, self.e["bones"])
        if wa is None and wb is None:
            return
        if (wa is None) != (wb is None):
            self.add("mesh-weights", "weights", "mesh_weighting_toggled", target, wa is not None, wb is not None)
            return
        ba = sorted({n for d in wa for n in d})
        bb = sorted({n for d in wb for n in d})
        if ba != bb:
            self.add("mesh-weights", "weights", "weight_bones_changed", target, ba, bb,
                     added=sorted(set(bb) - set(ba)), removed=sorted(set(ba) - set(bb)))
        if not same_topology:
            return
        for bone in sorted(set(ba) | set(bb)):
            d = [db.get(bone, 0.0) - da.get(bone, 0.0) for da, db in zip(wa, wb)]
            changed = [x for x in d if abs(x) > W_EPS]
            if changed:
                self.add("mesh-weights", "weights", "weights_changed", f"{target}@{bone}", None, None,
                         vertices_changed=len(changed), gained=sum(1 for x in changed if x > 0),
                         lost=sum(1 for x in changed if x < 0), mean_abs=round(sum(map(abs, changed)) / len(changed), 4),
                         max_abs=round(max(map(abs, changed)), 4))

    # constraints
    def constraints(self):
        for kind in ("ik", "transform", "path", "physics"):
            ga = {c["name"]: c for c in self.g.get(kind, [])}
            ea = {c["name"]: c for c in self.e.get(kind, [])}
            for n in ea.keys() - ga.keys():
                self.add("constraints", kind, "constraint_added", n, None, ea[n])
            for n in ga.keys() - ea.keys():
                self.add("constraints", kind, "constraint_removed", n, ga[n], None)
            for n in ga.keys() & ea.keys():
                diff = {f: [ga[n].get(f), ea[n].get(f)] for f in set(ga[n]) | set(ea[n]) if ga[n].get(f) != ea[n].get(f)}
                if diff:
                    self.add("constraints", kind, "constraint_changed", n, {f: v[0] for f, v in diff.items()},
                             {f: v[1] for f, v in diff.items()})

    # animations
    def animations(self):
        ga, ea = self.g.get("animations", {}), self.e.get("animations", {})
        for n in ea.keys() - ga.keys():
            self.add("animate", "animation", "animation_added", n, None, sorted(ea[n]))
        for n in ga.keys() - ea.keys():
            self.add("animate", "animation", "animation_removed", n, sorted(ga[n]), None)
        for n in sorted(ga.keys() & ea.keys()):
            for group in ("bones", "slots"):
                g_, e_ = ga[n].get(group, {}), ea[n].get(group, {})
                for item in sorted(set(g_) | set(e_)):
                    for tl in sorted(set(g_.get(item, {})) | set(e_.get(item, {}))):
                        self.timeline(n, f"{group}.{item}.{tl}", g_.get(item, {}).get(tl, []), e_.get(item, {}).get(tl, []))
            for key in ("drawOrder", "events", "ik", "transform", "deform", "attachments"):
                if ga[n].get(key) != ea[n].get(key):
                    self.add("animate", "timeline", "timeline_changed", f"{n}:{key}", None, None)

    def timeline(self, anim: str, path: str, ka: list, kb: list):
        if ka == kb:
            return
        ta = {round(k.get("time", 0.0), 4): k for k in ka}
        tb = {round(k.get("time", 0.0), 4): k for k in kb}
        added, removed = sorted(tb.keys() - ta.keys()), sorted(ta.keys() - tb.keys())
        changed, dmax = 0, 0.0
        for t in ta.keys() & tb.keys():
            if ta[t] != tb[t]:
                changed += 1
                for f in ("value", "x", "y"):
                    if isinstance(ta[t].get(f), (int, float)) and isinstance(tb[t].get(f), (int, float)):
                        dmax = max(dmax, abs(tb[t][f] - ta[t][f]))
        kind = "timeline_added" if not ka else "timeline_removed" if not kb else "timeline_changed"
        self.add("animate", "timeline", kind, f"{anim}:{path}", len(ka), len(kb), keys_added=len(added),
                 keys_removed=len(removed), keys_changed=changed, max_value_delta=round(dmax, 3))


def diff(gen: dict, edit: dict, character: str | None = None, bucket: str = BUCKET,
         sources: tuple = ("generated", "edited")) -> list:
    d = Diff(gen, edit, character, bucket, sources)
    d.bones()
    d.slots()
    d.attachments()
    d.constraints()
    d.animations()
    return d.out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("generated", type=Path)
    ap.add_argument("edited", type=Path)
    ap.add_argument("--out", type=Path, help="corrections.jsonl (default: print)")
    ap.add_argument("--character", help="default: the generated file's stem")
    ap.add_argument("--bucket", default=BUCKET)
    a = ap.parse_args(argv)
    gen = json.loads(a.generated.read_text(encoding="utf-8"))
    edit = json.loads(a.edited.read_text(encoding="utf-8"))
    recs = diff(gen, edit, a.character or a.generated.stem, a.bucket, (str(a.generated), str(a.edited)))
    lines = "\n".join(json.dumps(r, sort_keys=True, default=str) for r in recs)
    if a.out:
        a.out.write_text(lines + ("\n" if lines else ""), encoding="utf-8")
        by = {}
        for r in recs:
            by[r["kind"]] = by.get(r["kind"], 0) + 1
        print(f"{len(recs)} corrections -> {a.out}: " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
    else:
        print(lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
