"""rig_sleeves.py - write the sleeve meshes (spine_rig.py stage 5b).

A whole-sleeve arm (annotation role `arm`, placed by rig_place with a "mesh" record on its upper arm) becomes one
weighted Spine mesh in its upper arm's slot (rig_mesh). Its weights are chosen once the animations are known, so no
triangle folds over the largest elbow bend any animation uses (+ rig_mesh.FOLD_MARGIN, each way).

  mesh_report = rig_sleeves.write(ex, anims, bones, place_info, crossing)
"""
from __future__ import annotations

import numpy as np

import rig_mesh


def write(ex, anims: dict, bones: list, place_info: dict, crossing: dict) -> dict:
    """Fill in the mesh attachment of every sleeve mesh in ex.skin (a rig_slots.Export). bones: the skeleton's bone
    list; crossing: sleeve slot -> the holds that draw it over the torso (rig_anim). Doubts are appended to ex.doubts.
    Returns the report per sleeve (report.json "meshes")."""
    pieces, world, units, prefix, doubts = ex.pieces, ex.world, ex.units, ex.prefix, ex.doubts
    mesh_report = {}
    bone_index = {b["name"]: i for i, b in enumerate(bones)}
    for n in sorted(pieces):
        mesh = pieces[n].get("mesh")
        if not mesh:
            continue
        fa = mesh["fore"]
        turns = [k_["value"] for an_ in anims.values() for k_ in an_.get("bones", {}).get(fa, {}).get("rotate", [])]
        need = (min(turns + [0.0]) - rig_mesh.FOLD_MARGIN, max(turns + [0.0]) + rig_mesh.FOLD_MARGIN)
        img = pieces[n]["img"]
        pts_ = mesh["points"]
        st = rig_mesh.strip(np.asarray(img.convert("RGBA"))[..., 3] > 0, pts_["shoulder"], pts_["elbow"], pts_["wrist"])
        to_units = lambda P, x: np.array([units(x.world(q)) for q in P])               # noqa: E731
        bind = rig_mesh.fitted(st.uv, mesh.get("fit"))       # the width fit moves the bind geometry, not the uvs
        m_ = rig_mesh.choose(st, to_units(bind, mesh["upper"]), to_units(bind, mesh["lower"]), world[fa][0], need)
        att = f"{prefix}{mesh['arm']}"
        ex.skin[n][att] = rig_mesh.attachment(st, m_, world[n], world[fa], bone_index[n], bone_index[fa], img.size)
        mesh_report[n] = {"arm": mesh["arm"], "scale_vs_sheet": round(place_info[n]["sleeve_scale"], 4),
                          "width_fit": place_info[n].get("width_fit"),
                          **rig_mesh.info(st, m_, need), "over_torso_in": crossing.get(n, [])}
        print(f"  {n}: sleeve mesh {mesh['arm']}, {len(st.ts)} rows, elbow {need[0]:.0f}..{need[1]:.0f} deg needed, "
              f"fold-free {m_.covered[0]:.0f}..{m_.covered[1]:.0f}"
              + ("" if m_.design == rig_mesh.DEFAULT else f" (weights {m_.design})"))
        if not m_.ok:
            doubts.append({"part": n, "reason": "mesh_fold_range", "need_deg": mesh_report[n]["need_deg"],
                           "covered_deg": mesh_report[n]["covered_deg"]})
            print(f"  ? doubt: {n}: no weights keep the sleeve mesh unfolded over the elbow's whole range")
    return mesh_report
