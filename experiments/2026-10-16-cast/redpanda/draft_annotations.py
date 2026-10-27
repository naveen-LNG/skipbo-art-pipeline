"""Draft annotations for the red panda: rough points read by eye off gridded pieces (scripts/grid_pieces.py) and the
gridded master (scripts/grid_image.py); sides from each piece's position on its sheet (scripts/locate.py: on the
body sheet the picture-left column is the character's right). Writes annotations.json with every piece `proposed`;
rebuild.sh then records the checkpoint decisions. _l = the character's left = the picture's right."""
import json
from pathlib import Path

HERE = Path(__file__).parent
B, H, P, F = "redpanda-body-parts", "redpanda-hands-parts", "redpanda-poses-parts", "redpanda-face-parts"
SL, PP, E = "redpanda-sleeves-parts", "redpanda-point-palm-parts", "redpanda-ears-parts"
PW = "redpanda-paws-parts"
SW, BT, TR, PP2 = "redpanda-sleeves-wide-parts", "redpanda-boots-parts", "redpanda-trousers-parts", "redpanda-point-palm2-parts"
ROUND1 = "round 1 (onion/joints review + spine_qa)"


def piece(role, side, pts, *, name=None, variant=None, facing=None, conf=0.8, note="", painted_as=None):
    d = {"role": role, "side": side, "status": "proposed", "confidence": conf,
         "points": {k: {"at": list(v)} for k, v in pts.items()}}
    for k, v in (("name", name), ("variant", variant), ("facing", facing), ("note", note), ("painted_as", painted_as)):
        if v:
            d[k] = v
    return d


def ignored(note, role=""):
    return {"role": role, "side": "", "status": "ignored", "confidence": 0, "points": {}, "note": note}


