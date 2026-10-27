# Experiment 2026-10-11: rigs built from confirmed annotations

**Problem (art director, on the part-variants rigs):**
- Fox: the hands looked attached backwards, the arms sat in the wrong place, the boots looked detached, and there were hairline gaps at the torso, hips and legs.
- Moose: the point gesture turned the hand thumb-down, brown filler showed round the legs, and the rounded shoulders looked stitched on.

**Goal:** the agent annotates every piece (joints, side, painted face, layers), the user confirms each sheet at a checkpoint, and code builds the rig from the confirmed annotations instead of guessing. Design: [`docs/superpowers/specs/2026-10-11-rig-annotations-design.md`](../../docs/superpowers/specs/2026-10-11-rig-annotations-design.md).

Both rigs were approved by the art director after four review rounds. Both pass all 15 `spine_qa` checks:
- structure, setup, seams, thumbs, sockets, landmarks, layer order;
- all 8 animations.

The fox's sleeves were also checked in the Spine 4.2 web player.

## What was wrong, and the fix

| Defect | Cause | Fix |
|---|---|---|
| Hands backwards; point thumb-down | Hand side and mirror were picked by eye in `prep.py`; nothing recorded which way the thumb or palm faced | Each hand is annotated with its painted face (palm/back) and thumb tip. The mirror follows anatomy: for a left hand, thumb on the picture right if palm, left if back. Point and thumbs-up choose an outward or across-body pose that keeps the thumb up. New palm-facing point and fist drawings were generated and annotated in two follow-up sessions. |
| Arms in the wrong place, stitched shoulders | Pivots guessed from blob shape; arms always drawn over the torso | The shoulder, elbow and wrist come from the master points. Each character's sleeves sit under the straps or vest (picked from an A/B). |
| Boots detached | Boot drawn whole in front of the trouser leg | Worn-item split (Spine's "front and back layers" practice): the boot's inside goes behind the trousers and the shell in front. The trouser legs are narrowed so they fit the openings. |
| Moose brown filler | Leg tubes wider than the hips' openings, sticking out below the hooves | The generated leg tubes are not used; the moose's trousers cover the hoof cuffs. |
| Hairline gaps | `solidify` froze the grey anti-aliased edge band into opaque pixels | The cleaned edges are now coloured from the inside; a new `seams` check catches these lines. |
| Elbows showing round caps when bent (found in review) | Two rigid pieces per arm | One whole-sleeve drawing per character, rigged as a two-bone weighted mesh. The fit is solved so it never folds over the bends the animations use. Width is fitted to the master, and the elbow is round. |

## Checkpoints

| # | What the user confirmed | Decisions |
|---|---|---|
| 1 | Master joint points and hands, both characters | Leave out both characters' generated leg tubes |
| 2–5 | Body, hands, poses and face sheets | Painted-face labels corrected: fox open hand = back, both thumbs-ups = palm |
| Sleeves | Whole-sleeve pieces for the mesh arms | — |
| 6 (4 rounds) | Rig frames, before and after | Sleeves under the straps or vest; fox shoulders raised 1.5% and tucked 1.5% (from a 3×3 grid); fox legs in the boots with a narrower stance; moose cuff drawn over the glove |

## Numbers

| | Fox | Moose |
|---|---|---|
| Setup IoU vs master | 0.902 | 0.873 |
| Thumb error at holds (point, thumbs-up, hold-card) | 5°, 10°, 10° | 5°, 10°, 10° |
| Doubts left in `rig/report.json` | ground_miss ×2, hips_too_wide, shoulder_mismatch ×2, matcher ×2, worn_opening_guessed ×2 | shoulder_outside_torso ×2 |

The remaining doubts are known trade-offs:
- the fox's boots and hips are clamped at their size limits;
- the tiptoe boots have no painted inside, so their cut is fitted to the top silhouette;
- the moose's master shoulders sit outside its torso piece.

## Files

- `fox/`, `moose/`: `annotations.json` (confirmed), `draft_annotations.py` (how the first draft was read off the pieces), `annotations/` (checkpoint pictures), `rig/` (Spine 4.2 skeleton, atlas, images, `qa/`)
- `before_after_fox.png`, `before_after_moose.png`, `before_after_closeups.png`: the old part-variants rig against this rig
- `shoulders_ab_*.png`, `fox_shoulder_grid.png`, `moose_hand_layer_ab.png`, `hands_painted_side.png`: the pictures used for each decision

## Still open

- **Fox stance:** the trouser legs are narrower than the master's spacing, and the tiptoe boots touch in cheer. Regenerating the hips with narrower legs would fix both.
- **Moose crease:** a small scarf-coloured fillet shows in the hold-card elbow crease, as in the approved build.
- **Fox cuffs:** the paw sits slightly off-centre in its cuff after the sleeve fit (socket offset 0.32/0.37, limit 1.0).
- **Mesh weights:** the sleeve weights are solved, so change them by editing the annotation and rebuilding, not by hand in the Spine editor.
