"""Draft annotations for the beaver: meaning and rough points read by eye off gridded views of each split piece
(scripts/grid_pieces.py) and the gridded master. Sheet positions (scripts/locate.py) give the sides: on the body sheet
the picture-left column is the character's right. Writes annotations.json with every piece `proposed`; the checkpoints
confirm them. Points are 0..1 of each image. _l = the character's left = the picture's right."""
import json
from pathlib import Path

HERE = Path(__file__).parent
B, H, P, F = "beaver-body-parts", "beaver-hands-parts", "beaver-poses-parts", "beaver-face-parts"
PP = "beaver-point-palm-parts"
SL, FP, TR, TL = "beaver-sleeves3-parts", "beaver-fist-palm-parts", "beaver-trousers-parts", "beaver-tail-parts"
ROUND3 = ("round 3 (user review + Jev joint audit against the master): whole sleeves replace the stuck-on two-piece "
          "arms, a palm-facing fist replaces the back-facing one (cheer showed the back of the fists), one trousers "
          "piece with cuffs keeps the boots under the cuffs, the tail is repainted as the master holds it")


def piece(role, side, pts, *, name=None, variant=None, facing=None, conf=0.8, note="", painted_as=None):
    d = {"role": role, "side": side, "status": "proposed", "confidence": conf,
         "points": {k: {"at": list(v)} for k, v in pts.items()}}
    for k, v in (("name", name), ("variant", variant), ("facing", facing), ("note", note), ("painted_as", painted_as)):
        if v:
            d[k] = v
    return d


LEG_NOTE = ("the hips piece was painted as long shorts whose leg openings already reach the master's hem (the rig needed a "
            "0.57 squash on the separate legs); the boots go under the hips' openings instead, as on the moose")
ROUND1 = ("round 1 (rig QA): the arm pieces are ~1.3x the master's arm, so the shoulders moved in and up and the elbows sit at "
          "the pieces' upper-arm share (0.47) of shoulder->wrist; the boots tuck under the trouser openings")

