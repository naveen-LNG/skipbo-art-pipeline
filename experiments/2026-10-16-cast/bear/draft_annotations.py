"""Draft annotations for the bear: meaning and rough points read by eye off gridded views of each split piece
(tools/grid_pieces.py, tools/grid_image.py) and the gridded master. Sheet positions (tools/locate.py) give the sides:
the picture-left column is the character's right. Writes annotations.json with every piece `proposed`; rebuild.sh
then marks them confirmed/fixed (self-review, see README). Points are 0..1 of each image. _l = the character's left
= the picture's right. Master points live in geom.py (shared with make_parts.py)."""
import json
from pathlib import Path

import geom

HERE = Path(__file__).parent
B, H, P, F = "bear-body-parts", "bear-hands-parts", "bear-poses-parts", "bear-face-parts"
PP = "bear-point-palm-parts"
TO, TR, AR = "bear-torso-parts", "bear-trousers-parts", "bear-arm-parts"
CL = "bear-clog-parts"
CLP = json.loads((HERE / "parts.json").read_text())["clogs"]   # ankle and ground in the stubbed clog (make_parts.py)
CLOG_NOTE = "ankle on the master 0.01 inward of the hem centre (round 3: the clogs sat 0.012 too far out)"
TRP = json.loads((HERE / "parts.json").read_text())["trousers"]      # master points in the cut's fractions (make_parts.py)


def piece(role, side, pts, *, name=None, variant=None, facing=None, conf=0.8, note="", painted_as=None):
    d = {"role": role, "side": side, "status": "proposed", "confidence": conf,
         "points": {k: {"at": list(v)} for k, v in pts.items()}}
    for k, v in (("name", name), ("variant", variant), ("facing", facing), ("note", note), ("painted_as", painted_as)):
        if v:
            d[k] = v
    return d


def ignored(note, role=""):
    return {"role": role, "side": "", "status": "ignored", "confidence": 0, "points": {}, "note": note}


