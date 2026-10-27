#!/usr/bin/env python3
"""Text -> Kokoro speech + a timed mouth-shape (viseme) track, read off the synthesiser itself.

    ../../../wisen-studio/tts/.venv/bin/python scripts/lipsync.py "Hey there!" --voice am_michael --out results/line1

Writes <out>.wav, <out>.phonemes.json (every phoneme with its start/end) and <out>.cues.json (the mouth track).

Why no aligner: Kokoro's duration predictor gives every phoneme token a length in frames of 600 samples
(40 per second at 24 kHz) and the decoder is driven by exactly those lengths, so len(audio) ==
sum(pred_dur) * 600 and each phoneme's span is known to the sample. (An aligner such as Rhubarb or
Montreal Forced Aligner is only needed for audio we did not synthesise: a recorded actor.)

Mouth shapes are Rhubarb Lip Sync's nine (the Preston Blair / Hanna-Barbera set animators already use):
  X rest   A M B P (closed)   B most consonants, "ee"   C "eh", "ae"   D "ah" (widest)
  E "oh", "er" (slightly round)   F "oo", "w" (pucker)   G F V (teeth on lip)   H L (tongue up)
"""
import argparse, json, wave
import numpy as np

SR, FRAME = 24000, 600            # Kokoro: 24 kHz audio, one duration frame = 600 samples = 25 ms

# misaki (Kokoro's American English G2P) phoneme -> mouth shape. Diphthongs are two shapes, half the time each.
VISEME = {}
for chars, shape in [("pbm", "A"),
                     ("tdnkɡŋszʃʒʧʤjθðhɾʔçx" "i", "B"),     # tongue/teeth consonants and "ee" read as a near-closed, stretched mouth
                     ("ɛæɪəʌᵊᵻɐe", "C"),
                     ("ɑɒa", "D"),
                     ("ɔɜɚɹr" "o", "E"),
                     ("uwʊ", "F"),
                     ("fv", "G"),
                     ("l", "H")]:
    for c in chars:
        VISEME[c] = shape
DIPHTHONG = {"A": "CB", "I": "DB", "W": "DF", "O": "EF", "Y": "EB"}   # eɪ aɪ aʊ oʊ ɔɪ
PAUSE = set(" !,.:;?—…\"“”()")   # spaces and punctuation: rest if long, else given to the neighbours
STRESS = set("ˈˌː")              # zero-sound marks: their time goes to the next phoneme


def synth(text, voice, speed):
    import warnings
    warnings.filterwarnings("ignore")
    from loguru import logger
    logger.remove()
    from kokoro import KPipeline
    pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    vocab = pipe.model.vocab
    audio, phones, off = [], [], 0
    for r in pipe(text, voice=voice, speed=speed):
        a = r.audio.numpy() if hasattr(r.audio, "numpy") else np.asarray(r.audio)
        d = [int(x) for x in r.pred_dur.tolist()]
        assert len(a) == sum(d) * FRAME, "Kokoro audio no longer equals its durations"
        toks = [c for c in r.phonemes if c in vocab]          # the model reads only in-vocab symbols, one duration each
        assert len(toks) == len(d) - 2
        t = off + d[0] * FRAME                                 # after <bos>
        phones.append({"p": "<bos>", "start": off / SR, "end": t / SR})
        for c, n in zip(toks, d[1:-1]):
            phones.append({"p": c, "start": t / SR, "end": (t + n * FRAME) / SR})
            t += n * FRAME
        phones.append({"p": "<eos>", "start": t / SR, "end": (t + d[-1] * FRAME) / SR})
        audio.append(a)
        off += len(a)
    return np.concatenate(audio), phones


