"""Level the picture above the fireplace in the finale. Nano Banana kept its skewed top edge through three edits,
so the frame quad (corners measured on room/finale-pass2.png) is warped onto a level rectangle that covers
every old frame pixel, with a soft contact shadow under it.

Writes room/finale.png and game/assets/finale.jpg.
Run: uv run --with pillow --with numpy --with scipy python scripts/straighten_frame.py
"""
import os
import numpy as np
from PIL import Image, ImageFilter

os.chdir(os.path.join(os.path.dirname(__file__), ".."))
QUAD = [(1221, 716), (1467, 682), (1467, 1037), (1222, 1042)]      # TL, TR, BR, BL of the frame's outer edge
X0, Y0, X1, Y1 = 1222, 682, 1467, 1041                               # level target rectangle

im = Image.open("room/finale-pass2.png").convert("RGB")
w, h = X1 - X0, Y1 - Y0
dst = [(0, 0), (w, 0), (w, h), (0, h)]
# perspective coefficients mapping each output pixel (x, y) to the input: x' = (ax+by+c)/(gx+hy+1), y' = (dx+ey+f)/(gx+hy+1)
A, B = [], []
for (x, y), (u, v) in zip(dst, QUAD):
    A += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]; B += [u, v]
coef = np.linalg.solve(np.array(A, float), np.array(B, float))
frame = im.transform((w, h), Image.PERSPECTIVE, tuple(coef), Image.BICUBIC)

# soft shadow down and to the right, as the original frame had, then the frame itself with a 1px feathered edge
shadow = Image.new("L", im.size, 0)
shadow.paste(150, (X0 + 6, Y0 + 8, X1 + 6, Y1 + 8)); shadow = shadow.filter(ImageFilter.GaussianBlur(7))
dark = Image.new("RGB", im.size, (150, 105, 70))
out = Image.composite(dark, im, shadow.point(lambda a: a * 0.45))
mask = Image.new("L", (w, h), 0); mask.paste(255, (1, 1, w - 1, h - 1)); mask = mask.filter(ImageFilter.GaussianBlur(0.8))
out.paste(frame, (X0, Y0), mask)
out.save("room/finale.png")
out.save("game/assets/finale.jpg", quality=90)
print("frame levelled:", (X0, Y0, X1, Y1))
