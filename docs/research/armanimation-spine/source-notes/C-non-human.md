# Armanimation - Non-human characters (rabbit, cow, quadruped review, sheep, wing, spider leg)

Caveat: auto-captions are thin. The cow stream is mostly silent working (long gaps), and the rabbit video skips 6:40-8:46 and 9:45-11:02 in the transcript. Items marked (inferred) are my reading, not stated by the author.

## 1. Per-video summary

**Rabbit - Rigging Rabbit in Spine 2D body head face** - https://youtu.be/ByNy6OI118k (23 min, a continuation: the video starts with IK already half-built)
- 0:00-3:07 Leg IK: two-bone IK, target is a child of the *last leg bone* (not a separate root-level target), so the paw is also a controller. Chest bone placed in the middle between the legs so both shoulders rotate evenly (1:09). Bone lengths in an IK pair should be similar; never leave an IK stretched in setup pose (2:40).
- 3:07-9:45 Face: no neck bone, "if I need that neck animation I move the head bone". Eye bones, eyebrow bone, upper and lower eyelid bones. Eyelid bones are NOT for blinking - they bend the lid into a happy or unhappy curve. Blink = swap between "closed" and "happy-closed" attachments, with the lid bones animated first so the swap is hidden (4:08, 8:46-9:17).
- 11:02-17:42 Rear leg re-cut from a PSD (re-import with Replace, delete the old mesh, rebuild mesh from scratch). Relaxed IK pose, extra tip-of-leg bone with rotation+scale inheritance off, IK set to Stretch (17:42).
- 17:42-23:32 Face rig: 2 controller bones + a red "reverse" helper bone (translate -100) for parallax; ear bones (3 per ear max) constrained to head movement; face painted on one bone with other bones locked. Ends on the unsolved "squeezed eye does not scale back in perspective" problem (23:02).