pieces = {
    f"{B}/12": piece("torso", "", {"neck": (0.50, 0.20), "waist": (0.50, 0.95)}, note="neck = base of the fur neck in the collar; waist = just above the sweater hem, so the hem overlaps the belt"),
    f"{B}/11": {"role": "hips", "status": "ignored", "confidence": 0, "points": {}, "note": ROUND3 + ": long shorts, replaced by the trousers piece"},
    f"{TR}/00": piece("hips", "", {"waist": (0.50, 0.11), "hip_l": (0.743, 0.98), "hip_r": (0.266, 0.98)},
                      note="composite (make_trousers.py): belt-to-crotch hips over the cuffed legs; openings at the cuffs"),
    f"{SL}/01": piece("arm", "either", {"shoulder": (0.621, 0.08), "elbow": (0.568, 0.52), "wrist": (0.52, 0.97)},   # round 6: sleeves2/01 widened (make_sleeve_wide.py)
                      painted_as="l", note="whole sleeve, both sides (the right is its mirror: piece 00 fitted 118 px off the master's right sleeve); points at the measured centres of its top and cuff; elbow at the master's elbow ratio (0.495)"),
    f"{B}/02": piece("hand", "l", {"wrist": (0.55, 0.07), "thumb_tip": (0.05, 0.55), "fingertip": (0.60, 0.97)}, facing="back",
                     conf=0.7, note="mitten, thumb toward the body as in the master"),
    f"{B}/03": piece("hand", "r", {"wrist": (0.45, 0.07), "thumb_tip": (0.95, 0.55), "fingertip": (0.40, 0.97)}, facing="back",
                     conf=0.7, note="mitten, thumb toward the body as in the master"),
    f"{B}/04": {"role": "leg", "side": "l", "status": "ignored", "confidence": 0, "points": {}, "note": LEG_NOTE},
    f"{B}/05": {"role": "leg", "side": "r", "status": "ignored", "confidence": 0, "points": {}, "note": LEG_NOTE},
    f"{B}/00": piece("foot", "l", {"ankle": (0.41, 0.10), "ground": (0.50, 0.97)}, name="boot", note="toe right = outward for the left foot"),
    f"{B}/01": piece("foot", "r", {"ankle": (0.59, 0.10), "ground": (0.50, 0.97)}, name="boot", note="toe left = outward for the right foot"),
    f"{TL}/16": piece("tail", "", {"root": (0.90, 0.15)}, note="repainted as the master holds it: root upper right, paddle lower left"),
    f"{B}/13": piece("ear", "l", {"root": (0.35, 0.85)}, conf=0.6, note="likely dropped: the expression heads include the ears"),
    f"{B}/14": piece("ear", "r", {"root": (0.65, 0.85)}, conf=0.6, note="likely dropped: the expression heads include the ears"),
    f"{B}/15": piece("head", "", {"neck": (0.50, 0.97)}),
    # hands sheet, row 1 (the character's left hand); row 2 repeats row 1 unmirrored, so it is spare
    f"{H}/11": piece("hand", "either", {"wrist": (0.45, 0.06), "thumb_tip": (0.95, 0.45), "fingertip": (0.45, 0.97)}, variant="open",
                     facing="palm", conf=0.7, note="palm pad visible; prompted palm-facing"),
    f"{FP}/00": piece("hand", "either", {"wrist": (0.50, 0.05), "thumb_tip": (0.85, 0.68)}, variant="fist", facing="palm", conf=0.8,
                      note="palm-facing fist; Jev cue score -0.049 (palm band), thumb to the right (Jev: right)"),
    f"{H}/09": {"role": "hand", "side": "either", "variant": "point", "status": "ignored", "confidence": 0, "points": {},
                "note": "round 2: back-facing, so the rig pointed it across the chest, where Jev read it as a grip and it hid "
                        "against the sweater; replaced by the palm-facing point from beaver-point-palm-parts/02"},
    f"{PP}/02": piece("hand", "either", {"wrist": (0.68, 0.04), "thumb_tip": (0.02, 0.40), "fingertip": (0.44, 0.98)}, variant="point",
                      facing="palm", conf=0.8, note="palm-facing point (curled fingertips on the palm show): points outward"),
    f"{H}/10": piece("hand", "either", {"wrist": (0.40, 0.05), "thumb_tip": (0.12, 0.45), "fingertip": (0.30, 0.95)}, variant="grip",
                     facing="back", conf=0.4, note="three-quarter view; which curl is the thumb is unclear"),
    f"{H}/06": piece("hand", "either", {"wrist": (0.04, 0.65), "thumb_tip": (0.50, 0.04)}, variant="thumbsup", facing="palm", conf=0.7,
                     note="painted with the wrist at the left side; curled fingers' fronts show"),
    # poses sheet: tiptoe boots are both painted as the left foot (toe right); the arm row came back as whole sleeves
    f"{P}/04": piece("foot", "either", {"ankle": (0.62, 0.17), "ground": (0.80, 0.97)}, name="boot", variant="tiptoe", painted_as="l",
                     conf=0.6, note="a tilted boot rather than toe-down; toe right = left foot"),
}
for i, expr in enumerate(["angry", "wink", "talking", "sad", "surprised", "laugh", "happy", "blink", "neutral"]):
    pieces[f"{F}/{i:02d}"] = piece("head", "", {"neck": (0.50, 0.97)}, variant=expr, conf=0.8)

for run in (B, H, P, PP, SL, FP, TR, TL):             # every other piece on the sheets is a spare
    for f in sorted((HERE / "runs" / run).glob("*_[0-9][0-9].png")):
        key = f"{run}/{f.stem[-2:]}"
        if key not in pieces:
            pieces[key] = {"role": "", "side": "", "status": "ignored", "confidence": 0, "points": {},
                           "note": "spare piece from the sheet, not used by the rig (unmirrored row-2 hand, duplicate boot, "
                                   "whole sleeve or superseded tail)"}

master = {
    "image": "beaver_master.png", "status": "proposed",
    "points": {"neck": [0.50, 0.355], "waist": [0.50, 0.60], "ground": [0.50, 0.875],
               "shoulder_l": [0.645, 0.405], "shoulder_r": [0.355, 0.405], "elbow_l": [0.745, 0.475], "elbow_r": [0.255, 0.475],
               "wrist_l": [0.842, 0.548], "wrist_r": [0.158, 0.548], "fingertip_l": [0.901, 0.621], "fingertip_r": [0.099, 0.621],
               "hip_l": [0.618, 0.805], "hip_r": [0.392, 0.805], "ankle_l": [0.600, 0.772], "ankle_r": [0.408, 0.772]},
    "hands": {"l": {"thumb_side": "medial", "facing": "back"}, "r": {"thumb_side": "medial", "facing": "back"}},
    "layers": {"upperarm": "under_torso"},
}
ann = HERE / "annotations.json"
old = json.loads(ann.read_text()) if ann.exists() else {}
(ann).write_text(json.dumps({"version": old.get("version", 1), "character": "beaver", "master": master, "pieces": pieces},
                            indent=2, sort_keys=True) + "\n")
print(ann, len(pieces), "pieces")
