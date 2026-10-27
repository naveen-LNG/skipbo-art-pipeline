# Red panda through the pipeline (2026-10-16)

Workstream C of [Spine Pro + new cast](../../2026-10-16-spine-pro/PLAN.md): a red panda explorer from text only, through the existing pipeline, with the beaver's lessons applied up front. The ringed tail is the star: the pro-rig workstream turns it into a bending chain, so it had to be fully visible and one clean shape.

**Result.**
- `spine_qa.py rig/redpanda.json --master redpanda_master.png`: **all 20 checks pass**, silhouette IoU 0.908 (`rig/spine_qa.txt`).
- Nano Banana Pro: **10 images in 9 jobs**, of the 14 budgeted.
- `jev_qa.py` (optional) gives **one FAIL**: the point hold's thumb isn't up. The thumb is folded across the palm, as the prompt asked; see "What still looks off".
- `./rebuild.sh` rebuilds `rig/` from the split sheets: local art fixes, annotations, sheet checks, build, `spine_qa` and the joints, onion and motion sheets.

![frames](frames.png)

`frames.png` shows setup, wave, point, thumbs_up, cheer_jump, hold_card, walk, run, squat, jump_hurdle, wave_flag and emotions. GIFs and strips of every animation are in `rig/qa/`.

## Nano Banana Pro calls

| # | Tag | Images | Purpose | Outcome |
|---|---|---|---|---|
| 1 | `redpanda-master` | 2 | Text-only master (`master-textonly.txt`, `--n 2`) | Both pass `--contract`. 01 kept: its tail curves up beside the body, fully visible. In 00 the tail curls behind the boot |
| 2 | `redpanda-body` | 1 | Body sheet | "Hips" came back as the whole trousers, the arms as whole sleeves, the ears as pointed horn shapes. Used: torso, trousers, paws, boots, tail, head base |
| 3 | `redpanda-hands` | 1 | Hands sheet, fist and point asked palm-facing | Fist palm-facing (first time on any character). Point back-facing. Row 2 is unmirrored, some of it wrist-down: spare |
| 4 | `redpanda-poses` | 1 | Tiptoe boots and a second tail | Tiptoes used; the tail is spare |
| 5 | `redpanda-face` | 1 | 9 expression heads | All used |
| 6 | `redpanda-sleeves` | 1 | `sleeves-pair.txt` | Both sleeves used (widened locally) |
| 7 | `redpanda-props` | 1 | `props-pair.txt`: flag and hurdle | Flag used. The hurdle had a ghost boot in its foot, so it was mirrored from its clean half |
| 8 | `redpanda-point-palm` | 1 | `hands-point-palm.txt` | Back-facing again (Jev cue score -0.42), plus a ghost boot fragment. Not used |
| 9 | `redpanda-point-palm2` | 1 | The same template, with the palm cues spelled out in `HANDS` (`POINT2`) | Palm pad, fingertips and the folded thumb all show (Jev +0.35). Used |

No prompt ran twice. Every prompt is in `prompts/redpanda.env`, and the scripts are `scripts/gen_sheets.sh` and `scripts/gen_fixes.sh`.

## Checkpoints (self-approved, no one to ask overnight)