**Cow - Rigging a cow in Spine 2d quadruped** - https://youtu.be/A-2rGB-1rJY (~41 min live stream, head already rigged)
- 0:03-1:39 Container bone first, then body with two rotational branch bones (chest and hip) "so I can have this curvy movement"; a long body bone is kept anyway for extra hip motion.
- 1:39-10:14 Front foreground leg: more bones than anatomy needs ("why did you over complicate this portion") to get a bent/raised leg; meshing and reordering triangles to fix sharp edges; leg animated mostly by one bone (move, rotate, scale) plus the foot rotation at the end.
- 12:21-14:33 Tail: bone chain drawn with the Pose tool, tip isolated so it does not deform; bound after.
- 15:02-16:35 Rear leg IK: IK structure built from the ROOT (not from the hip), with reversed chain + longer bone; disabling rotation inheritance warns about flipping.
- 36:30-39:30 Binding: body bound to the *controller* bones not the IK children; discusses downside of the single-IK pattern (leg doesn't follow when airborne -> needs transform constraint) vs the example project's double IK; hide IK targets via bone selection groups; save "useless" bones into a selection and toggle visibility.
- 41:02 Last tip: keep images inside bones, not the root folder (cut off mid-sentence).

**Quadruped Rig Review** - https://youtu.be/T_jJ6LsZiWU (6 min; the best overview)
- Whole creature walk-through, bone-by-bone (see section 3).
- Key idea 0:00-1:26: "reversed bone" on the rear legs replaces double IK per leg.
- 1:26-2:22 Head, constrained ears, reverse bone behind head for hair/volume.
- 2:22-4:17 Snout, nostrils, pupils, eyelids, blink via states, mouth+chin.
- 4:17-4:50 Shadow = 2 bones, 1 mesh, scaled down on jumps.
- 4:50-6:15 Ad for a jump workshop (anticipation, exclamation pose, recovery).

**Sheep jump** - https://youtu.be/fsrP1TFH9N0 (~39 min, animation not rigging)
- 0:00-3:12 Start with the root/main bone Y-axis only, then curves; offset body bones 2 frames; extra drag frame.
- 3:12-9:29 Chest/hip "balls" (the two spine branch bones) exaggerate the main move; back legs push, front legs relaxed go up first so they land first, body rotates down to catch.
- 10:26-13:42 Face fixes the emotion (jumping looked like screaming): happy eyes, partly closed, mouth shape.
- 14:10-27:54 Legs last: shift weight (translate legs back), ghosting/onion skin on slots-inside-bones, offset legs by a frame, landing with different leg timing; Ctrl+Shift+J to copy setup pose back for idle.
- 29:56-38:44 Shadow fade/scale, tail drag, ears offset + scale for volume, two fur bones with rotation.

**Wing** - https://youtu.be/fuHw_Mys2tg (10 min, mechanical bird, Spine)
- Shoulder bone with elbow/wrist "joint" bones all as siblings (Shift-add) under the shoulder, red manual controller bones for each joint (2:06-3:13).
- Chain driven by a short IK (two-bone) with softness and stretch (4:24), target parented to a joint, plus transform constraints at 50% mix so intermediate bones follow the controller halfway (5:28), then a second transform constraint for the chain root (7:41).
- Ordering problems fixed with the constraint "Recalculate order" (6:02).
- Meshes bound last, weights adjusted by posing extremes (9:07-9:59).

**Spider leg (Spine 4.3 new Transform Constraint)** - https://youtu.be/DQwVU3nhT4Q (10 min)
- One IK + three transform constraints: moving the hip bone's X makes the leg target do a procedural step. Details in section 5.

## 2. How the author analyses the creature before rigging
- Start from the question "what motion do I need?" not anatomy: "I'm thinking of anatomy of the leg so I would like to see this portion to bend" (cow 1:39). If the art has no anatomy cues "you need to guess" (cow 2:07).
- Split along motion: body into hip + chest halves via bones (not separate images, he keeps the body as meshes bound across hip/chest bones); legs cut where they must fold. Rabbit rear leg was re-cut in Photoshop into pieces "otherwise I will have very little range of motion here" (11:02). A "relaxed" leg pose is redrawn rather than extreme poses.
- Near/far sides: foreground legs get the full rig (IK + extra bones); background legs are simplified: "I will at least need this portion... let's keep it simple", then copy the foreground set for consistency (cow 24:17-29:15). For the rabbit, one visible rear leg: duplicate IK for the far leg and place its target in the same spot as other targets (13:26). Slot order matters (sheep 19:49: far leg must go in front/behind correctly).
- Face is separated from head mesh: eyes, eyelids (lower+upper), eyelashes separate from lids, eyebrows merged in head but "separated with rings (edge loops)" so they do not stretch the face (review 4:17). Chin is part of mouth.
- Keep one mesh where deformation matters (body/face skin) and rely on bones + weights; separate images where parts need independent rotation or occlusion (eyelashes, white of the eye, ears, legs).
- Keep images inside bones (folder = bone) rather than at root so ghosting/onion skin shows the container (cow 41:02, sheep 18:52).
- Sheep: "I don't concentrate on feet at all" initially; body first, face/emotion, then legs, tail/ears/fur last. Order of work: main bone -> offset spine -> head -> face -> legs -> secondary.

## 3. Bone layout per creature

### Generic quadruped (review video, cow, sheep share this layout)
- `container/root` bone holds everything EXCEPT the shadow (review 0:00).
- `body` (main animated bone, also a long bone with arm in cow).
- Two branches off body: `hip` and `chest`, both rotation-only, "control the hip and chest separately... add layers of animation" (review 0:30; cow 0:39 "curvy movement"; sheep 3:12 "these two balls" used to exaggerate jumps).
- Tail: 2 bones in review; longer chain in cow drawn with Pose tool, tip isolated so it does not deform.
- Front legs: simple, upper/lower/foot with standard IK (review 0:30).
- Rear legs: IK chain with an extra "reversed bone" per leg, used instead of a double IK. "if character is going down this is not moving, I will be moving it manually each time" -> lets him keep the foot planted and add anticipation/leaning, and scale it for perspective rotation (review 1:00).
- Cow rear leg: IK structure built from the root outward ("note I'm not adding it from here... we need to go outside"), reverse-IK chain with longer bone for the part equal to the anatomical heel; the target sits outside the leg chain so it is a pure target; leg rotation lives on the controller bone, not on IK children (cow 15:02, 39:30).
- Cow front leg: extra short bone in the middle (shoulder/forearm area) to get a bendy joint and a raised-leg shape; controller bone with move, rotate and scale; foot rotation last (cow 3:49, 9:14).
- Binding rule: body mesh is bound to the red CONTROLLER bones, not the IK children, so he can still add manual motion on top (cow 36:30-37:02).
- Head: head bone sits on the front part of the spine (review 1:26 "connected to the neck and back portion of the spine"); rabbit has no neck bone at all (3:07).
- Reverse bone at the back of the head for volume behind it (hair, puff): "it will really worth the value to read with that one", one bone plus a negative-translate constraint (review 1:54; rabbit 18:13-18:47 "translate to minus hundred").
- Ears (rabbit): max 3 bones per ear, "volume with these three bones you can achieve so much better effect by scaling, skewing"; a 2-bone version for floppy top; constrained to head move/rotate (translate constraint) so when head moves left the near ear goes back and the far ear forward (rabbit 18:47-21:52). Sheep: ear scale + offset used for volume (sheep 36:45).
- Face bones: eye, pupil (small, limited or placed manually; eye lines need manual tiny offsets), upper and lower eyelid bones (curve only, no blink), eyebrow, nostrils (1 bone each, moved/scaled for sniff), snout, mouth + chin (chin must follow the mouth), 2 fur bones on sheep.
- Shadow: 2 bones + 1 simple mesh, outside the container (review 4:17).
- Cow organization: controllers are coloured red; IK targets and other rarely-used bones are saved under one named bone selection and hidden via its dots (or made transparent, which he calls risky because later animators cannot find them) (cow 34:27-35:59).
- No explicit bone count given anywhere. Rabbit: ears 3 bones per ear, 2 face controllers. Review rig: "two bones" tail, shadow 2 bones.

### Rabbit (upright-ish)
- Chest bone placed BETWEEN the two IK leg chains (not too far to one side), so one leg does not move much while the other moves too much; it mimics shoulder-joint movement (rabbit 1:09). Both legs use 2-bone IK with the target as a child of the end bone (paw doubles as controller). IK mix off = target stays on the ground, so add a transform constraint to follow when airborne.
- Rear leg: 3 chain bones, a separate tip-of-leg bone (rotation and scale inheritance OFF to prevent distortion, can shrink to avoid snapping/perspective), IK stretch on.
- Face: eye bone x2 + eyelids lower/upper (2 each) + eyebrow; face controllers x2 and one red reverse (helper) bone (icon changed so it is not grabbed).

### Wing (mechanical bird)
- Shoulder bone -> elbow joint -> wrist joint all direct children of the shoulder (Shift-add siblings), so control bones are not a chain.
- Red manual control bones per joint, coloured so they are distinguishable and nested in the last joint.
- One single stretch/compress bone running through the chain and parented to the joint so it moves like a chain.
- 2-bone IK with softness at the tip; target parented to the elbow control; 2 transform constraints at 50% make middle bones follow half of the parent's motion.
- Gives: top and bottom positions controlled by one bone, wing tip separately movable without moving elbow.

### Spider leg (4.3)
- Hip bone (the driver), leg bone with the IK target as a child ("target inside this leg bone, that's why we have the ability to rotate it"), 2-bone IK. Everything else is constraints (see section 5).

## 4. Mesh and weight technique
- Weights are painted per mesh with a bone selected and other bones LOCKED so only the target bone is painted (rabbit 21:52). Unlock the reverse/helper bone before painting it.
- Selecting vertices by bone value: with "select all the points that have that value" -> add bone -> assign full weight, then reduce a little for feather/blend (rabbit 4:38-5:05).
- Vertex density: sparse in flat areas, a dense band where it bends (rabbit 13:55 "create a little bit dense vertices here"; cow 17:12 "this is going to be a bendy part more points here"). Add points to make "nice triangles opening up and down" in the joint.
- Avoid long thin triangles: they cause "bad deformation lines" on rotation; make shorter ones (cow 20:33-21:09). Reorder (triangle/edge flip) to avoid sharp elbow edges (cow 5:40).
- Test weights in animation mode with a bind pose: pose bones, move/rotate, tweak, "pass back so it jumps to original position" (setup <-> animation toggle). Author does this in animation mode for face (cow 19:08).
- Bind only the bones that actually influence; also bind far bones "just in case" - not affected if too far (cow 17:12).
- Eyelid trick: the lid bone has a weight region on the white-eye area OFF so the white does not move; lid mesh needs extra ring of vertices (rabbit 5:36-6:07). Eyelashes are separate and bound too.
- Face/head turns (2.5D): not a true head turn; uses reverse bones (negative translate constraints) for parallax, ear constraints, eye and pupil positions managed manually, state swaps. Squeezed eye "does not scale back in perspective" - would need an extra bone and a scale transfer; he gave up (rabbit 23:02).
- Body deform: pelvis/chest rotation bones with a shared body mesh gives spine curve; scaling the reverse bones gives perspective rotation of rear leg (review 1:00).
- Eyebrows merged with head and separated by edge rings so they do not stretch the face (review 4:17).
- Rear leg re-import: "replace" the attachment, delete old mesh and rebuild; do mesh from scratch since only 2 bones bound (rabbit 16:13-17:11).
- Tail tip is isolated (bound 100% to one bone) so it doesn't deform (cow 13:41).

## 5. Constraints used
- IK (2-bone): paw/foot target as child of the leg, Stretch enabled, bone lengths about equal, never stretched in setup pose (rabbit 2:40). "I always make the stretch for IK for the legs" (cow 21:43).
- Single-IK + manual-control pattern vs double IK: advantage - one timeline per leg for rotate/translate/scale; downside - disabling IK mix leaves target on the ground; remedy a transform constraint making the target follow the leg when airborne (rabbit 1:41-2:40; cow 37:34-39:03). Example-project double IK is "easier to use but harder to build"; he stays with his pattern.
- No IK per hind leg alone: review rig uses a "reversed bone" instead of a second IK (review 0:00-1:26).
- Transform constraints for ears: ear bones follow head translate/rotate with the sign flipped (reverse helper set to translate -100); values are animated, not set at rigging (rabbit 20:33 "I'm not giving value right now I will do it in animation").
- Transform constraints with mix 50% for chain followers (wing 5:28), Recalculate Order button to fix constraint ordering (wing 6:02).
- Spider leg 4.3 recipe (DQwVU3nhT4Q):
  - Constraint A (rotation): hip X -> leg rotation, ADDITIVE on (so the leg stays animatable), source range 0-100 px mapped to 0-10 deg, then flipped to 10 -> 0 because it rotated the wrong way.
  - Constraint B (translate X): additive + CLAMP so that nothing moves until hip X enters the window 80-100 px; maps a 20 px window to a 100 px step (later 100-200).
  - Constraint C (translate Y): second constraint with source window 100-120 px mapped to Y 50 -> 0 (reversed) so the foot comes down; B maps to Y 0 -> 50 (up). "The difference in these ranges is creating the speed variation. If you convert a small range to a big one you get much faster movement."
  - Rotation compensation with small ranges (15 then 5 deg).
  - Order of values: bone must be at 0 or the additive mixes; "6 px from zero = 6%" gotcha.
- Path constraints, physics constraints: not used in these six videos. Squash/stretch is done with scale on bones, not constraints.
- Reverse constraint on head: negative translate for hair/volume bone.

## 6. Animation notes
- Jump (sheep): start with only root Y, then add rotation for weight; offset body bones by 2 frames and add a drag frame; make the apex longer than physics permits "for time to say yay" (sheep 0:30-3:12).
- Push with back legs; the front legs relaxed go up first -> land first; body rotates down to "catch" (5:10).
- Compensation: when head/spine rises, the lower back goes down; neck quick bend then relax; don't bend the neck "artificially".
- Emotion before legs: face (happy eyes, partially closed) fixed "screaming like an animal" (10:26).
- Blink: ease the lids down slowly then snap the closed state, then ease out (rabbit 8:46-9:17: "start slow and then instantly snap... quick start then slowing down").
- Weight shift: translate legs backward when the body goes up so the body stays balanced (sheep 14:10-19:49); use ghosting (onion skin) on slots-inside-bones.
- Landing: front/back legs land with different timing (1 frame offset), small step back to idle; Ctrl+Shift+J copies the setup pose back for idle (27:54).
- Tail drag: lags behind with small bounce; ear wiggle offset; scale for volume; fur bones rotate; shadow fade and scale (29:56-37:45).
- "Pose keyframing is faster than finding curves in the graph editor" (20:51). Save energy: don't over-polish simple animations (32:46).
- Review: eye lines need tiny manual offsets; chin follows mouth; scale for perspective on rear-leg reverse bone.

## 7. Gotchas and review feedback
- (Review) Rear legs: reversed bone avoids double IK; it doesn't follow the body automatically - you move it by hand when the body goes down.
- Never leave an IK stretched in setup pose (snapping); equal bone lengths; make a relaxed bend, not an extreme pose (rabbit 12:27).
- Disabling rotation/scale inheritance breaks the character flip (cow 16:05) - only do it if you won't flip or know the workaround.
- IK targets that are not children stay on the ground when the mix is lowered; airborne characters need a transform constraint.
- Long thin triangles -> ugly deformation; add vertices on the bend.
- Replacing an attachment: use Replace on import; old mesh is kept and may crop the new image.
- Constraint order: if transform constraints fight, Recalculate Order.
- Sheep: eye rig transparent-fade tricks are "not obvious" to other animators; prefer separate closed / happy-closed states that don't need explanation (sheep 11:28-13:12). Don't hide behind fur: leg slot order.
- Transparent or hidden bones: risky for hand-off; use named selections to hide.
- Rabbit: perspective scale of squeezed eye not solved.

## 8. SCREENSHOT PICKS
| videoId | m:ss | What should be on screen | Why |
|---|---|---|---|
| T_jJ6LsZiWU | 0:15 | Full quadruped skeleton tree: container > body > hip/chest, tail, legs | Cleanest whole-rig layout with parent hierarchy |
| T_jJ6LsZiWU | 0:55 | Rear leg with the reversed bone highlighted | The no-double-IK trick |
| T_jJ6LsZiWU | 1:50 | Head with constrained ears + reverse bone at back of head | Ear/volume helpers |
| T_jJ6LsZiWU | 2:40 | Eyelid and eye bones | Face rig layout |
| T_jJ6LsZiWU | 4:30 | Shadow with two bones and mesh | Shadow setup |
| A-2rGB-1rJY | 1:39 | Body with hip and chest bones and the first leg bones | Hip/chest rotational branches |
| A-2rGB-1rJY | 15:30 | Rear leg reverse-IK structure built from root | IK target placement |
| A-2rGB-1rJY | 20:33 | Mesh in weights view with long triangles and the fix | Shows weight/triangle problems |
| A-2rGB-1rJY | 35:23 | Bone selection groups used to hide IK targets | Organization |
| ByNy6OI118k | 13:55 | Rear-leg mesh with dense vertices at the bend and IK | Mesh density near joint |
| ByNy6OI118k | 19:17 | Three-bone ears | Ear layout and rationale |
| fuHw_Mys2tg | 5:28 | Wing with transform constraint dialog at 50% | Transform-constraint follow chains |
| DQwVU3nhT4Q | 8:00 | Spider leg with constraint panel (A/B/C) and ranges | 4.3 transform constraint recipe |
| fsrP1TFH9N0 | 19:20 | Sheep with ghosting on, legs raised | Weight shift and onion skin |

## Take-aways for our generated animal characters (Python-written Spine JSON)
- Add hip + chest sibling bones under body, bind the body mesh to both; add a tail chain of 2-3, ears of up to 3 bones each, a reverse bone behind the head (translate -100%).
- Make the face and body skinned meshes with a denser ring around joints; keep legs as meshes bound to 2-3 bones.
- Use IK for legs with the target as a controller; add a tip bone with inheritance off; add transform constraints where limbs must follow when airborne.
- Eyes: closed + happy-closed attachments, with lid bones animated before the swap.
