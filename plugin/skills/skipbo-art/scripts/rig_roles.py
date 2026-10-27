"""rig_roles.py - what a part is: its bone's parent role and its draw layer (role), and the draw order of the layers
(LAYERS, back to front).

A part's role comes from the annotations when there are any (ann_roles: a hat named "beanie" is a hat), else it is
guessed from its name (role_from_name). Part names follow <part>[_l|_r] without the character prefix; _l = the
character's left = the picture's right.
"""
from __future__ import annotations

import re


# --annotations: (bone parent role, draw layer) of each annotated role (rig_annotations.ROLES). A part's role comes
# from the annotations, not from its name, so a hat named "beanie", feet named "sneaker" and neckwear named "neckwear"
# are a hat, feet and neckwear. A prop hangs from the neckwear when its name says it does (bell, medal, pendant,
# badge: role_from_name), else from the torso.
ROLE_SLOTS = {
    "torso": ("hips", "torso"), "hips": ("root", "hips"), "head": ("torso", "head"), "hat": ("head", "hat"),
    "ear": ("head", "back"), "antler": ("head", "back"), "horn": ("head", "back"), "neckwear": ("torso", "neckwear"),
    "upperarm": ("torso", "arm"), "arm": ("torso", "arm"), "forearm": ("upperarm", "forearm"),
    "hand": ("forearm", "hand"), "leg": ("hips", "leg"), "foot": ("leg", "foot"), "tail": ("hips", "back"),
    "prop": ("torso", "front"),
    "legs": ("hips", "hips"),   # whole-legs poses: their own slot just above the trousers (rig_variants.add_legs)
}


def ann_roles(ann) -> dict | None:
    """Part name -> annotated role (rig_place.output_roles) for annotations `ann`; None for a legacy build."""
    if ann is None:
        return None
    import rig_place
    return rig_place.output_roles(ann)


def annotated_role(part: str, roles: dict | None):
    """The annotated role of part `part` (an output name: hand_l, sneaker_r, head_base, tail_up), or None without
    annotations or when no output has that name (then the name decides: role_from_name).
    roles: output name -> annotated role (ann_roles)."""
    if not roles:
        return None
    return roles.get(part) or roles.get(re.sub(r"_(l|r)$", "", part))


def role(part: str, roles: dict | None = None) -> tuple[str, str]:
    """(bone parent role, draw layer) for a part name without the character prefix: from its annotated role when
    `roles` (ann_roles) knows it, else guessed from the name (role_from_name; legacy builds)."""
    r = annotated_role(part, roles)
    if r is None:
        return role_from_name(part)
    if r == "prop" and role_from_name(part)[0] == "neckwear":
        return "neckwear", "front"
    return ROLE_SLOTS[r]


def is_role(part: str, roles: dict | None, want: str, names: tuple) -> bool:
    """Whether part is a `want` (tail, ear, foot...): its annotated role, else its name without the side in `names`."""
    r = annotated_role(part, roles)
    return r == want if r is not None else re.sub(r"_(l|r)$", "", part) in names


def headgear(n: str, roles: dict | None) -> bool:
    """Ears, antlers and horns (they sway in the idle): annotated role, else a back-layer part named so."""
    r_ = annotated_role(n, roles)
    return r_ in ("ear", "antler", "horn") if r_ is not None else \
        bool(role(n)[1] == "back" and re.search(r"antler|horn|ear", n))


def soft_kind(n: str, roles: dict | None) -> str | None:
    """"tail" or "ear" for the parts that follow through in the cheer jump (annotated role, else the name)."""
    r_ = annotated_role(n, roles)
    if r_ is not None:
        return r_ if r_ in ("tail", "ear") else None
    base_ = re.sub(r"_(l|r)$", "", n)
    return "tail" if base_ == "tail" else "ear" if base_ in ("ear", "ears") else None


def foot_of(side: str, pieces, roles: dict | None) -> str | None:
    """The foot piece on a side: annotated role foot (any name), else named hoof, foot, shoe or boot."""
    if roles:
        return next((n for n in pieces if annotated_role(n, roles) == "foot" and n.endswith(f"_{side}")), None)
    return next((f"{f_}_{side}" for f_ in ("hoof", "foot", "shoe", "boot") if f"{f_}_{side}" in pieces), None)


def role_from_name(part: str) -> tuple[str, str]:
    """(bone parent role, draw layer) for a part name without the character prefix, guessed from its name's tokens."""
    p = re.sub(r"_(l|r)$", "", part)
    tokens = set(p.split("_"))

    def has(*words: str) -> bool:
        return any(w in tokens for w in words)

    if has("hips", "pelvis", "waist"):
        return "root", "hips"
    if p == "torso" or has("chest", "body"):
        return "hips", "torso"
    if p in ("head_base", "head"):
        return "torso", "head"
    if has("cap", "hat", "helmet", "crown", "beret", "hood"):
        return "head", "hat"
    if has("antler", "antlers", "horn", "horns", "ear", "ears"):
        return "head", "back"
    if has("hair", "tuft", "fringe", "bun"):
        return "head", "hat"
    if has("scarf", "collar", "tie", "necklace", "bowtie", "neckerchief"):
        return "torso", "neckwear"
    if has("bell", "medal", "pendant", "badge"):
        return "neckwear", "front"
    if has("upperarm"):
        return "torso", "arm"
    if has("forearm"):
        return "upperarm", "forearm"
    if has("hand", "paw", "mitten", "glove"):
        return "forearm", "hand"
    if has("leg", "thigh"):
        return "hips", "leg"
    if has("hoof", "foot", "shoe", "boot", "feet"):
        return "leg", "foot"
    if has("tail"):
        return "hips", "back"
    return "torso", "front"  # props


# draw order, back to front. Generated parts: tails and ears behind everything, so a tail always passes behind the legs;
# arms in front of the torso, each round sleeve top sitting over the rounded shoulder, hand tucked under its cuff.
LAYERS = ["back", "leg", "foot", "hips", "torso", "hand", "forearm", "arm", "neckwear", "head", "hat", "front"]
LAYERS_MASTER_CUT = ["back", "leg", "foot", "hips", "arm", "forearm", "hand", "torso", "neckwear", "head", "hat", "front"]
LIMBS = {"arm", "forearm", "hand", "leg", "foot", "back"}  # rotation search + axis-aligned bones
