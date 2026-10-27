# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Props from the props-pair sheet. The hurdle came back with a faded ghost boot merged into its left foot and smudged
semi-transparent feet, so it is rebuilt from its clean right half mirrored (the red and white bar stays symmetric),
and alpha under 100 is dropped. The flag is used as split. Writes props/flag.png, props/hurdle.png."""
import glob
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parents[1]
(HERE / "props").mkdir(exist_ok=True)
Image.open(glob.glob(str(HERE / "runs/redpanda-props-parts/*_01.png"))[0]).convert("RGBA").save(HERE / "props/flag.png")
h = np.asarray(Image.open(glob.glob(str(HERE / "runs/redpanda-props-parts/*_00.png"))[0]).convert("RGBA")).copy()
w = h.shape[1]; half = h[:, w - w // 2:]
out = np.concatenate([half[:, ::-1], half], 1)
out[..., 3] = np.where(out[..., 3] < 100, 0, out[..., 3])
ys, xs = np.nonzero(out[..., 3]); out = out[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
Image.fromarray(out, "RGBA").save(HERE / "props/hurdle.png"); print("props/flag.png props/hurdle.png", out.shape)
