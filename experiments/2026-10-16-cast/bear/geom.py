"""Shared geometry for the bear: master points (0..1 of bear_master.png, 1792x2400) read off gridded zooms and colour
measurements, and the torso points that set the rig's global scale. _l = the character's left = the picture's right.
Imported by make_parts.py (which paints pieces at the rig's scale) and draft_annotations.py."""
MW, MH = 1792, 2400

MASTER = {
    "neck": [0.50, 0.335], "waist": [0.50, 0.522], "ground": [0.50, 0.955],
    "shoulder_l": [0.745, 0.335], "shoulder_r": [0.255, 0.335],
    "elbow_l": [0.81, 0.435], "elbow_r": [0.19, 0.435],
    "wrist_l": [0.865, 0.552], "wrist_r": [0.135, 0.552],
    "fingertip_l": [0.895, 0.690], "fingertip_r": [0.105, 0.690],
    "hip_l": [0.634, 0.870], "hip_r": [0.366, 0.870],
    "ankle_l": [0.635, 0.849], "ankle_r": [0.365, 0.849],
}

# body-sheet torso (bear-body-parts/09): neck = bottom of the fur V, waist just above the shirt's rounded bottom, so
# the shirt overlaps only the top of the red waistband (the apron is tied over the shirt in the master)
TORSO_NECK_Y, TORSO_WAIST_Y = 0.26, 0.952
TORSO_H = 601                                           # px, the split piece's height


def global_scale() -> float:
    """Master px per body-sheet px, as rig_place.global_scale computes it (neck-to-waist, master over torso)."""
    m = (MASTER["waist"][1] - MASTER["neck"][1]) * MH
    return m / ((TORSO_WAIST_Y - TORSO_NECK_Y) * TORSO_H)