| # | Checkpoint | What I looked at | Decision |
|---|---|---|---|
| 0 | Master | Both variants side by side; `spine_qa --contract` (01: flat bg, no shadow, centred, leg gap 28.8%, arm gaps 38/100% of rows); head front-facing; colour contrast (mustard sleeve / dark mitten / olive trousers / brown boots) | 01 approved. Risk noted: the left mitten overlaps the tail's lower bend |
| 1 | Master points | `annotations/master_overlay.png` and the gridded master. Thumbs lateral and palm, as painted. `upperarm: under_torso` (jacket over the sleeve tops, as on the beaver) | Approved. Shoulders, wrists, fingertips, waist and ankles were later moved by rig review (status `fixed`) |
| 2 | Body sheet | `redpanda-body-parts_overlay.png`; the gridded pieces; `locate.py` for the sides | Approved, with the substitutions below |
| 3 | Hands | `redpanda-hands-parts_worn.png` and `point-palm2_worn.png` (all thumbs ticked); `check --jev` | Approved. Two doubts answered "correct as annotated": the rest left mitten (Jev -0.21, "back") stays palm, because a plain mitten with its thumb lateral is a palm by anatomy and matches the master; the grip at confidence 0.5 passes the thumbs check at hold_card |
| 4 | Poses, sleeves, ears, face | Overlays and worn strips | Approved |
| 6 | Rig | `spine_qa` 20/20; `frames.png`; `rig/qa/joints.png`, `onion.png`, `motion.png` every round; `jev_qa.py` summary | Approved with the open issues below |

`annotations.json`: master `fixed`; pieces 13 `confirmed`, 15 `fixed` (changed in a review round, each with a note), 34 `ignored` (spares, with a reason). `--allow-proposed` was used only for the first exploratory build.

## Fix rounds

| Failure (how found) | Cause | Fix |
|---|---|---|
| Body sheet ears unusable (by eye) | Pointed horn shapes turned ~150 deg, outside the matcher's +-90 deg. The face heads have no ears | `make_ears.py`: the master's ears, each with a 34 px band of head fur under its base, hidden behind the head |
| Point back-facing, twice (by eye, Jev -0.42) | The model's default for this pose | Palm cues described in `HANDS` (call 9) |
| `structure`: tail, hips and torso pivots off, weak torso joint | The hips waist sat in the belt's centre dip, and the jacket hem met the belt edge to edge | `make_trousers.py`: a belt-coloured band above the belt, hidden under the jacket. Hips waist inside it; torso waist just above its hem. Moving the torso down instead hid half the belt |
| `sleeve_too_thin` 1.32 both sides; `sockets` hand spill 6.2% | The master's lower sleeves are fatter than the drawing, and the fit only narrows | `make_sleeve_wide.py`: tapered 1.36x from the elbow. A first ramp starting lower left 1.22-1.26, because the fit measures 25-45% below the elbow |
| `walk`/`run`: boots detached, then `run`/`jump_hurdle` unstitched (0.18; 3.2x) | The boots are exactly as tall as the master's visible boots, so nothing was under the trousers | `make_boots.py`: the shaft stretched 130 px; master ankle at 0.745, well above the hem (E 40 and E 90 were not enough) |
| Boots 35 px inward (onion) | The ankle x was read by eye at 0.45; the shaft's measured centre is 0.345 | Measured centres |
| Wide shorts, crotch too low (onion) | The sheet's crotch is at 0.58 of the piece (master ~0.50), and its leg gap is half as wide | `make_trousers.py`: crotch cut higher and wider, inner edges shaded; legs carried straight to 0.91 (the boot rims had peeked beside tapering hems) |
| Cheer tiptoes ~1.2x too big (frames) | Variants are scaled to the rest boot by area, and the taller rest boots raised that area | Tiptoes padded with a repeated full-width shaft row to the same area growth (stretching their narrow tilted top made a cone) |
| `sockets` right hand spill 4.4 → 3.5% | Mitten wide for its cuff, hanging at its own 44 deg against the sleeve's 16 deg | Hands 0.9x; the right fingertip turned a third of the way toward the sleeve (the beaver's rule): 1.5% |
| `seams` hand_l/tail 0.10-0.14 | A 1-2 px grey rim inside the mittens' opaque edge, over the cream tail tip (`wave_flag` mid, found with `scripts/seam_debug.py`) | `make_paws.py`: the rim recoloured from inside, edge pulled in 1 px, on the rest paws and the hand variants: 0.059 |

## What still looks off

