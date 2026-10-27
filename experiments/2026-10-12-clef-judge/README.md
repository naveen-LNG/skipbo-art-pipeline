# Decision models as rig image judges (2026-10-12 to 2026-10-15)

Question: can a System One decision model with vision replace or pre-filter the LLM / human look at rig renders?
Can it say whether a stitch is wrong, which part, and which way to nudge it? Three models got the same images and
questions: Cloudflare Clef Flash (9B), Clef 27B and TypeSafe Jev 1.14.

**Final verdict (round 5):**

**Jev 1.14 is the model to build on for detection.**
- One frame at a time, it separates real rejected frames from their fixes:
  - full body: AUROC 0.99
  - three rig generations: AUROC 0.89, and 1.00 for the previous build vs approved
- It flags joints that moved since the previous render (91%; 0.04 when nothing changed).
- With the master crop beside the render, it flags displaced joints: AUROC 0.82 on audited labels.

**No model gives a usable fix direction.** Every model is at 27-34% (chance is 25%), and Box edges are as coarse as the shifts. Keep nudges in code.

**Pairwise "which is worse" is roughly level across all three models.**

Rounds 1-3 below predate the label audit. Their joint-crop numbers count four flawed "approved" hand joints as clean, and
understate Jev and 27B. `rig-judge-trial.html` is the full report, with every test compared across all three models.
No pipeline code was changed.

## Setup
- Model: `@cf/cloudflare/clef-flash` via Workers AI (`/ai/run`, System One contract). The local Ollama build
  (`clef-flash` mxfp8, 11.5 GiB) does not load on this 16 GB Mac: Metal caps the working set at 11.8 GiB, minus a 512 MiB floor.
- Contract notes: Ollama `/v1/systemone` takes raw base64 `images[]`; Cloudflare requires `data:image/png;base64,` URIs.
  The image costs 1 token per 32x32 px (+3), and the context is 24,576 tokens.
- Test data (ground truth by construction or by human review):
  - **Synthetic** (`scripts/gen.py`): the approved fox and moose rigs, rendered one slot layer at a time and recomposited with one change:
    - one slot shifted 3/8/16/24 px up/down/left/right
    - a sleeve over the torso, or the tail/antler in front
    - a mirrored hand
    - clean setup and animation frames as negatives

    120 were sampled (38 clean, 82 defective).
  - **Real** (`scripts/slice_real.py`): 19 before/after pairs sliced from the checkpoint-6 review sheets
    (`before_after_{fox,moose}.png`, `shoulders_ab_{fox,moose}.png`), with the label text cropped out.
  - **Joint crops** (`scripts/joints.py`): 252 close-ups of hand/cuff, neck, waist, feet, tail and antler joints, upscaled to 448 px.
    The boxes come from the clean render, as pipeline code would know them.

## Results (489 calls, 538k input tokens, about 1.9k neurons, about $0.02; median latency 0.7 s)

| Condition | What it saw | Result |
|---|---|---|
| Full frame, 6 typed questions | one ~520x720 render | Synthetic AUROC **0.38**, real AUROC **0.61**. P(defect) is about 0.2 for everything, nothing crosses 0.5, and every `kind` answer is `none` |
| Master + frame (setup pose) | reference + render | Same: P(defect) is flat across 3 to 24 px shifts |
| Joint close-up, narrow noul | one 448 px joint crop | AUROC **0.52**; TPR 0.73 / FPR 0.69 at 0.5. Even an obviously floating glove is not separated from a clean cuff |
| Part / side / direction | any of the above | At chance: direction 24-27% (4-way), part 19-24% |
| **Pairwise, order-averaged** | two renders of the same pose | Picked the defective render **15/19**. Full-body before/after **10/11** (mean P 0.55-0.78); sleeve-over-torso **5/8** (all within 0.43-0.63, so no signal) |

Pairwise has a position bias: it answers "image 1" about 70% of the time. Always ask both orders and average.

## Takeaways
1. Clef Flash does not *see* pixel-level stitching faults (gaps, offsets, layer order) at any crop scale tried. Its
   probabilities are flat, not just badly thresholded. Keep `spine_qa`'s geometric checks as the detector. They are exact
   and free.
