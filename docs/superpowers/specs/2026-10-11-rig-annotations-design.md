# Rig annotations and confirmation checkpoints: design

Date: 2026-10-11. Status: approved in conversation, awaiting written-spec review.

## Problem

The fox and moose rigs (`experiments/2026-10-11-part-variants/`) pass every `spine_qa` check, but the art director found these defects by eye:

| Character | Defect | Cause |
|---|---|---|
| Fox | Hands look attached backwards | Side, mirror and thumb direction of each hand piece are decided by eye in a hand-written `prep.py`; nothing records which way the thumb or palm faces, so no code can catch a wrong pick |
| Fox | Arms not stitched in the right place | The shoulder pivot is guessed from blob geometry; the sleeve sits on top of the torso's shoulder instead of coming out of the armhole under the strap |
| Fox | Boots look detached | The leg's end is never placed inside the boot opening; blue leg shows beside the boot |
| Fox, Moose | Pixel-thin gaps at torso, hips and legs | Not yet diagnosed; leading guess is the soft edge of each cut-out lying over the piece below |
| Moose | `point` turns the hand 180° and points thumb-down | The point variant got the mirror that puts the thumb on the body side (`medial`); held out level, a medial thumb is underneath |
| Moose | Brown filler round the legs | Trouser legs are wider than the hips' leg holes and run out below the hooves; the hoof pieces also include a trouser cuff |
| Moose | Rounded shoulders look stitched | The generated torso has cream shoulder caps, and the sleeve's round top sits on them (a double bulge). In the master the vest armhole covers the sleeve, but the draw order always puts arms over the torso |

Most of these are errors of meaning (which hand, which way the thumb points, that a leg goes *into* a boot) that the code turned into geometry errors.

## Goal

The agent running the skill annotates the master and every generated piece. The user confirms the annotations at checkpoints inside the skill, and code builds the rig from the confirmed annotations instead of guessing.

Success:
1. All seven defects above are gone in the rebuilt fox and moose rigs, shown in before/after frames.
2. `spine_qa` passes, including the new checks below.
3. The checkpoints ran for real on both characters.

**Out of scope:**
- a local annotation model (a later direction; the file format is designed so one can write it);
- a point-dragging annotation editor (same);
- generating new art.

## Division of labour

| Who | Does |
|---|---|
| **The LLM** (the agent, by looking) | Meaning: role, variant, side, thumb tip, palm or back, layer hints, rough points |
| **Code** | Snaps rough points to exact geometry, derives mirror and rotation, places and validates |
| **The user** | Confirms or corrects at checkpoints |

The current colour matcher is kept for two jobs: it drafts rough points, and it cross-checks the placement.

## 1. The annotation file

One `<char>/annotations.json` per character. Annotations sit on the **raw split pieces** (the `parts-split` outputs), keyed `<split-run-dir>/<index>`. Code derives each piece's mirror, rotation and file name, which replaces the hand-written `prep.py`.

```json
{
  "version": 1,
  "character": "fox",
  "master": {
    "image": "fox_master.png",
    "points": {
      "neck": [0.50, 0.38], "waist": [0.50, 0.62],
      "shoulder_l": [0.62, 0.45], "elbow_l": [0.70, 0.52], "wrist_l": [0.76, 0.60], "fingertip_l": [0.82, 0.68],
      "hip_l": [0.56, 0.70], "ankle_l": [0.58, 0.86], "ground": [0.50, 0.97]
    },
    "hands": {"l": {"thumb_side": "lateral", "facing": "palm"}, "r": {"thumb_side": "lateral", "facing": "palm"}},
    "layers": {"upperarm": "over_torso"},
    "status": "confirmed"
  },
  "pieces": {
    "fox-hands-parts/05": {
      "role": "hand", "variant": "point", "side": "either",
      "points": {"wrist": {"at": [0.48, 0.05], "kind": "round_end"}, "thumb_tip": {"at": [0.20, 0.40], "kind": "point"}},
      "facing": "palm",
      "status": "proposed", "confidence": 0.6, "note": "thumb partly hidden"
    },
    "fox-poses-parts/04": {
      "role": "foot", "variant": "tiptoe", "side": "l",
      "points": {"ankle": {"at": [0.50, 0.10], "kind": "opening"}, "ground": {"at": [0.55, 0.95], "kind": "point"}},
      "status": "confirmed", "confidence": 0.9
    }
  }
}
```

**Coordinates**
- They run from 0 to 1 across each source image, so they don't depend on resolution.
- Each point holds the rough `at`. Code adds `snapped` (and, for openings, `width` and `depth`) beside it and never overwrites `at`.

**Point kinds**
- `round_end`: snapped to the centre of the circle that fits the painted round end.
- `opening`: snapped to the centre of a rim, with the opening's width and its depth into the piece.
- `point`: not snapped.

