"""Name the split pieces (by looking at the contact sheets) and put every variant joint-end-up."""
from pathlib import Path
from PIL import Image, ImageOps
R = Path("runs")
def g(tag, i): return next((R / tag).glob(f"*_{i:02d}.png"))
def save(im, d, name): im.save(Path(d) / f"fox_{name}.png")
def op(im, *ops):
    for o in ops:
        im = ImageOps.mirror(im) if o == "mirror" else im.rotate(o, expand=True)
    return im
B = "fox-body-v2-parts"
body = {0: "boot_r", 1: "boot_l", 2: "leg_l", 3: "leg_r", 4: "tail", 5: "hand_l", 6: "hand_r", 7: "forearm_l", 8: "forearm_r",
        9: "upperarm_l", 10: "upperarm_r", 11: "hips", 12: "torso", 13: "ear_l", 14: "ear_r", 15: "head_base"}
mirror_body = {"boot_l", "hand_r"}          # the sheet painted both of a pair facing one way; mirror one side
for i, n in body.items():
    im = Image.open(g(B, i)).convert("RGBA")
    save(op(im, "mirror") if n in mirror_body else im, "body", n)
# hands: the character's left set, joint (wrist) at the top; the right set is its mirror image
H = "fox-hands-parts"
left = {"open": op(Image.open(g(H, 10))), "fist": op(Image.open(g(H, 9))), "point": op(Image.open(g(H, 5))),
        "grip": op(Image.open(g(H, 4))), "thumbsup": op(Image.open(g(H, 1)), "mirror", -90)}   # wrist left -> top, thumb outwards
for v, im in left.items():
    save(im.convert("RGBA"), "variants", f"hand_l_{v}")
    save(op(im.convert("RGBA"), "mirror"), "variants", f"hand_r_{v}")
raised = Image.open(g("fox-arms-parts", 2)).convert("RGBA")
save(raised, "variants", "upperarm_l_raised"); save(op(raised, "mirror"), "variants", "upperarm_r_raised")
P = "fox-poses-parts"
tip = Image.open(g(P, 4)).convert("RGBA")                      # toe points right, like boot_l (mirrored above)
save(tip, "variants", "boot_l_tiptoe"); save(op(tip, "mirror"), "variants", "boot_r_tiptoe")
save(Image.open(g(P, 1)).convert("RGBA"), "variants", "tail_up")