2. The "nudge N px left/right" idea fails: direction is at chance even for 24 px shifts on zoomed crops.
   Offsets are better found by code, e.g. aligning a part's mask to the master or its socket.
3. The one usable signal is a **regression check between fix rounds** on whole frames (10/11 on real
   before/after pairs). The n is small: validate on more rounds before gating anything on it. It costs about $0.00004 per
   pair (both orders) and about 1-2 s.
4. Not yet tried: Clef 27B (`@cf/cloudflare/clef`, about 6x the price, still inside the free tier for a run this size),
   multi-image with the master *crop* aligned to the same joint, and calibration on a larger pool of real rejected frames.

## Reproduce
```
uv run scripts/gen.py <dir>          # synthetic set (needs repo spine_qa)
uv run scripts/slice_real.py <dir>   # real before/after tiles
python3 scripts/run.py <dir> solo|ref|pair|joint --backend cloudflare [--sample synthetic120] [--swap 1]
python3 scripts/score.py <dir> <results.jsonl>; python3 scripts/score2.py
```
Credentials: `~/.config/clef/cloudflare.env` (`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_AUTH_TOKEN`, mode 600).
The paths in `score2.py` and `joints.py` assume the scratch layout (`real/`, `data/`, `data/joints/`).

## Round 2 (2026-10-13): joint close-ups with the master crop as reference
- **Setup:** setup pose only (`scripts/joints_ref.py`), using a snapshot of the T20 rigs.
  - Each crop is a square centred on the bone's attachment point, rendered at 1600 px with doubled shifts, so defect sizes match round 1 and the render is as sharp as the master.
  - The same box is mapped onto the master through `report.json` `master_frame`.
  - 363 crops: 180 shifted 8/16/24 px in 4 directions, 183 untouched.
  - Both conditions ran on the identical crops with the same two questions.
- **Render crop only:** AUROC **0.65** (0.59-0.71), rising with the shift (0.58 / 0.66 / 0.71). Catches 21% at 10% false alarms. Direction 26%.
- **Master crop + render crop:** AUROC **0.62** (0.56-0.67). Catches 31% at 10% false alarms. Direction 21%. The model answers "up" for most shifts.
- **Pattern:**
  - Clef reacts to visible gaps (boot out of the trouser leg 0.80-0.82 vs clean 0.64; hand down out of the cuff 0.71 vs 0.50).
  - A part pushed into its neighbour scores like clean. Head, hoof and antler shifts barely register.
  - The master doesn't help because the clean rig already differs from it. With the master, tail answers are a flat 0.32.
- **Code baseline:** phase correlation of the master crop against the render crop gets direction right 43% (48% at 24 px). Registering the moved part's own mask should do better.
- **Files:** `results/round2/`. 726 calls, about 0.5M tokens, inside the free tier.

## Round 3 (2026-10-13): Clef 27B (`@cf/cloudflare/clef`) on the same items
982 calls, 978k tokens, about 21.3k Neurons, median 0.83 s. Full table: `results/clef27b/compare.txt`.

| Condition | AUROC Flash | AUROC 27B | Direction Flash / 27B |
|---|---|---|---|
| Joint crop, render only | 0.65 | 0.62 | 26% / 27% |
| Joint crop + master crop | 0.62 | 0.63 | 21% / 29% |
| Full frame, planted | 0.38 | 0.41 | 24% / 27% |
| Full frame, real reviewed | 0.61 | 0.63 | n/a |
| Pairwise, both orders | 15/19 | **17/19** | n/a |

- **Detection and direction:** no better on 27B. It answers "down" for most shifts, where Flash answered "up".
- **Pairwise is the one gain:**
  - Full-body pairs: mean P(correct) 0.66 → 0.76, every fox pair ≥ 0.80.
  - Sleeve pairs: 0.55 → 0.60, so the 7/8 is only marginal.
  - The "image 1" position bias fell from 71% to 58%.

## Round 4 (2026-10-15): Jev 1.14 (TypeSafe) with the new Box question
- **Setup:**
  - `jev-1.14.0`, `TypeSafe-Danger-Zone-Images: true`, images as base64 `assets` referenced from `state` (`scripts/run_jev.py`).
  - Same items and question wording as the Clef runs, plus Box questions:
    - joint crops: the moved part in `render`, and in `master` too in the with-master condition
    - full frames: "the part that looks wrong"
  - Ground-truth part boxes come from the rig layers (`labels_gt.jsonl`).
  - 982 calls, 1.75M tokens, about $0.07.
