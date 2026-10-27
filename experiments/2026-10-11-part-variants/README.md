# Experiment 2026-10-11: generated part variants instead of master cut-outs

**Problem (art director):**
- Faces animated well, but arms looked glued to the body when raised (fox and moose).
- The fox's tail looked drawn over its leg.
- Most limbs were being cut out of the master instead of using generated parts.

**Goal:** generate every rig part, plus a minimum set of pose variants per part (as already done for expressions), and swap the variants in the animations.

## What was wrong

| Symptom | Cause in the old rig |
|---|---|
| Arms glued at the shoulder | Upper arms were cut from the master and kept a flat straight edge where the sleeve touched the body. There was no round shoulder for that edge to turn on, and only one drawing of the arm, which was rotated |
| Tail in front of the leg | Draw order was already right (tail first). The leg cut excluded every pixel under the generated tail, leaving a notch the tail showed through |
| "Extraction" | 12 of the fox's 15 pieces were master cuts. The generated limbs were used only to find where to cut |

## References used

- **Spine, "How to cut your assets for animation":** joint overlaps as circular as possible, limbs drawn straight, hidden areas painted.
- **Cut-out practice (Adobe Character Animator and Toon Boom forums and docs):** a two-circle joint with the pivot at the centre "never breaks"; an upper arm the same width up to the shoulder, ending in a semicircle.
- **Spine, "Rigging new poses"; Moho switch layers; Live2D arm groups:** when rotation runs out, swap in new art, keyed mid-motion.
- **Cartoon Animator G3:** 30 hand sprites in Natural / Hold / Point / Open groups. **Toon Boom:** hand swap libraries. **Our reference rig pack:** fist, point, two-point, thumb up, flat.
- **Spine slots and draw-order keys:** tails at the bottom of the stack.

This became the minimum variant set: 5 hands per side, a raised sleeve, a tiptoe foot and a tail up. See `plugin/skills/skipbo-art/references/spine-parts.md`.

## Pipeline changes

- **Prompts:**
  - `body-sheet.txt` v2: limbs upright with the joint end at the top, every joining end round, torso painted with the arms removed (rounded shoulders, sides painted), hips including the crotch.
  - New `hands-sheet.txt` (6 poses × 2 hands) and `poses-sheet.txt` (piece + variant rows).
- **`spine_rig.py`:**
  - Generated parts by default (`--cut-from-master` keeps the old path).
  - Limbs pinned like a cut-out with concentric round ends; feet ground-anchored; legs assembled from the boot up; hands sized to the master.
  - Piece ends told apart by painted orientation.
  - New draw order: arms in front of the torso, tail behind everything.
  - `--variants` attachments, aligned at the joint and scaled per kind.
  - Enclosed thin alpha made opaque; edge colours decontaminated.
  - New `thumbs_up`, `point` and `hold_card` animations; swaps in `wave` and `cheer_jump`.
- **`spine_qa.py`:**
  - `stitched` measured locally at the joint, with a per-attachment baseline.
  - Setup IoU in the master's frame.
  - Fragments and slivers checked on every attachment.
  - New `draw_order` and `variant_misfit` checks; `occluded` also catches tucked parts losing most of what showed.
- **`tools/render_frames.py`:** a labelled frame grid for checking poses by eye.

## Results

Both rigs pass every check: structure, setup and all 8 animations.

| | Fox | Moose |
|---|---|---|
| Setup IoU vs master | 0.900 | 0.883 |
| Pieces from the master | 0 (was 12) | 0 (was 13) |
| Variant attachments | 15 | 14 (no tail) |
| Nano Banana Pro calls | 5 | 6 |

- Before/after at the cheer apex: [`before_after_cheer.png`](before_after_cheer.png) (old fox, new fox, old moose, new moose).
- The new gestures: [`new_gestures.png`](new_gestures.png).
- Rigs: [`fox/rig/`](fox/rig/), [`moose/rig/`](moose/rig/), with QA GIFs in `rig/qa/`.

**Found by looking at frames after the metrics passed:**
1. a boot matched onto the orange tail;
2. legs matched up into the torso;
3. hands drawn too small and hidden under the cuff;
4. a raised sleeve covering its forearm;
5. a thumbs-up pointing down (the wrist was found from a sideways axis);
6. a forearm attached backwards;
7. a bell on the muzzle;
8. a paw hidden under the scarf;
9. see-through eye whites on the fox's `sad` head (an old defect: the old QA checked only the active head).

Each one now has a fix in the rig and, where measurable, a QA check (`occluded` for 3, 4 and 8; `slivers` on every attachment for 9).

**Generation notes:**
- Fox: the first hands sheet drew realistic five-finger hands; the fix was naming the mitten shape and wrist-up for every pose. The arm row needed "only the sleeve from shoulder to elbow, without any cuff".
- Moose: three body passes. The torso, legs and hooves merged until the prompt named where each piece ends (belt, hem). The final rig mixes two same-scale sheets.

**Still open:**
- The fox's generated torso is wider than the master's. It's within the IoU gate, but it's a visible difference.
- The `spine-parts` template and server workflow file now include the hands and poses sheets (built by `tools/build_spine_workflow.py`) and are published to the server.
- Whether a pose *reads* still needs eyes.
