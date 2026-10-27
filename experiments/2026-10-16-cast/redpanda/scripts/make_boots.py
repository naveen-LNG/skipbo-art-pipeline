# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""The body sheet's boots are as tall as the master's visible boots, so with the ankle at the boot's rim and the rim at
the trousers' hem nothing of the boot is under the trousers: the boots came off the trouser legs in walk and run
(unstitched / detached); E 40 still lost 80% of the overlap in run, and E 90 (ankle 0.76) still 55%: E 130 with the master ankle at 0.745 keeps the ankle disk clear of the hem. Stretch each boot's top 30% (the plain shaft above the laces) by E px, so the shaft reaches up
under the trousers and the visible boot below the hem keeps its painted look. Writes runs/redpanda-boots-parts/boot_00.png
(left, toe right) and boot_01.png and prints the rim point in the new image's fractions."""
import glob
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parents[1]; E = 130; TOP = 0.30
RIM = {"00": (0.345, 0.06), "01": (0.646, 0.06)}
d = HERE / "runs/redpanda-boots-parts"; d.mkdir(parents=True, exist_ok=True); pts = {}
for n, (rx, ry) in RIM.items():
    im = Image.open(glob.glob(str(HERE / f"runs/redpanda-body-parts/*_{n}.png"))[0]).convert("RGBA")
    w, h = im.size; ys = int(TOP * h)
    top = im.crop((0, 0, w, ys)).resize((w, ys + E), Image.LANCZOS)
    out = Image.new("RGBA", (w, h + E)); out.paste(top, (0, 0)); out.paste(im.crop((0, ys, w, h)), (0, ys + E))
    out.save(d / f"boot_{n}.png")
    pts[n] = [rx, round(ry * h * (ys + E) / ys / (h + E), 4)]; print(n, "rim", pts[n], "size", out.size)
# tiptoe variants (poses sheet 04 left, 03 right) are scaled to the rest boot by area, so the taller rest boots made the
# cheer_jump tiptoes ~1.2x too big: give each tiptoe the same area growth. Stretching its top (narrow, tilted) turned
# it into a long cone, so instead repeat its full-width shaft row at 0.15 of its height (under the rim) e times.
def area(im): return int((np.asarray(im)[..., 3] > 128).sum())
k = np.mean([area(Image.open(d / f"boot_{n}.png")) / area(Image.open(glob.glob(str(HERE / f"runs/redpanda-body-parts/*_{n}.png"))[0])) for n in RIM])
TIP = {"04": (0.40, 0.08), "03": (0.60, 0.08)}
for n, (rx, ry) in TIP.items():
    im = Image.open(glob.glob(str(HERE / f"runs/redpanda-poses-parts/*_{n}.png"))[0]).convert("RGBA"); w, h = im.size; ys = int(TOP * h)
    a0 = area(im); e = 0
    while True:
        e += 2
        yi = int(0.15 * h); row = im.crop((0, yi, w, yi + 1)).resize((w, e))
        out = Image.new("RGBA", (w, h + e)); out.paste(im.crop((0, 0, w, yi)), (0, 0)); out.paste(row, (0, yi)); out.paste(im.crop((0, yi, w, h)), (0, yi + e))
        if area(out) >= k * a0:
            break
    out.save(d / f"tiptoe_{n}.png")
    # the ankle sits in the repeated band with 64% of the band below it, as on the rest boots (the hem 83 of their 130
    # added px below the ankle), so the swapped tiptoe hangs at the rest boot's height
    pts["tiptoe_" + n] = [rx, round((int(0.15 * h) + 0.36 * e) / (h + e), 4)]; print("tiptoe", n, "E", e, pts["tiptoe_" + n])
import json; (d / "points.json").write_text(json.dumps(pts))
