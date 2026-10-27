# Bear: a chunky character through the pipeline (2026-10-16)

Goal: a new character from text through the existing character-to-Spine pipeline. The bear is big, round and heavy, unlike the slim fox and beaver, to test wide proportions. The beaver's lessons were applied from the start. Workstream D of [`../../2026-10-16-spine-pro/PLAN.md`](../../2026-10-16-spine-pro/PLAN.md).

**Verdict.**
- **QA:** `spine_qa.py rig/bear.json --master bear_master.png` passes all 20 checks (`qa.log`).
- **Calls:** 9 Nano Banana Pro calls of the 14 budgeted, with no third seed. The one fix call was a palm-facing point, with changed words.
- **Looks:** the frames read well, and the rig matches the master closely (silhouette IoU 0.918).
- **What the wide body broke:** the body sheet's torso came back ~1.2x too wide for its height, its lower body came back as shorts at 2/3 of the master's height, and feet under wide trouser hems barely overlap them. All three were fixed with experiment-local scripts; none needed a new call.

![final frames](frames_final.png)

More poses: `frames_motion.png`. Review sheets: `rig/qa/{joints,onion,motion}.png`. GIFs: `rig/qa/<anim>.gif`.

## The bear
- **Master** (`runs/bear-master/`, `prompts/bear.env` `MASTER_CHARACTER`): `master-textonly.txt`, one call with 2 variants. Both passed `spine_qa.py --contract`: leg gap 24.6% / 23.1%, arm gaps 72-89%.
  - Picked 00, because 01 drew a bib apron over the torso.
  - Variant 00 has the sleeves rolled to the elbow, not mid-forearm. The sheets got a second `CHARACTER` that describes the master as painted, because a sheet's CHARACTER NOTES override image_1.
- **The apron, planned before the sheets:** part of the hips piece, not a piece of its own. It is tied at the waist and only lies over the trousers. So one hips piece (waistband + apron + trousers to the hems) sits over the clogs (`foot: under_hips`), under the shirt, and needs no new role or layer.
- **Colour contrast**, checked by eye on the master:
  - shirt = sleeve (both white, so the arms are `upperarm: under_torso`);
  - forearm fur (honey) ≠ mitten (chocolate, prompted "darker than the fur");
  - trousers ≠ clogs.
- **Sheets:** 6 calls in parallel (`gen_sheets.sh`): body, hands, poses (tiptoe clogs only: no tail, and whole-arm meshes skip the raised sleeve), face, whole arms, props.

## Nano Banana Pro calls

| # | Tag | Purpose | Result |
|---|---|---|---|
| 1-2 | `bear-master` (`--n 2`, which `comfy.py` bills as 2 calls) | Text-only master | 00 used |
| 3 | `bear-body` | Body sheet: head, ears, torso, "whole lower body as ONE piece", 2-piece arms, paws, clogs | Head, ears, rest paws, clogs and torso used. The lower body came back as shorts |
| 4 | `bear-hands` | Hands, fist and point asked palm-facing | Row 1 used: all wrist-up, and the fist and point came back palm-facing. Row 2 painted 3 poses upside down |
| 5 | `bear-poses` | Tiptoe clogs | A tilted side view, plus 3 ghost smudges (not split). Used, then dropped in round 5 |
| 6 | `bear-face` | 9 expression heads | All used. The heads include the ears, so the ear pieces drop |
| 7 | `bear-arms` | Whole arms (`prompts/arms-pair.txt`, a copy of `sleeves-pair.txt` that asks for the arm down to a furry wrist) | Used after trimming: it painted a honey fur paw at each arm's end |
| 8 | `bear-props` | Flag + hurdle (`props-pair.txt`) | Both used |
| 9 | `bear-point-palm` | Palm-facing point (`hands-point-palm.txt`, `POINT` in `bear.env`): the sheet's point was back-facing | 00 used: palm pad visible, thumb out to the side |

## Checkpoints (self-approved; nobody was available to ask)

| # | What I looked at | Decision |
|---|---|---|
| 0 master | Both variants side by side, `spine_qa --contract` | 00: waist apron as specified, head front, no tail, no hat, paws empty |
| 1 master points | `annotations/master_overlay.png` | Approved. Shoulders inside the shirt's shoulder, elbows at the roll's centre, wrists at the mitten tops (the mitten is drawn over the forearm), hands `back`/medial, layers `upperarm: under_torso`, `hand: over_forearm`, `foot: under_hips` |
| 2 body | `bear-body-parts_overlay.png`, `bear-arm-parts_overlay.png`, gridded pieces | Approved. Rest paws, clogs, head, ears; the sheet's torso, hips and 2-piece arms ignored, each with a note |
| 3 hands | `bear-hands-parts_worn.png` | Approved. Every gesture is ticked: thumbs up for point, thumbs-up and grip; palm fists for cheer. The grip (conf 0.5) reads as an OK ring at hold_card, which is fine. **My miss:** I labelled the sheet's point palm, but it shows the back of the hand (knuckle bumps, thumb tucked behind). The worn strip ticked it, because it trusts the label. Jev's hold check caught it in round 10, and the re-roll's worn strip is ticked on both sides |
| 4 poses | `bear-poses-parts_overlay.png` | Approved in round 1, then dropped in round 5 (giant clog, below) |
| 5 faces | Face sheet against `tools/locate.py` grid order | Approved: 9 expressions, mapped by sheet position |
| 6 rig | `frames_final.png`, `frames_motion.png`, `rig/qa/{joints,onion,motion}.png`, GIF strips, `jev_qa.py` | Approved after round 9, with the open items below |

