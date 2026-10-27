# Rig Annotations and Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The rig is built from agent-written, user-confirmed annotations instead of geometric guesses, which fixes the fox and moose hand, arm, boot, leg, shoulder and seam defects.

**Architecture:**
- **Focused modules** next to the existing scripts:
  - `rig_annotations.py`: schema, validation, normalising, CLI;
  - `rig_snap.py`: snapping rough points to geometry;
  - `rig_hands.py`: the thumb/mirror rule and gesture hold angles;
  - `rig_overlay.py`: the checkpoint pictures.
- **`spine_rig.py --annotations`** places parts from the confirmed points and writes `rig/annotations.resolved.json`.
- **`spine_qa.py`** gets new checks that read that file.
- **The skill docs** drive the checkpoints.

**Tech Stack:** Python ≥ 3.9, numpy, Pillow (no new dependencies); pytest via `uv run --with pytest --with numpy --with pillow pytest tests`.

**Spec:** `docs/superpowers/specs/2026-10-11-rig-annotations-design.md` (read it before any task).

## Global Constraints

- Scripts dir: `plugin/skills/skipbo-art/scripts/`. Sibling imports are plain `import rig_snap` (the script's dir is on `sys.path` under both `uv run` and `python`). `tests/conftest.py` puts the scripts dir and `tests/` on `sys.path`.
- No new third-party dependencies. Each new script carries the same `# /// script` header as `spine_rig.py`.
- Coordinates in `annotations.json` run from 0 to 1 across the source image, origin top-left, y down. Coordinates in `outputs` records and in `annotations.resolved.json` are pixels of the output image.
- Thresholds (verbatim from the spec, plus one plan decision):

  | Constant | Value | Source |
  |---|---|---|
  | `CONFIDENCE_DOUBT` | 0.7 | spec |
  | `STRETCH_MAX` | 0.15 | spec |
  | `NARROW_MAX` | 0.15 | spec |
  | `MATCHER_DISAGREE` | 0.04 (of body height) | spec |
  | `THUMB_TOL` | 45° | spec |
  | `SOCKET_SPILL` | 0.03 | spec |
  | `LANDMARK_DRIFT` | 0.01 (of body height) | spec |
  | push-in | depth / 3 | spec |
  | snap search radius | 0.15 × the piece's short side | spec |
  | `MIRROR_AMBIGUOUS` | 30° | plan decision: the difference between the two mirror candidates' thumb errors below which the choice becomes a doubt |

- Where the constants live, so parallel tasks import the same names:

  | Module | Constants |
  |---|---|
  | `rig_annotations` | `CONFIDENCE_DOUBT` |
  | `rig_hands` | `THUMB_TOL`, `MIRROR_AMBIGUOUS` |
  | `rig_place` | `STRETCH_MAX`, `NARROW_MAX`, `MATCHER_DISAGREE` |
  | `spine_qa` | `SOCKET_SPILL`, `LANDMARK_DRIFT`, `SEAM_MAX` |

- `_l` = the character's left = the picture's right (the existing convention).
- Without `--annotations`, `spine_rig.py` output must stay identical (the golden test in Task 6).
- Commit after every task with a message ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A hand piece whose thumb points along the forearm axis** (thumbs-up drawn sideways), where both mirrors score about the same. Expected: a doubt, never a silent pick. Test: Task 3 `test_choose_mirror_ambiguous_is_flagged`.
2. **A piece key in `annotations.json` whose split image file is missing**, or an index that doesn't exist. Expected: a hard error naming the key. Test: Task 1 `test_missing_piece_file_is_error`.
3. **Re-running `normalise`** after a Fix. Expected: the outputs are overwritten, not duplicated, and the files left over from a renamed piece are removed. Test: Task 8 `test_normalise_is_idempotent`.
4. **A character with no tail, no hats, or hooves instead of boots** (the moose). Expected: placement and QA skip missing roles without crashing. Test: Task 9 `test_synthetic_without_tail_or_feet`.
5. **`--allow-proposed` builds**: they must be visibly marked. Expected: `report.json` has `"allow_proposed": true` and the console prints a warning. Test: Task 9 `test_allow_proposed_is_stamped`.

## Dependency graph (for parallel execution)

```
T0 scaffold ─┬─ T1 schema ────────┬─ T7 overlay ───┬─ T10 CLI propose/check ─┐
             ├─ T2 snap ──────────┤                │                         ├─ T13 annotate fox+moose (main session, user checkpoints)
             ├─ T3 hands ─────────┼─ T8 normalise ─┘                         │
             ├─ T4 synth fixture ─┤                                          │
             ├─ T5 seams ─────────┼──────────────────────── T12 QA checks ───┤
             └─ T6 matcher refactor ─ T9 rig placement ─ T11 rig variants+resolved ─┘
                                                                     T14 docs (after T10, T11) ─┐
                                                                     T15 rebuild + before/after + write-up (after T12–T14) ─ final review
```

**Waves:**
1. T1–T6 in parallel;
2. T7, T8, T9 in parallel;
3. T10, T11;
4. T12, T14 in parallel, and T13;
5. T15.

Parallel tasks use git worktrees and are merged into `part-variants` in task order.

---

### Task 0: Test scaffold (main session)

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1:** `tests/conftest.py` inserts `<repo>/plugin/skills/skipbo-art/scripts` and `<repo>/tests` at the front of `sys.path`.
- [ ] **Step 2:** `tests/test_smoke.py::test_scripts_importable` imports `spine_qa` and asserts `hasattr(spine_qa, "Rig")`.
- [ ] **Step 3:** Run `uv run --with pytest --with numpy --with pillow pytest tests -q` and expect `1 passed`. Commit.

---

### Task 1: Annotation schema and validation

**Files:**
- Create: `plugin/skills/skipbo-art/scripts/rig_annotations.py`
- Test: `tests/test_annotations_schema.py`

**Interfaces:**
- Produces (in `rig_annotations.py`):
  - `ROLES: dict[str, tuple[str, ...]]`, the required points per role:
    - `torso`: neck, waist, shoulder_l, shoulder_r
    - `hips`: waist, hip_l, hip_r
    - `upperarm`: shoulder, elbow
    - `forearm`: elbow, wrist
    - `hand`: wrist, thumb_tip
    - `leg`: hip, hem
    - `foot`: ankle, ground
    - `tail`, `ear`, `antler`, `horn`, `hat`, `prop`: root
    - `head`, `neckwear`: neck
  - `fingertip` is also required for a hand whose variant is not `fist` or `thumbsup`.
  - `MASTER_POINTS`: neck, waist, ground, plus `_l`/`_r` of shoulder, elbow, wrist, fingertip, hip, ankle.
  - `DEFAULT_KIND: dict[str, str]`:
    - `round_end`: the shoulder, elbow, wrist and hip points of upperarm, forearm, hand and leg, and the leg's `hem`;
    - `opening`: the torso's `shoulder_l`/`shoulder_r`, the hips' `hip_l`/`hip_r`, the foot's `ankle`;
    - `point`: everything else.
  - `@dataclass Point(name: str, at: tuple[float, float], kind: str, snapped: tuple[float, float] | None = None, width: float | None = None, depth: float | None = None, snap: str = "none")`. `snap` is one of `none`, `ok`, `failed`. `width` and `depth` are in pixels of the source image.
  - `@dataclass Output(name: str, file: str, mirrored: bool, rotated: float, points: dict[str, tuple[float, float]], widths: dict[str, float], depths: dict[str, float])`. Points, widths and depths are in output-image pixels.
  - `@dataclass Piece(key: str, role: str, name: str, variant: str | None, side: str, points: dict[str, Point], facing: str | None, status: str, confidence: float, note: str = "", mirror: bool = False, painted_as: str | None = None, outputs: list[Output] = field(default_factory=list))`.
    - `name` is the base part name used in file names (`boot`, `hoof`, `cap`, `upperarm`, `head_base`, …) and defaults to `role`.
    - `side` is one of `l`, `r`, `either`, `""`.
    - `facing` is `palm`, `back` or None.
    - `status` is `proposed`, `confirmed` or `fixed`.
  - `@dataclass Master(image: str, points: dict[str, tuple[float, float]], hands: dict[str, dict], layers: dict[str, str], status: str)`.
  - `@dataclass Annotations(version: int, character: str, master: Master, pieces: dict[str, Piece], path: Path)`.
  - `class AnnotationError(ValueError)`, whose message lists every problem, one per line.
  - `load(path: Path) -> Annotations`: validates and raises `AnnotationError`.
  - `save(ann: Annotations, path: Path | None = None) -> None`: round-trips exactly. Keys are sorted; floats are rounded to 4 decimals for normalised values and 2 for pixels.
  - `validate(ann: Annotations) -> list[str]`.
  - `unconfirmed(ann: Annotations) -> list[str]`: the keys still `proposed`, plus `"master"` if the master is `proposed`.
  - `piece_image(ann: Annotations, key: str) -> Path`: resolves `"<split-run-dir>/<NN>"` to `<ann.path.parent>/runs/<split-run-dir>/*_<NN>.png` (NN zero-padded to 2). Raises `AnnotationError` if it is missing.

**Validation rules:**
- the role is known;
- every required point is present;
- no point name is outside the role's set plus `fingertip`/`thumb_tip`;
- every `at` is within [0, 1];
- `kind` is in `round_end`, `opening`, `point`;
- `side == "either"` is only allowed when the role is `hand` or `painted_as` is set;
- `master.layers` keys are a subset of `{"upperarm"}`, and the values are `under_torso` or `over_torso`;
- `confidence` is in [0, 1];
- `version == 1`.

- [ ] **Step 1: Write the failing tests** in `tests/test_annotations_schema.py`:
  - `test_roundtrip`: save then load gives an equal `Annotations`.
  - `test_missing_required_point`: a torso with no `waist` raises `AnnotationError` whose message contains `torso` and `waist`.
  - `test_unknown_point_name`: a hand with `elbow` raises an error naming it.
  - `test_coordinate_out_of_range`: `at=[1.2, 0.5]` raises an error.
  - `test_either_needs_hand_or_painted_as`: a leg with `side="either"` and no `painted_as` raises; with `painted_as="l"`, it validates.
  - `test_fist_needs_no_fingertip`: hand variants `fist` and `thumbsup` validate without `fingertip`; `point` without it raises.
  - `test_unconfirmed_lists_proposed_and_master`.
  - `test_missing_piece_file_is_error`: `piece_image` on a key with no file raises `AnnotationError` containing the key.
  - `test_bad_layer_value`: `{"upperarm": "behind"}` raises.
- [ ] **Step 2:** Run `uv run --with pytest --with numpy --with pillow pytest tests/test_annotations_schema.py -q`. Expect FAIL (ImportError).
- [ ] **Step 3:** Implement the interfaces above in `rig_annotations.py`. Write the JSON exactly like the spec's example, with an extra `outputs` list per piece.
- [ ] **Step 4:** Run the tests. Expect all to pass.
- [ ] **Step 5:** Commit: `rig_annotations: schema, load/save, validation`.

---

### Task 2: Snapping

**Files:**
- Create: `plugin/skills/skipbo-art/scripts/rig_snap.py`
- Test: `tests/test_snap.py`

**Interfaces:**
- Produces:
  - `axis_ends(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]`: copied verbatim from `spine_rig.py:225-232`.
  - `@dataclass SnapResult(at: tuple[float, float], width: float | None = None, depth: float | None = None)`. Pixels.
  - `snap_round_end(alpha: np.ndarray, p: tuple[float, float], radius: float) -> SnapResult | None`.
    - Fit a circle (algebraic least squares) to the alpha boundary pixels within `radius` of `p`.
    - Return the centre and `width = 2 * r`.
    - Return None when there are fewer than 12 boundary pixels, when `r` falls outside `[0.15, 1.5] * radius`, or when the centre is not inside `alpha`.
  - `snap_opening(alpha: np.ndarray, p: tuple[float, float], inward: tuple[float, float], radius: float, depth_frac: float = 0.35) -> SnapResult | None`.
    - Walk from `p` against `inward` to the piece's edge (the rim).
    - Step `0.05 * radius` back inside.
    - Measure the alpha extent perpendicular to `inward` there.
    - Return the extent's midpoint, `width` = the extent, and `depth = depth_frac * width`.
    - Return None if `p` is more than `radius` from any opaque pixel.
  - `inward_axis(alpha: np.ndarray, p: tuple[float, float]) -> tuple[float, float]`: a unit vector from `p` towards the alpha centroid.
  - `boundary(alpha: np.ndarray) -> np.ndarray`: (N, 2) xy of the opaque pixels that have a transparent 4-neighbour.

- [ ] **Step 1: Write the failing tests**, using shapes drawn with PIL in the test:
  - `test_round_end_capsule`: a capsule (rectangle 60 wide plus a semicircle of radius 30 centred at (100, 60)); rough point (110, 50), radius 45. The snap is within 1 px of (100, 60), and the width is within 3 px of 60.
  - `test_round_end_rejects_far_point`: a rough point 200 px away returns None.
  - `test_opening_boot`: a 70-wide rectangle (x 50..120, y 40..200); rough point (90, 45), inward (0, 1), radius 40. `at` is within 2 px of (85, 42); width is 70 ± 2; depth is 0.35 × width ± 1.
  - `test_opening_tilted`: the same rectangle rotated 20°. The width stays 70 ± 3.
  - `test_axis_ends_matches_spine_rig`: on random points, equal to `spine_rig.axis_ends`.
- [ ] **Step 2:** Run `pytest tests/test_snap.py -q`. Expect FAIL.
- [ ] **Step 3:** Implement `rig_snap.py`.
- [ ] **Step 4:** Run the tests. Expect all to pass.
- [ ] **Step 5:** Commit: `rig_snap: round-end and opening snapping`.

---

### Task 3: Hand rule

**Files:**
- Create: `plugin/skills/skipbo-art/scripts/rig_hands.py`
- Test: `tests/test_hands.py`

**Interfaces:**
- Produces:
  - `HOLD_FOREARM_DEG: dict[str, float]`: the forearm's world angle at each variant's hold, for the character's left side (0 = out to the picture's right, 90 = up):
    - rest −90, open 85, fist 65, point 5, thumbsup 10, grip 170.
  - `GESTURE_ARM_DEG: dict[str, tuple[float, float]]`: upper arm and forearm world angles used by `spine_rig.gesture`, moved here from `spine_rig.py:1317-1319`:
    - thumbs_up (−55, 10), point (5, 5), hold_card (−95, 170).
  - `THUMB_TARGET: dict[str, str]`: open → medial, fist → medial, point → up, thumbsup → up, grip → up. The rest hand's target comes from the master's `thumb_side`.
  - `side_deg(deg_left: float, side: str) -> float`: `side == "r"` gives `180 - deg_left`.
  - `target_deg(target: str, side: str) -> float`:
    - up → 90; down → −90;
    - lateral → 0 for `l`, 180 for `r`;
    - medial → 180 for `l`, 0 for `r`.
  - `thumb_world_deg(thumb_vec: tuple[float, float], forearm_deg: float) -> float`.
    - `thumb_vec` is (dx, dy) in a joint-end-up image (y down).
    - The image's +y maps to the world direction `forearm_deg`.
    - Returns world degrees with y up.
  - `ang_diff(a: float, b: float) -> float`: absolute difference in [0, 180].
  - `choose_mirror(thumb_vec: tuple[float, float], variant: str, side: str, rest_target: str | None = None) -> tuple[bool, float]`.
    - Returns `(mirror, margin)`: `mirror=True` means flip horizontally (dx → −dx).
    - `margin` = |error(unmirrored) − error(mirrored)| in degrees.
    - The variant `None` or `"rest"` uses `rest_target`.

