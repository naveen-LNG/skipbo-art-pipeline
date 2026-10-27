"""Draft annotations for the moose: meaning and rough points read by eye off gridded views of each split piece.
Writes annotations.json with every used piece `proposed` (the checkpoints confirm them) and every spare piece `ignored`.
Points are 0..1 of each image. _l = the character's left = the picture's right."""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
A, B, H, P, F = "moose-body-a-parts", "moose-body-b-parts", "moose-hands-parts", "moose-poses-parts", "face-heads"


def piece(role, side, pts, *, name=None, variant=None, facing=None, conf=0.8, note="", painted_as=None, mirror=False):
    d = {"role": role, "side": side, "status": "proposed", "confidence": conf,
         "points": {k: {"at": list(v)} for k, v in pts.items()}}
    for k, v in (("name", name), ("variant", variant), ("facing", facing), ("note", note), ("painted_as", painted_as), ("mirror", mirror)):
        if v:
            d[k] = v
    return d


pieces = {
    f"{A}/12": piece("torso", "", {"neck": (0.50, 0.20), "waist": (0.50, 0.94), "shoulder_l": (0.86, 0.17), "shoulder_r": (0.14, 0.17)},
                     note="neck = base of the neck stub; waist = centre of the belt buckle; shoulder points sit under the vest where the hidden sleeve top joins (the cream shoulder caps are painted on the torso)"),
    f"{A}/10": piece("hips", "", {"waist": (0.50, 0.24), "hip_l": (0.79, 0.95), "hip_r": (0.21, 0.95)},
                     note="waist = belt buckle; hip points = the trouser leg openings"),
    f"{A}/00": piece("foot", "l", {"ankle": (0.50, 0.04), "ground": (0.55, 0.97)}, name="hoof",
                     note="hoof with its painted trouser cuff; the cuff top is the opening"),
    f"{A}/01": piece("foot", "r", {"ankle": (0.50, 0.04), "ground": (0.45, 0.97)}, name="hoof"),
    f"{A}/05": piece("hand", "l", {"wrist": (0.40, 0.06), "thumb_tip": (0.95, 0.52), "fingertip": (0.55, 0.97)}, facing="palm",
                     note="fur cuff at the wrist"),
    f"{A}/06": piece("hand", "r", {"wrist": (0.60, 0.06), "thumb_tip": (0.05, 0.50), "fingertip": (0.45, 0.97)}, facing="palm"),
    f"{A}/09": piece("prop", "", {"root": (0.50, 0.08)}, name="bell", note="hangs from the scarf by its loop"),
    f"{A}/11": piece("neckwear", "", {"neck": (0.45, 0.25)}, name="scarf"),
    f"{A}/13": piece("ear", "l", {"root": (0.08, 0.50)}),
    f"{A}/14": piece("ear", "r", {"root": (0.08, 0.50)}, mirror=True, note="painted pointing right like the left ear; mirrored"),
    f"{A}/15": piece("hat", "", {"root": (0.50, 0.95)}, name="cap"),
    f"{A}/16": piece("head", "", {"neck": (0.50, 0.97)}),
    f"{A}/17": piece("antler", "r", {"root": (0.93, 0.85)}),
    f"{A}/18": piece("antler", "l", {"root": (0.05, 0.85)}),
    f"{B}/08": piece("upperarm", "either", {"shoulder": (0.33, 0.22), "elbow": (0.66, 0.78)}, painted_as="l"),
    f"{B}/06": piece("forearm", "l", {"elbow": (0.26, 0.24), "wrist": (0.62, 0.72)}, note="wrist = the cuff end; fur tufts below it"),
    f"{B}/07": piece("forearm", "r", {"elbow": (0.70, 0.24), "wrist": (0.38, 0.72)}),
    # hands sheet: painted once each, mirrored per side by the thumb rule
    f"{H}/10": piece("hand", "either", {"wrist": (0.50, 0.97), "thumb_tip": (0.97, 0.42), "fingertip": (0.45, 0.03)}, variant="open", facing="palm",
                     note="painted wrist down"),
    f"{H}/00": piece("hand", "either", {"wrist": (0.50, 0.04), "thumb_tip": (0.90, 0.60)}, variant="fist", facing="back", conf=0.5,
                     note="thumb tip hard to see on the fist"),
    f"{H}/04": piece("hand", "either", {"wrist": (0.50, 0.04), "thumb_tip": (0.05, 0.57), "fingertip": (0.42, 0.97)}, variant="point", facing="back"),
    f"{H}/02": piece("hand", "either", {"wrist": (0.55, 0.04), "thumb_tip": (0.05, 0.40), "fingertip": (0.30, 0.90)}, variant="grip", facing="back",
                     conf=0.5, note="which curl is the thumb is unclear"),
    f"{H}/05": piece("hand", "either", {"wrist": (0.97, 0.55), "thumb_tip": (0.48, 0.03)}, variant="thumbsup", facing="palm",
                     note="painted with the wrist at the right side"),
    # raised sleeves and tiptoe hoof
    f"{P}/06": piece("upperarm", "l", {"shoulder": (0.50, 0.22), "elbow": (0.50, 0.82)}, variant="raised"),
    f"{P}/07": piece("upperarm", "r", {"shoulder": (0.50, 0.22), "elbow": (0.50, 0.82)}, variant="raised"),
    f"{P}/02": piece("foot", "either", {"ankle": (0.50, 0.04), "ground": (0.55, 0.97)}, name="hoof", variant="tiptoe", painted_as="l"),
}
for i, expr in enumerate(["angry", "blink", "happy", "laugh", "neutral", "sad", "surprised", "talking", "wink"]):
    pieces[f"{F}/{i:02d}"] = piece("head", "", {"neck": (0.50, 0.96)}, variant=expr, conf=0.7)

