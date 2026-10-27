"""Draft annotations for the fox: meaning and rough points read by eye off gridded views of each split piece.
Writes annotations.json with every piece `proposed`; the checkpoints confirm them. Points are 0..1 of each image.
_l = the character's left = the picture's right."""
import json
from pathlib import Path

HERE = Path(__file__).parent
B, H, A, P, F = "fox-body-v2-parts", "fox-hands-parts", "fox-arms-parts", "fox-poses-parts", "face-heads"


def piece(role, side, pts, *, name=None, variant=None, facing=None, conf=0.8, note="", painted_as=None):
    d = {"role": role, "side": side, "status": "proposed", "confidence": conf,
         "points": {k: {"at": list(v)} for k, v in pts.items()}}
    for k, v in (("name", name), ("variant", variant), ("facing", facing), ("note", note), ("painted_as", painted_as)):
        if v:
            d[k] = v
    return d


LEG_NOTE = ("the dungaree leg tubes of the hips piece run from the crotch into the boots, so the separate leg has no visible span "
            "(61 px in the master against a 445 px painted leg): using it left blue leg showing beside the boots")

pieces = {
    f"{B}/12": piece("torso", "", {"neck": (0.50, 0.24), "waist": (0.50, 0.97), "shoulder_l": (0.95, 0.22), "shoulder_r": (0.05, 0.22)},
                     note="neck = top of the purple collar; waist = bottom of the bib"),
    f"{B}/11": piece("hips", "", {"waist": (0.50, 0.55), "hip_l": (0.79, 0.97), "hip_r": (0.21, 0.97)},
                     conf=0.6, note="waist = the point at the bottom of the bib in the master; hip points = the dungaree leg openings, which sit inside the boots"),
    f"{B}/09": piece("upperarm", "l", {"shoulder": (0.33, 0.27), "elbow": (0.62, 0.72)}),
    f"{B}/10": piece("upperarm", "r", {"shoulder": (0.67, 0.27), "elbow": (0.375, 0.72)}),
    f"{B}/07": piece("forearm", "l", {"elbow": (0.44, 0.29), "wrist": (0.50, 0.97)}),
    f"{B}/08": piece("forearm", "r", {"elbow": (0.56, 0.29), "wrist": (0.50, 0.97)}),
    f"{B}/05": piece("hand", "l", {"wrist": (0.55, 0.06), "thumb_tip": (0.93, 0.55), "fingertip": (0.45, 0.97)}, facing="back"),
    f"{B}/06": piece("hand", "r", {"wrist": (0.55, 0.06), "thumb_tip": (0.93, 0.53), "fingertip": (0.45, 0.95)}, facing="back"),
    f"{B}/02": {"role": "leg", "side": "l", "status": "ignored", "confidence": 0, "points": {}, "note": LEG_NOTE},
    f"{B}/03": {"role": "leg", "side": "r", "status": "ignored", "confidence": 0, "points": {}, "note": LEG_NOTE},
    f"{B}/00": piece("foot", "l", {"ankle": (0.45, 0.07), "ground": (0.50, 0.97)}, name="boot", note="toe points right = outwards for the left foot"),
    f"{B}/01": piece("foot", "r", {"ankle": (0.55, 0.07), "ground": (0.50, 0.97)}, name="boot", note="toe points left = outwards for the right foot"),
    f"{B}/04": piece("tail", "", {"root": (0.04, 0.35)}),
    f"{B}/13": piece("ear", "l", {"root": (0.40, 0.85)}, conf=0.6, note="likely dropped: the expression heads include the ears"),
    f"{B}/14": piece("ear", "r", {"root": (0.60, 0.85)}, conf=0.6, note="likely dropped: the expression heads include the ears"),
    f"{B}/15": piece("head", "", {"neck": (0.50, 0.95)}),
    # hands sheet: painted once each, mirrored per side by the thumb rule
    f"{H}/10": piece("hand", "either", {"wrist": (0.50, 0.03), "thumb_tip": (0.97, 0.52), "fingertip": (0.45, 0.97)}, variant="open", facing="back"),
    f"{H}/09": piece("hand", "either", {"wrist": (0.55, 0.03), "thumb_tip": (0.88, 0.70)}, variant="fist", facing="back", conf=0.6,
                     note="thumb wraps the front of the fist; tip hard to see"),
    f"{H}/05": piece("hand", "either", {"wrist": (0.50, 0.03), "thumb_tip": (0.95, 0.58), "fingertip": (0.55, 0.97)}, variant="point", facing="back"),
    f"{H}/04": piece("hand", "either", {"wrist": (0.70, 0.03), "thumb_tip": (0.05, 0.42), "fingertip": (0.20, 0.90)}, variant="grip", facing="back",
                     conf=0.5, note="which curl is the thumb is unclear"),
    f"{H}/01": piece("hand", "either", {"wrist": (0.97, 0.62), "thumb_tip": (0.48, 0.03)}, variant="thumbsup", facing="palm",
                     note="painted with the wrist at the right side"),
    # raised sleeve, tiptoe boot, tail up
    f"{A}/02": piece("upperarm", "either", {"shoulder": (0.51, 0.23), "elbow": (0.36, 0.83)}, variant="raised", painted_as="l"),
    f"{P}/04": piece("foot", "either", {"ankle": (0.35, 0.06), "ground": (0.55, 0.97)}, name="boot", variant="tiptoe", painted_as="l",
                     conf=0.6, note="toe right = left foot"),
    f"{P}/01": piece("tail", "", {"root": (0.03, 0.62)}, variant="up"),
}
for i, expr in enumerate(["angry", "blink", "happy", "laugh", "neutral", "sad", "surprised", "talking", "wink"]):
    pieces[f"{F}/{i:02d}"] = piece("head", "", {"neck": (0.50, 0.96)}, variant=expr, conf=0.7)

for run in (B, H, A, P):          # every other piece on the sheets is a spare (duplicates, superseded sleeves)
    for f in sorted((HERE / "runs" / run).glob("*_[0-9][0-9].png")):
        key = f"{run}/{f.stem[-2:]}"
        if key not in pieces:
            pieces[key] = {"role": "", "side": "", "status": "ignored", "confidence": 0, "points": {},
                           "note": "spare piece from the sheet, not used by the rig"}

master = {
    "image": "master.png", "status": "proposed",
    "points": {"neck": [0.50, 0.452], "waist": [0.50, 0.735], "ground": [0.50, 0.94],
               "shoulder_l": [0.625, 0.455], "shoulder_r": [0.375, 0.455], "elbow_l": [0.72, 0.53], "elbow_r": [0.28, 0.53],
               "wrist_l": [0.795, 0.605], "wrist_r": [0.205, 0.605], "fingertip_l": [0.86, 0.69], "fingertip_r": [0.14, 0.69],
               "hip_l": [0.585, 0.85], "hip_r": [0.415, 0.85], "ankle_l": [0.59, 0.82], "ankle_r": [0.41, 0.82]},
    "hands": {"l": {"thumb_side": "medial", "facing": "back"}, "r": {"thumb_side": "medial", "facing": "back"}},
    "layers": {"upperarm": "under_torso", "foot": "over_hips"},
}
(HERE / "annotations.json").write_text(json.dumps({"version": 1, "character": "fox", "master": master, "pieces": pieces},
                                                   indent=2, sort_keys=True) + "\n")
print(HERE / "annotations.json", len(pieces), "pieces")
