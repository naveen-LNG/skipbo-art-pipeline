# Lip sync for the Spine characters (2026-10-17)

Goal: make a rigged character (the beaver from [2026-10-15-beaver-jev-hands](../2026-10-15-beaver-jev-hands/README.md)) talk in sync with English speech. The scope is the face only: mouth shapes and their timing, not the body. The voice is Kokoro (`am_michael`, `af_heart`, American English), installed for wisen-studio.

**Verdict: it works, end to end, with no aligner and no extra model.**
- **Timing comes free from Kokoro.** Its duration predictor gives every phoneme a length in 25 ms frames, and the decoder is driven by exactly those lengths: `len(audio) == sum(pred_dur) × 600` samples, asserted on every chunk. Each phoneme's span is known to the sample. No forced alignment, no ASR.
- **Art: one Nano Banana Pro call** for the nine mouth shapes (`prompts/mouth-sheet.txt`), then **four one-shape re-rolls** to fix continuity breaks (round 2 below). The patches are registered on the rig's neutral head to within 1–3 px.
- **Rig: one new slot, `mouth_patch`.** It holds a feathered mouth patch over the head, and one slot-only `talk_<line>` animation per line, played on track 1 over `idle` (or walk, wave...) on track 0. All 15 `spine_qa` checks pass, and every existing animation still passes.
- **Expressions stay free.** The same mouth patches talk cleanly over all six expression heads (`results/expressions_x_mouths.png`). Emotion lives in the eyes and brows, which the head slot swaps; speech lives in the mouth slot. Blinks happen mid-sentence.
- **Sync, measured.** Mouth openness was correlated with audio loudness per animation frame. The correlation peaks at lag 0 on both lines (r = 0.58 and 0.49) and drops within ±1 frame. A 1-frame (42 ms) error is inside the ~45 ms a viewer can notice.

Watch: `results/line1.mp4`, `results/line2.mp4` (head, mouth shape and waveform with playhead, with sound). Rig frames: `beaver/talk_frames.png`.

## How it works

```
text ─► Kokoro (KPipeline) ─► audio + phonemes + per-phoneme durations
                                   │
                    phoneme → mouth shape (misaki IPA → Rhubarb A–H, X)
                                   │
                    animator rules: 24 fps, hold ≥ 2 frames, never drop M/B/P, lead 1 frame
                                   │
                    cues.json ─► Spine slot keys (talk_<line>) + audio event
```

| Step | Script | Notes |
|---|---|---|
| Mouth sheet | `scripts/gen_mouth_sheet.sh` | image_1 = the rig's neutral head on grey; image_2 = the beaver's own face sheet (format and mouth painting). `--n 2`; picked `_00` (better F/V). |
| Re-rolls | `scripts/gen_mouth_L.sh`, `scripts/gen_mouth_fixes.sh` | One shape each, as an edit of the sheet's own head for that shape (`prompts/mouth-{L,D,E,G}-edit.txt`), 2 variants each. |
| Rebuild | `scripts/rebuild.sh` | Decals (sheet + `--replace` re-rolls), the Spine copy, the videos, the sync check and the expressions grid, from the existing audio. |
| **Decals (current)** | `scripts/mouth_decals.py` | Round 3, below. Only the mouth is swapped, laid on the rig head's own muzzle. Review: `beaver/mouths/review.png` (row 2 outlines each decal and the fixed muzzle). |
| Patches (v1, superseded) | `scripts/extract_mouths.py` → `beaver/mouths_v1/` | Cut the 3×3 grid; `--replace SHAPE=png` takes a shape from a single-head re-roll. Key only the large background regions, so grey shading on the white teeth stays opaque. Register each head on the rig head: scale from the bbox, then shift by phase correlation on the eyes and nose. The mask is the union of where the shapes differ from the sheet's rest head, plus the rig head's own mouth, closed, grown 14 px and feathered 6 px. It starts 3 px below the nose and keeps 10 px inside the head outline, so the nose and silhouette always come from the rig head. One mask serves every shape. Colour is matched per channel on the mask's soft ring. Review: `beaver/mouths_v1/review.png`. |
| Timing | `scripts/lipsync.py` (run with `wisen-studio/tts/.venv/bin/python`) | Writes `.wav`, `.phonemes.json` (every phoneme with start and end, plus the raw shape track) and `.cues.json` (the smoothed track). |
| Review video + sync check | `scripts/render.py` | ffmpeg comes from `imageio-ffmpeg` via uv; nothing is installed system-wide. |
| Spine | `scripts/spine_talk.py` | A copy of the rig in `beaver/rig_talk/`. The source rig is untouched. |
| Expressions test | `scripts/expr_grid.py` | |

