"""Draft annotations for the rabbit: meaning and rough points read by eye off gridded views of each split piece
(tools/grid_pieces.py) and the gridded master (tools/grid_image.py). Sheet positions (tools/locate.py) give the sides:
on the body sheet the picture-left column is the character's right. Writes annotations.json with every piece
`proposed`; rebuild.sh then marks the self-reviewed ones confirmed or fixed. Points are 0..1 of each image.
_l = the character's left = the picture's right."""
import json
from pathlib import Path

HERE = Path(__file__).parent
B, H, F, SL = "rabbit-body-parts", "rabbit-hands-parts", "rabbit-face-parts", "rabbit-sleeves-parts"
PP = "rabbit-point-palm-parts"
TO, TR, EA = "rabbit-torso-parts", "rabbit-trousers-parts", "rabbit-ears-parts"   # make_torso.py, make_trousers.py (round 2)
SLW = "rabbit-sleeves-wide-parts"           # make_sleeve_wide.py output (round 1+)


def piece(role, side, pts, *, name=None, variant=None, facing=None, conf=0.8, note="", painted_as=None, mirror=None):
    d = {"role": role, "side": side, "status": "proposed", "confidence": conf,
         "points": {k: {"at": list(v)} for k, v in pts.items()}}
    for k, v in (("name", name), ("variant", variant), ("facing", facing), ("note", note), ("painted_as", painted_as),
                 ("mirror", mirror)):
        if v:
            d[k] = v
    return d


SPARE_ARM = ("two-piece arm spare: the rig uses one whole sleeve per arm (sleeves-pair.txt); kept as the fallback if the "
             "short, fat sleeve mesh folds")
pieces = {
    f"{TO}/00": piece("torso", "", {"neck": (0.50, 0.22), "waist": (0.50, 0.72)},
                     note="body-sheet torso 12 made symmetric (its picture-left armhole was open); neck = top of the green collar; waist at 0.72 so neck-to-waist gives the global scale the torso and trouser widths need (1.35, round 1)"),
    f"{TR}/00": piece("hips", "", {"waist": (0.577, 0.226), "hip_l": (0.787, 0.96), "hip_r": (0.36, 0.96)},
                     note="body-sheet trousers 11 with both legs (no leg pieces), openings filled with cloth, legs narrowed 0.92 at the hems and the cotton tail painted in behind the right hip (make_trousers.py); the leg ends go into the boots (foot: over_hips)"),
    f"{B}/10": {"role": "tail", "side": "", "status": "ignored", "confidence": 0, "points": {},
                "note": "round 6: painted into the trousers piece (make_trousers.py). The matcher put the ball on the cheek, the paw, "
                        "then outside the trousers (its rim is the background's grey and the paw hides half of it)"},
    f"{EA}/00": piece("ear", "r", {"root": (0.50, 0.93)}, note="body piece 13 (picture-left of the pair), root stretched 1.6x downward to tuck behind the head (make_ears.py)"),
    f"{EA}/01": piece("ear", "l", {"root": (0.50, 0.93)}, note="body piece 14 (picture-right of the pair), root stretched like the right ear"),
    f"{B}/15": piece("head", "", {"neck": (0.50, 0.93)}, note="head base without features; the expression heads replace it"),
    f"{B}/06": piece("hand", "l", {"wrist": (0.38, 0.10), "thumb_tip": (0.18, 0.78), "fingertip": (0.70, 0.97)}, facing="back",
                     conf=0.75, note="relaxed mitten, thumb toward the body as in the master (back of the paw)"),
    f"{B}/07": piece("hand", "r", {"wrist": (0.62, 0.10), "thumb_tip": (0.82, 0.78), "fingertip": (0.30, 0.97)}, facing="back",
                     conf=0.75, note="relaxed mitten, thumb toward the body as in the master (back of the paw)"),
    f"{B}/00": piece("foot", "l", {"ankle": (0.42, 0.09), "ground": (0.50, 0.97)}, name="boot", note="toe right = outward for the left foot"),
    f"{B}/01": piece("foot", "r", {"ankle": (0.60, 0.09), "ground": (0.50, 0.97)}, name="boot", note="toe left = outward for the right foot"),
    f"{B}/03": {"role": "foot", "side": "either", "variant": "tiptoe", "status": "ignored", "confidence": 0, "points": {},
                "note": "round 4: a tilted boot, not toe-down; its worn cut left 227 px of slivers and it overlapped the trousers 3.4x "
                        "as much as the rest boot (variant_misfit). Dropped: cheer_jump and jump_hurdle skip the tiptoe swap"},
    f"{SLW}/00": piece("arm", "l", {"shoulder": (0.50, 0.17), "elbow": (0.50, 0.57), "wrist": (0.50, 0.97)},
                      note="whole sleeve of the left arm (sleeves sheet piece 00, picture right), widened toward the cuff by make_sleeve_wide.py; elbow at the master's elbow ratio"),
    f"{SLW}/01": piece("arm", "r", {"shoulder": (0.50, 0.17), "elbow": (0.50, 0.57), "wrist": (0.50, 0.97)},
                      note="whole sleeve of the right arm (sleeves sheet piece 01), widened toward the cuff"),
    # hands sheet, row 1 (the character's left hand, sheet y 0.25); row 2 is the other hand, spare
    f"{H}/11": piece("hand", "either", {"wrist": (0.60, 0.05), "thumb_tip": (0.03, 0.45), "fingertip": (0.55, 0.97)}, variant="open",
                     facing="palm", conf=0.75, note="palm pad with its creases visible, four fingers spread"),
    f"{H}/10": piece("hand", "either", {"wrist": (0.50, 0.05), "thumb_tip": (0.88, 0.52)}, variant="fist", facing="palm", conf=0.75,
                     note="palm-facing fist: curled fingertips toward us, thumb folded across from the right"),
    f"{H}/08": piece("hand", "either", {"wrist": (0.60, 0.05), "thumb_tip": (0.03, 0.45)}, variant="thumbsup", facing="palm", conf=0.7,
                     note="wrist up, thumb out to the left, the curled fingers' fronts show"),
    f"{H}/07": piece("hand", "either", {"wrist": (0.55, 0.05), "thumb_tip": (0.12, 0.58), "fingertip": (0.55, 0.95)}, variant="grip",
                     facing="back", conf=0.7, note="loose grip, thumb on the left beside the first finger; labelled palm the worn strip put the thumb 170 deg off, as back it sits on top of the pinch (worn strip reviewed)"),
    f"{H}/09": {"role": "hand", "side": "either", "variant": "point", "status": "ignored", "confidence": 0, "points": {},
                "note": "back-facing point (knuckles, no palm pad): the rig would point it across the chest, where it reads as a grip "
                        "(beaver lesson); replaced by the palm-facing point"},
}
# palm-facing point (hands-point-palm.txt): filled in after the split
PP_PIECE = None
pp = sorted((HERE / "runs" / PP).glob("*_[0-9][0-9].png"))
if pp:
    # the left-hand piece of the pair (sheet picture-left = the character's right hand, thumb to the left edge)
    pieces[f"{PP}/01"] = piece("hand", "either", {"wrist": (0.68, 0.04), "thumb_tip": (0.03, 0.50), "fingertip": (0.43, 0.98)},
                               variant="point", facing="palm", conf=0.8, note="palm-facing point: points outward with the thumb up")