- [ ] **Step 1: Write the failing tests:**
  - `test_target_deg_sides`;
  - `test_point_left_thumb_up`: thumb_vec (+1, 0) at the point hold for `l` → the thumb is within 10° of 90 when unmirrored. Then `choose_mirror((1, 0), "point", "l") == (False, m)` with `m > 90`.
  - `test_point_moose_regression`: thumb_vec (−1, 0), `point`, side `l` → mirror True.
  - `test_right_side_mirrors`: for every variant in `THUMB_TARGET`, `choose_mirror(v, var, "r")[0] != choose_mirror(v, var, "l")[0]` for v = (1, 0.2).
  - `test_choose_mirror_ambiguous_is_flagged`: thumb_vec (0, 1) (along the forearm) → `margin < MIRROR_AMBIGUOUS` (30).
  - `test_rest_uses_master_target`: the rest variant with `rest_target="lateral"`, side `l`, thumb (−1, 0) → mirror True.
- [ ] **Step 2:** Run `pytest tests/test_hands.py -q`. Expect FAIL.
- [ ] **Step 3:** Implement. `MIRROR_AMBIGUOUS = 30.0` lives here.
- [ ] **Step 4:** Run the tests. Expect all to pass.
- [ ] **Step 5:** Commit: `rig_hands: gesture thumb targets and mirror rule`.