Preview the rig with sound: the `beaver-talk` entry in `.claude/launch.json`, then open `http://localhost:8771/talk.html`. The page plays `idle` on track 0 and the line on track 1, and every frame it sets track 1's time from `audio.currentTime`, so the picture can't drift from the sound. *Not verified visually here:* the browser pane was hidden, so WebGL didn't paint. The original `preview.html` was blank the same way. The runtime state was checked in the real spine-player instead (`mouth_patch` = `beaver_mouth_D` at 0.95 s, on "I'm"), and the frames were rendered with `spine_qa`'s renderer.

### The mouth shapes (Rhubarb Lip Sync's set)

| Shape | Sounds | Kokoro (misaki) phonemes |
|---|---|---|
| X rest | silence, punctuation, word gaps ≥ 120 ms | `<bos> <eos> . , ! ?` |
| A closed | M B P | `p b m` |
| B near-closed, stretched | most consonants, "ee" | `t d n k ɡ ŋ s z ʃ ʒ ʧ ʤ j θ ð ɾ ʔ i` |
| C open | "eh", "ae", schwa | `ɛ æ ɪ ə ʌ ᵊ ᵻ` |
| D wide | "ah" | `ɑ ɒ` |
| E round | "oh", "er", r | `ɔ ɜ ɚ ɹ` |
| F pucker | "oo", "w" | `u w ʊ` |
| G teeth on lip | F V | `f v` |
| H tongue up | L | `l` |

- **Diphthongs** are two shapes, half the time each: `A`=eɪ→C,B; `I`=aɪ→D,B; `W`=aʊ→D,F; `O`=oʊ→E,F; `Y`=ɔɪ→E,B.
- **`h`** takes the next sound's shape.
- **Stress marks** (`ˈ ˌ`) get durations from the model too; their time goes to the next phoneme.

### Animator rules (`lipsync.smooth`)

- 24 fps, each shape held at least 2 frames (on twos). This gives about 6–7 changes a second, which reads as speech rather than flicker.
- A lip closure (A) may last one frame but is never dropped. A missing M/B/P closure is the most visible lip-sync error.
- The mouth leads the sound by 1 frame, as in hand-animated dialogue.

## What the mouth is: image swaps, not a mesh

There is **no mesh and no deformation** on the face. The `mouth_patch` slot holds 9 flat images (region attachments), and the talk animation switches which one is visible, about 6–7 times a second. It's the same mechanism as the expression heads in the head slot. Each image is the rig head's own muzzle with one mouth shape painted in, so swapping it changes only the mouth.

**What carries over to any character unchanged:**
- **Timing.** Text → Kokoro → phonemes with times → the nine shapes → cues (`lipsync.py`). Nothing in it knows about the beaver.
- **Spine.** A slot over the head, region attachments, a slot-only `talk_<line>` animation on track 1, the audio event (`spine_talk.py`). Any rig built by `spine_rig.py` gets this.
- **Art request.** The mouth-sheet prompt and the one-shape re-roll prompts. Only the character notes change.

**What is beaver-specific (in `mouth_decals.py`), and what a human needs instead:**

| Assumption | Beaver | Human-like character |
|---|---|---|
| The mouth sits on a distinct muzzle colour | Cream (G/R ≈ 0.8) against orange fur (≈ 0.55) | Lips and skin are close in hue. Find the mouth by difference from a mouthless base head (inpainted, or one image edit), not by colour. |
| The nose is a dark blob | Yes, the anchor for everything below it | A soft shaded nose. Anchor on the registered face instead, or on face landmarks (a face-mesh model on the painted face). |
| A drawn nose-to-mouth line | Yes, redrawn from the rig's own line | Usually only a soft shadow. The same erase-and-redraw works, or skip it. |
| The face outline never changes | True: the muzzle is a rigid snout | **False.** An open human mouth drops the jaw and the chin moves. A pure swap freezes the chin, which reads as a mask. |

**Recommendation for human-like characters: swaps plus a jaw bone (the hybrid).**
- Keep the mouth swaps for the shape (lips, teeth, tongue).
- Split the head into an upper head and a jaw/chin piece on a `jaw` bone. That's one more piece on the body sheet, which the parts pipeline already handles.
- Key a small jaw drop per shape: D most, C/H/E some, A/B/G/F none.
- A full mesh (Live2D-style deformation of lips and cheeks) is the step after that. It looks smoother, but it needs a painted mouth interior and hand-weighted meshes per character. Worth it for a hero character, not for a cast.

## Research: ways to lip-sync a 2D rig

From background knowledge; none of these were benchmarked here.

