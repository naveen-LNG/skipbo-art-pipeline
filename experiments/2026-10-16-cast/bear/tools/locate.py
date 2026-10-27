# /// script
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""Where each split piece sat on its sheet (so left/right pairs can be told apart by position). Masked SSD by FFT at
1/4 scale. uv run locate.py <sheet.png> <split dir>  -> NN  cx cy (0..1 of the sheet)"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.signal import fftconvolve
K = 4
S = Image.open(sys.argv[1]).convert("RGB"); S = np.asarray(S.resize((S.width // K, S.height // K))).astype(float) / 255
for f in sorted(Path(sys.argv[2]).glob("*_[0-9][0-9].png")):
    P = Image.open(f).convert("RGBA"); P = np.asarray(P.resize((max(1, P.width // K), max(1, P.height // K)))).astype(float) / 255
    m = (P[..., 3] > 0.8).astype(float); ssd = 0
    for c in range(3):
        I, T = S[..., c], P[..., c] * m
        ssd = ssd + fftconvolve(I * I, m[::-1, ::-1], "valid") - 2 * fftconvolve(I, T[::-1, ::-1], "valid") + (T * T).sum()
    y, x = np.unravel_index(np.argmin(ssd), ssd.shape)
    print(f.stem[-2:], f"{(x + P.shape[1] / 2) / S.shape[1]:.2f} {(y + P.shape[0] / 2) / S.shape[0]:.2f}", f"rms={np.sqrt(max(ssd.min(),0) / m.sum() / 3):.3f}")
