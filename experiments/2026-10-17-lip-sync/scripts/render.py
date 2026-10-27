#!/usr/bin/env python3
"""Mouth track + mouth patches -> a review video with sound, and an objective sync check.

    uv run --with numpy --with pillow --with imageio-ffmpeg scripts/render.py results/line1 \
        --heads ../2026-10-15-beaver-jev-hands/beaver/face-heads --mouths beaver/mouths

Each frame: the rig's neutral head (the blink head for a few frames now and then, to show the mouth slot is
independent of the eyes), the cue's mouth patch over it, and a strip with the waveform, the playhead, the
phonemes and the current shape. Writes <line>.mp4 and <line>.sync.json.

Sync check: each shape has an openness (X 0 ... D 1); the openness track is correlated with the audio's
loudness envelope over lags of -6..+6 frames. A track in sync peaks at a lag of 0 to 2 frames with the
mouth ahead (animators lead the sound by a frame or two).
"""
import argparse, json, os, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw

OPEN = {"X": 0.0, "A": 0.0, "G": 0.15, "B": 0.25, "F": 0.3, "E": 0.5, "C": 0.6, "H": 0.6, "D": 1.0}
NAMES = {"X": "rest", "A": "M B P", "B": "consonant / ee", "C": "eh", "D": "ah", "E": "oh / er", "F": "oo / w", "G": "F V", "H": "L"}
BG = (214, 214, 214)


def shape_at(cues, frame):
    cur = cues[0]["shape"]
    for c in cues:
        if c["frame"] <= frame:
            cur = c["shape"]
        else:
            break
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("line", help="results/<name> (reads .wav, .cues.json, .phonemes.json)")
    ap.add_argument("--heads", required=True)
    ap.add_argument("--mouths", required=True)
    ap.add_argument("--char", default="beaver")
    ap.add_argument("--no-blink", action="store_true")
    a = ap.parse_args()
    cues = json.load(open(a.line + ".cues.json"))
    ph = json.load(open(a.line + ".phonemes.json"))
    fps, dur = cues["fps"], cues["duration"]
    with wave.open(a.line + ".wav") as w:
        sr = w.getframerate()
        audio = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
    n = int(np.ceil(dur * fps))
    neutral = Image.open(f"{a.heads}/{a.char}_head_neutral.png").convert("RGBA")
    blink = Image.open(f"{a.heads}/{a.char}_head_blink.png").convert("RGBA")
    mouths = {k: Image.open(f"{a.mouths}/mouth_{k}.png").convert("RGBA") for k in OPEN}
    W, Hh, S = neutral.width + 40, neutral.height + 30, 130
    W += W % 2
    H = Hh + S + (Hh + S) % 2
    blinks = set() if a.no_blink else {f for t in (1.6, 4.3) for f in range(int(t * fps), int(t * fps) + 3)}
    # waveform strip, pre-drawn
    strip = Image.new("RGB", (W, S), (245, 245, 245))
    d = ImageDraw.Draw(strip)
    hop = len(audio) / W
    for x in range(W):
        seg = audio[int(x * hop): int((x + 1) * hop) + 1]
        v = float(np.abs(seg).max()) if len(seg) else 0
        d.line([(x, 45 - v * 40), (x, 45 + v * 40)], fill=(150, 150, 170))
    for c in cues["cues"]:
        x = c["time"] / dur * W
        d.line([(x, 90), (x, 100)], fill=(60, 60, 60))
        d.text((x + 1, 100), c["shape"], fill=(40, 40, 40))
    for p in ph["phonemes"]:
        if p["p"] not in ("<bos>", "<eos>", " ", "ˈ", "ˌ"):
            d.text((p["start"] / dur * W, 2), p["p"], fill=(110, 60, 60))
    frames_dir = a.line + "_frames"
    os.makedirs(frames_dir, exist_ok=True)
    for f in range(n):
        im = Image.new("RGBA", (W, H), BG + (255,))
        head = blink if f in blinks else neutral
        im.alpha_composite(head, (20, 20))
        s = shape_at(cues["cues"], f)
        im.alpha_composite(mouths[s], (20, 20))
        im = im.convert("RGB")
        im.paste(strip, (0, Hh))
        dr = ImageDraw.Draw(im)
        x = f / fps / dur * W
        dr.line([(x, Hh), (x, Hh + S)], fill=(220, 40, 40), width=2)
        dr.text((12, 8), f"{s}  {NAMES[s]}", fill=(30, 30, 30))
        dr.text((W - 80, 8), f"{f / fps:5.2f}s", fill=(30, 30, 30))
        im.save(f"{frames_dir}/{f:05d}.png")
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", f"{frames_dir}/%05d.png", "-i", a.line + ".wav",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", "-b:a", "128k", "-shortest",
                    a.line + ".mp4"], check=True)
    # sync check: openness vs loudness, per animation frame
    spf = sr / fps
    rms = np.array([np.sqrt(np.mean(audio[int(i * spf): int((i + 1) * spf)] ** 2) + 1e-12) for i in range(n)])
    loud = np.clip((20 * np.log10(rms) + 50) / 40, 0, 1)        # -50..-10 dBFS -> 0..1
    opn = np.array([OPEN[shape_at(cues["cues"], f)] for f in range(n)])
    lags = {}
    for lag in range(-6, 7):            # lag > 0: the mouth is ahead of the sound by `lag` frames
        x, y = (opn[:n - lag], loud[lag:]) if lag >= 0 else (opn[-lag:], loud[:n + lag])
        lags[lag] = round(float(np.corrcoef(x, y)[0, 1]), 3)
    best = max(lags, key=lags.get)
    out = {"frames": n, "fps": fps, "corr_by_lag": lags, "best_lag_frames": best, "corr_at_best": lags[best],
           "lead_frames_applied": cues["lead_frames"]}
    json.dump(out, open(a.line + ".sync.json", "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("frames", "best_lag_frames", "corr_at_best")} | {"corr_lag0": lags[0]}))
    import shutil
    shutil.rmtree(frames_dir)


if __name__ == "__main__":
    main()