| Approach | What it is | Fit for these Spine characters |
|---|---|---|
| **Mouth-slot swaps** (this experiment) | 6–12 drawn mouth shapes in a slot; timing from phonemes. The Preston Blair / Hanna-Barbera chart; Rhubarb's A–H, X set. | **Recommended.** Matches our "every piece is generated art" pipeline and the shipped style. Cheap at runtime (slot keys only). Combines with any expression and any body animation. |
| Whole-head swaps | Each mouth shape is a whole expression head (as `head_talking` is today). | Works, but ties mouth to emotion (9 shapes × N emotions), and small outline differences between generated heads "boil" at 6–7 swaps a second. |
| Mesh deformation | A mouth mesh (or jaw and lip bones) deformed between shapes, often driven by a continuous "open" value. This is Live2D's `ParamMouthOpenY` / `ParamMouthForm`. | Smoother in-betweens and fewer drawings. But it needs a painted mouth interior under deformable lips, hand-weighted meshes, and more rigging per character. Worth it for a hero character, not for a cast. |
| Hybrid | Swaps for shape, plus a small jaw bone or a scaleY key on the patch driven by loudness. | The cheapest polish on top of what we have. Next step if swaps feel too stepped. |
| Volume-only ("flap") | Open amount from the audio's loudness, no phonemes. Common in VTubing and many casual games. | Works for any audio, any language, in real time. It reads as talking but never closes on M/B/P. Good as a fallback for audio we have no phonemes for. |
| Neural video lip sync | Wav2Lip, SadTalker, MuseTalk, LatentSync, LivePortrait: they repaint the pixels of a video. | Not for a Spine runtime: no rig and no reuse. Only for pre-rendered cutscenes. |

**Where timing can come from:**

| Audio | Timing source |
|---|---|
| TTS we synthesise | The engine's own durations: Kokoro here. Cloud TTS has the same idea: Azure TTS sends viseme events, Amazon Polly sends viseme speech marks. |
| Recorded voice | A forced aligner: Rhubarb Lip Sync (PocketSphinx for English, a phonetic recogniser for other languages, takes the dialogue text as a hint; it ships a Spine integration that writes the animations into the skeleton JSON), Montreal Forced Aligner, or WhisperX. |
| Live audio | Loudness only, or a realtime viseme model (Oculus/Meta OVRLipSync, 15 visemes). |

**Does the accent matter?** Little, for drawn mouths.
- Kokoro's American (`a`) and British (`b`) G2Ps differ mostly in vowel quality and rhoticity. British drops most `ɹ`, so fewer E shapes.
- Vowels that move between accents mostly stay inside the same mouth shape (C/D/E). Nine shapes are coarse enough that the accent barely shows.
- Other languages: the shape set holds, but each needs its own phoneme→shape table. espeak-ng languages also come with durations (`kokoro_server.phoneme_words` already reads them).

## Round 2: continuity fixes (after review: "about 70%, the tongue sticking out breaks it")

Someone reading the lips follows the mouth from frame to frame, so any shape that changes the character's identity breaks the reading. Four shapes did, plus one pipeline bug:

| Shape | Problem | Fix |
|---|---|---|
| H "L" | A tongue-out "blep", hanging out the side | Edit of the sheet's "eh" head: tongue tip raised against the back of the front teeth, entirely inside the mouth. Picked `_00`; `_01` twisted the tongue sideways. |
| E "oh" (33 frames over the two lines) | The beaver's big front teeth vanished | Edit: keep the round mouth, teeth hanging from its top edge. Picked `_01`; `_00` opened too wide and read as "eh". |
| D "ah" | Teeth stretched, with a dark jagged crack | Edit: clean teeth at their closed-mouth size. Picked `_00`. |
| G "F/V" | A lopsided smirk with a stray glint | Edit: symmetric, both corners level, teeth on the lower lip. Picked `_01`. |
| All shapes (pipeline) | The background key made light-grey tooth shading see-through, so the head underneath showed through as grey cracks. This was most of D's "crack". | Key only large background regions; small enclosed ones stay opaque. |
| All shapes | The patch covered the bottom of the nose (twitching by its registration error) and reached the chin outline (`spine_qa` seams: `mouth_patch/torso` 0.143) | The patch starts below the nose and stays 10 px inside the head outline. The seam is back to 0.0. |

