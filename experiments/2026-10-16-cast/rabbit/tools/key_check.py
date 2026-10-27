# /// script
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""Can the pipeline key this master? rig_match.master_mask / spine_qa setup treat a pixel as figure when its RGB is
more than 0.06 from the median border colour. A light-grey character on the light-grey background drops out (the
first rabbit masters: paws and head within 0.03). Prints the share of the filled silhouette that the key misses and
writes <out.png>: master | key mask (holes red).  uv run tools/key_check.py <master.png> <out.png>"""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage
im = Image.open(sys.argv[1]).convert("RGB"); m = np.asarray(im, np.float32) / 255
border = np.concatenate([m[0], m[-1], m[:, 0], m[:, -1]]); bg = np.median(border, 0)
key = np.linalg.norm(m - bg, axis=2) > 0.06
filled = ndimage.binary_fill_holes(ndimage.binary_closing(key, iterations=6))
miss = filled & ~key
print(f"bg {np.round(bg * 255).astype(int).tolist()}  figure {key.mean():.3f}  holes inside silhouette {miss.sum() / max(1, filled.sum()):.3%}")
vis = np.zeros(m.shape, np.uint8); vis[key] = 255; vis[miss] = (255, 0, 0)
out = Image.new("RGB", (im.width * 2, im.height)); out.paste(im, (0, 0)); out.paste(Image.fromarray(vis), (im.width, 0))
out.thumbnail((1400, 1400)); out.save(sys.argv[2])