---

### Task 4: Synthetic test character

**Files:**
- Create: `tests/synth_character.py`
- Test: `tests/test_synth.py`

**Interfaces:**
- Produces `make_character(root: Path, *, tail: bool = True, feet: str = "boot", hand_thumb_wrong: bool = False) -> Path`. It returns the path to `root/annotations.json` and draws, with PIL, a flat-coloured front-view figure:
  - `root/master.png` (600 × 900, flat background (214, 214, 214)): a torso, hips, two 3-segment arms hanging at about −70°, two legs, two boots (or hooves), a head circle, and a tail if asked. Each part has a distinct flat colour, so the matcher works.
  - The raw split pieces in `root/runs/synth-body-parts/*_NN.png`, one RGBA per part, each painted joint end up with round ends, at 0.8 × the master's scale. A boot has a visible opening rim. The hand has a thumb bump on one side.
  - The hand variants in `root/runs/synth-hands-parts/` (open, fist, point, thumbsup, grip). With `hand_thumb_wrong`, the point variant's thumb is on the other side.
  - `root/annotations.json`, valid under Task 1, every status `confirmed`. Exact points are known from construction (no snapping needed). The `outputs` records are filled in, and the output PNGs are written to `root/body/`, `root/variants/` and `root/face-heads/` as `synth_<name>.png`, as Task 8 would.
