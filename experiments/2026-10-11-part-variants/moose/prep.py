"""Name the split Moose pieces (by looking at the contact sheet) and put every variant joint-end-up.
Body sheet A gave every piece separate except the arms; sheet B (same scale) gave the arms."""
from pathlib import Path
from PIL import Image, ImageOps
R = Path("runs")
def g(tag, i): return Image.open(next((R / tag).glob(f"*_{i:02d}.png"))).convert("RGBA")
def save(im, d, name): im.save(Path(d) / f"moose_{name}.png")
A, B = "moose-body-a-parts", "moose-body-b-parts"
for i, n in {0: "hoof_l", 1: "hoof_r", 2: "leg_l", 3: "leg_r", 5: "hand_l", 6: "hand_r", 9: "bell", 10: "hips", 11: "scarf",
             12: "torso", 13: "ear_l", 14: "ear_r", 15: "cap", 16: "head_base", 17: "antler_r", 18: "antler_l"}.items():
    save(g(A, i), "body", n)
save(g(B, 8), "body", "upperarm_r"); save(ImageOps.mirror(g(B, 8)), "body", "upperarm_l")
save(g(B, 6), "body", "forearm_l"); save(g(B, 7), "body", "forearm_r")
H = "moose-hands-parts"
left = {"open": g(H, 10).rotate(180, expand=True), "fist": g(H, 0), "point": g(H, 4), "grip": g(H, 2),
        "thumbsup": ImageOps.mirror(g(H, 5)).rotate(-90, expand=True)}
for v, im in left.items():
    save(im, "variants", f"hand_l_{v}"); save(ImageOps.mirror(im), "variants", f"hand_r_{v}")
P = "moose-poses-parts"
save(g(P, 6), "variants", "upperarm_l_raised"); save(g(P, 7), "variants", "upperarm_r_raised")
save(g(P, 2), "variants", "hoof_l_tiptoe"); save(ImageOps.mirror(g(P, 2)), "variants", "hoof_r_tiptoe")