for i, expr in {8: "neutral", 7: "blink", 6: "happy", 5: "laugh", 4: "surprised", 3: "sad", 2: "angry", 1: "talking", 0: "wink"}.items():
    pieces[f"{F}/{i:02d}"] = piece("head", "", {"neck": (0.50, 0.97)}, variant=expr, conf=0.8,
                                     note="expression head, no ears; position on the 3x3 face sheet gives the expression (tools/locate.py)")

for run in (B, H, F, SL, SLW, PP, TO, TR, EA):             # every other piece on the sheets is a spare
    for f in sorted((HERE / "runs" / run).glob("*_[0-9][0-9].png")):
        key = f"{run}/{f.stem[-2:]}"
        if key not in pieces:
            pieces[key] = {"role": "", "side": "", "status": "ignored", "confidence": 0, "points": {},
                           "note": "replaced by its repaint (make_torso.py / make_trousers.py / make_ears.py)" if key in (f"{B}/11", f"{B}/12", f"{B}/13", f"{B}/14") else
                           SPARE_ARM if run == B and f.stem[-2:] in ("04", "05", "08", "09") else
                           "spare piece from the sheet, not used by the rig (the other hand's row, a second tiptoe boot)"}

master = {
    "image": "rabbit_master.png", "status": "proposed",
    "points": {"neck": [0.52, 0.48], "waist": [0.51, 0.63], "ground": [0.51, 0.968],
               "shoulder_l": [0.655, 0.53], "shoulder_r": [0.365, 0.53], "elbow_l": [0.71, 0.585], "elbow_r": [0.305, 0.585],
               "wrist_l": [0.765, 0.645], "wrist_r": [0.245, 0.645], "fingertip_l": [0.8275, 0.797], "fingertip_r": [0.1725, 0.792],
               "hip_l": [0.595, 0.85], "hip_r": [0.43, 0.85], "ankle_l": [0.595, 0.84], "ankle_r": [0.43, 0.84]},
    "hands": {"l": {"thumb_side": "medial", "facing": "back"}, "r": {"thumb_side": "medial", "facing": "back"}},
    "layers": {"upperarm": "under_torso", "foot": "over_hips"},
}
ann = HERE / "annotations.json"
old = json.loads(ann.read_text()) if ann.exists() else {}
ann.write_text(json.dumps({"version": old.get("version", 1), "character": "rabbit", "master": master, "pieces": pieces},
                          indent=2, sort_keys=True) + "\n")
print(ann, len(pieces), "pieces")