Snap failures kept their rough points: the arm shoulders (the cap isn't a circle), the clog ankles and the grip wrist. Each rough point was checked on its overlay.

## Experiment-local pieces (`make_parts.py`, rebuilt by `rebuild.sh`)

| Piece | Why | What |
|---|---|---|
| `runs/bear-torso-parts/` | The global scale comes from neck-to-waist (1.079). At that scale the sheet's shirt is ~1.2x the master's width, and since the arms are under the torso, it also swallowed the sleeve tops | Narrowed 0.86 across, to the master's shirt width just above the waistband |
| `runs/bear-trousers-parts/` | The body sheet's lower body is shorts at 2/3 of the master's height (the beaver's first failure, again) | Cut from the master: waistband + apron + trousers to the hems, painted at the rig's scale. It has no cut joint edge. Its top runs 60 px up under the shirt. The clog-toe notch in each hem is repainted with the hem's own profile, and the outline is defringed |
| `runs/bear-arm-parts/` | The arms sheet painted a fur paw on each arm | Cut at the forearm's narrowest row, with a rounded end. The mitten is drawn over it |
| `runs/bear-clog-parts/` | The side-view clogs are ~0.9x the master's length, and their tops sat only ~50 px under the wide hems | Widened 1.10, plus a hidden honey-fur ankle stub above the heel opening. Below a lifted hem it reads as the bear's ankle. The pivot sits up in the stub |
| `props/` | The hurdle's grey split rim left a seam over the trousers (0.11) | Rim pixels take the nearest solid colour |

The master cut breaks the "every piece is generated" rule on purpose. That rule exists because cut edges at moving joints look glued on. This piece has no such edge: the shirt hem covers its top, and its hems cover the clogs. It is also why the waist and legs match the master pixel for pixel on the onion sheet.

## Fix rounds (failure / cause / fix)

| Round | Failure | Cause | Fix |
|---|---|---|---|
| 1 | `structure`: torso pivot off the hips, torso-hips overlap 0 px; a background hairline at the waist | The shirt's rounded hem met the waistband's curved top edge to edge | The trousers piece carries the master's shirt under the torso (top at 0.497) |
| 2 | Still off: the trousers piece started below the waist | The shirt's shaded hem is within 18 RGB of the grey background, so the colour key dropped it | Take the shirt above the band by position, not colour |
| 2 | Clogs detached, `ground_miss` 0.73 | I lowered the master ankles to offset a socket push that doesn't exist | Reverted; measured the clogs in the master frame instead (`tools/measure_rig.py`) |
| 3 | `seams` hips/clog 0.07 | The master cut's outline pixels hold the background grey | The outer 3 px take colours from 3 px inside |
| 4 | `seams` hips/hurdle 0.11 | The hurdle split's soft grey rim | Defringed the props |
| 4 | `unstitched` clogs in walk/run (overlap 0.23x) | The hips bob up and the clog tops sat only ~50 px under the hems | Hidden fur ankle stub on each clog |
| 5 | Giant tiptoe clogs in cheer_jump (found in the Spine web player by the gallery agent); `variant_misfit` once the stub was added | **Pipeline:** the tiptoe variant got `scaleX` 3.17. Its snapped opening (137 px) was measured against the rest clog's unsnapped cross width (362 px) | Tiptoe dropped (the swap is skipped without it). Verified: no `tiptoe` attachment in `rig/bear.json`, and the cheer_jump frames are normal |
| 6 | `unstitched` clogs in jump_hurdle (overlap 1.8x while the feet are tucked) | The joint disk centred on the heel opening; the tuck slides the clog body into it | Pivot raised 0.17 of the piece into the stub, master ankles 0.026 higher |
| 6 | `jerky_bones` hands in cheer_jump: 0.0121 against a 0.012 limit | I had moved the master wrists 23 px down the arm to offset the hand's push into the cuff, which lengthened the arm's swing radius | Reverted the wrists. The mittens now sit ~20 px higher and further out than the master's |
| 7 | (all pass) Review: the repainted hem notch showed as a lighter block with a seam at both ankles | A flat colour from the rows above | Copy the hem's vertical profile from the nearest clear column, ramped in |
| 8 | `mesh_fold` in wave, hand seam 0.097 | I nudged the wrists 0.004 inward and 0.0045 down to fix the mitten offset | Reverted (round 9 = round 7 + the notch fix): 20/20 |
| 10 | `jev_qa` hold **FAIL**: point thumb not up (P 0.16); `spine_qa` thumbs passed at 5° | The point piece was back-facing and I had labelled it palm, so the rig pointed it outward with the painted thumb hidden | 1 call, `hands-point-palm.txt`. Jev: point reads as point, P(thumb up) 0.74, no FAIL. `spine_qa` 20/20 |

## What still looks off
- **Mittens** sit ~20 px higher and further out than the master's (onion sheet). Moving them broke `jerky_bones` or `mesh_fold`; on this short, fat arm both margins are thin.
- **Shoulders:** the torso's painted armhole shading shows as a crease line where it lies over the sleeve cap. The master's shirt flows into the sleeve.
- **Sleeve mesh:** `mesh_fold_range` doubts on both arms (needs up to 104.6°, covers 95°). `mesh_fold` passes in every animation; the short, fat arm is at its limit.
- **`shoulder_outside_torso` (25 px):** the narrowed torso's shoulders are inside the master's shoulder points. Only the bone origin moved.
- **Hems:** the trouser bottoms are straight lines where the notch was repainted, softer than the master's rounded hems.
- **No tiptoe:** the clogs stay flat in cheer_jump and jump_hurdle flight.
- **Ankle stubs:** below the hems in walk/run they read as plain flat honey fur.
- **Waist:** a tiny kink in the band's top edge at the centre, where the shirt's lowest point meets it (motion sheet).
- **Hurdle:** small next to a bear this wide (0.2 of body height); the jump clears it by little.

## Pipeline issues found
1. **Tiptoe variant scaled 3.2x** (`rig_variants`, feet): a tilted variant's snapped ankle opening is compared with the rest foot's unsnapped cross width. `spine_qa` passed it in round 4: it covered its joint, and its overlap ratio was inside 0.4-2.5. Only the Spine web player showed it. Worked around by dropping the variant.
2. **Global scale from neck-to-waist alone:** a chunky body sheet paints the torso wider for its height than the master. The rig keeps the sheet's width, so a wide character's torso comes out ~1.2x too wide, with nothing raised as a doubt. Worked around by narrowing the torso.
3. **"Whole lower body as ONE piece" still comes back as shorts**, the second character to do so. The body-sheet template says "each leg in two (leg, foot)", which fights a legless trousers piece.
4. **`sleeves-pair.txt` can't express a rolled sleeve over a bare forearm.** A local copy asked for the arm "down to a furry wrist", and the model painted a fur paw there.
5. **Snap gaps:** round-end snap fails on an elongated sleeve cap; opening snap fails on a clog's heel opening and on slanted mitten tops (the rough points are fine).
6. **A hand's `facing` label is trusted everywhere** (worn strip, rig, `spine_qa` thumbs). A wrong label passes them all; only Jev's rendered-hold check caught it. Prompting "palm-facing" in `HANDS` was not enough for the point on this sheet, though it worked for the fist.
7. **No `timeout` on macOS:** my first `timeout 900 uv run … jev_qa.py` silently did nothing. Not a pipeline bug, but worth knowing in run scripts.

## Jev review (`jev_qa.py`, against the approved fox and moose)
See `jev_qa.log` (and `jev_qa_round9.log`), `rig/qa/jev/`.

Round 10 (final build), 230 calls, no FAIL:
- **Joints:** both shoulders score above the approved rigs' worst (2.17 / 2.13 against 1.95), the crease where the torso edge lies over the sleeve cap (see above). The other 8 joints are within the approved range.
- **Pairs** against round 9: all about the same (0.46-0.53), as expected, since only the point hand changed.
- **Holds:** point, thumbs_up, wave and cheer read as intended. hold_card reads as a grip, with a WARN that it "may be drawn as the other hand". By eye it is the OK-ring grip held across the belly, and `spine_qa`'s thumb check gives it 10°.
- **Frames:** mean P(defect) 0.61 against the approved 0.56. Ranked first are thumbs_up 1.0-1.4 s (by eye: the sleeve pinches a little near the shoulder as the elbow bends), run 0.16 s (the fur ankle stub shows below a hem) and hold_card (half-hidden grip, as on every rig).
- **Round 9:** the same, except the point hold FAILed. That was the catch.

## Reproduce
```
./gen_sheets.sh                 # 6 sheet calls (needs bear_master.png); the master call is in the table above
# split each sheet: comfy.py run parts-split --image 1=<sheet> --tag bear-<x>-parts  (COMFY_RUNS_DIR=runs)
./rebuild.sh                    # make_parts.py -> draft_annotations.py -> check -> spine_rig.py -> spine_qa.py
uv run ../../../plugin/skills/skipbo-art/scripts/joint_crops.py rig/bear.json --annotations annotations.json
```
Helpers in `tools/`: `grid_image.py` and `grid_pieces.py` (read points by eye), `locate.py` (sheet positions → sides), `try_snap.py` (where a rough point snaps), `measure_rig.py` (setup bboxes in the master frame), `bones.py`.