After the fixes the teeth show in every shape except the "oo" pucker (by design). The tongue never leaves the mouth, and the nose and outline never move. `spine_qa`: 18/18 pass. The sync numbers are unchanged (the timing didn't change).

## Round 3: the mouth stays on the face (after review: "the mouth moves out of the muzzle; the bottom of the nose blurs")

**Cause:** v1 swapped a muzzle-sized patch cut from each generated head. Every generation paints its own cream muzzle, so between shapes:
- the muzzle's outline swam: G's was wider, and D's had a dropped jaw 57 px taller than the rig's;
- the feathered patch edge left soft double edges on its sides;
- the fade-in under the nose blended two different nose shadows into a blur.

**Fix (`scripts/mouth_decals.py`): swap only the mouth, never the muzzle.**
1. **Muzzle.** Each head's muzzle is found by colour: cream has G/R ≈ 0.8, fur ≈ 0.55. Each row is filled between its outermost cream pixels, because an open mouth splits the cream ring and plain hole filling misses it.
2. **Mouth features.** Inside the muzzle, every pixel that isn't plain cream: lines, lips, the dark inside, the tongue, plus the white teeth. Closed and filled. The decal is the features plus 5 px of cream.
3. **Base.** The rig's neutral head with its own mouth inpainted (OpenCV Telea plus a soft blur inside the hole). The philtrum is kept down to 14 px under the nose; below that, each decal carries its own.
4. **Fit.** A mouth that would spill past the rig muzzle is scaled about its top until it sits 6 px inside: D ×0.78, E ×0.92, H ×0.98. The rest fit as painted.
5. **Nose line.** Drawn once per patch from the rig's own line (round 4, below). This replaced a sideways snap of each decal.
6. **Colour.** Matched on a cream ring around the decal, mean only, contrast within ±10%. (Scaling by the ring's spread washed D and E out.)
7. **Patch = base + decal (1.5 px feather).** Its alpha is the rig muzzle, and outside the decal its pixels are the rig head's own. The patch edge is invisible, and the muzzle outline, cheeks and nose shadow never change.

**Round 4, the nose line (philtrum).** Each shape painted its own nose-to-mouth line. Where the rig head's line met the shape's, there was a break, a kink or a dark dot (most visible on "oo"). Now the line is drawn once:
- the base has the rig's line erased, each row bridged across a straight line fitted to it;
- each patch gets one continuous line from the nose to where that mouth's upper lip starts, re-drawn from the rig line's own cross-section and slanting to meet the mouth;
- the line is never drawn over the mouth decal.

The upper lip is found as the first row where the mouth pixels around the line are wider than a line. The search starts 20 px above the mouth body, so cheek creases near the nose don't count.

**Result:**
- The muzzle outline is identical in all nine shapes (`beaver/mouths/review.png`, row 2).
- The nose bottom is crisp.
- D's mouth sits inside the muzzle.
- `spine_qa` passes 18/18 (`mouth_patch/torso` 0.0).
- Sync is unchanged.

## Known gaps and next steps

- **Talking over the happy or laugh head shows a faint second muzzle edge** at its lower right. Those heads painted a bigger muzzle than neutral, and the patch carries the neutral muzzle. The talk animations use neutral and blink, which are clean. To talk while happy, build a base per expression head (the same inpainting, no new art) and pick the patch set from the head showing.

- **F ("oo") hides the teeth.** That's correct for a pucker, and it lasts only a few frames, but it's the one remaining identity change. If it still reads oddly, re-roll it with the teeth tips just visible above the rounded lips.
- **Talking while happy looks neutral-mouthed.** The mouth set is drawn on the neutral muzzle, so the smile corners are lost. For a happy talking line, add a second, smiling mouth set (one more call with the happy head as image_1) and pick the set from the line's emotion.
- **Shape transitions are hard cuts.** Spine can't cross-fade attachments. If D→A pops, add Rhubarb-style in-between rules (D→A goes through C for one frame) or the hybrid jaw squash.
- **Recorded voice:** wire Rhubarb (or WhisperX + the same phoneme table) for audio we didn't synthesise. Needs a binary or model download.
- **Into the skill:** a `mouth-sheet.txt` prompt plus `spine_rig.py --mouths` that adds the slot and `talk_*` animations at build time.

## Files

- `prompts/mouth-sheet.txt`: the nine-shape sheet prompt.
- `beaver/runs/beaver-mouths/`: the two generated sheets (`_00` used); `beaver/runs/beaver-mouth-{L,D,E,G}/`: the re-rolls.
- `beaver/mouths/`: the current patches (`mouth_X..H.png`: base + decal), `base.png` (the mouthless muzzle), `mouths.json` (nose, cut, fit scales, snaps), `review.png`. `beaver/mouths_v1/`: the round-2 muzzle patches, for comparison.
- `beaver/rig_talk/`: the beaver rig with `mouth_patch`, `talk_line1`, `talk_line2`, the wavs and `talk.html`.
- `results/line{1,2}.{wav,phonemes.json,cues.json,sync.json,mp4}`, `results/expressions_x_mouths.png`.
