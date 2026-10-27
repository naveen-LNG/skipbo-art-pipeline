# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Round 4: spine_qa `weak_joints` on both ears (overlap with the head 121 / 147 px against 157 / 209 needed). The
body sheet painted each ear ending in a short rounded root, so little of it tucks behind the head. Stretch the
bottom quarter of each ear 1.6x downward: more root hidden behind the head, nothing visible changes.
Writes runs/rabbit-ears-parts/ear_00.png (body piece 13, right ear) and ear_01.png (14, left ear)."""
import glob
from pathlib import Path
from PIL import Image
HERE = Path(__file__).parent; CUT, K = 0.75, 1.6
d = HERE / "runs/rabbit-ears-parts"; d.mkdir(parents=True, exist_ok=True)
for out, n in (("00", "13"), ("01", "14")):
    im = Image.open(glob.glob(str(HERE / f"runs/rabbit-body-parts/*_{n}.png"))[0]).convert("RGBA")
    w, h = im.size; c = int(CUT * h)
    low = im.crop((0, c, w, h)).resize((w, int((h - c) * K)), Image.LANCZOS)
    new = Image.new("RGBA", (w, c + low.height)); new.paste(im.crop((0, 0, w, c)), (0, 0)); new.paste(low, (0, c))
    new.save(d / f"ear_{out}.png")
    print(out, h, "->", new.height, "root y", round((c + (0.95 * h - c) * K) / new.height, 3))