- Also produces `TRUTH: dict`, written to `root/truth.json`: the master's joint positions in master pixels and each piece's true points, for assertions in later tasks.

- [ ] **Step 1: Write the failing tests:**
  - `test_make_character_valid`: `rig_annotations.load(make_character(tmp))` has no errors and every piece status is `confirmed`.
  - `test_variants_present`;
  - `test_no_tail_option`.
- [ ] **Step 2:** Run them. Expect FAIL.
- [ ] **Step 3:** Implement `synth_character.py`.
- [ ] **Step 4:** Run them. Expect all to pass.
- [ ] **Step 5:** Commit: `tests: synthetic character fixture`.

---

### Task 5: Hairline seams — diagnose, fix, and the `seam_lines` check

**Files:**
- Modify: `plugin/skills/skipbo-art/scripts/spine_rig.py:93-124` (`solidify`), only if the diagnosis points there
- Modify: `plugin/skills/skipbo-art/scripts/spine_qa.py` (new `check_seams`, wired into `main`)
- Test: `tests/test_seams.py`

**Interfaces:**
- Produces `spine_qa.check_seams(rig: Rig, canvas: Canvas, frames: list[tuple[str | None, float]]) -> dict`, returning `{"pass": bool, "seams": {"<upper>/<lower>": score}}`.
  - It scores the setup pose plus one middle frame per animation.
  - `SEAM_MAX` is a module constant.
- `main` adds `report["seams"]`.

**Diagnosis first (superpowers:systematic-debugging):**
- Render the fox setup with `tools/render_frames.py` at 1400 px.
- Probe the pixels across the hips/leg edge and the vest/trouser edge of the moose.
- Leading hypothesis: fully transparent pixels (alpha 0) keep their RGB (often black or grey), and bilinear resampling in `Canvas.layer` and the Spine runtime blends that colour into the edge (a dark or pale hairline). `solidify` only recolours pixels with alpha > 0.
- Confirm or refute this with a probe before changing anything.

**Seam score:**
- For each pair of slots (`upper` drawn after `lower`), take the boundary pixels of `upper`'s alpha that lie inside `lower`'s alpha eroded by 3 px.
- At each one, read the luminance L_e on the composite, L_in 3 px inside `upper` (along the inward normal of the alpha gradient), and L_out 3 px outside.
- The pixel is a line pixel when L_e < min(L_in, L_out) − δ or L_e > max(L_in, L_out) + δ.
- Score = the fraction of line pixels (δ = 0.04 on 0..1 luminance).
- Painted folds inside a piece are never sampled, because only piece boundaries are.

- [ ] **Step 1:** Write the diagnosis probe. Record the finding as a comment at the top of `tests/test_seams.py`.
- [ ] **Step 2: Write the failing tests:**
  - `test_seam_score_detects_dark_rim`: two synthetic RGBA layers, the upper with a black alpha-0 border, rendered via `spine_qa`; the score is > `SEAM_MAX`.
  - `test_seam_score_clean`: the same with the border colour bled; the score is ≤ `SEAM_MAX`.
  - `test_fix_removes_rim`: the fixed image-prep function applied to the dark-rim layer gives a clean score.