pieces = {
    f"{TO}/00": piece("torso", "", {"neck": (0.50, geom.TORSO_NECK_Y), "waist": (0.50, geom.TORSO_WAIST_Y)},
                      note="body-sheet torso narrowed 0.86 across (make_parts.py); neck = bottom of the fur V, waist "
                           "just above the shirt's rounded bottom so it overlaps only the top of the waistband"),
    f"{B}/09": ignored("the sheet's torso, ~1.25x the master's width at the rig's scale; narrowed copy in bear-torso-parts", "torso"),
    f"{TR}/00": piece("hips", "", {k: TRP[k] for k in ("waist", "hip_l", "hip_r")},
                      note="waistband + apron + trousers to the hems, cut from the master at the rig's scale "
                           "(make_parts.py); openings at the hems, clogs under them"),
    f"{B}/00": ignored("the sheet's clog; widened copy in bear-clog-parts", "foot"),
    f"{B}/01": ignored("the sheet's clog; widened copy in bear-clog-parts", "foot"),
    f"{B}/04": ignored("the sheet's 'whole lower body' came back as shorts 2/3 of the master's height; replaced by "
                       "the master-cut trousers piece", "hips"),
    f"{AR}/00": piece("arm", "l", {"shoulder": (0.32, 0.17), "elbow": (0.449, 0.548), "wrist": (0.588, 0.97)},
                      note="whole arm (white sleeve, rolled cuff at the elbow, bare fur forearm) from the arms sheet, "
                           "its fur paw cut off at the wrist; elbow at the master's elbow ratio (0.47), in the roll"),
    f"{AR}/01": piece("arm", "r", {"shoulder": (0.68, 0.17), "elbow": (0.551, 0.548), "wrist": (0.409, 0.97)},
                      note="mirror twin of arm 00, painted for the right arm"),
    f"{B}/02": piece("hand", "l", {"wrist": (0.60, 0.075), "thumb_tip": (0.10, 0.62), "fingertip": (0.60, 0.97)},
                     facing="back", conf=0.7, note="mitten, thumb toward the body as in the master"),
    f"{B}/03": piece("hand", "r", {"wrist": (0.40, 0.075), "thumb_tip": (0.90, 0.62), "fingertip": (0.40, 0.97)},
                     facing="back", conf=0.7, note="mitten, thumb toward the body as in the master"),
    f"{CL}/00": piece("foot", "r", {"ankle": CLP["00"]["ankle"], "ground": (0.42, CLP["00"]["ground"][1])}, name="clog",
                     note="side-view clog widened 1.10 with a hidden honey-fur ankle stub above its heel (make_parts.py), toe left = outward for the right foot; ankle = the heel opening. " + CLOG_NOTE),
    f"{CL}/01": piece("foot", "l", {"ankle": CLP["01"]["ankle"], "ground": (0.58, CLP["01"]["ground"][1])}, name="clog",
                     note="side-view clog widened 1.10, toe right = outward for the left foot. " + CLOG_NOTE),
    f"{B}/10": piece("ear", "l", {"root": (0.30, 0.85)}, conf=0.6, note="likely dropped: the expression heads include the ears"),
    f"{B}/11": piece("ear", "r", {"root": (0.70, 0.85)}, conf=0.6, note="likely dropped: the expression heads include the ears"),
    f"{B}/12": piece("head", "", {"neck": (0.50, 0.97)}),
    # hands sheet, row 1 = the character's left hand, wrist up (row 2 painted the open hand, fist and grip upside down)
    f"{H}/10": piece("hand", "either", {"wrist": (0.50, 0.05), "thumb_tip": (0.03, 0.47), "fingertip": (0.50, 0.97)},
                     variant="open", facing="palm", conf=0.7, note="palm pad and fingertip pads visible"),
    f"{H}/08": piece("hand", "either", {"wrist": (0.55, 0.05), "thumb_tip": (0.10, 0.58)}, variant="fist", facing="palm",
                     conf=0.8, note="palm-facing fist (prompted): curled fingers toward the viewer, thumb across from the left"),
    f"{H}/11": ignored("round 10: drawn back-facing (knuckle bumps, thumb tucked behind) although prompted palm, and I "
                       "labelled it palm; Jev's hold check failed the point (P(thumb up) 0.16). Replaced by bear-point-palm-parts/00", "hand"),
    f"{PP}/00": piece("hand", "either", {"wrist": (0.33, 0.05), "thumb_tip": (0.92, 0.50), "fingertip": (0.55, 0.97)},
                      variant="point", facing="palm", conf=0.85, note="palm-facing point (hands-point-palm.txt): palm pad and "
                      "curled fingertips toward the viewer, thumb out to the side"),
    f"{H}/06": piece("hand", "either", {"wrist": (0.04, 0.62), "thumb_tip": (0.50, 0.03)}, variant="thumbsup",
                     facing="palm", conf=0.7, note="painted with the wrist at the left side; curled fingers' fronts show"),
    f"{H}/07": piece("hand", "either", {"wrist": (0.74, 0.13), "thumb_tip": (0.30, 0.75), "fingertip": (0.05, 0.60)},
                     variant="grip", facing="back", conf=0.5, note="thumb and first finger make a ring at the lower left"),
    # poses sheet: both tiptoe clogs are painted toe right (the left foot)
    f"{P}/02": ignored("round 5: dropped. The tilted side-view tiptoe clog came out 3.2x too big in the rig (scaleX 3.17: its "
                       "snapped opening, 137 px, against the rest clog's unsnapped cross width, 362 px), a giant clog in "
                       "cheer_jump in the Spine player (gallery review); after the ankle stub it also failed variant_misfit. "
                       "Without a tiptoe variant the swap is skipped", "foot"),
}
for i, expr in {8: "neutral", 7: "blink", 6: "happy", 4: "laugh", 3: "surprised", 5: "sad", 2: "angry", 1: "talking",
                0: "wink"}.items():
    pieces[f"{F}/{i:02d}"] = piece("head", "", {"neck": (0.50, 0.97)}, variant=expr, conf=0.8)

for run in (B, H, P, TO, TR, AR, F, CL, PP):                    # every other piece on the sheets is a spare
    for f in sorted((HERE / "runs" / run).glob("*_[0-9][0-9].png")):
        key = f"{run}/{f.stem[-2:]}"
        if key not in pieces:
            pieces[key] = ignored("spare piece, not used by the rig (body-sheet two-piece arms, row-2 hands, "
                                  "relaxed duplicate, rest clogs on the poses sheet)")
pieces["bear-arms-parts/00"] = ignored("raw arm with a fur paw; trimmed copy in bear-arm-parts")
pieces["bear-arms-parts/01"] = ignored("raw arm with a fur paw; trimmed copy in bear-arm-parts")

master = {
    "image": "bear_master.png", "status": "proposed", "points": geom.MASTER,
    "hands": {"l": {"thumb_side": "medial", "facing": "back"}, "r": {"thumb_side": "medial", "facing": "back"}},
    "layers": {"upperarm": "under_torso", "hand": "over_forearm", "foot": "under_hips"},
}
ann = HERE / "annotations.json"
ann.write_text(json.dumps({"version": 1, "character": "bear", "master": master, "pieces": pieces},
                          indent=2, sort_keys=True) + "\n")
print(ann, len(pieces), "pieces")