LEG_NOTE = ("the hips piece and the hoof cuffs cover the whole trouser leg in the master, so the leg tube has no visible span: "
            "using it pokes out round the hooves (the old brown filler)")
for run in (A, B, H, P):
    for f in sorted((HERE / "runs" / run).glob("*_[0-9][0-9].png")):
        key = f"{run}/{re.search(r'_(\d\d)\.png$', f.name).group(1)}"
        if key not in pieces:
            leg = run == A and key.endswith(("/02", "/03"))
            pieces[key] = {"role": "leg" if leg else "", "side": ("l" if key.endswith("/02") else "r") if leg else "",
                           "status": "ignored", "confidence": 0, "points": {},
                           "note": LEG_NOTE if leg else "spare piece from the sheet, not used by the rig"}

master = {
    "image": "master.png", "status": "proposed",
    "points": {"neck": [0.50, 0.45], "waist": [0.50, 0.69], "ground": [0.50, 0.935],
               "shoulder_l": [0.638, 0.439], "shoulder_r": [0.362, 0.439], "elbow_l": [0.741, 0.539], "elbow_r": [0.259, 0.539],
               "wrist_l": [0.82, 0.615], "wrist_r": [0.18, 0.615], "fingertip_l": [0.875, 0.695], "fingertip_r": [0.125, 0.695],
               "hip_l": [0.585, 0.86], "hip_r": [0.415, 0.86], "ankle_l": [0.61, 0.76], "ankle_r": [0.39, 0.76]},
    "hands": {"l": {"thumb_side": "lateral", "facing": "palm"}, "r": {"thumb_side": "lateral", "facing": "palm"}},
    "layers": {"upperarm": "under_torso", "foot": "under_hips", "hand": "under_forearm"},
}
(HERE / "annotations.json").write_text(json.dumps({"version": 1, "character": "moose", "master": master, "pieces": pieces},
                                                   indent=2, sort_keys=True) + "\n")
print(HERE / "annotations.json", len(pieces), "pieces")
