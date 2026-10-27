# /// script
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""Round 3: the pipeline keys the master by distance from the border colour (> 0.06, rig_match.master_mask and
spine_qa's setup IoU), and the rabbit's pale muzzle, forehead highlight and paw highlights sit within 0.06 of the
light-grey background (tools/key_check.py: 4.8% of the silhouette reads as holes). The rig fills those holes, so the
setup IoU counted them against it. Recolour only the background: pixels within 0.05 of the border colour and connected
to the border, plus a soft blend of the anti-aliased rim, shift to a sand yellow that no part of the rabbit uses (a blue-grey first try sat as close to the grey fur as the old grey did to the muzzle). Nothing inside the outline
changes. Writes rabbit_master.png from rabbit_master_orig.png (runs/rabbit-master3/..._00.png)."""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
HERE = Path(__file__).parent
NEW = np.array([228, 210, 140], np.float32) / 255
m = np.asarray(Image.open(HERE / "rabbit_master_orig.png").convert("RGB"), np.float32) / 255
border = np.concatenate([m[0], m[-1], m[:, 0], m[:, -1]]); bg = np.median(border, 0)
d = np.linalg.norm(m - bg, axis=2)
cand = d < 0.05
lab, _ = ndimage.label(ndimage.binary_opening(cand, iterations=3))   # opened: a 1-2 px leak through a pale rim (the
                                                                      # tail's) must not reach the highlight inside
edge_labels = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])); edge_labels = edge_labels[edge_labels > 0]
outside = ndimage.binary_dilation(np.isin(lab, edge_labels), iterations=3) & cand
# the cotton tail's rim is painted in the background's own grey (221,219,224 against 218): no colour rule separates
# them, so the ball (read off the gridded master: left edge x 0.276, top 0.669, bottom 0.766) is kept by hand
H_, W_ = d.shape; yy, xx = np.mgrid[:H_, :W_]
outside &= np.hypot(xx - 0.341 * W_, yy - 0.7175 * H_) > 117
near = ndimage.binary_dilation(outside, iterations=4) & (np.hypot(xx - 0.341 * W_, yy - 0.7175 * H_) > 117)            # the anti-aliased rim just outside the figure
w = np.where(outside, 1.0, np.where(near, np.clip(1 - (d - 0.05) / 0.10, 0, 1), 0.0))[..., None]
out = m + w * (NEW - bg)
Image.fromarray((np.clip(out, 0, 1) * 255).round().astype(np.uint8), "RGB").save(HERE / "rabbit_master.png")
print("background", np.round(bg * 255).astype(int).tolist(), "->", (NEW * 255).astype(int).tolist(), f"outside {outside.mean():.3f}")
