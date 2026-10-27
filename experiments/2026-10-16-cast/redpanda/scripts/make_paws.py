# /// script
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""The rest mittens (redpanda-body-parts/04, 05) carry a 1-2 px rim of the sheet's grey inside their opaque edge, which
spine_qa's `seams` counts where the left mitten lies over the cream tail (0.10-0.135 of that edge, limit 0.10).
Recolour every pixel within RING px of the edge from the nearest pixel deeper inside and pull the edge in by 1 px.
The raised fist over the tail tip in wave_flag scored 0.14 the same way, so the hand-sheet variants get it too.
Writes runs/redpanda-paws-parts/paw_00..05.png (body 04, 05; hands 07 fist, 08 open, 09 thumbs-up, 06 grip), same size and points."""
import glob
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
HERE = Path(__file__).resolve().parents[1]; RING = 3
d = HERE / "runs/redpanda-paws-parts"; d.mkdir(parents=True, exist_ok=True)
SRC = [("body", "04"), ("body", "05"), ("hands", "07"), ("hands", "08"), ("hands", "09"), ("hands", "06")]
for i, (sheet, n) in enumerate(SRC):
    a = np.asarray(Image.open(glob.glob(str(HERE / f"runs/redpanda-{sheet}-parts/*_{n}.png"))[0]).convert("RGBA")).astype(np.float32)
    solid = a[..., 3] >= 250
    inner = ndimage.binary_erosion(solid, iterations=RING)
    _, (iy, ix) = ndimage.distance_transform_edt(~inner, return_indices=True)
    ring = (a[..., 3] > 0) & ~inner
    a[ring, :3] = a[iy, ix, :3][ring]
    dist = ndimage.distance_transform_edt(a[..., 3] > 127)
    a[..., 3] = np.where(dist <= 1, 0, np.minimum(a[..., 3], np.clip((dist - 1) * 255, 0, 255)))
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA").save(d / f"paw_{i:02d}.png")
print("ok")