tr_pts = json.loads((HERE / "runs" / TR / "points.json").read_text())
bt_pts = json.loads((HERE / "runs" / BT / "points.json").read_text())
sw_pts = json.loads((HERE / "runs" / SW / "points.json").read_text())
ear_roots = json.loads((HERE / "runs" / E / "roots.json").read_text())
pieces = {
    f"{B}/10": piece("torso", "", {"neck": (0.50, 0.17), "waist": tuple(tr_pts["torso_waist"])},
                     note="neck = base of the fur neck in the collar; waist above the jacket hem, so the hem overlaps the belt top (" + ROUND1 + ": 0.95 left a weak torso/hips joint, 0.93 hid half the belt; now just above the hem, the hips reach up under it)"),
    f"{B}/09": ignored("replaced by its crotch-cut copy redpanda-trousers-parts/00 (make_trousers.py)", "hips"),
    f"{TR}/00": piece("hips", "", {k: tuple(tr_pts[k]) for k in ("waist", "hip_l", "hip_r")},
                     note="the sheet's 'hips' is the whole trousers at the master's length (belt to hem), so it is used leg-less: "
                          "openings at the hems, boots under them (feet under_hips, the moose layout); the master's trousers have no cuffs"),
    f"{B}/02": ignored("trouser leg: the hips piece already reaches the hems", "leg"),
    f"{B}/03": ignored("trouser leg: the hips piece already reaches the hems", "leg"),
    f"{B}/07": ignored("whole sleeve on the body sheet; the sleeves-pair sheet's sleeves are used", "arm"),
    f"{B}/08": ignored("whole sleeve on the body sheet; the sleeves-pair sheet's sleeves are used", "arm"),
    f"{B}/11": ignored("ear painted as a pointed horn turned ~150 deg; the master's ears are used (scripts/make_ears.py)", "ear"),
    f"{B}/12": ignored("ear painted as a pointed horn turned ~150 deg; the master's ears are used (scripts/make_ears.py)", "ear"),
    f"{B}/04": ignored("replaced by its de-fringed copy redpanda-paws-parts/00 (make_paws.py)", "hand"),
    f"{B}/05": ignored("replaced by its de-fringed copy redpanda-paws-parts/01 (make_paws.py)", "hand"),
    f"{PW}/00": piece("hand", "l", {"wrist": (0.47, 0.05), "thumb_tip": (0.92, 0.32), "fingertip": (0.45, 0.96)}, facing="palm",
                     conf=0.75, note="relaxed mitten, thumb out to the side (lateral) as in the master"),
    f"{PW}/01": piece("hand", "r", {"wrist": (0.53, 0.05), "thumb_tip": (0.08, 0.32), "fingertip": (0.55, 0.96)}, facing="palm",
                     conf=0.75, note="relaxed mitten, thumb out to the side (lateral) as in the master"),
    f"{B}/00": ignored("replaced by its taller-shaft copy redpanda-boots-parts/00 (make_boots.py)", "foot"),
    f"{B}/01": ignored("replaced by its taller-shaft copy redpanda-boots-parts/01 (make_boots.py)", "foot"),
    f"{BT}/00": piece("foot", "l", {"ankle": tuple(bt_pts["00"]), "ground": (0.50, 0.98)}, name="boot", note="toe right = outward for the left foot; ankle at the shaft rim's measured centre (" + ROUND1 + ": 0.45 put the boots inward)"),
    f"{BT}/01": piece("foot", "r", {"ankle": tuple(bt_pts["01"]), "ground": (0.50, 0.98)}, name="boot", note="toe left = outward for the right foot; ankle at the shaft rim's measured centre"),
    f"{B}/06": piece("tail", "", {"root": (0.06, 0.62)},
                     note="the ringed J as the master holds it: root at the lower left behind the trousers, tip up at the top"),
    f"{B}/13": piece("head", "", {"neck": (0.50, 0.97)}),
    f"{E}/00": piece("ear", "r", {"root": tuple(ear_roots["00"])}, note="cut from the master with a band of head fur under its base"),
    f"{E}/01": piece("ear", "l", {"root": tuple(ear_roots["01"])}, note="cut from the master with a band of head fur under its base"),
    # sleeves-pair: picture-left sleeve = the character's right arm
    f"{SL}/00": ignored("replaced by its widened copy redpanda-sleeves-wide-parts/00 (make_sleeve_wide.py)", "arm"),
    f"{SL}/01": ignored("replaced by its widened copy redpanda-sleeves-wide-parts/01 (make_sleeve_wide.py)", "arm"),
    f"{SW}/00": piece("arm", "l", sw_pts["00"],
                      note="whole sleeve; points on the measured centreline; elbow at the master's elbow ratio (0.525)"),
    f"{SW}/01": piece("arm", "r", sw_pts["01"],
                      note="whole sleeve; points on the measured centreline; elbow at the master's elbow ratio (0.53)"),
    # hands sheet row 1 (top); row 2 repeats it unmirrored, some poses wrist-down
    f"{H}/08": piece("hand", "either", {"wrist": (0.50, 0.05), "thumb_tip": (0.03, 0.45), "fingertip": (0.45, 0.96)}, variant="open",
                     facing="palm", conf=0.75, note="palm with its creases shows; thumb on the image left"),
    f"{H}/07": piece("hand", "either", {"wrist": (0.50, 0.05), "thumb_tip": (0.12, 0.52)}, variant="fist", facing="palm", conf=0.8,
                     note="palm-facing fist from the first sheet: curled fingertips across the bottom, thumb folded across from the left"),
    f"{H}/10": ignored("point painted back-facing (smooth back, knuckles); replaced by redpanda-point-palm-parts/02", "hand"),
    f"{PP}/02": ignored("point painted back-facing again (Jev cue score -0.42, back); replaced by redpanda-point-palm2-parts/00", "hand"),
    f"{PP2}/00": piece("hand", "either", {"wrist": (0.50, 0.04), "thumb_tip": (0.86, 0.40), "fingertip": (0.74, 0.98)}, variant="point",
                       facing="palm", conf=0.8, note="palm pad, curled fingertips and the thumb across the palm show; index down at the right"),
    f"{H}/09": piece("hand", "either", {"wrist": (0.04, 0.55), "thumb_tip": (0.42, 0.03)}, variant="thumbsup", facing="palm", conf=0.7,
                     note="painted with the wrist at the left side; curled fingers' fronts show"),
    f"{H}/06": piece("hand", "either", {"wrist": (0.55, 0.04), "thumb_tip": (0.15, 0.82), "fingertip": (0.12, 0.50)}, variant="grip",
                     facing="back", conf=0.5, note="smooth back of the hand; index curled at the left over the thumb below it"),
    # poses sheet: both rest boots toe-left (spare); tiptoes 04 toe right (left foot), 03 toe left (right foot)
    f"{P}/04": ignored("replaced by its taller-shaft copy redpanda-boots-parts/tiptoe_04 (make_boots.py)", "foot"),
    f"{P}/03": ignored("replaced by its taller-shaft copy redpanda-boots-parts/tiptoe_03 (make_boots.py)", "foot"),
    f"{BT}/04": piece("foot", "l", {"ankle": tuple(bt_pts["tiptoe_04"]), "ground": (0.75, 0.97)}, name="boot", variant="tiptoe", conf=0.7,
                      note="toe right = left foot; shaft stretched like the rest boots' so the area-matched swap keeps its size"),
    f"{BT}/03": piece("foot", "r", {"ankle": tuple(bt_pts["tiptoe_03"]), "ground": (0.25, 0.97)}, name="boot", variant="tiptoe", conf=0.7,
                      note="toe left = right foot; shaft stretched like the rest boots'"),
}
for src, dst in ((f"{H}/07", f"{PW}/02"), (f"{H}/08", f"{PW}/03"), (f"{H}/09", f"{PW}/04"), (f"{H}/06", f"{PW}/05")):
    pieces[dst] = dict(pieces[src], note=pieces[src].get("note", "") + " (de-fringed copy of " + src + ", make_paws.py)")
    pieces[src] = ignored("replaced by its de-fringed copy " + dst + " (make_paws.py)", "hand")
