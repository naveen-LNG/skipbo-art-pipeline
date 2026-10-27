# Character → Spine parts

Proven on the Moose and the Fox (2026-10-11). The inputs are one master plus four generated sheets:
- a body sheet: every part painted whole, with round joint ends;
- a hands sheet: 6 poses per hand;
- a poses sheet: raised sleeve, tiptoe foot, tail up;
- (optional) two legs sheets, in-betweens of whole legs (stand to crouch, stand to tuck), for squats and jumps with bent knees;
- a face sheet: 9 expression heads.

**Every piece of the rig is generated art.** The master is only a placement and scale reference. Variants are swappable attachments, keyed by the animations.

Why: limbs cut from the master had flat cut edges where they touched the body. Raised arms looked glued on, and a tail cut out of a leg left a hole that read as the tail drawn in front ([experiment](../../../../experiments/2026-10-11-part-variants/README.md)). The professional cut-out practice this follows:
- every joint is a round overlap with the pivot at the circle's centre;
- hidden areas are painted;
- art is swapped when rotation runs out (Spine "rigging new poses", Moho switch layers, Cartoon Animator hand sets).

Cost per character: 4–6 Nano Banana Pro calls, including one or two re-rolls with changed words.

## Stages

1. **Master (approve before anything else).**
   `comfy.py run nb-pro --prompt-file references/prompts/spine/master.txt --var CHARACTER="…" --image 1=<design ref> --image 2=references/styles/blocks-characters/refs/shipped-hippo-atlas-small.jpg --image 3=references/styles/blocks-characters/refs/shipped-raccoon-atlas.jpg --var ASPECT=3:4 --var TEMP=0.6 --n 2 --tag <char>-master`
   Pick a variant that meets the **rig input contract** below. It's the reference for everything after. Annotate it once the first sheet is split (stage 6, checkpoint 1).
   **No design ref** (a character from words only): `master-textonly.txt` instead, with the two style atlases as image_1 and image_2 and the whole look in `CHARACTER` (the beaver, 2026-10-15: one call, 2 variants, one passed the contract).

   **Rig input contract.** Measure it with `uv run scripts/spine_qa.py --contract <variant>.png …`, which checks the background, faint shadow, centring, leg gap, arm gaps and keying (`keyable`). Then check the rest by eye. The checks apply to the colour-matching path (`--cut-from-master`, and the matcher that cross-checks the annotations), where a miss means mis-cut limbs:
   - background visible between each arm and the body along the whole arm;
   - background visible between the legs, from the feet up to the crotch (the colour path finds the crotch by scanning down the centre line below the torso);
   - one flat plain background and no cast shadow (the background is keyed from the border colour);
   - **keyable** (measured): the figure keys as more than 0.06 from the border colour (`rig_match.master_mask`, the setup IoU), so pale fur or a white muzzle close to the background's grey drops out as holes. Under 1.5% of the silhouette may key out (`key_holes_pct_of_silhouette`; the rabbit's rejected masters 4.5-7.6%, every rigged master at most 0.25%). A failing master on an otherwise good design: recolour only its background (the rabbit's `make_master_bg.py`) or re-roll with a darker background named in the prompt;
   - front view, symmetrical and centred;
   - **colour contrast at every cut:** sleeve ≠ vest and scarf; hand ≠ sleeve; foot ≠ trouser. The colour path separates these by colour; with annotations the placement doesn't depend on it, but the cross-check does.

   - a solid ground shadow (not measured; check by eye).

   If the design breaks the colour-contrast rule (bare arms in body colour, for example), say so before rigging: the cuts at the shoulder, wrist and ankle will be unreliable. Pick a variant with the head facing front; the checker doesn't measure head direction.
   The master prompt's wording was A/B-tested against an explicit leg-gap and colour-contrast version on the fox (2 variants each). All 4 met the contract, and the art director preferred the original prompt's look, so the original stays. The checker is the safeguard.
   **CHARACTER notes:** 1–3 sentences describing what image_1 shows: species, fur/skin colours, each costume piece with its colour, accessories, tail and props. They override image_1, so write a detail only if you can see it or the user stated it, and ask rather than invent. See `characters/moose.md` for the format.
2. **Write the PIECES list** for this character after *looking at the master*: four rows, every piece named concretely (see `references/characters/fox.md`, `moose.md`).
   - Generic categories made the model merge arms, drop an antler and add eyebrows.
   - Name where each piece **ends** when clothing hides the split. The Moose needed: the torso "ending at the gold belt buckle"; the leg "from the crotch down to its hem, with nothing below the hem"; the hoof "only the hoof that shows below the hem".
   - Spell out "four separate sleeve pieces: upper half / lower half of the sleeve".
   - **Trousers whose cuffs lie over the boots** (one-piece trousers, `master.layers` `"leg": "in_hips"`, stage 7): write the hips as "only the top of the trousers: the belt and the trousers below it down to the crotch and no further, with two rounded leg openings just below the crotch", and the legs as "left leg, right leg (each trouser leg alone, from just above the crotch down to its cuff, the cuff painted as it looks from the front with no opening showing, nothing below it)". The rig joins them into one piece.
3. **Body sheet:** `nb-pro`, prompt `body-sheet.txt`, `--var PIECES="…" --var CHARACTER="…"`, image_1 = approved master, image_2 = hippo atlas, `ASPECT=1:1 TEMP=0.4`.
   - Every piece is **final art**. The prompt asks for limbs painted upright with the joint end at the top, and every joining end fully round ("like the end of a sausage"). It also asks for the torso painted as it looks with the arms removed (rounded shoulders, sides painted to the waist) and the hips painted whole, including the crotch.
   - Check: upper arm and forearm are separate, no flat cut edges, nothing merged (a cap joined to the head, trousers joined to the torso). Two sheets painted at the same scale can be mixed piece by piece; compare torso widths first.
   - The rig places every piece at one scale, the body sheet's (`report.json` `global_scale_master_px_per_part_px`; from the torso's neck-to-waist, cross-checked against the torso's and head's widths: a `scale_disagree` doubt), and a two-point part only stretches 15%. A piece from another sheet painted at another scale comes out too long or short (the beaver's trousers from a second sheet: 25% too long, a 0.75 stretch doubt); rescale it to the body sheet's scale first.
   - Also check the pieces against the **master's** proportions, not only each other: a hips piece painted as long shorts with leg openings near the hem leaves the separate legs nowhere to go (the beaver's first body sheet); and arms painted 1.3x the master's arm length end up squashed and stuck on at the shoulder. "Only the top of the trousers, from the belt down to the crotch and no further" fixed the hips.
3b. **Hands sheet:** `nb-pro`, prompt `hands-sheet.txt`, `--var HANDS="…"` (6 poses, see the character files), same images, `ASPECT=3:2 TEMP=0.4`.
   - Poses: relaxed, open (wave), fist, point, thumbs-up, grip (pinching a thin card, with nothing drawn in it).
   - **Ask for the fist and the point palm-facing from the start.** All three characters so far came back with back-facing ones and needed a re-roll: a back-facing fist raised in cheer_jump shows the back of the hand, and a back-facing point is held across the chest, where it reads as a grip. Say "fist, palm side facing the viewer: the curled fingers and the thumb across them visible" and "point, the palm facing the viewer: index finger straight down, the other fingers curled onto the palm". When one still comes back back-facing, `hands-fist-palm.txt` / `hands-point-palm.txt` paint just that pose for both hands (one call, `--var HANDS=…`, `ASPECT=4:3`).
   - Every hand is wrist up and a chunky mitten like the master's. The first fox run drew realistic five-finger hands until the prompt said so.
3c. **Poses sheet:** `nb-pro`, prompt `poses-sheet.txt`, `--var POSES="…"`, `ASPECT=16:9` or `1:1`.
   - Rows: upper arm + **upper arm raised** (the same sleeve with its shoulder end bunched into a soft fold), foot + **foot on tiptoe**, tail + **tail up**.
   - Say "an upper arm is only the sleeve from shoulder to elbow, without any cuff". Otherwise the rest piece comes back as a whole sleeve.
   - For whole sleeves (role `arm`), `sleeves-pair.txt` (`--var SLEEVE="…"`, `ASPECT=4:3`) paints just the two sleeves, large. The poses template asked for whole sleeves on the beaver let faded ghosts of the atlas leak in and merge into the cuffs.
   - Describe the tail **as the master holds it** ("its narrow root at the upper right, where it joins the hips, the wide paddle at the lower left"). The matcher turns a tail at most 90 deg each way, so a tail painted the other way up can't be fitted (the beaver's first tail hung upside down).