**Joint names are shared.** A master point, a parent's socket and a child's end that meet use the same joint name. For example, the master's `shoulder_l`, the torso's `shoulder_l` (a point: the socket position as annotated) and the upper arm's `shoulder` (a round end) are one joint.

**Required points for each role** (`_l`/`_r` on the parent's sockets):

| Role | Points |
|---|---|
| master | `neck`, `waist`, `shoulder_*`, `elbow_*`, `wrist_*`, `fingertip_*`, `hip_*`, `ankle_*`, `ground` |
| torso | `neck`, `waist`; optional `shoulder_l`, `shoulder_r` (points, never snapped; the upper arm hangs from the master's shoulder, so these only cross-check the torso) |
| hips | `waist`, `hip_l`, `hip_r` (openings) |
| upperarm | `shoulder`, `elbow` (round ends) |
| forearm | `elbow`, `wrist` (round ends) |
| hand | `wrist` (round end), `thumb_tip`, and `fingertip` (point; omitted for a fist) |
| leg | `hip`, `hem` |
| foot | `ankle` (opening), `ground` |
| tail, ear, antler, horn | `root` |
| head, neckwear | `neck` |
| hat, props (bell…) | `root` | A missing required point, or an unknown name, is a validation error.

**Other fields**
- **Hands:**
  - `thumb_side` is `lateral` (away from the body) or `medial` (towards it), for the hand as worn in the rest pose;
  - `facing` is `palm` or `back`;
  - on pieces, the thumb is given by the `thumb_tip` point, and code works out `thumb_side` from it once the side and mirror are known.
- **`side`:** `l`, `r`, or `either` (one painted piece serves both sides, mirrored for one of them).
- **`status`:** `proposed`, `confirmed` or `fixed`.
- **`confidence`:** from 0 to 1. Below 0.7, the piece gets its own doubt question.
- **`master.layers`:** draw-order overrides by role, for example `"upperarm": "under_torso"`.

## 2. Checkpoint flow in the skill

| # | After | Shown | Asked |
|---|---|---|---|
| 1 | Master approved (contract passes) | Master overlay: labelled points, thumb arrows, layer hints | Approve / Fix + doubts (always asks the sleeve-under-vest question for a character with a vest or straps) |
| 2 | Body sheet split | Overlay | Approve / Fix + doubts |
| 3 | Hands sheet split | Overlay + as-worn strip | Approve / Fix + doubts |
| 4 | Poses sheet split | Overlay + as-worn strip | Approve / Fix + doubts |
| 5 | Face sheet split | 9 heads with expression names and neck point | Approve / Fix |
| 6 | Rig built, `spine_qa` passes | Frame grid: setup, wave peak, point hold, thumbs-up hold, cheer apex, hold-card | Approve / Fix + doubts (matcher disagreements, QA warnings) |

### Each sheet checkpoint (2–5)

1. **Draft.** `rig_annotations.py propose <split-dir> --annotations <file>` adds the sheet's pieces with rough points from geometry (painted joint ends, rims). The agent looks at the numbered contact sheet and fills in role, variant, side, thumb tip and facing. It corrects the rough points and sets `confidence`.
2. **Render.** `rig_annotations.py check <file>` validates, snaps, and writes two pictures:
   - `annotations/<sheet>_overlay.png`: every piece numbered and labelled (`hand · point · either · palm · thumb lateral`). Rough points are hollow circles, snapped points filled, thumbs are arrows, openings are ellipses.
   - `annotations/<sheet>_worn.png`: each variant after its derived mirror and rotation, drawn on a stub forearm in its gesture's hold pose, with the character's left on the picture's right.
3. **Show.** The agent opens both PNGs with the OS viewer (`open` on macOS, `start` on Windows) and prints the paths.
4. **Ask.** One AskUserQuestion call:
   - question 1 is "Approve / Fix" for the sheet;
   - questions 2–4 are doubts with concrete options (for example "Thumb on piece 05 points: away from body / towards body");
   - doubts are pieces under 0.7 confidence (naming any failed snaps), or limits exceeded; a failed snap on a confident piece is not a question, `check` lists it under `snap_failed`;
   - any further doubts go in a follow-up call.
5. **Fix.** A Fix answer is one sentence. The agent edits the file, sets those pieces to `fixed`, renders again and asks again about that sheet only. Approve sets the sheet's pieces to `confirmed`.

### Checkpoint 6 Fix routing

- A wrong point, side or layer → edit the annotation and rebuild.
- Bad art → regenerate that sheet with changed words (one Nano Banana Pro call), then return to its checkpoint.

### The gate is the file

- `spine_rig.py --annotations` refuses to build while any piece or the master is `proposed`, and lists them.
- `--allow-proposed` overrides this for experiments only, and is stamped into `report.json`.
- An agent without AskUserQuestion asks the same questions in plain text.
- The one-shot `spine-parts` template still generates all sheets in one go. Checkpoints 1–5 then run back to back on its output.

## 3. Rig changes

### New `scripts/rig_annotations.py`

A module and a CLI (`propose`, `check`, `normalise`). Dependencies are numpy and Pillow, like the other rig scripts.
- **Validate:** schema, required points per role, joint names, coordinate ranges, status gate.
- **Snap:**
  - `round_end`: fit a circle to the alpha boundary within a search radius of the rough point (about 15% of the piece's short side), and take its centre;
  - `opening`: find the rim near the point, then take its centre, its width (alpha extent across the opening's inward axis at the rim, followed inward over a rounded-off rim until the width levels off) and its depth (how far the hollow runs into the piece);
  - an opening's inward axis: fixed for upright-painted pieces (`FIXED_INWARD`: hips hip_l/hip_r image-up, foot ankle image-down); otherwise toward its partner point on the same piece (`OPENING_PARTNER`: hem → hip, forearm wrist → elbow, hand wrist → fingertip); without the partner, toward the alpha centroid;
  - a failed snap keeps `at` and sets `snap: "failed"` (a doubt only on a piece under 0.7 confidence); a failed `round_end` still gets a width: the piece's cross-section across its principal axis at `at`; a failed `opening` gets the cross-section across its inward axis at `at` (followed over a rounded-off rim the same way) as its width and 0.35 × that as its depth (a point just outside the outline is measured where the axis enters the piece).
- **Normalise:**
  - turn each piece joint end up;
  - choose the mirror for each side (for `either`: both sides) by the hand rule below;
  - write `body/<char>_<part>[_l|_r].png` and `variants/<char>_<part>_<variant>.png`;
  - record every operation in the file.
- **Render:** the overlay and the as-worn strip.

### `spine_rig.py --annotations <file>`

**Placement from annotations**
- **Two-point parts** (torso, hips, upper arm, forearm, leg):
  - rotation and position come from lining up the piece's two joints with the master's;
  - width stays at the sheet's overall scale, set by the torso's neck-to-waist length against the master's;
  - length stretches (`scaleY`) to hit both joints exactly, by up to ±15%; beyond that, a doubt.
- **Hands:** the wrist goes on the master's wrist; the rotation lines the wrist-to-fingertip direction up with the master's (for a fist with no fingertip point: wrist to the piece's centroid).
- **Feet:** the opening centre goes on the master's ankle and the ground point on the master's ground line.
- **Neckwear:** its `neck` point goes on the master's neck.
- **Head, hat, tail, ears, antlers, props:** placed by the current matcher as today; the annotated point (`neck` or `root`) only sets the pivot, replacing today's guessed pivot.

**Socket fit**
- A child's end is pushed into its parent's opening by a third of the opening's depth.
- The child's width at that end is narrowed to the opening's width, by up to 15%; beyond that, a doubt.
- This applies to the leg hem into the foot, the leg top into the hips, and the upper arm into the torso.

**Layers.** `master.layers` overrides the default order in `LAYERS`. `upperarm: under_torso` draws the upper arm only under the torso (the forearm and hand stay in front of it), so the vest's armhole covers the sleeve top as in the master.

**Hand rule**
- Each gesture declares a target for the thumb in its hold pose:

  | Gesture | Thumb target |
  |---|---|
  | `point` | up |
  | `thumbs_up` | up |
  | `wave` | towards the head |
  | `hold_card` | up |
  | `cheer_jump` fists | towards the head |

- Code takes the forearm's world angle at the hold pose and picks the mirror whose thumb points closest to the target. The same function drives `normalise` and the as-worn strip.
- The thumb's direction is the part of wrist → thumb tip that runs across the hand's axis (wrist → fingertip, or image-down without a fingertip): `rig_hands.thumb_vector`. On painted hands the thumb tip sits well down the hand, so the raw wrist → thumb tip vector mostly follows the hand and decides nothing.
- The rest hands must match the master's `thumb_side` and `facing`; a mismatch is a doubt.

**Cross-check.** The current matcher still runs. If its placement is more than 4% of body height from the annotation's, that part becomes a doubt at checkpoint 6, and both placements are recorded in `report.json` (`matcher_disagreement`).

**Output.** `rig/annotations.resolved.json` holds every annotated point in attachment-local coordinates, for QA.

**Unchanged:**
- without `--annotations`, the current path (it also drafts the rough points for `propose`);
- `--cut-from-master` stays as it is;
- `main()` gains only the calls into `rig_annotations.py`; placement code moves out of `main()` rather than growing it.

### Hairline seams

Diagnose before fixing (pixel probes across the seams on both rigs). The candidate fixes:
- extend the colour of the lower piece about 2 px under the overlap;
- tighten the upper piece's soft edge where it lies over its parent.

The fix is done when `seam_lines` (below) passes.

## 4. QA, tests and verification

### New `spine_qa.py` checks

These are active when `rig/annotations.resolved.json` exists, so old rigs check as before.

| Check | Fails when | Would fail on today's rigs |
|---|---|---|
| `thumb_dir` | At a gesture's hold frame, the thumb (wrist → thumb tip across the hand bone's direction, as `rig_hands.thumb_vector`, carried through the bones) is more than 45° from the gesture's target | Moose `point` |
| `socket_fit` | In any frame, a child's end leaves its parent's opening, or more than 3% of the child's width shows beside or below the parent near the joint | Fox boots, moose legs |
| `seam_lines` | Along any edge where one piece lies over another, a 1–2 px strip is lighter or darker than both sides by more than a threshold. The threshold is tuned so today's rigs fail and the fixed rigs pass, and is checked against painted folds so they don't false-alarm | Fox and moose hips/legs |
| `landmark_drift` | In the setup pose, a placed joint is more than 1% of body height from its master point | Fox shoulders (expected) |

All existing checks stay.

### Unit tests

New `tests/`, written before the code. Run with `uv run --with pytest --with numpy --with pillow pytest tests`. They use shapes generated in the test:
- `round_end` snapping finds a circle's centre within 1 px;
- `opening` snapping finds a rim's centre, width and depth;
- mirror choice: for each gesture's forearm angle and each side, the thumb lands on the target (this includes the moose `point` regression);
- validation rejects missing points, unknown names and coordinates out of range, and refuses `proposed` without `--allow-proposed`;
- the two-point line-up hits both joints within ±15% length, and raises a doubt beyond it;
- socket fit narrows within 15%, and raises a doubt beyond it.

### End to end

1. Annotate the existing fox and moose raw pieces through the real checkpoints (the user answers them).
2. Rebuild both rigs with `--annotations`.
3. `spine_qa` must PASS for both, including the new checks.
4. Before/after frame grids for every defect in the Problem table.
5. Write it up in `experiments/2026-10-11-rig-annotations/README.md`.

### Docs

- `SKILL.md`: the routing row and common mistakes (no more `prep.py`, annotate and confirm before rigging).
- `references/spine-parts.md`:
  - stages 6–8 rewritten around annotations and checkpoints;
  - new rows in the QA failure table;
  - the "still not caught automatically" list shrinks (thumb direction, wrong-side hand).
- `README.md` status list.

## Error handling summary

| Situation | Result |
|---|---|
| Schema error, missing or unknown point, coordinate out of range | Hard error naming the piece and the point |
| Snap failed | Rough point kept, `snap: failed`, doubt |
| Stretch over 15% or narrowing over 15% | Doubt; the rig still builds with the clamped value |
| Matcher disagrees by more than 4% of body height | Doubt at checkpoint 6, recorded in `report.json` |
| Any piece `proposed` | `spine_rig.py` refuses, unless `--allow-proposed` |

## 5. Weighted-mesh sleeves (added after checkpoint 6, round 3)

**Why:** each arm is two rigid drawings, so folded elbows (hold-card, cheer) show the round caps where they meet. Professional rigs bend a single sleeve image with a weighted mesh (Spine weights; vertices across the joint ~50/50 between the two bones).

**Art.** One whole-sleeve drawing per character (shoulder to the end of the cuff, straight, joint end up), mirrored for the other side. New role `arm` with points `shoulder` (round_end), `elbow` (point: where it bends) and `wrist` (opening). Confirmed at a sheet checkpoint like every other piece.

**Rig.** When a side has an `arm` output, `spine_rig.py --annotations` writes a Spine `mesh` attachment in that side's upper-arm slot instead of the upper-arm and forearm region attachments:
- a strip mesh along the sleeve axis: 2 columns × 12 rows of vertices (edges at the sleeve outline), triangulated per quad;
- weighted vertices: each vertex is bound to the upper-arm and forearm bones; the forearm weight = smoothstep across a band of ±0.5 sleeve-width around the annotated elbow point (0 above, 1 below);
- placement: the sleeve's shoulder point on the master shoulder, elbow and wrist lined up with the master elbow and wrist (two-point rules as for limbs; the forearm bone's length from the sleeve's elbow→wrist);
- the raised-sleeve swap is not used for mesh arms; hands, layers and gestures are unchanged;
- without an `arm` piece: the two-piece arms as before.

**QA.** `spine_qa.py` renders weighted meshes (vertex = Σ weight × bone world transform × bind position; triangles drawn with per-triangle affine warps), so all existing checks apply. New check `mesh_fold`: no triangle's signed area changes sign in any frame (the elbow bent beyond what the mesh can follow).