for i, expr in enumerate(["wink", "talking", "angry", "sad", "surprised", "laugh", "happy", "blink", "neutral"]):
    pieces[f"{F}/{i:02d}"] = piece("head", "", {"neck": (0.50, 0.97)}, variant=expr, conf=0.8)

for run in (B, H, P, F, SL, PP, E, SW, BT, TR, PP2, PW):              # every other piece on the sheets is a spare
    for f in sorted((HERE / "runs" / run).glob("*_[0-9][0-9].png")):
        key = f"{run}/{f.stem[-2:]}"
        if key not in pieces:
            pieces[key] = ignored("spare piece from the sheet, not used by the rig (row-2 hand, rest boot from the poses "
                                  "sheet, second tail, ghosted point hand)")

master = {
    "image": "redpanda_master.png", "status": "proposed",
    "points": {"neck": [0.43, 0.345], "waist": [0.43, 0.570], "ground": [0.43, 0.93],
               "shoulder_l": [0.568, 0.408], "shoulder_r": [0.290, 0.408], "elbow_l": [0.635, 0.478], "elbow_r": [0.22, 0.478],
               "wrist_l": [0.682, 0.553], "wrist_r": [0.190, 0.556], "fingertip_l": [0.753, 0.6205], "fingertip_r": [0.1186, 0.632],
               "hip_l": [0.531, 0.79], "hip_r": [0.335, 0.79], "ankle_l": [0.526, 0.745], "ankle_r": [0.342, 0.745]},
    "hands": {"l": {"thumb_side": "lateral", "facing": "palm"}, "r": {"thumb_side": "lateral", "facing": "palm"}},
    "layers": {"upperarm": "under_torso"},
}
ann = HERE / "annotations.json"
old = json.loads(ann.read_text()) if ann.exists() else {}
ann.write_text(json.dumps({"version": old.get("version", 1), "character": "redpanda", "master": master, "pieces": pieces},
                          indent=2, sort_keys=True) + "\n")
print(ann, len(pieces), "pieces")