3d. **Legs sheets (whole legs, for squats and jumps with bent knees):** build the rig once without them, then one `nb-pro` call per movement with prompt `legs-inbetweens.txt`, `ASPECT=21:9 TEMP=0.4`, and these images:
   - image_1: the approved master;
   - image_2: the key-pose frame at the end of the movement (`keypose.txt`: a deep crouch; the top of a tucked jump);
   - image_3: the rig's own rest legs, from `scripts/rig_rest_legs.py rig/<char>.json legs_rest.png --annotations annotations.json`; pass the `_grey` image.

   Each sheet paints 5 drawings of the belt, trousers and boots only, played left to right as one smooth movement: `squat` (stand to deep crouch) and `jump` (stand, push-off, tuck).
   - The trousers piece has no knees, so a squat could only squash it. The drawings are swapped in for the trousers and feet instead, like the hands: `squat`, `jump_hurdle` and `plant_seed` bend the knees and tuck the legs with them. A rig without them keeps squashing the hips.
   - Vars: `COUNT=5`, `REST_USE="Drawing 1 is this image exactly, at the same size, with the same painting; every other drawing is painted exactly like it."`, `MOVE`, `STEPS` and `CHARACTER`. The wording that worked on the beaver is in `experiments/2026-10-16-keypose-refs/prompts/keyposes.env` (`MOVE_SQUAT`, `STEPS_SQUAT`, `MOVE_JUMP`, `STEPS_JUMP`). Three things matter:
     - **image_3 as drawing 1.** Without it the model paints lanky legs: height over belt width 1.6–1.9 against the rig's 0.91.
     - **Each drawing's height in numbers** ("drawing 3 four fifths of drawing 1"). Otherwise the knees spread but the legs never shorten.
     - **No wording about an empty band above.** It invites faint ghost copies.
   - **In-betweens where a step is big.** A sheet repainted with 8 drawings failed on the beaver: the legs came out lanky, the paint drifted and the order wandered. Paint each in-between from its two finished neighbours instead. `legs-midpoint.txt` takes image_1 = drawing A and image_2 = drawing B (`MOVE`: the movement in one sentence) and paints "A exactly | in-between | B exactly" in one call, so the new drawing can only match their paint. Cut the middle drawing at the sheet's pixel scale, using the copies' belts: `experiments/2026-10-16-keypose-refs/scripts/cut_mid.py`. The beaver needed four: squat 3–4 and 4–5, jump 2–3 and 3–4.
   - **Split and annotate.** Split the sheet like the others and drop any ghost copies. Each drawing gets role `legs`, name `legs` and variant `<sheet>_<n>` (`squat_1` … `squat_5`, `jump_1` …, left to right), or `<sheet>_<a>-<b>` for an in-between. Two points:
     - `waist`: the middle of the belt, where the master's waist point sits on the master's belt;
     - `ground`: the soles' line, midway between the feet.

     Mark a drawing that adds nothing `ignored`; the beaver's `squat_2` is as tall as drawing 1 and barely bent. Drawing 1 is required: it sets the sheet's scale.
   - **The rig** (`rig_variants.add_legs`):
     - two slots, `legs_a` and `legs_b`, just above the trousers and hidden at rest, each on its own bone at the master's waist (appended after the other bones);
     - **one scale per sheet**, fitted so drawing 1 covers the rig's own rest trousers and feet (as wide at the waist, as tall from the waist to the soles). A per-drawing scale flickered by up to 15%.
     - An in-between's height is declared halfway between its neighbours' (the model paints the shape halfway, not reliably the height), and the drawing is squashed to it (`report.json` → `squash`).
     - Doubt `legs_aspect`: a sheet that has to stretch more than 12% one way to fit. The beaver's jump sheet stretches x0.77: it was painted lankier.
   - **The moves** (`rig_anim.leg_track`, driven by progress):
     - Each sheet has a progress p, 0 standing to 1 at full crouch or tuck, keyed with holds. The drawing shown is the nearest in p along its sequence: the rig's own parts, then drawing 2, 3 and on, with the in-betweens in their places. The rig's parts stay on screen until the first swap, so nothing pops at the start.
     - The drawings sit in p halfway between evenly spaced and spaced by height change (`legs_spacing`). Evenly spaced alone, an in-between halves the legs' speed in its interval and jerks the body.
     - The legs' height is a Catmull-Rom curve over p through the drawings' heights; each slot's bone squashes or stretches its drawing to it, within about 10%. On the ground the hips drop by the height lost, so the soles stay put.
     - **Every swap cross-fades** (`cross_fade`). Drawings alternate between `legs_a` and `legs_b`. The incoming one fades in over 2 frames before the swap, then the outgoing one fades out over 2 frames (Spine `rgba` slot keys), so one is always opaque. The rig's own trousers and feet fade the same way, with their worn back slots.
       - On the beaver the average swap pop fell from 0.8–2.5% to under 0.2% of the lower body's pixels (`experiments/2026-10-16-keypose-refs/scripts/pops.py`).
       - `spine_qa` draws the fade (slot alpha), but judges a fading slot by its whole drawing. A slot faded out entirely is judged as hidden.
     - `squat` (2 s): down into the crouch, hold, back up; the arms hang beside the knees and the tail lies out flat behind.
     - `jump_hurdle` (2.9 s): crouch (the squat sheet), push off and tuck (the jump sheet), land and absorb (the squat sheet from 1.74 s). The sheets meet at p = 0, on the rig's own legs. In the air the body rides its own arc and the legs fold under it.
     - The jump sheet only lifts the hips with its push-off, on the way up. Letting its fold move the hips while the body lands jerked a character whose legs are half its height (`spine_qa`); that was kp_rig's original plan, which the beaver tolerated.
     - Experiments: `experiments/2026-10-16-keypose-refs` (sections 2a and 2b) and `experiments/2026-10-16-legs-variants`.