- **Jev hold FAIL on point:** P(thumb up) 0.27. The palm-facing point has its thumb folded across the palm, so no thumb sticks up. Jev reads it as a point (P 0.90), and `spine_qa`'s geometric thumb is 5 deg from up. One more call asking for "the thumb sticking up along the side of the hand" would clear it.
- **Jev joints WARN:** both ankles (2.32 / 2.11, approved max 1.81) and the tail (1.72 vs 1.32).
  - Ankles: below each hem the rig shows plain stretched shaft where the master shows laces. There is also a small step on each leg's outer edge at 0.91, where the straightened leg meets the painted rounded hem.
  - Tail: the generated tail's rings fall in different places from the master's.
- **Frames:** mean P(defect) 0.69 against 0.56 for the approved rigs. The top of the review list is jump_hurdle (arms out, small hurdle), thumbs_up and wave (a dark mitten in front of the rust tail, low contrast).
- **Mittens:** at rest they are about 0.85x the master's and sit a little further out along the sleeve (onion arm rows). Larger ones spilled past the cuff.
- **Shoulders:** the torso piece's painted side shading shows as a soft dark oval where each sleeve goes under the jacket. The master has a smooth shoulder.
- **hold_card:** the grip reads as a fist on the belly (Jev WARN "may be the other hand"; known on every character).
- **Ears:** cut from the master, not generated. They are fine at the small idle and cheer turns, but they would show their hidden band if turned past ~10 deg.

## Pipeline issues found

- **The body sheet's hips came out as the whole trousers.** The `body-sheet.txt` cutting rules ("each leg in two") fight PIECES that ask for leg-less hips. The model painted belt-to-hem trousers anyway. That suits this character, but the rig then has no knees or crotch control. Handled locally (`make_trousers.py`).
- **Boots as tall as the master's visible boots leave no overlap under the trousers.** Foot ground-matching scales the boot to the visible height, so feet under the hips detach in `run`. A "boot shaft extends up under the trousers" phrase in PIECES, or a rig-side hidden extension, would fix it upstream (`make_boots.py` here).
- **Area-matched foot variants inherit any change to the rest foot's area.** Tiptoes grew 1.2x after the rest boots were extended. Matching by width at the sole would be robust.
- **The `seams` check flags grey rims inside a piece's opaque edge**, which rig cleaning (alpha 250+ trusted) keeps. A one-pixel recolour at `check` time would remove them for every piece.
- **zsh eats `:r` in `$R:run:0.1`** when calling `tools/render_frames.py` (history modifier). Quote it as `"${R}:run:0.1"`; the README examples use bare `rig/x.json:anim:t`, which is fine.
- `spine_qa` takes about 5 minutes on this rig: 13 animations and a 2400 px master.

## Files

| Path | What |
|---|---|
| `redpanda_master.png` | Approved master (`runs/redpanda-master/*_01.png`) |
| `prompts/redpanda.env` | CHARACTER, PIECES, HANDS, POSES, SLEEVE, PROPS, POINT, POINT2 |
| `scripts/gen_sheets.sh`, `scripts/gen_fixes.sh` | The Nano Banana Pro jobs, each followed by `parts-split` |
| `scripts/make_{ears,props,sleeve_wide,boots,trousers,paws}.py` | Local art fixes (see Fix rounds); each writes its own `runs/redpanda-*-parts/` |
| `draft_annotations.py` | All annotation points, with notes; `rebuild.sh` records the checkpoint decisions |
| `scripts/{grid_image,grid_pieces,locate,measure_master,seam_debug}.py` | Reading points by eye, sides by sheet position, colour measurement of the master, per-frame seam scores |
| `props.json`, `props/` | Flag (held) and hurdle (ground) for `wave_flag` and `jump_hurdle` |
| `rig/` | `redpanda.json`, atlas, images, `report.json`, `spine_qa.txt`, `qa/` (GIFs, strips, `joints.png`, `onion.png`, `motion.png`, `jev/`) |
| `frames.png` | The frame grid above |