- [ ] **Step 3:** Run them. Expect FAIL.
- [ ] **Step 4:** Implement `check_seams`. Calibrate `SEAM_MAX` so the existing `experiments/2026-10-11-part-variants/{fox,moose}/rig` setups FAIL. Record their scores in the commit message.
- [ ] **Step 5:** Implement the fix where the diagnosis points. If the hypothesis holds: in `solidify`, bleed the nearest opaque colour into the alpha-0 pixels within 4 px of the part ("alpha bleeding"), leaving alpha unchanged.
- [ ] **Step 6:** Rebuild both existing rigs into a scratch dir with the commands in `experiments/2026-10-11-part-variants/*/rig/README.md` (or the README's spine_rig invocation), and run `spine_qa.py`. `seams` must PASS and every other check must stay PASS. Run the unit tests and expect all to pass.
- [ ] **Step 7:** Commit: `Fix hairline seams (<root cause>) and add seam_lines QA check`.

---

### Task 6: Extract the matcher placement (no behaviour change)

**Files:**
- Modify: `plugin/skills/skipbo-art/scripts/spine_rig.py:237-357`
- Test: `tests/test_rig_golden.py`

**Interfaces:**
- Produces, in `spine_rig.py`:
  - `@dataclass MasterFrame(work: np.ndarray, fg: np.ndarray, k: float, ground_y: float, top: float, mid_x: float, half_w: float)`;
  - `load_master(path: Path) -> MasterFrame`;
  - `match_parts(frame: MasterFrame, parts: dict[str, tuple[Path, np.ndarray]], cut_from_master: bool) -> tuple[dict, dict, float]`, returning `(placed, renames, g)`. This is stages 1–2 moved verbatim, including the nested `band`, `between` and `near_arm_end` helpers.
  - `main` calls these. The output is byte-identical.

- [ ] **Step 1: Write the golden test.**
  - `test_fox_rig_unchanged` builds the fox rig into `tmp_path` with the existing command:
    - `--master experiments/2026-10-11-fox-parts/fox_master.png`
    - `--body experiments/2026-10-11-part-variants/fox/body`
    - `--heads experiments/2026-10-11-fox-parts/fox-spine/face-heads`
    - `--variants experiments/2026-10-11-part-variants/fox/variants`
    - `--name fox`
  - It then compares `fox.json` with a copy generated from the pre-refactor commit, saved once as `tests/golden/fox.json`: bones and skins equal to within 0.01.
  - Mark it `@pytest.mark.slow`; `conftest` registers the marker.
- [ ] **Step 2:** Generate `tests/golden/fox.json` from the current HEAD before refactoring. Run the test and expect PASS.
- [ ] **Step 3:** Refactor.
- [ ] **Step 4:** Run the golden test again. Expect PASS.
- [ ] **Step 5:** Commit: `spine_rig: extract master loading and matcher placement`.

---

### Task 7: Checkpoint pictures

**Files:**
- Create: `plugin/skills/skipbo-art/scripts/rig_overlay.py`
- Test: `tests/test_overlay.py`

**Interfaces:**
- Consumes: Task 1's `Annotations`, `Piece`, `Point`, `piece_image`; Task 3's `HOLD_FOREARM_DEG`, `side_deg`, `THUMB_TARGET`.
- Produces:
  - `render_sheet_overlay(ann: Annotations, run_dir: str, out: Path, cell: int = 260) -> Path`: draws each piece whose key starts with `run_dir + "/"` in a grid cell.
    - Above each cell: the number and the label `role · variant · side · facing · thumb <lateral|medial>`. The thumb side is computed from the outputs when they exist, otherwise blank.
    - Rough points: hollow circles. Snapped points: filled. Openings: ellipses of the snapped width. `thumb_tip`: an arrow from the wrist.
    - Doubtful pieces (confidence < 0.7 or `snap == "failed"`) get a red frame.
  - `render_master_overlay(ann: Annotations, out: Path) -> Path`: the master with labelled points, thumb arrows from `hands`, and `layers` written in the corner.
  - `render_worn_strip(ann: Annotations, run_dir: str, out: Path, h: int = 300) -> Path`: for each output of each hand, foot and upper-arm piece in `run_dir`:
    - draw a grey stub forearm at `side_deg(HOLD_FOREARM_DEG[variant], side)`;
    - paste the output image rotated so its wrist→fingertip (or wrist→centroid) runs along the stub, wrist on the stub's end;
    - label it `<name> <target> ✓/✗` from `rig_hands.thumb_world_deg` vs `target_deg`, tolerance `THUMB_TOL`;
    - the character's left goes on the picture's right.

- [ ] **Step 1: Write the failing tests** on the synthetic character (Task 4):
  - `test_sheet_overlay_writes_png` (size > 0, one cell per piece);
  - `test_master_overlay_writes_png`;
  - `test_worn_strip_marks_wrong_thumb`: with `hand_thumb_wrong=True`, the returned list of labels (have `render_worn_strip` also return `list[tuple[str, bool]]`) has `("hand_l_point", False)`.
- [ ] **Step 2:** Run them. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run them. Expect all to pass. Look at one PNG yourself (Read the image) and fix anything unreadable.
- [ ] **Step 5:** Commit.

---

### Task 8: Normalise (replaces `prep.py`)

**Files:**
- Modify: `plugin/skills/skipbo-art/scripts/rig_annotations.py`
- Test: `tests/test_normalise.py`

**Interfaces:**
- Consumes: Task 2's `snap_round_end`, `snap_opening`, `inward_axis`; Task 3's `choose_mirror`.
- Produces:
  - `snap_all(ann: Annotations) -> None`:
    - fills each `Point.snapped/width/depth/snap` from the piece's image (radius = 0.15 × the image's short side);
    - also snaps the master's shoulder, elbow, wrist, hip and ankle points as `round_end`, but only records them (the master's `at` is used as given).
  - `normalise(ann: Annotations) -> list[str]`: writes the output PNGs and fills `Piece.outputs`. Returns the doubt strings for mirror choices with margin < 30°.
    - Rotate limbs (upperarm, forearm, hand, leg, foot) so the proximal point is above the distal one:
      - upperarm: shoulder → elbow; forearm: elbow → wrist; leg: hip → hem;
      - hand: wrist → fingertip, or wrist → centroid;
      - foot: ankle → ground.
      - The vector is turned to point straight down; rotation uses `expand=True`, BICUBIC.
    - Other roles are not rotated.
    - Hands: mirror per side by `choose_mirror` (`either` gives two outputs).
    - Other roles: `mirror` flips; `either` with `painted_as` writes the painted side as is and the other mirrored.
    - Output names:
      - `f"{name}_{side}"`, plus `f"_{variant}"` when there is a variant;
      - heads: `head_base`, or `head_<variant>`.
    - Output dirs: `body/` for rest parts, `variants/` for variants, `face-heads/` for heads, all under `ann.path.parent`, file `f"{character}_{outname}.png"`.
    - Every point (using `snapped` when ok, else `at`) is transformed into output pixels; widths and depths are scaled.
    - Before writing, delete the stale `<character>_*.png` in those dirs that no longer belong to any output.
  - `doubts(ann: Annotations) -> list[dict]`, each `{"key", "reason", "options"}` for:
    - confidence < 0.7;
    - `snap == "failed"`;
    - an ambiguous mirror;
    - a rest hand whose `facing` ≠ the master's `hands[side]["facing"]`.

- [ ] **Step 1: Write the failing tests** on the synthetic character:
  - `test_normalise_rotates_joint_up`: in each limb output, the proximal point's y < the distal point's y, and |dx| < 3 px.
  - `test_normalise_hand_mirror`: with `hand_thumb_wrong=True`, the `hand_l_point` output has `mirrored != hand_l_open`'s, and its thumb target check passes.
  - `test_normalise_is_idempotent`: run twice; the same files, and no extra files.
  - `test_points_follow_transform`: the output wrist point lands on an opaque pixel near the top edge.
  - `test_doubts_low_confidence`: set one piece to 0.5 and it appears in `doubts`.
- [ ] **Step 2:** Run them. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run them. Expect all to pass.
- [ ] **Step 5:** Commit.

---

### Task 9: `spine_rig.py --annotations`: placing the rest parts