- **Detection (AUROC), Flash / 27B / Jev:**

  | Condition | Flash | 27B | Jev |
  |---|---|---|---|
  | Joint crop, render only | 0.65 | 0.62 | 0.54 |
  | Joint crop + master crop | 0.62 | 0.63 | 0.65 |
  | Full frame, planted | 0.38 | 0.41 | 0.45 |
  | **Real rejected frames, all** | 0.61 | 0.63 | **0.84** |
  | **Real rejected frames, full body** | 0.73 | 0.76 | **0.99** (CI 0.94-1.00) |
  | Real rejected frames, sleeves | 0.42 | 0.42 | 0.62 (CI 0.31-0.91) |

- **Pairwise, both orders:** 15/19. Full body 11/11 (mean 0.82); sleeves 4/8. No "image 1" position bias (18/38).
- **Box localisation:**
  - Mean IoU 0.50 with the true part; 53% of boxes at IoU ≥ 0.5; 0.63 for parts fully inside the crop.
  - Box confidence is low (0.03-0.19), barely ranks box quality (rank correlation 0.33 render-only, 0.00 with master), and is miscalibrated as a probability (ECE 0.37-0.48).
- **Box for the fix direction** (render box minus master box):
  - Right on 34% of the 156 shifts a box can show. Perfect boxes get 100%.
  - Box edges are off by a median 9% of the crop, while the shifts move edges 6/11/17% of the crop. Too coarse for 8-24 px offsets.
- **Box pointing at the defect in full frames:** centre inside the changed region 20%, against about 7% by chance.
- **Files:** `results/jev/`, `compare.txt`.

## Round 5 (2026-10-15): label audit, new real-world tests, page rebuilt with three models per test
- **Label audit:**
  - The 183 clean joint crops are only 15 distinct images (one per joint of the approved setup pose).
  - Four don't match the master: the fox hands (glove off-centre in the cuff, a deferred T20 issue) and the moose hands (furry wrist band, glove turned).
  - Joint-crop results are now reported both as labelled and audited, with those four removed from the clean set (`results/round5/audit_clean.png`).
  - Audited AUROC, joint crop + master: Flash 0.66, 27B 0.78, **Jev 0.82**.
- **Master boxes:** Jev's hand boxes on the master contain both of the hand-placed wrist and fingertip landmarks 79% of the time. The earlier master IoU was against the rig's position and understated it.
- **New test, three rig generations** (`scripts/gen_rounds.py`):
  - Oldest build (fox-parts/moose-parts), previous build (part-variants), approved: 19 poses, 96 frames, 58 pairs.
  - One frame at a time (AUROC):

    | Model | All | Previous build vs approved | Oldest build vs approved | Fox | Moose |
    |---|---|---|---|---|---|
    | Flash | 0.62 | | | | |
    | 27B | 0.67 | | | | |
    | **Jev** | **0.89** (0.83-0.95) | 1.00 | 0.69 | 0.98 | 0.75 |

  - Pairs (which is worse, both orders): Flash 52/58, 27B 51/58, Jev 49/58. Jev is weaker on oldest-build pairs (11/20).
- **New test, joint crop against the previous render** (exact ground truth on both sides):

  | Model | Says "moved" on shifted crops | Mean on identical pairs | Direction |
  |---|---|---|---|
  | Flash | 7% | | 27% |
  | 27B | 56% | | 28% |
  | **Jev** | **91%** | 0.04 | 34% (43% at 24 px) |

- **Box:**
  - Direction from two boxes stays around 33-37% (master, previous render, same or separate requests).
  - Two-pass Box (crop tight around the first box, box again) didn't help: IoU 0.49 → 0.48.
  - TypeSafe rejects images with a side of 256-277 px despite the documented 256 px minimum; 320 px works.
- **Page:** rebuilt as `rig-judge-trial.html` (local copy in this folder), every test compared across all three models.
- **Spend this round:** Flash $0.06, 27B $0.34, Jev $0.12 cumulative.
