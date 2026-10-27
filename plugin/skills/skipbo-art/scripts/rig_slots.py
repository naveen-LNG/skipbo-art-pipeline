"""rig_slots.py - a rig's slots, default skin and images (spine_rig.py stage 4, after the bones).

Each placed piece gets a slot on its bone, sorted back to front (layer_key), and a region attachment (region_att) whose
image is saved to <out>/images. With annotations a worn foot drawn over the leg is cut at its ankle opening (rig_worn)
into a shell in its own slot and a back part in slot <foot>_back, drawn behind the legs (worn_cut); the back slot
swaps in sync with its shell (sync_worn). A sleeve mesh (rig_mesh) sits in its upper arm's slot; its attachment is
written later (rig_sleeves), once the animations say how far its elbow bends.

  ex = rig_slots.Export(out, prefix, pieces, patches, world, units, LAYERS, ann, doubts)
  ex.write_parts(); ex.add_heads(heads, head_pc, trust)   # then ex.slots, ex.skin, ex.images
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import rig_worn
from rig_image import solidify
from rig_roles import ann_roles, role


class Export:
    """The slots, skin and image names of one rig as they are written. pieces, patches (patch -> the piece it
    patches), world (bone -> ((x, y) units, world angle)) and units (master px -> Spine units) as in spine_rig.main;
    layers: the draw order in use (rig_roles.LAYERS as spine_rig set it); doubts: appended to."""

    def __init__(self, out: Path, prefix: str, pieces: dict, patches: dict, world: dict, units, layers: list, ann,
                 doubts: list):
        self.out, self.prefix, self.pieces, self.patches = out, prefix, pieces, patches
        self.world, self.units, self.layers, self.ann, self.doubts = world, units, layers, ann, doubts
        self.slots, self.skin, self.images = [], {}, []
        self.roles = ann_roles(ann)              # annotated roles set layers (None: guessed from the names)
        # a hand on a sleeve-mesh side hugs its sleeve's slot: directly above it with hand over_forearm (a glove's cuff
        # over the sleeve's end), directly below it otherwise (tucked under the cuff), at rest and in every drawOrder key
        self.hand_over = ann is not None and ann.master.layers.get("hand") == "over_forearm"
        # worn items (annotations): a foot drawn over the leg/hips is cut at its ankle opening (rig_worn) into a shell,
        # in its own slot, and a back part (the inside and the back half of the rim) in slot <foot>_back on the same
        # bone, drawn behind the leg/hips; its variants are cut the same way and the back slot swaps with the shell.
        self.worn, self.worn_report = {}, {}     # foot slot -> {"slot": back slot, "atts": {shell att: back att}}
        if ann is not None:
            import rig_place
            self.worn_ok = rig_worn.feet_worn(ann, rig_place.has_legs(ann))
        else:
            self.worn_ok = False

    def region_att(self, n: str, pc: dict, img) -> dict:
        """Region attachment of piece record pc (spine_rig.main's pieces) with image img, on bone n."""
        (bx, by), brot = self.world[n]
        cx, cy = self.units((pc["cx"], pc["cy"]))
        dx, dy = cx - bx, cy - by
        c_, s_ = math.cos(math.radians(-brot)), math.sin(math.radians(-brot))
        return {"x": round(dx * c_ - dy * s_, 2), "y": round(dx * s_ + dy * c_, 2), "scaleX": round(pc["unit"], 4),
                "scaleY": round(pc.get("unit_y", pc["unit"]), 4), "rotation": round(pc["angle"] - brot, 2),
                "width": img.width, "height": img.height}

    def layer_key(self, n, mesh_layer="arm"):
        """Sort key of piece n's slot, back to front."""
        pieces, layers, hand_over = self.pieces, self.layers, self.hand_over
        owner = self.patches.get(n, n)
        # a sleeve mesh (rig_mesh) in the upper arm's slot is drawn at the upper arm's layer (master.layers: under the
        # torso with upperarm under_torso, so straps and vests cover its top); holds whose forearm crosses the body
        # move it up with a drawOrder key (rig_anim.crossing_offsets). mesh_layer: the layer to sort it at.
        lay = mesh_layer if "mesh" in pieces.get(owner, {}) else role(owner, self.roles)[1]
        sleeve = f"upperarm_{owner[-1]}" if role(owner, self.roles)[1] == "hand" and re.search(r"_(l|r)$", owner) else ""
        if "mesh" in pieces.get(sleeve, {}):                     # just above / below its sleeve (hand_over)
            return (layers.index(mesh_layer), False, sleeve, False, 1 if hand_over else -1)
        # annotations: what hangs on the neckwear (a bell) is drawn with it, just above it, so an arm crossing the
        # chest (drawn above the neckwear, rig_place.apply_layers) passes in front of both
        hung = self.ann is not None and lay == "front" and role(owner, self.roles)[0] == "neckwear"
        return (layers.index("neckwear" if hung else lay), hung, owner, n.endswith("_patch"), 0)

    def worn_cut(self, slot: str, out_name: str, att: str, img):
        """The image to save for attachment `att` of `slot`: its shell when it is cut (the back part is saved and
        registered as <att>_back), else img itself."""
        ann, worn, doubts = self.ann, self.worn, self.doubts
        op = rig_worn.opening(ann, out_name) if self.worn_ok else None
        if op is None or (slot not in worn and att != f"{self.prefix}{slot}"):
            return img
        at, width, depth = op
        if not width:
            doubts.append({"part": out_name, "reason": "worn_no_width"})
            print(f"  ? doubt: {out_name}: no ankle opening width; drawn whole, not cut into a back and a shell")
            return img
        shell, back, info = rig_worn.split(img, at, width, depth)
        if info["method"] == "ellipse":           # no painted inside found: the cut is the snapped opening's ellipse
            doubts.append({"part": out_name, "reason": "worn_opening_guessed", "ellipse": info["ellipse"]})
            print(f"  ? doubt: {out_name}: no painted inside in the ankle opening; cut at the opening's ellipse "
                  f"{info['ellipse']} (check the front lip stays in front of the leg)")
        w_ = worn.setdefault(slot, {"slot": f"{slot}_back", "atts": {}})
        w_["atts"][att] = f"{att}_back"
        back.save(self.out / "images" / f"{att}_back.png")
        self.images.append(f"{att}_back")
        self.worn_report.setdefault(slot, {"back_slot": w_["slot"], "attachments": {}})["attachments"][att] = info
        return shell

    def write_parts(self):
        """A slot and rest attachment per piece, back to front, and the worn back slots just below the legs (or the
        hips, without legs)."""
        pieces, prefix, slots, skin, worn = self.pieces, self.prefix, self.slots, self.skin, self.worn
        for n in sorted(pieces, key=self.layer_key):
            if "mesh_of" in pieces[n]:                # a sleeve mesh's forearm half: drawn by its upper arm's slot
                continue
            mesh = pieces[n].get("mesh")
            att = f"{prefix}{mesh['arm']}" if mesh else f"{prefix}{n}"
            self.worn_cut(n, n, att, pieces[n]["img"]).save(self.out / "images" / f"{att}.png")
            self.images.append(att)
            bone = self.patches.get(n, n)
            slot = "head" if n == "head_base" else n
            slots.append({"name": slot, "bone": bone, "attachment": att})
            # a mesh is written once the animations say how far its elbow bends (rig_sleeves)
            skin[slot] = {att: {} if mesh else self.region_att(bone, pieces[n], pieces[n]["img"])}
            if slot in worn:
                skin[worn[slot]["slot"]] = {f"{att}_back": dict(skin[slot][att])}
        if worn:
            under = "leg" if any(role(n_, self.roles)[1] == "leg" for n_ in pieces) else "hips"
            at_ = next((i for i, s_ in enumerate(slots) if role(s_["bone"], self.roles)[1] == under),
                       min(i for i, s_ in enumerate(slots) if s_["name"] in worn))
            for k_, (sl_, w_) in enumerate(sorted(worn.items(), key=lambda kv: [s_["name"] for s_ in slots].index(kv[0]))):
                slots.insert(at_ + k_, {"name": w_["slot"], "bone": sl_, "attachment": w_["atts"][f"{prefix}{sl_}"]})

    def add_heads(self, heads: list, head_pc: dict | None, trust: int | None):
        """The expression heads (PNG paths) as attachments of the head slot, placed like the matched reference head
        (head_pc); the neutral one shown at rest. trust: solidify's edge trust."""
        from PIL import Image
        if not (heads and "head_base" in self.pieces):
            return
        for f in heads:
            img = solidify(Image.open(f), trust)
            img.save(self.out / "images" / f"{f.stem}.png")
            self.images.append(f.stem)
            self.skin["head"][f.stem] = self.region_att("head_base", head_pc, img)
        if f"{self.prefix}head_neutral" in self.skin["head"]:
            next(s_ for s_ in self.slots if s_["name"] == "head")["attachment"] = f"{self.prefix}head_neutral"

    def sync_worn(self, anims: dict):
        """Key each back slot's swaps in sync with its shell's (None: that variant is drawn whole), and its fades
        (rgba keys: the legs cross-fades, rig_anim.cross_fade)."""
        for slot_, w_ in self.worn.items():
            for anim_ in anims.values():
                keys_ = anim_.get("slots", {}).get(slot_, {}).get("attachment")
                if keys_:
                    anim_["slots"][w_["slot"]] = {"attachment": [{"time": k_["time"], "name": w_["atts"].get(k_["name"])}
                                                                 for k_ in keys_]}
                    if "rgba" in anim_["slots"][slot_]:
                        anim_["slots"][w_["slot"]]["rgba"] = [dict(k_) for k_ in anim_["slots"][slot_]["rgba"]]