**Files:**
- Create: `plugin/skills/skipbo-art/scripts/rig_place.py`
- Modify: `plugin/skills/skipbo-art/scripts/spine_rig.py` (arguments, the gate, a branch at stage 3a')
- Test: `tests/test_rig_annotated.py`

**Interfaces:**
- Consumes:
  - Task 1's `load`, `unconfirmed`, `Output`;
  - Task 6's `MasterFrame`, `match_parts`;
  - Task 4's fixture.
  - Pieces are read from `Piece.outputs` (the files are already joint end up and mirrored).
- Produces, in `rig_place.py` (all positions in full-resolution master pixels):
  - `two_point(img_size: tuple[int, int], Jp: tuple, Jd: tuple, P: tuple, D: tuple, g: float) -> dict` returns `{"cx", "cy", "angle", "unit", "unit_y", "stretch"}`.
    - Rotation and position put `Jp` → `P` and the direction `Jp→Jd` along `P→D`.
    - `unit = g` (width); `unit_y = g * clip(|PD| / (g * |JpJd|), 1 - STRETCH_MAX, 1 + STRETCH_MAX)`.
    - `stretch` is the raw ratio, used for the doubt.
  - `push_in(C: tuple, axis: tuple, depth: float) -> tuple`, returning `C + axis * depth / 3`.
  - `narrow(width_child: float, width_opening: float) -> tuple[float, float]` returns `(factor, raw)`, with `factor = clip(width_opening / width_child, 1 - NARROW_MAX, 1)`.
  - `apply_layers(layers: dict, base: list[str]) -> list[str]`: `upperarm: under_torso` moves `hand`, `forearm` and `arm` just before `torso`.
  - `place_from_annotations(ann, frame: MasterFrame, g: float) -> tuple[dict, dict, dict, list[dict]]` returns `(pieces, joints, bone_dir, doubts)`, where pieces have the same shape as in `spine_rig.main` plus `unit_y`.
- In `spine_rig.py`:
  - add `--annotations PATH` and `--allow-proposed`;
  - when `unconfirmed(ann)` is not empty and there's no `--allow-proposed`, `SystemExit` listing the keys;
  - `region_att` uses `scaleY = pc.get("unit_y", pc["unit"])`;
  - `report.json` gains `"annotations": str(path)`, `"allow_proposed": bool` and `"doubts": [...]`.

**Placement order:**
1. **Global scale:** g = |master neck→waist| / |torso output neck→waist|.
2. **Torso:** `two_point` neck→waist. **Hips:** waist → the midpoint of hip_l and hip_r, onto the master's waist and the midpoint of the master's hip_l and hip_r.
3. **Head, hat, tail, ears, antlers, props:** `match_parts` as today. Each pivot is its annotated `root`/`neck` point carried through its matched placement.
4. **Neckwear:** its `neck` point onto the master's neck at scale g.
5. **Feet:** the ankle opening centre onto the master's `ankle_*`, scale g. If the ground point misses the master's ground y by more than 2% of body height, raise a doubt.
6. **Legs:** `two_point` from P = `push_in`(the hips' placed `hip_*` opening, up into the hips) to D = `push_in`(the foot's ankle opening, down into the foot). The width factor is `narrow`(the leg width at the hem, the foot's ankle width) combined with the top against the hip opening.
7. **Upper arm:** `two_point` from `push_in`(the torso's placed `shoulder_*` opening, into the torso) to the master's `elbow_*`. **Forearm:** the upper arm's placed elbow → the master's `wrist_*`.
8. **Hand:** the wrist onto the placed forearm's wrist, rotated so wrist→fingertip (or wrist→centroid) runs along the master's wrist→fingertip, scaled so that length matches the master's within [0.8, 1.6] × g.
9. **Joints:** each joint is the proximal point; `bone_dir` = distal − proximal.

- [ ] **Step 1: Write the failing tests:**
  - `test_two_point_hits_both_joints`: placed Jp and Jd within 0.5 px of P and D for a 10% stretch.
  - `test_two_point_clamps_and_reports`: a 30% stretch gives `unit_y = g * 1.15` and `stretch = 1.3`.
  - `test_narrow_clamps`;
  - `test_apply_layers_under_torso`;
  - `test_synthetic_rig_joints_on_master` (slow): build the synthetic character with `--annotations`. Every upperarm, forearm, hand and leg bone origin is within 1% of body height of `truth.json`.
  - `test_synthetic_leg_inside_boot`: in `report.json` or the placed geometry, the leg's hem point lies inside the boot's opening ellipse.
  - `test_refuses_proposed`: set one piece to `proposed`; the run exits non-zero with its key in stderr.
  - `test_allow_proposed_is_stamped`;
  - `test_synthetic_without_tail_or_feet`: `make_character(tail=False, feet="hoof")` builds.
- [ ] **Step 2:** Run them. Expect FAIL.
- [ ] **Step 3:** Implement `rig_place.py` and the `spine_rig.py` branch. The legacy path is untouched (the golden test still passes).
- [ ] **Step 4:** Run all the tests, including slow ones. Expect all to pass.
- [ ] **Step 5:** Commit.

---

### Task 10: CLI `propose` / `check` / `normalise`

**Files:**
- Modify: `plugin/skills/skipbo-art/scripts/rig_annotations.py` (`main()`, `if __name__ == "__main__"`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Tasks 1, 2, 3, 7, 8, and `rig_snap.axis_ends`.
- Produces the commands:
  - `rig_annotations.py propose <char-dir>/runs/<split-run> --annotations <file> [--master <png>]`:
    - creates the file if needed (master points blank, master status `proposed`);
    - adds each split piece as `{"role": "", "status": "proposed", "confidence": 0}` with rough `top`/`bottom` round-end candidates from `axis_ends` (the end nearer the top as the first);
    - never overwrites a piece that already has a role;
    - prints the contact sheet path from `comfy.py sheet`, if the run dir has one, or writes `annotations/<run>_numbered.png`.
  - `rig_annotations.py check <file> [--sheet <run>]`:
    - validates; on errors, exit 2 and print them;
    - `snap_all`, `normalise`, `save`;
    - renders the master overlay and, for each sheet (or only `--sheet`), the overlay and the worn strip into `<char-dir>/annotations/`;
    - prints the paths and a JSON doubt list (`{"doubts": [...]}` on the last line);
    - exits 0.
  - `rig_annotations.py confirm <file> --sheet <run> | --master`: sets that sheet's `proposed` pieces (or the master) to `confirmed`.

- [ ] **Step 1: Write the failing tests** (subprocess on the synthetic character):
  - `test_propose_adds_pieces`;
  - `test_check_writes_overlays_and_doubts` (the last stdout line parses as JSON);
  - `test_check_exit_2_on_invalid`;
  - `test_confirm_sheet`.
- [ ] **Step 2:** Run them. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run them. Expect all to pass.
- [ ] **Step 5:** Commit.

---

### Task 11: Variants from annotations, resolved file, gesture constants, cross-check

**Files:**
- Modify: `plugin/skills/skipbo-art/scripts/spine_rig.py` (stage 4b variants, `gesture()` calls, report)
- Modify: `plugin/skills/skipbo-art/scripts/rig_place.py`
- Test: `tests/test_rig_annotated.py` (extend)

**Interfaces:**
- Consumes: Task 9's `place_from_annotations`; Task 3's `GESTURE_ARM_DEG`, `THUMB_TARGET`, `HOLD_FOREARM_DEG`.
- Produces:
  - **Variants, when annotations are given:** the joint comes from the output's annotated point (hand `wrist`, upperarm `shoulder`, foot `ankle`, tail `root`), replacing `joint_axis_size`. The scale comes from:
    - hands: the ratio of `widths["wrist"]`;
    - tubes: the width ratio of the proximal round end, and the length ratio of the two points (scaleY, clamp ±33% as today);
    - feet: the ratio of `widths["ankle"]`;
    - tails: the area, as today.
  - **`gesture(...)` calls** read `rig_hands.GESTURE_ARM_DEG` in both paths. The values are unchanged, so the golden test still passes.
  - **`rig/annotations.resolved.json`:**

    ```json
    {"attachments": {"<att>": {"slot": "...", "variant": "...|null", "side": "l|r|", "points": {"wrist": [x, y]}, "widths": {}}},
     "sockets": [{"child": "<att>", "child_point": "hem", "parent": "<att>", "parent_point": "ankle", "width": 0.0}],
     "holds": {"point": {"time": 1.2, "slot": "hand_l", "variant": "point"}, "thumbs_up": {"time": 1.2, ...},
               "hold_card": {"time": 1.2, ...}, "wave": {"time": 0.75, ...}, "cheer_jump": {"time": 0.95, "slot": "hand_l", "variant": "fist"}},
     "thumb_targets": {"hand_l_point": 90.0},
     "master_points_units": {"shoulder_l": [x, y]},
     "point_bones": {"shoulder_l": "upperarm_l", "elbow_l": "forearm_l", "wrist_l": "hand_l", "hip_l": "leg_l", "ankle_l": "<foot>_l", "neck": "head_base"},
     "body_height_units": 0.0}
    ```

    - Points are in attachment-image pixels.
    - Sockets: leg hem → foot ankle, leg hip → hips hip_*, upperarm shoulder → torso shoulder_*. `width` is in the parent image's pixels.
  - **Cross-check:** after annotation placement, run `match_parts`. For each part in both, if the distance between centres is more than `MATCHER_DISAGREE` × body height, append `{"part", "reason": "matcher_disagreement", "distance_frac"}` to the doubts.

- [ ] **Step 1: Write the failing tests:**
  - `test_resolved_written` (keys present; every hand attachment has `wrist` and `thumb_tip`);
  - `test_variant_wrist_on_rest_wrist`: in the setup pose with `hand_l_point` swapped in (via `spine_qa.Rig.pose(..., override=...)` and `att_matrix`), the variant's wrist is within 1.5% of body height of the rest hand's wrist;
  - `test_gesture_angles_from_rig_hands`;
  - `test_matcher_disagreement_reported`: move one master point by 10% of height in a copy; the doubt appears.
- [ ] **Step 2:** Run them. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run all the tests, including the golden test. Expect all to pass.
- [ ] **Step 5:** Commit.

---

### Task 12: New QA checks

**Files:**
- Modify: `plugin/skills/skipbo-art/scripts/spine_qa.py`
- Test: `tests/test_qa_annotations.py`

**Interfaces:**
- Consumes: Task 11's `annotations.resolved.json`, `Rig.pose`, `Rig.att_matrix`, `render`.
- Produces three checks, each active only when `rig/annotations.resolved.json` exists:
  - `check_thumbs(rig, resolved) -> dict`, `{"pass", "thumbs": {anim: err_deg}}`.
    - At each hold time, with the hold's variant active, carry `wrist` and `thumb_tip` through `att_matrix`.
    - The world angle of the thumb vector must be within `THUMB_TOL` of `target_deg(THUMB_TARGET[variant], side)`.
  - `check_sockets(rig, canvas, resolved, anims) -> dict`, `{"pass", "sockets": {"child/parent": worst_spill}}`.
    - Every 3rd frame of every animation, plus the setup.
    - The child's end point must lie within `width/2` of the parent's opening centre.
    - Spill = the child's opaque pixels within a disk (radius = the opening width) around the opening centre that are on the far side of the rim line (towards the parent's interior) and not covered by the parent's alpha, divided by the child's opaque pixels in that disk.
    - Fails above `SOCKET_SPILL`.
  - `check_landmarks(rig, resolved) -> dict`: in the setup pose, each `point_bones` bone's world origin must be within `LANDMARK_DRIFT` × `body_height_units` of `master_points_units`.
- `main` adds `report["thumbs"]`, `report["sockets"]` and `report["landmarks"]` when the file exists.

- [ ] **Step 1: Write the failing tests** on the synthetic rig built with annotations:
  - `test_thumbs_pass_synthetic`;
  - `test_thumbs_fail_when_mirror_flipped`: edit the resolved file to flip `thumb_tip` dx; FAIL with an error > 90°;
  - `test_socket_fail_when_leg_moved`: shift the leg attachment by +20 units in the json; FAIL;
  - `test_landmarks_pass_synthetic`;
  - `test_old_rig_unaffected`: on `experiments/2026-10-11-part-variants/fox/rig/fox.json` (no resolved file), the report has no `thumbs` key.
- [ ] **Step 2:** Run them. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run all the tests. Expect all to pass.
- [ ] **Step 5:** Commit.

---

### Task 13: Annotate the fox and the moose through the real checkpoints (main session; the user answers)

**Files:**
- Create: `experiments/2026-10-11-rig-annotations/{fox,moose}/annotations.json`
- Create: `experiments/2026-10-11-rig-annotations/{fox,moose}/runs` (symlinks to the part-variants runs, or copies of the used split dirs)
- Create: `experiments/2026-10-11-rig-annotations/{fox,moose}/master.png` (copy)
- Create: `experiments/2026-10-11-rig-annotations/{fox,moose}/face-heads` (via normalise)

**Inputs:**
- Fox:
  - master `experiments/2026-10-11-fox-parts/fox_master.png`;
  - split runs `fox-body-v2-parts`, `fox-hands-parts`, `fox-arms-parts`, `fox-poses-parts`;
  - heads from `experiments/2026-10-11-fox-parts/fox-spine/face-heads` (annotated as role `head`, keyed `face-heads/<NN>` after copying them into `runs/face-heads/` with the `*_NN.png` names).
- Moose:
  - master `experiments/2026-10-11-moose-parts/master-v1.png`;
  - split runs `moose-body-a-parts`, `moose-body-b-parts`, `moose-hands-parts`, `moose-poses-parts`;
  - heads from the moose face-heads folder used by the existing rig (find it from the old rig's image names).
- The existing `prep.py` mappings are hints for role and side only. Thumbs and mirrors come from looking.

- [ ] **Step 1 (checkpoint 1):** Write the master points by looking at the master overlay, iterating with `check` until the snapped and rough points agree. Open the overlay and ask AskUserQuestion: Approve / Fix, plus the sleeve-under-vest doubt for the moose (vest) and the fox (dungaree straps).
- [ ] **Step 2 (checkpoints 2–5, per sheet):** Run `propose`, fill in the meaning by looking at the numbered sheet, run `check`, open the overlay and the worn strip, then AskUserQuestion with Approve / Fix plus up to 3 doubts. Apply any Fix answers and repeat. Then `confirm`.
- [ ] **Step 3:** Commit the annotations (the PNG outputs under `annotations/` too).

---

### Task 14: Docs

**Files:**
- Modify: `plugin/skills/skipbo-art/SKILL.md`
- Modify: `plugin/skills/skipbo-art/references/spine-parts.md`
- Modify: `README.md`

- [ ] **Step 1:** In `spine-parts.md`:
  - replace stage 6 (naming and `prep.py`) with "6. Annotate and confirm (checkpoints 1–5)": the commands from Task 10, the AskUserQuestion pattern (open the PNGs first, the first question Approve/Fix, up to 3 doubts, a plain-text fallback), and the status gate;
  - stage 8 gains `--annotations`;
  - 8b gains the `thumbs`, `sockets`, `landmarks` and `seams` checks and checkpoint 6;
  - the QA failure table gets rows for those four;
  - "Still not caught automatically" drops thumb direction and the wrong-side hand.
- [ ] **Step 2:** In `SKILL.md`, the routing row mentions `rig_annotations.py`, and common mistakes gets two rows:
  - "Naming/mirroring parts by hand in a prep script → annotate and confirm; normalise derives it";
  - "Building a rig from `proposed` annotations → confirm at the checkpoints".
- [ ] **Step 3:** In `README.md`, add a status line and the layout entries for the new scripts and `tests/`.
- [ ] **Step 4:** Commit.

---

### Task 15: Rebuild, QA, before/after, write-up (main session plus one subagent)

**Files:**
- Create: `experiments/2026-10-11-rig-annotations/README.md`
- Create: `experiments/2026-10-11-rig-annotations/{fox,moose}/rig/`
- Create: `experiments/2026-10-11-rig-annotations/before_after_*.png`

- [ ] **Step 1:** For both characters, `uv run spine_rig.py --master … --body body --heads face-heads --variants variants --annotations annotations.json --name <c> --out rig`. Expect no doubts in `report.json`; any doubts become checkpoint 6 questions.
- [ ] **Step 2:** `uv run spine_qa.py rig/<c>.json --master master.png`. Expect PASS on every line, including `seams`, `thumbs`, `sockets` and `landmarks`.
- [ ] **Step 3:** Before/after grids with `tools/render_frames.py`, old rig vs new at the same times:
  - fox: setup, wave 1.0, thumbs_up 1.2;
  - moose: setup, point 1.2, hold_card 1.2;
  - zoomed crops of the fox's boots and the moose's legs and shoulders.
- [ ] **Step 4 (checkpoint 6):** Open the grids and ask AskUserQuestion: Approve / Fix, plus doubts.
- [ ] **Step 5:** Write `README.md`: the problem table from the spec with before/after links, root causes (including the seam diagnosis), numbers (setup IoU, QA), and what's still open. Commit.
- [ ] **Step 6:** A whole-branch review by a fresh subagent (superpowers:requesting-code-review), then fix its findings.

---

## Addendum: weighted-mesh sleeves (spec section 5)

### Task M1: spine_qa renders weighted meshes + `mesh_fold`
**Files:** Modify `plugin/skills/skipbo-art/scripts/spine_qa.py`; Test `tests/test_qa_mesh.py`.
- `Rig.att_matrix`/`Canvas.layer` path gains `mesh` attachments (Spine 4.2 JSON: `type: "mesh"`, `uvs`, `triangles`, `vertices` in weighted form `[boneCount, boneIndex, x, y, weight, ...]` per vertex, `hull`, `width`, `height`).
- Render: deform vertices with bone world matrices and weights; draw each triangle with PIL affine transform from its UV triangle (alpha-composited, bilinear).
- `mesh_fold`: for each mesh attachment, signed triangle areas in every frame keep the setup sign. Wire into `check_structure` (setup) and `check_anim`.
- Tests: hand-built JSON with a 2×3-vertex mesh bound to two bones; rotating the child bone 60° bends the strip (rendered alpha matches an expected polygon within 2%); 170° fold → `mesh_fold` fails; region-only rigs unchanged (golden).

### Task M2: `arm` role and mesh export
**Files:** Modify `rig_annotations.py` (role `arm`: shoulder round_end, elbow point, wrist opening; normalise like a limb), `rig_place.py`, `spine_rig.py`; Test `tests/test_rig_mesh.py` (+ synthetic arm in `tests/synth_character.py`).
- Placement per spec section 5; mesh JSON per M1's format; slots: the upper-arm slot carries the mesh, the forearm slot is not written for that side; variant `raised` ignored for mesh arms; resolved.json points for the mesh attachment use its bind image px.
- Tests: synthetic character with arm pieces builds; at the setup pose the mesh outline matches the straight sleeve; at the hold_card pose spine_qa passes including `mesh_fold`; without arm pieces output is byte-identical to before.

### Task M3 (main session, user checkpoint): generate and annotate real sleeves
- nb-pro body-sheet style call per character asking for "one whole sleeve from the shoulder to the end of the cuff, straight, the width of image_1's sleeve, joint end up"; split; annotate role `arm`; checkpoint with the user; rebuild; QA; checkpoint 6.
