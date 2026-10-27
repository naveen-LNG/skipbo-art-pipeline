# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""Code baseline on the same crop pairs: estimate the render crop's offset from the master crop by phase correlation
of edge maps (colour-independent). No model. Direction = sign of the dominant axis; detection score = offset size."""
import json
from pathlib import Path
import numpy as np
from PIL import Image

H = Path(__file__).parent / "jref"
lab = [json.loads(l) for l in open(H / "labels.jsonl")]


def edges(p):
    a = np.asarray(Image.open(p).convert("L"), dtype=np.float32) / 255
    gy, gx = np.gradient(a)
    e = np.hypot(gx, gy)
    w = np.outer(np.hanning(e.shape[0]), np.hanning(e.shape[1]))   # taper the borders
    return (e - e.mean()) * w


def shift(ref, img):
    F = np.fft.fft2(img) * np.conj(np.fft.fft2(ref))
    r = np.fft.ifft2(F / (np.abs(F) + 1e-6)).real
    y, x = np.unravel_index(np.argmax(r), r.shape)
    h, w = r.shape
    return (x - w if x > w // 2 else x), (y - h if y > h // 2 else y)   # +x right, +y down (image px)


rows = []
for r in lab:
    dx, dy = shift(edges(H / f"{r['id']}__ref.jpg"), edges(H / f"{r['id']}.jpg"))
    rows.append(dict(r, dx=float(dx), dy=float(dy)))
json.dump(rows, open(H / "register.json", "w"))
print(len(rows))