4. **Face sheet (9 expression heads):** `nb-pro`, prompt `face-sheet.txt`, the same image_1/image_2, `ASPECT=1:1 TEMP=0.4`. You get the same head 9 times (neutral, blink, happy, laugh, surprised, sad, angry, talking, wink) as whole-face swaps for the head slot. Separate eye/brow/mouth pieces (`face-features-sheet.txt`) come out about 2× too large; use them only if a rigger explicitly asks.
5. **Split each sheet:** `comfy.py run parts-split --image 1=<sheet.png> --tag <char>-body` (and `-face`). Run it from inside `<char>/` (or set `COMFY_RUNS_DIR=<char>/runs`), so the pieces land in `<char>/runs/<tag>/`: `rig_annotations.py propose` needs the split run directly under `<char>/runs/`. BEN2 cut-out → one RGBA PNG per separated piece, soft edges kept.
6. **Annotate and confirm (checkpoints 1–5).** Don't name, mirror or turn parts by hand: `prep.py` (see `experiments/2026-10-11-part-variants/fox/prep.py`) is superseded. The agent annotates by looking, the code snaps and derives, and the user confirms at each checkpoint. One file holds it all: `<char>/annotations.json`. Each split run lives in `<char>/runs/<split-run>/`, and `<split-run>` is the run folder name, which is the `--tag` you gave `parts-split`.

   | Who | Does |
   |---|---|
   | Agent (looks) | Role, variant, side, thumb tip, palm or back, layer hint, rough points, confidence |
   | Code | Snaps points to the exact geometry, turns each piece joint end up, picks the mirror for each side, writes the files, lists doubts |
   | User | Approves, or fixes in one sentence |

   Coordinates run from 0 to 1 across each image. Joint names are shared: the master's `shoulder_l` and the upper arm's `shoulder` (a round end) are one joint, and the master's point is where the upper arm hangs from. The torso's own `shoulder_l` is optional (a plain point); when given it only cross-checks the torso's placement. A missing required point or an unknown name is an error.

   | Role | Required points (kind) |
   |---|---|
   | master | `neck`, `waist`, `ground`; `shoulder`, `elbow`, `wrist`, `fingertip`, `hip`, `ankle`, each `_l` and `_r` |
   | torso | `neck`, `waist`; optional `shoulder_l`, `shoulder_r` (plain points, never snapped: a cross-check only) |
   | hips | `waist`, `hip_l`, `hip_r` (openings) |
   | upperarm | `shoulder`, `elbow` (round ends) |
   | forearm | `elbow` (round end), `wrist` (opening) |
   | arm (a whole sleeve, shoulder to cuff, drawn straight; replaces that side's upper arm and forearm with one bending mesh) | `shoulder` (round end), `elbow` (point: where it bends; annotate it at the master's elbow ratio along the arm, i.e. shoulder→elbow over shoulder→elbow→wrist as on the master, or that half stretches into a `stretch` doubt), `wrist` (opening) |
   | hand | `wrist` (opening), `thumb_tip`, and `fingertip` (none for a fist or thumbs-up) |
   | leg | `hip` (round end), `hem` (opening) |
   | foot | `ankle` (opening), `ground` |
   | tail, ear, antler, horn, hat, prop | `root` |
   | head, neckwear | `neck` |

   A round end snaps to the centre of the circle that fits the painted end. An opening snaps to the centre of a rim and records its width and depth. A plain point isn't snapped. The search radius is 0.6 × the piece's own width. A snap that moves the point more than 0.10 × width is rejected and the rough point kept.

   **Piece status.** `proposed` (draft), `confirmed` (the user approved), `fixed` (the agent corrected it after a Fix answer), `ignored`. Use `ignored` for a spare piece on a sheet that the rig doesn't use, or for a generated piece that doesn't fit (with a `note` saying why; the moose's generated leg tubes are ignored, because its hips and hoof cuffs cover the whole trouser leg). Feet with no leg piece are parented to the hips.

   **The file.** `annotations.json` doesn't exist until the first `propose` creates it (with `--character` and `--master`, see below). So run `propose` on the first split sheet, then fill in the master before annotating that sheet. The master part of the file looks like this:

   ```json
   "master": {
     "image": "fox_master.png",
     "points": {"neck": [0.50, 0.38], "waist": [0.50, 0.62], "ground": [0.50, 0.97],
                "shoulder_l": [0.62, 0.45], "shoulder_r": [0.38, 0.45], "elbow_l": [0.68, 0.55], "elbow_r": [0.32, 0.55],
                "wrist_l": [0.71, 0.64], "wrist_r": [0.29, 0.64], "fingertip_l": [0.72, 0.71], "fingertip_r": [0.28, 0.71],
                "hip_l": [0.56, 0.72], "hip_r": [0.44, 0.72], "ankle_l": [0.57, 0.88], "ankle_r": [0.43, 0.88]},
     "hands": {"l": {"thumb_side": "lateral", "facing": "palm"}, "r": {"thumb_side": "lateral", "facing": "palm"}},
     "layers": {"upperarm": "over_torso"},
     "status": "proposed"
   }
   ```
   - `points`: bare `[x, y]`, 0 to 1 across the master image, every name in the master row above.
   - `hands`: for each side, `thumb_side` is `lateral` (away from the body) or `medial` (towards it) as the hand hangs at rest, and `facing` is `palm` or `back`. They must agree: a palm facing the viewer puts the thumb lateral, a back puts it medial. A confirmed master that breaks this fails validation; a draft one gets a doubt.
   - `layers`: `upperarm` is `over_torso` (default) or `under_torso`. If the character has a vest or straps over the sleeve, set `under_torso` so the armhole covers the sleeve top as in the master, and always ask that question. It moves only the upper arm: forearm and hand stay in front of the torso, so a forearm across the belly stays visible. The forearm is then drawn over the upper arm at the elbow (by default the sleeve end covers the forearm's top). `foot` is `under_hips` (default) or `over_hips`, and only matters for a character with no leg pieces (the legs are part of the hips): `under_hips` hides the foot's top behind the trousers (a hoof cuff under trouser legs), `over_hips` draws it in front of the hips (dungaree legs that go into the boots). With leg pieces the order is leg, foot, hips whatever it says. `leg` is `separate` (default) or `in_hips`: one-piece trousers, the leg pieces composited under the hips into one piece, so the rig is leg-less (see stage 7, "Trouser cuffs over boots"); the master's `hip_l` / `hip_r` then mark the cuffs. `hand` is `under_forearm` (default: the hand tucked under its cuff) or `over_forearm`: the hand drawn over the forearm, for a glove or paw whose own cuff covers the sleeve's end (the moose's fur cuff over the sleeve's fur tufts).
   - `status`: `proposed`, then `confirmed` (user approved) or `fixed` (the agent corrected it after a Fix answer).

   **Checkpoint 1: master.** After the master passes the contract and its `master` block is filled in:
   1. `uv run scripts/rig_annotations.py check <char>/annotations.json` (no `--sheet`) writes `annotations/master_overlay.png`: labelled points, thumb arrows and layer hints.
   2. Open the PNG with the OS viewer, print the path, and ask (one AskUserQuestion call: "Approve / Fix", plus the sleeve-under-vest question for a vest or straps).
   3. Approve: `uv run scripts/rig_annotations.py confirm <char>/annotations.json --master`. Fix: edit the master points, hands or layers, set `status` to `fixed`, run `check` again, and ask again.

   **Checkpoints 2–5: each sheet** (body, hands, poses, then faces). Run the split from stage 5 first, then:
   1. **Draft.** `uv run scripts/rig_annotations.py propose <char>/runs/<split-run> --annotations <char>/annotations.json [--master <char>_master.png] [--character <char>]`. This adds a draft piece for each split image (role blank, rough points named `top` and `bottom`) and writes `annotations/<split-run>_numbered.png`. `--master` and `--character` are needed only the first time, when the file is created. Look at the numbered sheet. For each piece set `role`, `name`, `variant`, `side` (`l`, `r` or `either`), `facing`, `confidence` (0–1), and replace `top`/`bottom` with the role's own point names and the rough positions. `name` is the part name used in the file names and defaults to the role. It is free for foot, tail, ear, antler, horn, hat, neckwear and prop (`boot`, `sneaker`, `beanie`, `scarf`, `bell`): the rig takes each part's layer and parent from its role, not its name. For torso, hips, upperarm, forearm, arm, hand, leg, legs and head it must be the role itself (the rig's bones, animations and expression heads are keyed by those names), and no other role may use one of those names; validation says so. One name, one role; a name never ends in `_l` or `_r` (the side is added). A head's `variant` is its expression, and its `neck` point is where the neck meets the body. Don't leave `top`/`bottom` behind.
      A filled-in piece (key `<split-run>/<NN>`, for example `fox-hands-parts/05`) and a spare one:
      ```json
      "fox-hands-parts/05": {"role": "hand", "name": "hand", "variant": "point", "side": "either", "facing": "back",
        "confidence": 0.8, "status": "proposed",
        "points": {"wrist": {"at": [0.5, 0.03]}, "thumb_tip": {"at": [0.95, 0.58]}, "fingertip": {"at": [0.55, 0.97]}}},
      "fox-hands-parts/06": {"status": "ignored", "role": "", "points": {}, "note": "spare second fist, not used"}
      ```
      A point's `kind` comes from its role (table above): a `kind` stored in the file is ignored for the known roles. Code adds `snapped`, `width`, `depth` and never touches `at`. Two optional fields: `mirror: true` flips a piece as annotated, and `painted_as` (`l` or `r`) says which side a non-hand piece with `side: "either"` was painted as, so the other side is its mirror (a non-hand `either` piece without it is an error). Hands get their mirror from anatomy instead (below), so every hand needs `facing`: which side of the hand the drawing shows, `palm` or `back`. Judge it from the art. Fingers curled toward the viewer, or the palm's pad, mean `palm`. Knuckles, nails or the back of the paw mean `back`.
   2. **Render.** `uv run scripts/rig_annotations.py check <char>/annotations.json --sheet <split-run>` validates, snaps and turns the pieces. It writes `body/`, `variants/` and `face-heads/` (named `<char>_<part>[_l|_r]` and `<char>_<part>_<variant>`), and the pictures `annotations/master_overlay.png`, `<split-run>_overlay.png` (numbered pieces, labels, rough points hollow, snapped points filled, thumb arrows) and `<split-run>_worn.png` (each variant after its mirror and rotation, on a stub forearm at the pose its gesture will use, outward or across, labelled with the painted side; the character's left on the picture's right). The last line is JSON: `{"doubts", "worn", "unconfirmed", "snap_failed"}`. At checkpoint 3 (hands) add `--jev` when a TypeSafe key is set: `jev_facing.py` scores each hand piece's palm or back from five visible cues averaged over 16 turns (about $0.001 a piece, cached in `annotations/jev_cache.jsonl`), and a confident call that disagrees with the annotated `facing` becomes a doubt; the JSON then also carries `"jev"` (each hand's score and call). Without a key it prints SKIP and the check runs as usual.
   3. **Show.** Open the PNGs with the OS viewer (`open` on macOS, `start` on Windows) and print their paths.
   4. **Ask.** One AskUserQuestion call. Question 1 is "Approve / Fix" for the sheet. Questions 2–4 are the doubts from the JSON, with the options each doubt carries. More than 3 doubts go in a follow-up call. Without AskUserQuestion, ask the same questions in plain text.
   5. **Fix or approve.** A Fix answer is one sentence. Edit the annotation, set those pieces to `fixed`, run `check` again and ask about that sheet only. Approve: `uv run scripts/rig_annotations.py confirm <char>/annotations.json --sheet <split-run>` (for the master: `--master`).

   **What raises a doubt.**

   | Cause | Notes |
   |---|---|
   | Confidence under 0.7 | The piece gets its own question |
   | Hand without `facing` | It is mirrored by the old thumb-target rule, which can show an impossible hand |
   | Ambiguous hand mirror | The thumb tip sits (almost) on the hand's axis, so it has no side |
   | Rest hand facing differs from the master's | Or the master's `facing` is missing (or, for a hand without `facing`, its `thumb_side`) |
   | No pose shows a gesture hand's thumb up | point / thumbsup: neither outward nor across; grip: not across the belly. The `facing` is probably wrong |
   | Master hand `thumb_side` disagrees with its `facing` | Draft master only; a confirmed one fails validation |
   | Hand without a fingertip tilted over 30° after its quarter turn | |
   | `check --jev`: Jev's cue score calls the hand palm (≥ -0.05) or back (≤ -0.20) and the annotation says the other | In between is no call. Jev asked palm/back directly is at chance; the cues reach AUROC 0.89. It checks the label, not the pose: the beaver's backwards cheer fist was correctly labelled back (Jev agreed, -0.40), so no doubt fires; a back-facing fist raised in cheer shows its back, so use a palm-facing fist there. It reads the beaver grip as palm, a fair reading of that art: answer by looking |
   | Rig stretch or narrowing over 15% | The rig still builds with the clamped value |
   | `hips_too_wide` / `upperarm_too_wide`: a width fit over 35% | The hips' leg openings against the boots, or the upper arm's elbow against the forearm's; the rig builds with 35% |
   | `wrist_trim_ambiguous`: the forearm (or a forearm variant) is not trimmed at the wrist | The rest hand's colours near its wrist are all within 40 RGB of the sleeve's, so glove and sleeve can't be told apart; check the wrist by eye |
   | `sleeve_too_thin`: the master's sleeve is over 20% thicker than the sleeve drawing (`raw` > 1.2) | The width fit never widens, so the cuff reads smaller than the hand and the arm too thin (the beaver: 1.34; the approved fox 1.07, moose 1.15). Widen the sleeve art across, tapered: unchanged to the elbow, up to the measured ratio at the cuff. A uniformly wider sleeve folds at hold_card's elbow bend |
   | `sleeve_too_wide`: a whole sleeve's half is over 35% thicker than the master's | The sleeve sheet painted a much fatter sleeve; the rig narrows it by 35% (`parts.upperarm_<s>.width_fit.<half>.raw`). Regenerate the sleeve slimmer, or check the master points sit on the sleeve |
   | `mesh_fold_range`: a whole-sleeve mesh would fold at the elbow in some animation | No weights keep the sleeve's triangles unfolded over the largest elbow bend + 10° (`meshes.*.need_deg` vs `covered_deg`); a sleeve too short for its width. Check that hold in the frames; a slimmer or longer sleeve, or the two-piece arm, avoids it |
   | Matcher disagreement over 4% of body height | Asked at checkpoint 6 |
   | `gesture_across`: no head-clear across pose has the paw 4% of body height above hold_card's | Asked at checkpoint 6; the highest clear pose (or the fallback) is used, and the two holds may read alike |
   | `not_placed`: a rest output the rig couldn't place | Usually an output without a side on a sided role; see the codes below |

   The rig build (`spine_rig.py --annotations`) writes its doubts to `rig/report.json` → `doubts`, each `{"part", "reason", ...}`; ask about them at checkpoint 6. The `reason` codes:

   | Code | Meaning |
   |---|---|
   | `scale_disagree` (part `global_scale`) | A global-scale estimate (`torso_length`: neck-to-waist; `torso_width`, measured only where the master's arms are clear of the body; `head_width`, at the cheeks) is more than 15% off the scale used (`off_by`). Neck-to-waist is used unless the other two agree with each other and both disagree with it (`used: others`: the torso's points are the odd one out, as the rabbit's low waist point was). Check the torso's neck and waist points first, then whether a piece was painted out of proportion |
   | `variant_scale_disagree` | A foot variant's ankle widths give a scale more than 1.3x from its area ratio (one snapped, one not: the bear's tiptoe clog), so it was scaled by area (`width_ratio`, `area_ratio`, `snaps`). Fix the ankle points so both snap the same way |
   | `stretch` | A two-point part (or a sleeve half) stretched more than 15% along its length to reach both master joints |
   | `narrow` | A child's end narrowed more than 15% to fit its parent's opening (leg into boot or hips) |
   | `ground_miss` | A foot's scale hit its 0.85–1.15 limit matching the master's ankle-to-ground height (`ratio` is the raw one) |
   | `hips_too_wide` | Leg-less hips with feet `over_hips` needed more than 35% narrowing to fit the boots |
   | `upperarm_too_wide` | The upper arm's elbow end needed more than 35% narrowing to match its forearm |
   | `sleeve_too_wide` | A whole sleeve's half is more than 35% thicker than the master's sleeve |
   | `sleeve_too_thin` | The master's sleeve is more than 20% thicker than the sleeve drawing, which is never widened |
   | `shoulder_mismatch` | The torso's own shoulder point lands more than 4% of body height from the master's |
   | `shoulder_outside_torso` | The master's shoulder lies outside the placed torso; only the bone's origin moved (`moved_px`) |
   | `matcher_disagreement` | The colour matcher places a part more than 4% of body height from where the annotations put it |
   | `worn_opening_guessed` | A worn foot has no painted inside: its cut follows the top silhouette (or the opening's ellipse) |
   | `worn_no_width` | A worn foot has no ankle width, so it is drawn whole, not cut into back and shell |
   | `wrist_trim_ambiguous` | The hand shares the sleeve's colours at the wrist, so the forearm (or sleeve) was not trimmed |
   | `gesture_thumb` | No pose shows that gesture hand's thumb up (point, thumbs-up) or the grip isn't up across the belly |
   | `gesture_across` | No head-clear across pose puts the paw 4% of body height above hold_card's (`search` low or none) |
   | `mesh_fold_range` | No weights keep a sleeve mesh unfolded over the largest elbow bend the animations use, +10° |
   | `variant_guessed` | A pose variant lacks the annotated joint or widths to place it, so it used the guessed joint path |
   | `not_placed` | A rest output nothing placed (a sided role's output without `_l`/`_r`, say); it is left out of the rig |

   A snap that fails on a confident piece (0.7 or more) is not a question: it shows as a red label in the overlay and in `snap_failed`. Fix the rough point.

   **How the mirror is chosen: anatomy.** A hand's thumb direction is the thumb tip's sideways offset from the hand's axis (wrist to fingertip). Which side the thumb belongs on is fixed by the side of the hand that is painted, not by the gesture. Here it is for a hand joint end up (wrist on top, fingers down), seen from the front:

   | Hand | Shows | Thumb on |
   |---|---|---|
   | Left (character's left, picture right) | palm | image right (lateral) |
   | Left | back | image left (medial) |
   | Right | palm | image left (lateral) |
   | Right | back | image right (medial) |

   Each side's output is mirrored when the painted thumb is on the other image side (`rig_hands.anatomical_mirror`). Turning a hand in the picture plane keeps that side, so a gesture cannot choose the thumb, only the pose. A palm-facing hand pointing outward has its thumb up. A back-facing hand pointing outward has its thumb down. The old rule mirrored for the gesture's thumb target and produced exactly that impossible hand: thumb up, back of the hand showing, pointing outward.

   **How the gesture pose is chosen** (`rig_hands.hold_pose`, used by the worn strip, the doubts and `spine_rig.py`):

   | Gesture (hand) | Poses tried | Thumb target |
   |---|---|---|
   | `point` (point), `thumbs_up` (thumbsup) | `outward`: the arm out to the side (`GESTURE_ARM_DEG`). `across`: elbow at the side, forearm across the chest toward the other side, hand in front of the chest below the chin. `spine_rig.py` searches it per character: upper arm −85° to −45°, forearm 160° to 190° (character's left), the highest paw whose elbow, forearm and paw stay clear of the head (grown a little) and sit at least 4% of body height above the hold_card paw. Neckwear is no obstacle: the forearm and hand are drawn in front of it (see Draw order). If none is that high it takes the highest head-clear paw that is still above hold_card's, and if there is none it keeps `GESTURE_ARM_DEG_ACROSS` (−75°, 175°); either way it raises a `gesture_across` doubt (`report.json` gestures: `across_search` is `ok`, `low` or `none`). The worn strip judges the thumb at (−75°, 175°) | up: outward is used if its thumb is within 45° of up, else across if that one is; if neither, outward is kept with a doubt |
   | `hold_card` (grip) | across the belly only | up (a doubt if not) |
   | `wave` (open), `cheer_jump` (fist) | no choice | wherever anatomy puts the thumb (reported, not chosen) |
   | Rest hand | the master's pose | the master's `thumb_side` |

   So a back-facing point hand points across the body with its thumb up, and a palm-facing one points outward. A hand without `facing` falls back to the old thumb-target rule (`rig_hands.choose_mirror`, legacy) and raises a "facing missing" doubt.

   Limbs and hands are turned joint end up; feet are not rotated. This replaces the hand-written steps ("mirror the left set to get the right", "rotate the thumbs-up so the wrist is on top").

   **The gate is the file.** `spine_rig.py --annotations` refuses to build while the master or any piece is `proposed`, and lists them. `--allow-proposed` is for experiments only: the build prints a `WARNING` naming the keys still proposed, and `report.json` is stamped `allow_proposed`.

   **Get the role exactly right** (upperarm vs forearm vs hand, leg vs foot, ear vs antler): placement picks each part's points and layout by role, and the role, not the name, sets its draw layer and the bone it hangs from (a hat named `beanie` hangs from the head, neckwear named `neckwear` is drawn under the head, feet named `sneaker` are feet and swap to their tiptoe variant). Left/right on a pair only needs a best guess; the rig corrects it (see `renamed` in `rig/report.json`).
7. **Heads need no scaling:** `spine_rig.py` matches the neutral expression head against the master to find its size and position. If the expression heads include the ears (the fox's did), the rig drops the separate ear pieces so ears aren't doubled. (`comfy.py scale --match-width` is still available for hand-assembled rigs.)
8. **Build the Spine skeleton:** `uv run scripts/spine_rig.py --master <char>_master.png --annotations <char>/annotations.json --heads <char>/face-heads --variants <char>/variants --out <char>/rig` (without uv: `pip install numpy pillow`, then `python scripts/spine_rig.py …`). `--body` is ignored when `--annotations` is given: the body parts come from the file's outputs, and `--heads` and `--variants` default to the folders of the outputs `check` wrote (so you can leave them off). `--name` defaults to the annotations' `character`; given and different, the build stops. Without `--annotations` the old colour-matching path runs (with `--body <char>/body --name <char>`; parts' layers are then guessed from their names).
   - **Placement from annotations.** The confirmed joints decide where the rest parts go; the colour matcher below still runs as a cross-check.
     - Torso, hips, upper arm, forearm, leg: rotation and position line the piece's two joints up with the master's. Width stays at the sheet's scale; length stretches by up to 15% to hit both joints. Beyond that, the code clamps and raises a doubt.
     - Upper arm: its shoulder goes on the master's `shoulder_*` (the single source of truth), not pushed in. If the torso carries its own shoulder point and it lands more than 4% of body height from the master's, that is a `shoulder_mismatch` doubt. If the master's shoulder lies outside the placed torso (annotated on the shoulder's outline), the bone's origin moves to the nearest point the torso and the upper arm share; the move is the shoulder's push-in and a `shoulder_outside_torso` doubt. The upper arm's art still hangs from the master's shoulder; only the rotation point moves, so the sleeve swings under the vest without lifting off the torso.
     - The hips bone runs from the top of the hips, through the waist, toward the leg openings: into its own part.
     - Hips without legs, feet `over_hips` (trouser legs running into the boots, the fox): the hips are narrowed across (scaleX about the centre line, height kept, waist still on the master's) until each leg opening is at most 0.8 times its boot's ankle opening (annotated widths, master px), so the trousers go into the boots instead of swallowing them. At most 35%; beyond that a `hips_too_wide` doubt. `report.json` `parts.hips.width_fit` records `{factor, raw}`.
     - Upper arm width: narrowed across so its elbow round end is as wide as the forearm's (annotated widths, master px), so the sleeve reads as one tube instead of stepping at the elbow. Never widened; at most 35%, beyond that an `upperarm_too_wide` doubt. Only the rest upper arm is narrowed: its variants (raised sleeves, whose bunched painted shape is intentional) keep their painted width, scaled against the rest's un-narrowed width. `parts.upperarm_*.width_fit` records it.
     - Forearm at the wrist (whatever `hand` says: a glove's cuff over the sleeve, or the moose's cream sleeve cuff over the glove's fur band): the forearm, and any forearm variant, is trimmed past its wrist rim (the line across the forearm through the wrist opening, 0.15 times the opening's depth toward the elbow; 2 px feather), so the sleeve's own fur tufts don't show beside the glove's. The trim is colour-aware only: with no rest hand on that side it is skipped (`wrist_trim` records `{"skipped": "no_rest_hand"}`); hand colours within 40 RGB of a sleeve colour are dropped first, and if none are left it is skipped too (`{"skipped": "ambiguous_colours"}`, a `wrist_trim_ambiguous` doubt). Otherwise past the line only pixels nearer the rest hand's colours near its wrist (its fur cuff, the glove) than the sleeve's own colours go, so the sleeve cuff's rounded bottom stays and a sleeve-coloured cuff (the fox's) is left whole; sleeve-coloured specks not joined to the sleeve or thinner than 6 px go too, and the trimmed pixels take the kept colour (no fur RGB under alpha 0). `parts.forearm_*.wrist_trim` records the trimmed and feathered pixel counts; where the trim removed or faded anything, `annotations.resolved.json` gives that forearm attachment a `rim_inset`, and the QA socket check measures the glove's spill past that moved rim (a forearm left whole keeps its rim).
     - Whole sleeve (role `arm`): on its side it replaces the upper arm and forearm with one weighted mesh in the upper arm's slot (`scripts/rig_mesh.py`; the forearm bone stays, with no slot of its own). The sleeve is scaled by its own shoulder→elbow→wrist length against the master's (a sleeve sheet paints at its own scale: the fox's at ~1.8x the body sheet), then each half lines up with its master joints like a limb (`stretch` doubts as usual). It is wrist-trimmed like a forearm, and the hand goes into its wrist opening. **Width fit:** a sleeve sheet paints at its own proportions (the fox's was fatter for its length than the master's), so each half's thickness is measured on the master across its axis (shoulder→elbow at 40/50/60%, elbow→wrist at 25/35/45%, above the cuff) and the mesh's bind geometry, not the texture, is narrowed across the axis (centred on the master's tube when both halves are measured; otherwise about the drawing's own centre, so the elbow never jogs sideways), the two halves blended across the elbow; never widened, at most 35% (a `sleeve_too_wide` doubt beyond). A master edge is a step to a different colour: a step back into the same cloth (a knit ripple, shading) is walked past. A master edge against a part drawn over the sleeve (a vest or straps with `upperarm: under_torso`, the scarf, the head, a sweater body of the same yarn) hides the sleeve's own edge, so that sample isn't measured. Before this rule, the beaver's knit ripples read as edges and re-centred one sleeve 117 px; a half with fewer than two measured samples keeps its painted width (the moose's upper sleeve, under its vest). `upperarm_too_wide` never applies, and the raised-sleeve swap is off for that side (`mesh_skipped_variants`). Factors: `report.json` `parts.upperarm_<s>.width_fit` and `meshes.*.width_fit` (`factor`, `offset_px`, `raw`, `samples`). **Elbow:** small bends keep the spec's weights (smoothstep over ±0.5 sleeve width). A bigger bend fits each vertex's motion (least squares over the needed bends, the holds weighted most) to a tube bent like a beam over a band around the elbow, measured in sleeve widths and never reaching above the shoulder point (the shoulder end stays rigid with the upper arm), then fills the crease out to the corner where the upper arm's and forearm's inner sides meet, so nothing behind shows through it - a round outer elbow and a closed inner crease from static binds only. Where that would fold, the plain fit is used, and past that a fold-free per-side grid design is blended in near the elbow (without the fill). Bands from 0.8 to 1.4 widths above the elbow and 0.6 to 1.0 below are tried shortest first: a closed crease wins, then a longer band only if it rounds the outer elbow by more than 2°, so the bend stays at the elbow instead of bowing the whole upper arm. No triangle folds over the largest elbow bend the animations use, +10° each way (`report.json` `meshes.*`: `need_deg`, `covered_deg`, the design: `smooth` band in true widths, `grid_share`, `crease_fill`, `outer_corner_deg`, `crease_gap`). **Large bends:** a short, fat sleeve can't fold much past ~110°; when no design covers the need, the build raises a `mesh_fold_range` doubt (the fox's sleeve, at ~1.3 widths per half, can't take the old across point's ~150°). Draw order: the mesh sits at the upper arm's layer (under the torso with `upperarm: under_torso`, straps over its top); in hold_card, and in point or thumbs-up when they go across, a drawOrder key lifts it to where a forearm is drawn (above the torso, above neckwear) on the last frame before the forearm reaches the torso, and drops it back on the first frame after it leaves (`meshes.*.over_torso_in`). The hand hugs its sleeve's slot in every frame: directly below it (tucked under the cuff, the default and the moose's choice) or directly above it with `hand: over_forearm`, and moves with it in those keys; spine_qa's `layer_order` check holds every hand to that side of its forearm or sleeve. The mesh's bind positions and weights are solved by the rig (fold-free over the needed bends, each triangle owned by the bone on its side of the elbow), not hand-editable smoothstep weights: change the sleeve's annotation and rebuild rather than painting weights in the Spine editor.
     - Hands are **sized** by the master's wrist-to-fingertip against the piece's (`HAND_SCALE` 0.8-1.6 of the sheet's), so the master's `wrist_*` point decides the hand's size as well as its place. The piece's wrist is its hidden top, so put the master's wrist where that top would be, inside the cuff, or move `fingertip_*` out to match. Annotated where the mitten leaves the cuff, the beaver's hands came out 1.2x too small. The hand's angle against its sleeve matters too: a mitten hanging more upright than a slim cuff swings its top corner out beside it (sockets spill).
     - Hands: the wrist goes a third of the cuff's depth into the forearm's wrist opening, along the forearm (a hand-in-forearm socket for QA), and the wrist-to-fingertip direction lines up with the master's (a fist: wrist to centroid). The hand bone runs along the rest hand image's own axis (image-down; hands are joint end up), not along that wrist-to-fingertip line, and every hand variant is turned so its own image-down lies along the bone (attachment rotation 90) with its wrist on the bone's origin; a variant does not copy the rest hand's turn. In the gestures, wave and cheer_jump the hand turns to continue the forearm's line at the hold, the convention rig_hands' thumb and pose rules assume.
     - Feet: the ankle opening goes on the master's ankle and the foot is scaled so its ankle-to-ground height matches the master's, within 0.85 to 1.15 times the sheet's scale; hitting that limit is a `ground_miss` doubt, with the raw ratio. Feet with no leg piece hang from the hips. Without legs and with feet `over_hips` (the fox), each foot moves across so its ankle opening's centre stands under the placed (narrowed) hips' leg opening on its side, still at the master's ankle height: `parts.boot_*.ankle_shift` records `{dx}` (master px), and it is the ankle's push-in (the QA landmark tolerance).
     - Neckwear: its `neck` point goes on the master's neck, then the colour matcher snaps it within 4% of body height (a scarf's ring centre and the master's neck need not be the same point; a low scarf opens a gap under the chin).
     - Head, hat, tail, props: placed by the matcher as before; the annotated `neck` or `root` point sets the pivot.
     - Trouser cuffs over boots with separate leg pieces: impossible, because with leg pieces the order is always leg, foot, hips and the boots go over the legs. Set `master.layers` `"leg": "in_hips"` (**one-piece trousers**): spine_rig composites the belt-to-crotch hips over its two cuffed legs into one hips piece at the sheet's scale (`scripts/rig_trousers.py`; each leg's hip pushed into its opening by a third of the depth, narrowed to it by up to 15%), so the rig has no leg bones and the feet go `under_hips`, under the cuffs. The composite's `hip_l` / `hip_r` are the legs' hems, so annotate the **master's** `hip_l` / `hip_r` at the trouser cuffs. Ask the body sheet for the hips to the crotch plus two cuffed trouser legs (stage 2), never for "the whole lower body as ONE piece": that fights the template's "each leg in two" and came back as shorts (the beaver, the bear) or belt-to-hem trousers (the rabbit, the red panda), each rebuilt with a local `make_trousers.py`. A boot painted only as tall as the master's visible boot barely tucks under the cuff, so walk and run lifted it out (`detached`, `unstitched`): every leg-less rig with its feet under the hips (one-piece trousers or not) now gives each foot a hidden shaft (`scripts/rig_shaft.py`): 6% of body height above its ankle opening, as wide as the opening, in the foot's own colours (each column's lighter shades just below the opening), drawn behind the foot and kept only under the placed hips, in one straight band inside the trouser leg's narrowest row (inset 8% each side, so a stepping foot's growth can't push it out beside a wider cuff), so the setup pose doesn't change. The foot's annotated points move down by the rows added. Pose variants (a tiptoe) get the same shaft, as high in master px and kept where the rest's is hidden, so `variant_misfit` stays near 1; they are still sized against the painted foot alone. `report.json` records `parts.<foot>.shaft` and `variants.<att>.shaft`. No more local `make_boots.py` (the red panda) or painted ankle stub (the bear).
     - Ears, antlers, horns: matched after the head and hat, on their annotated side (never swapped: a mirrored ear carries the other side's lighting), with the annotated root on the head, preferring master pixels nothing else explains.
     - A pivot that falls outside its own part (matched parts, neckwear) moves to the part's nearest opaque pixel.
     - Socket fit: a child's end is pushed into its parent's opening by a third of the opening's depth, and its width is narrowed to the opening's by up to 15% (leg into foot, leg into hips). The upper arm is never pushed in or narrowed to an opening: it hangs from the master's shoulder (it is only narrowed to its forearm, above). The hand is pushed into the forearm's wrist the same way, without narrowing.
     - Draw order: `master.layers` overrides the default. `"upperarm": "under_torso"` draws the upper arm (only) under the torso, so a vest or strap covers the sleeve top; `"foot": "over_hips"` draws the feet of a character without leg pieces in front of the hips; `"hand": "over_forearm"` draws the hand over its forearm. A character with neckwear has its forearm and hand drawn just above the neckwear (in their order so far, still under the head), and what hangs on the neckwear (a bell) is drawn with it, so an arm crossing the chest (point or thumbs-up across, hold_card) passes in front of a hanging scarf and its bell; the upper arm stays under the neckwear, which wraps over the shoulders.
     - **Worn items.** A foot drawn over the leg (or over the hips with `foot: over_hips`) is cut at its ankle opening into two attachments on the foot's bone: `<foot>_back` (the inside of the opening plus the back half of its rim, in its own slot just below the legs, or below the hips without legs) and the shell (everything else, in front). Drawn as one layer, the boot's dark inside covered the trouser leg and the boot read as an object stuck in front of the leg; now the leg goes into the boot behind its front lip. Spine's asset guide: avoid drawing elements that appear in front of and behind an object on the same layer. Toon Boom (cutters) and Spine (clipping attachments) can mask at runtime, but clipping is CPU-expensive, so the split is static (`scripts/rig_worn.py`). The opening is the painted inside (the dark region the rim encloses near the annotated ankle); with no painted inside (a tiptoe boot seen tilted) the cut follows the piece's own top silhouette: across the opening (its annotated width, up to 15% wider where the painted top runs on) each column's topmost opaque pixel is fitted with the upper half of a sheared ellipse through the opening's two ends (the shaft's side walls, where the top drops away, are left out; a fit spanning under 0.6 times the width, or whose chord at the ankle point's x is more than the depth from its height - a pull-on loop, a notch or a buckle captured it - is refused and the cut falls back to the snapped opening's ellipse: ankle point, width/2 x depth/2), and the back part is the band between that top and the lower half of the same ellipse, depth/2 below the chord, so both lips are smooth arcs (an ellipse centred on the ankle point left an L-shaped corner on the fox's tiptoe). Where the front lip meets the outline at the two ends the shell thins to a wedge; those wedges go behind whole (`lip_ends_px`). Still a `worn_opening_guessed` doubt; `worn` records the `ellipse` (centre on the chord, half-width, depth/2), `band` (the top's height) and `tilt`. A variant with an opening (tiptoe) is cut too and its back swaps with it. A foot under the hips (the moose) is not cut; a foot without an ankle width is drawn whole and becomes a `worn_no_width` doubt. The back's crescent band thins to a few pixels at the rim's two ends; those thin tips go to the shell whole (`tips_px`), since the leg never reaches them and they would be slivers. `report.json` `worn` records each cut.
     - If the matcher's placement differs from the annotation's by more than 4% of body height, `report.json` records both (`matcher_disagreement`) and the part becomes a doubt at checkpoint 6.
     - `rig/annotations.resolved.json` holds every annotated point in attachment-local coordinates, for QA.
   - **Placement by colour (without `--annotations`).** Torso, hips, head and head items are matched onto the master (masked colour matching inside body-layout bands), and left/right is fixed on pairs. Limbs are then **assembled like a pinned cut-out**:
     - each arm piece's round end is made concentric with its parent's (shoulder inside the torso; elbow; wrist a quarter cuff-width under the cuff);
     - feet stand where the master's feet touch the ground, so a same-coloured tail can't lure them;
     - each leg runs from its boot rim to its leg opening in the hips, slanting at most 8°, with its top tucked under the hips;
     - hands are scaled up to the master's hand area when the sheet painted them small;
     - a small item not touching its parent (a bell beside a regenerated scarf) is pinned onto it.
   - **Ends are told apart by how a piece was painted** (joint end up), never by which end is nearer: a forearm matched too high was attached backwards that way.
   - **Draw order, back to front:**
     1. tail and ears
     2. legs
     3. feet
     4. hips
     5. torso
     6. hand
     7. forearm
     8. upper arm (round sleeve top over the rounded shoulder)
     9. neckwear
     10. head
     11. hat
     12. front (props; with annotations a bell hung on the neckwear is drawn with the neckwear instead)

     With annotations, `master.layers` and neckwear change this order (see Draw order under placement from annotations).
   - **Variants** become extra attachments in their part's slot.
     - Each is scaled to its rest part: tubes by width and by length separately (`scaleX`/`scaleY`); hands by wrist width; feet and tails by area.
     - Tubes are turned to the rest part's axis, and each variant is placed so its joint lands on the rest part's joint. With annotations a hand variant's image-down runs along the hand bone (so at a hold it continues the forearm), and a rest part narrowed to fit narrows its variants by the same factor.
   - **Cleaning.** Semi-transparent pixels enclosed by a part are made opaque: background removal had thinned the fox's eye whites. Soft edge pixels take the colour of the nearest solid pixel, which removes pale hairline seams. With annotations only the opaque body (alpha 250 or more) is trusted: the fox's laugh head ended in a 1-2 px ring at alpha 238-249 still holding ~10% of the sheet, a pale hairline where the head lies over the raised sleeve in cheer_jump.
   - `--cut-from-master` restores the old behaviour (limbs cut from the master, orphan patches). Use it only to compare.
   - **Thumbs.** The hand variants are mirrored by anatomy (see stage 6), and `point` and `thumbs_up` hold whichever pose (outward or across) shows the thumb up. `report.json` → `gestures` records, per animation and side, the hand's `facing`, the `pose`, the arm angles, the thumb's world angle, its target and the error. `annotations.resolved.json` → `holds` carries each hold's `pose` and `thumb_target`.
   - Animations are defined as target angles, keyed every frame with eased transitions:
     - `idle`, `blink`, `emotions`.
     - `wave`: open hand swapped in mid-raise.
     - `cheer_jump`: squash, jump, raised sleeves, fists, tail up and tiptoe in flight, fist pumps, soft landing.
     - `thumbs_up`, `point` (with annotations: outward, or across the chest when only that shows the painted hand's thumb up), `hold_card` (forearm across the belly, below any scarf, paw in the grip pose).
     - Body moves, front view, in place (`rig_anim.locomotion`, `squat`, `jump_hurdle`, `wave_flag`):
       - `walk` (1 s loop) and `run` (0.64 s loop): the hips bob (lowest at each contact) and sway, the torso and head counter-tilt, and the arms swing. In `run` the arms bend with fists at the waist, pumping, and the face is happy. A foot under the trousers stays planted and lifts a little as it steps, growing slightly as it comes toward the viewer. A boot worn over the trouser leg (the fox) or hung on a leg piece rides with the hips instead and only grows, or the leg would leave the boot.
       - `squat` (2 s): there are no knees to bend, so the hips squash along their axis (the trousers shorten to 0.7) and drop by the same amount, keeping the feet on the ground. The bones lying along the hips' axis (torso, feet, legs) get the inverse squash. Arms out for balance.
       - `jump_hurdle` (one-shot, 2.2 s; needs a ground prop): crouch behind the hurdle (drawn in front of the legs), jump toward the viewer over it (18% of body height; a drawOrder key moves it behind at the apex), land a little nearer (lower and 8% bigger), absorb, recover. Arms out to the sides for balance, feet tucked and on tiptoe, surprised at take-off, laughing on landing.
       - `wave_flag` (3.2 s; needs a held prop): the fist (palm fist) closes on the stick, held upright at rest. The arm rises like the wave (0.9 s: the fist lies beyond the hand, so a 0.7 s raise jerked it), swings the flag ±18° while the cloth flutters (the prop bone's scale), and comes down.
       - Garden moves (props with `use`; the garden experiment, 2026-10-16):
         - `plant_seed` (2.6 s; needs a `grow` ground prop): squat (hips 0.68) and lean 4° toward the plant, the arm on its side reaching down and out with a grip paw, the other arm out as in `squat` (left at rest, the squash pushed the idle paw 6% past its cuff), head tilted to the plant with the `look` heads; event `seed` at 1.2 s.
         - `water` (3.8 s; needs a `water` held prop, optionally its `attached` stream): the arm out to the side with the forearm angled down and the paw *straight* on it (a wrist bent 60-70° off the forearm spilled 20-33% of the paw past the cuff), so the can's handle crosses the closed fingers. The can tips 72°, the forearm rolling 55% of it (a fist that doesn't turn ends with the handle running along the fingers). Arm, can and stream move in front of the torso for the whole move (`front_of_body`, a drawOrder key): a tipping can swings its body toward the character and otherwise vanishes behind the sweater. Head 9° toward the plant, eyes on it (`look` / `look_happy`), event `pour` as the stream appears.
         - `grow_0..N` (0.9 s, for track 1): show stage n with a squash-and-stretch pop and hold it; a game sets track 1 on the events and leaves track 0 to the character.
         - Place the plant from the pose, not by eye: `experiments/2026-10-16-garden-grow/scripts/fit_garden.py` reads where the stream starts mid-pour, puts the stem 7.5% of body height right of the landing point and sets the stream's `fall` to end on the mound's shoulder. Then rebuild.
     - **Props** (`spine_rig.py --props props.json`, `scripts/rig_props.py`): a prop that isn't in the master can't be matched onto it, so its points are given instead. A held prop (`kind: held`, `grip`, `tip`, `length` as a share of body height) hangs from bone `prop_<name>` at the middle of the left fist, drawn just behind the hand so the fist closes over the stick. A ground prop (`kind: ground`, `base`, `height`, `front`) hangs from the root, drawn in front. Both are hidden at rest and shown only by the animation that uses them. `props-pair.txt` paints two props in one call (`--var PROPS="Left: … Right: …"`). A ground prop may also take `x` (to the viewer's right), `behind` (slot first) and `stages` (images that replace each other on one slot, each scaled so its base is `width` wide: a plant growing on one mound). An `attached` prop hangs at the image point `at` of the prop named by `on`, with its own point `top` there, at that prop's scale, and keeps upright (`inherit: noRotationOrReflection`): a water stream on a can's spout. `use` (`water`, `grow`) assigns a prop to the garden moves; `jump_hurdle` and `wave_flag` take only props without it. Without `--props`, `jump_hurdle` and `wave_flag` are skipped. `spine_qa` doesn't judge props' occlusion (going behind the jumper is the point), judges a bone's jerks only over the frames it draws in (a stream that appears mid-move), and doesn't stitch an upright hanging bone to its parent (a stream touches its spout but is no joint).
     - Every swap is keyed mid-motion, and a swap is skipped when the character lacks that variant.
     - Raised-arm poses are **computed per character**: the highest shoulder and forearm angles that keep elbow and paw clear of the whole head assembly (head, ears, antlers, hat). For the fox's wide cheeks that was 15°/65°; for the moose, 55°/65°.
     - Limits learned from the frame-to-frame check: about 180° of arm swing needs ≥ 0.65 s (gestures raise and lower over 0.7 s each, `rig_anim.GESTURE_RAISE`/`GESTURE_LOWER`: a 0.55 s lower jerked the beaver's long arm back from across the chest); fist pumps at most 2 per second at 5°; a jump of about 12% of body height with a flight of about 0.85 s; at most 18% with a 0.94 s flight and a 0.28 s push-off when the body also scales (jump_hurdle), and arms still at the apex (spine_qa's canvas has 25% headroom, so a higher jump cuts off the fox's ears). Cubic (hermite) easing starts with a sudden acceleration that adds to the body's motion; ease arm raises with `smooth` (smootherstep), which starts and stops with zero acceleration.
8b. **QA, required:** `uv run scripts/spine_qa.py <char>/rig/<char>.json --master <char>_master.png`. It renders every frame of every animation without Spine and must print PASS for all of these:
   - `structure`: pivots inside both parts, enough joint overlap, no reversed bones, no stray pixels;
   - `setup`: silhouette IoU against the master ≥ 0.85;
   - each animation:
     - every part attached and stitched (overlap never below 0.5× its rest size, never growing by more than 8% of the part);
     - no holes at joints;
     - no velocity jumps (angle under 4°/frame, position under 1.2% of body height per frame);
     - nothing clearly visible at rest becoming mostly hidden, and nothing tucked at rest (a hand under its cuff) losing more than 65% of what showed (`occluded`);
     - `seams`: no pale hairlines where one piece lies over another (setup pose and mid-animation; at most 10% of a pair's shared edge);
     - `thumbs`: at each hold frame the thumb (its sideways offset across the hand's axis, carried through the bones) is within 45° of the hold's target: up for point, thumbs_up and hold_card at the pose they chose, and for wave and cheer_jump where anatomy puts the painted side's thumb (they have no pose to choose, so a fixed target would fail by design);
     - `sockets`: a child's end stays inside its parent's opening, with under 3% of its width showing beside or below the parent near the joint;
     - `landmarks`: in the setup pose each joint is within 1% of body height of its master point, plus the push-in recorded in `annotations.resolved.json`;
     - `layer_order`: in the setup pose and every frame (drawOrder keys included) each hand is drawn on the side of its forearm's or sleeve mesh's slot that `master.layers.hand` says (below by default: tucked under the cuff; above with `over_forearm`);
     - `mesh_fold` (inside `structure` for the setup pose and inside each animation's check for its frames): no triangle of a sleeve mesh flips (the elbow bent further than the mesh can follow).
   - `thumbs`, `sockets`, `landmarks` and `layer_order` depend on `rig/annotations.resolved.json` and run only when it exists, so rigs built without annotations are checked as before. `seams`, `mesh_fold` and the rest always run.
   - `stitched` is measured in a disk about one limb-width across around the joint, against the setup pose with the same attachments, so arms crossing in front of the torso and swaps don't false-alarm.
   - `setup` IoU is computed in the master's own frame, read from `rig/report.json`.
   - `structure` also fails on:
     - detached islands or stray pixels in **any** attachment, including every variant and expression head (`fragments`, `slivers`);
     - a tail drawn after the legs or hips (`draw_order`);
     - a variant that, swapped into the setup pose, no longer covers its joint or overlaps its parent less than 0.4× or more than 2.5× as much as the rest part (`variant_misfit`);
     - a variant drawn more than 1.6× bigger or smaller than its rest attachment in the setup pose (square root of the drawn area), expression heads included (`variant_size`). It still fails when the variant closes its joint, as the bear's 3.2× tiptoe clog did.

   Then **look at the frames yourself**: `uv run tools/render_frames.py out.png 700 rig/<char>.json:cheer_jump:0.83 rig/<char>.json:thumbs_up:1.2 …` (repo tool), or open `qa/<anim>.gif`. The metrics have missed defects before:
   - a vest sliver riding on an arm;
   - faint fringe lines;
   - with generated limbs, a boot matched onto the tail, a backwards forearm and a thumbs-up pointing down, each of which passed every check at first.

   Never call an animation working from a single still frame.

8c. **Jev review, optional** (needs `TYPESAFE_API_KEY`; skips without it): `uv run scripts/jev_qa.py <char>/rig/<char>.json --ref experiments/2026-10-11-rig-annotations/fox/rig/fox.json --ref experiments/2026-10-11-rig-annotations/moose/rig/moose.json [--prev <previous build>/<char>.json]` (outside the repo: any approved rigs, at least two). It writes `rig/qa/joints.png` first, with no key needed (`scripts/joint_crops.py` alone does the same): the setup pose rendered into the master's pixel frame and both cut at the same box around every joint, master | rig. That sheet found every defect of the beaver's first review (sleeves stuck on, a neck gap, no trouser cuffs, boots off centre). Then Jev, about 200 calls (~$0.02, cached in `rig/qa/jev/`):
   - `joints`: Jev's 0-3 "how broken" per joint; WARN when above the worst score of that joint type on the approved rigs. Never a fixed threshold: every approved joint scores P(matches master) < 0.5.
   - `pairs` (with `--prev`): "which build matches the master better", both orders averaged; above 0.6 better, below 0.4 WARN worse. One pair is noise (an unchanged joint reads about 0.5), a pattern is signal.
   - `frames`: P(rigging defect) for 6 frames per animation, ranked; the ones above the approved rigs' 90th percentile go in `rig/qa/jev/frames_to_review.png`. A reading list, not a verdict (on the beaver: hold_card's half-hidden grip and the big pointing hand).
   - `holds`: the hand at each gesture hold. **FAIL** only when a point or thumbs_up hold doesn't show the thumb up (AUROC 0.99: the "thumbs-up pointing down" defect). WARN when a hold doesn't read as its pose, a point aims across the body, or anatomy (Jev's finger and thumb directions plus the annotated facing) says it is the other hand; that last one false-alarms on the approved moose wave.
   Exit code 1 only on a hold FAIL. `rig/qa/jev/jev_qa.json` has everything.

   **Checkpoint 6: rig review.** Once `spine_qa` passes, render the frame grid: setup, wave peak, point hold, thumbs-up hold, cheer apex and hold-card, with `tools/render_frames.py` (one `rig/<char>.json:<anim>:<seconds>` per frame). Where that repo tool isn't available (the skill installed on its own), show what `spine_qa` already wrote instead: `rig/qa/setup_vs_master.png`, the strips `rig/qa/<anim>_strip.png` (wave, point, thumbs_up, cheer_jump, hold_card) and the GIFs `rig/qa/<anim>.gif`. Also show the three sheets `uv run scripts/joint_crops.py rig/<char>.json` writes (8c writes the first): `rig/qa/joints.png`; `rig/qa/onion.png`, arms, waist and legs with the master in red and the rig in cyan, so a part too wide, too thin or a few px off shows as a coloured fringe (the beaver's wide trousers, thin sleeves and outward boots, invisible in the 0.92 silhouette IoU); and `rig/qa/motion.png`, wrists, waist and ankles followed through the animations (a hand bigger than its cuff, a belt gap, a boot peeking beside a cuff). No check measures those three yet, so look, and when 8c ran, its summary: the joints WARNs, worse pairs, `frames_to_review.png` and hold issues, in a few lines. Open it, print the path and ask in one AskUserQuestion call: question 1 "Approve / Fix", then up to 3 doubts (matcher disagreements from `report.json`, QA warnings, Jev WARNs that you can also see on the crops). Route a Fix answer by its cause:
   - a wrong point, side or layer: edit the annotation (status `fixed`), re-run `check` and the rig build, and show the grid again;
   - bad art: regenerate that sheet with changed words (one Nano Banana Pro call), split it, and go back through its checkpoint.
9. Hand over the `rig/` folder. In the Spine editor use **Import Data → `<char>.json`**; images resolve from `./images/`.

The `spine-parts` template (and the server workflow **SKIPBO - Character to Spine parts (Nano Banana Pro)**) runs the whole chain in one go: master, body, face, hands and poses sheets, each split into transparent pieces. That's 5 Nano Banana Pro calls with `--var CHARACTER= PIECES= HANDS= POSES=`, and no pause to approve the master. Use it when the master is very likely to be right; otherwise run the stages separately. Annotating and confirming (stage 6) and the rig build stay manual: run checkpoints 1–5 back to back on its output.

## Part list (front-view rig)

**Body:** head base (fixed features only), hat, horns/antlers ×2, ears ×2, neck items (scarf, bell…), torso with neck stub, upper arm ×2, forearm ×2, hand ×2, hips, leg ×2, foot ×2, tail, props.

**Face:** 9 whole-face expression heads, swapped in the head slot.

**Minimum variant set:**

| Part | Variants | Used by |
|---|---|---|
| Hand (per side) | open, fist, point, thumbsup, grip | wave, cheer_jump, point, thumbs_up, hold_card |
| Upper arm (per side) | raised | cheer_jump |
| Foot (per side) | tiptoe | cheer_jump (in flight) |
| Tail | up | cheer_jump (in flight) |

This follows the hand libraries in Cartoon Animator, Toon Boom and the reference rig pack, cut down to what the animations use. Add a variant only together with an animation that keys it.

## Checks before handing over
- Count matches the PIECES list, plus 9 heads. Extra pieces usually mean faint ghosts or a piece split in two.
- Joint ends are rounded; the torso is complete under the scarf and head.
- No eyes, brows or mouth on the body sheet; all 9 heads within a few pixels of the same width.
- In the rig: `spine_qa.py` passes (step 8b), and you've looked at the frames. The layout bands in `spine_rig.py` (`BANDS`) assume a front-view, two-legged rest pose; adjust them for unusual body plans (very long necks, four legs).

## When spine_qa fails

Causes seen on the Moose:

| QA failure | Usual cause | Fix |
|---|---|---|
| `pivot_off_joint` on a shoulder | Pivot landed in the scarf or on the vest edge | Check the contract (arms clear of the body); the shoulder pivot must step into the torso, not the neckwear |
| `pivot_off_joint` / `weak_joints` on a hand or foot | Wrist or ankle centred across the wrong direction, or the cuff assigned to the hand | Recentre across the forearm's own axis; the forearm's wrist cap takes the cuff too |
| `weak_joints` on antlers / ears | Only a thin base shows above the parent | Hidden root under the parent (automatic for behind-the-head parts) |
| `unstitched` (overlap ratio far from 1) | Pivot not at the overlap, or a reversed bone | Joints come from the overlap between part and parent; bones point into their own part |
| `slivers` (stray pixels) on a limb | Neighbour pixels (vest edge) or anti-alias fringe inside a master-cut piece | Colour-classify limb pixels against the torso and neckwear only (never the head: hands share its browns); open the mask |
| `joint_holes` in the rest pose | Hairline of master pixels that no piece covers | Orphan pixels become static torso/hips patches |
| `jerky_bones` | Sparse or linear keys, reversals with no easing | Key every frame; ease in and out of every hold |
| `setup` IoU < 0.85 | Parts matched into the wrong place | Check `placement.png`; part types misnamed, or the master breaks the contract |
| `fragments` | A detached blob inside a part (tail bits in a paw cap) | Master cuts keep only their largest connected body |
| `occluded` (hand/forearm) | A raised arm passes behind the head | Arm poses are searched for head clearance; widen the head zone if a new head item appears |
| `occluded` (ears/antlers) | Raised paws cover separate ear or antler pieces | The head zone includes every head item, not just the face |
| Placement: tail on the face, paw on the tail | Same-colour parts with no layout constraint | Tails have a lower-body band; hands are searched near the end of their own sleeve |
| Holes punched in boots | Tail colour exclusion applied everywhere | Colour-test against the tail only near the tail |
| `GPU out of memory` from the server | Someone else's models fill the shared T4 | `comfy.py` waits and resubmits up to 3 times |
| `occluded` on forearms with a raised sleeve | The raised-sleeve variant was painted longer than the rest sleeve | Tube variants are scaled in length too (scaleX/scaleY) |
| `occluded` hand in `hold_card` | The paw passes under the scarf | The pose holds the card across the belly |
| `variant_misfit` | Variant not painted joint end up, or a wide pose (thumbs-up) | Turn it joint end up; hands find the wrist from the top edge |
| `variant_size` | A variant scaled against a width measured unlike its rest's (one snapped, one not), or a mis-annotated joint width | Look for a `variant_scale_disagree` doubt in `report.json` (feet are cross-checked by area). Fix the joint point so both snap, or re-measure the width |
| `thumbs` | Thumb more than 45° from the gesture's target at its hold frame | Wrong side, mirror or `thumb_tip`: fix the point or the hand's `facing`, re-run `check`, rebuild. Look at `<sheet>_worn.png` |
| `sockets` | A child's end leaves its parent's opening, or leg or sleeve shows beside the boot or hips | Check the parent's opening point (`ankle`, `hip_*`) and its snapped width; a leg wider than the opening by over 15% is a doubt; ignore a generated leg the hips already cover |
| `layer_order` | A hand drawn on the wrong side of its forearm or sleeve slot (a glove over the cuff against `hand: under_forearm`, or the reverse) at rest or after a drawOrder key | A draw-order bug in rig_slots (`layer_key`) or rig_anim (`crossing_offsets`); `master.layers.hand` is what the check holds the rig to |
| `mesh_fold` | A sleeve mesh's triangle flips at rest or in some frame: the elbow bends further than the mesh's weights can follow | Usually a `mesh_fold_range` doubt in `report.json` came first. A sleeve too short or fat for the bend: regenerate it slimmer or longer, ease the pose (check the hold in the frames), or use the two-piece arm |
| `landmarks` | A setup joint is over 1% of body height from its master point | Fix whichever point is off (master or piece); a snap that failed shows as a red label in the overlay |
| `seams` | Pale hairline along a piece edge lying over another piece | A grey anti-aliased band left on a piece's edge, or a wrong draw order; look at the piece's edge, then `master.layers` (`upperarm: under_torso`) |
| Setup IoU low with generated parts | Legs matched up into the torso; a boot on the tail | Feet are ground-anchored and legs assembled from the boot up; check `placement.png` |

**Still not caught automatically:**
- the texture inside a round joint cap rotates with the limb (invisible on plain sleeves, but can show on patterns at big bends);
- whether a pose *reads* (the first cheer passed every metric but looked like a stiff T);
- head direction in the master;
- the assembled body drifting from the master's proportions (the fox's generated torso is wider than the master's). The setup IoU only catches large drift.

A "straight cut edge" metric was tried and dropped: painted boot rims and cuffs scored higher than real cut seams.

Each new check here (stray pixels, fragments, occlusion) was added after a defect passed the metrics and was then caught by looking at frames. Keep looking.