def to_segments(phones, rest_after=0.12):
    """Phonemes -> contiguous (start, end, shape) segments, before any smoothing.
    Every phoneme first gets a shape or a role; the time of the zero-shape tokens is then handed over:
    a stress mark's time goes to the next phoneme, a short word gap is split between its neighbours,
    and "h" (no mouth shape of its own) takes the shape of the sound after it."""
    items = []                                   # [start, end, shape | None, role]
    for ph in phones:
        p, s, e = ph["p"], ph["start"], ph["end"]
        if p in ("<bos>", "<eos>") or (p in PAUSE and (p != " " or e - s >= rest_after)):
            items.append([s, e, "X", "rest"])    # silence, punctuation or a long word gap: the mouth rests
        elif p == " ":
            items.append([s, e, None, "gap"])
        elif p in STRESS:
            items.append([s, e, None, "stress"])
        elif p == "h":
            items.append([s, e, None, "h"])
        elif p in DIPHTHONG:
            a, b = DIPHTHONG[p]
            items += [[s, (s + e) / 2, a, "v"], [(s + e) / 2, e, b, "v"]]
        else:
            items.append([s, e, VISEME.get(p, "B"), "v"])
    for k in range(len(items) - 2, -1, -1):      # h takes the next shape (back to front, so "h" before a stress mark works)
        if items[k][3] == "h":
            items[k][2] = next((x[2] for x in items[k + 1:] if x[2]), "X")
    segs = []
    for k, (s, e, v, role) in enumerate(items):
        if v is None and role == "gap" and segs:
            segs[-1][1] = (s + e) / 2            # previous shape holds the first half; the next starts at the middle
            continue
        if v is None:                            # a stress mark, or a gap with nothing before it: the next shape starts here
            continue
        start = s
        if k and items[k - 1][2] is None:
            prev = items[k - 1]
            start = (prev[0] + prev[1]) / 2 if prev[3] == "gap" and segs else prev[0]
        segs.append([start, e, v])
    for a, b in zip(segs, segs[1:]):             # contiguous
        a[1] = b[0]
    return segs


def smooth(segs, fps=24, lead=1, hold=2):
    """Animator's rules on the raw track, on a frame grid:
    - quantise to `fps`, each shape held at least `hold` frames (on twos), except a lip closure (A),
      which may be a single frame but is never dropped: a missing M/B/P closure is the most visible lip-sync error;
    - merge repeats; a too-short shape gives its frames to the longer neighbour;
    - shift the mouth `lead` frames ahead of the sound (the eye expects the shape slightly before the sound)."""
    f = [[round(s * fps), round(e * fps), v] for s, e, v in segs]
    f = [x for x in f if x[1] > x[0] or x[2] == "A"]
    for x in f:
        if x[1] == x[0]:
            x[1] = x[0] + 1
    for a, b in zip(f, f[1:]):        # re-tile after rounding
        b[0] = a[1] if b[0] < a[1] else b[0]
        b[1] = max(b[1], b[0] + 1)
    changed = True
    while changed:
        changed = False
        merged = []
        for x in f:
            if merged and merged[-1][2] == x[2]:
                merged[-1][1] = x[1]
                changed = True
            else:
                merged.append(x)
        f = merged
        for i, x in enumerate(f):
            n = x[1] - x[0]
            if n < hold and not (x[2] == "A" and n >= 1) and len(f) > 1:
                prev, nxt = (f[i - 1] if i else None), (f[i + 1] if i + 1 < len(f) else None)
                # give the frames to the longer neighbour, unless that neighbour is a closure we must keep short
                tgt = max((y for y in (prev, nxt) if y), key=lambda y: (y[2] != "A", y[1] - y[0]))
                if tgt is prev:
                    prev[1] = x[1]
                else:
                    nxt[0] = x[0]
                f.pop(i)
                changed = True
                break
    cues = [{"frame": max(0, s - lead), "time": round(max(0, s - lead) / fps, 4), "shape": v} for s, e, v in f]
    cues[0]["frame"], cues[0]["time"] = 0, 0.0
    end = f[-1][1]
    return cues, end / fps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--voice", default="am_michael")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--lead", type=int, default=1, help="frames the mouth leads the sound")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    audio, phones = synth(a.text, a.voice, a.speed)
    with wave.open(a.out + ".wav", "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    raw = to_segments(phones)
    cues, dur = smooth(raw, a.fps, a.lead)
    json.dump({"text": a.text, "voice": a.voice, "phonemes": phones,
               "raw": [{"start": round(s, 4), "end": round(e, 4), "shape": v} for s, e, v in raw]},
              open(a.out + ".phonemes.json", "w"), indent=1, ensure_ascii=False)
    json.dump({"fps": a.fps, "lead_frames": a.lead, "duration": round(len(audio) / SR, 4), "cues": cues},
              open(a.out + ".cues.json", "w"), indent=1)
    from collections import Counter
    print(json.dumps({"duration": round(len(audio) / SR, 3), "phonemes": len(phones), "cues": len(cues),
                      "changes_per_s": round(len(cues) / (len(audio) / SR), 1),
                      "shapes": dict(Counter(c["shape"] for c in cues))}))


if __name__ == "__main__":
    main()
