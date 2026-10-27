# B - Full character rig setup and animation workflow (Armanimation / Arman)

Sources (auto-captions, interpreted): 9Zv-Mb7zi2U (Rigging Part 1), jKzIo566gnk (Idle Part 2), GujtDSo2pvM (Tracer #2 rig explained), 8bx_bFp1QD4 (Rigging course overview), wxC9yiYwg4c (Common mistakes and tips), H2LktmTdxGI (Optimize your project), zHvQ_GqJsQQ (Spine 4.3 beta, Mar 2026).
Caveat: the rig videos are voiced-over screen recordings with sparse narration. Node names/values are only stated when spoken. Items marked (inferred) are my reading, not quoted.

---

## 1. Per-video summary

### 9Zv-Mb7zi2U - Full Setup Part 1 (https://youtu.be/9Zv-Mb7zi2U)
Character: a heavy, angry fish-in-a-jar/mech-ish creature with beak, hair, bubbles (series goal: 2 attacks, 1 idle, 1 take-damage).
- 0:01-0:29 Bones are added early "so I can test the mesh right away". Create tool + hold Ctrl and click an image: the bone is made centered on that image. First bone: `pelvis`, enlarged, "in the middle" of the piece. Then `hip` below it.
- 1:27-2:21 Leg chain `hip -> leg -> foot`, each bone placed by looking at the middle of the circular joint piece (hip ball, knee piece). Bone placement trade-off stated: lower the pivot = better ground contact but weirder bending; "I like to place it somewhere in the middle".
- 2:21-5:50 Leg meshing/weighting: dense points at the knee (inner bend), few on the back where the surface collapses into itself; points far from the joint bind 100% to one bone, only a narrow band near the knee blends. Heel must be controlled by the foot bone ("it needs to control the heel... otherwise you won't have a bone to do that"). Weights fade "as it gets closer to this part"; use Overlay to view. Second leg: tried a simpler mesh dragged out from the bone origin; "maybe this was totally enough... why complicate things?" (6:18-7:45). Fixed a part cutting in by changing the draw order, not the mesh.
- 7:45-9:09 Torso upward from pelvis: `waist` -> `chest` -> `head` ("head bone will contain the beak, the hair, and everything else"). Many region slots moved into a bone: select them, click the slot icon, press P, click the bone (9:09-11:03). Select tips: Ctrl+box-select keeps selection to one type (bones only / regions only; meshes win priority otherwise).
- 11:03-14:33 Lower hip piece meshed and weighted to waist+pelvis+hip so the stretch is controllable. Extra bones: beak (to "bite"), hair, a bubbles bone off the chest, arm chain from chest; triangles must not cross the scar on the arm so the scar stays intact at 100% weight.
- 15:02-18:56 IK for legs: redraw the foot bone so it touches the end of the shin (else stretch makes it slide). Create IK constraint on the leg chain, tick Stretch. Then to get ONE bone that both moves and rotates the foot: add a transform constraint from the IK target to the foot (rotate + scale mixed in, "match" off after aligning with Alt-redraw). IK/constraints can be toggled off per-animation ("IK is not permanent") so the character can float with FK legs.

### jKzIo566gnk - Idle Part 2 (https://youtu.be/jKzIo566gnk)
- 0:01-5:00 Rig finish: foot meshed; "no need" for highlights, shoulders unrigged until needed. Adds a `face` bone child of head holding all face region attachments; face mesh bound to head+face; scaling `face` = fake 3D turn. "It took me 20 seconds to rig the 3D folder face." (1:55). Separate beak bone with weights swapped using "swap" in the weights list.
- 5:47-8:20 Shoulder bone, weld between meshes (so shared edge points stay in sync); optional slider constraint driven by a bone's rotation to fade a shadow mesh (a 5-frame animation, range 0..5 mapped to rotation 0..-100/-200).
- 8:57-17:38 Bubbles loop: bubbles under a container bone; each bubble translates diagonally; X and Y keys offset separately to get circles; timeline stretched to 320/600 frames with differing lengths so they never visibly repeat; nested motion (bone inside container with inherit scale/rotation off or compensation on) gives "extra layer"; motion-trail display used to check path. Delivered as a separate animation the client can play on another track.
- 17:38-21:08 Idle: "understand who your character is" (heavy angry character in chill pose). Breathing: 60 frames, key everything with Ctrl+Shift+L ("set to setup pose / key all"), chest-expansion bone moved up/down, optional pelvis motion; legs slightly bent before IK ("if they are not, right away you will see knees nothing"). Then separate rotation timelines on arms with offsets so nothing is static or in sync.
- 21:44-34:58 Idle variation: duplicate the idle, add a "reposition" shift (weight shift to a foot, head/face turn to camera, mouth swap), key everything at start and end ("Ctrl+Shift+L... I can do whatever I want here. Everything after and before will not be changed"), clear in-betweens, then fix curves in the graph, move the hip 8 frames before the foot, copy keys back to loop. Created a big yellow helper bone with custom icon to bend the body (31:05) weighted lightly to waist/chest.

### GujtDSo2pvM - Tracer #2 Rig Explained (https://youtu.be/GujtDSo2pvM)
- 0:56-2:22 Root structure: first creates "one bone that will replace the root bone" (character container) - used for moving/exaggerating jumps; everything character-related lives under it. Then `pelvis`, placed "a little bit behind" the body to allow the motion, "to apply main movement". Only after those does he animate/rig other parts.
- 1:54 IK targets for legs are the foot-ball bones moved to be children of the character container ("reduce bone count by two", easier to animate).
- 2:22-2:51 Uses inherit-rotation OFF on shoulders/head/straps so they don't rotate with the torso frame.
- 2:51-3:47 Face is "very simple bindings" with 2 face pieces + head, no constraints. Fingers: one finger bone chain with 3 bones, the others are fakes ("create illusion").
- 3:47-5:16 Finger mesh: 3 vertices on the outer edge where it bends, 2 on the inner -> "nice rigid phalanx". Fix self-overlap by reordering triangles. Don't cut limbs into pieces needlessly (cloth arm bends fine as one mesh); when you must cut, end pieces in a circular/round way.
- 5:16-6:12 Pivot-finding trick: pose an extreme + opposite extreme, loop, preview; with Create tool hold Alt and tap in the viewport to re-draw the bone from that exact point -> repositions the pivot visually.
- 6:12-7:07 Two leg attachments in one slot (standing-pose leg vs contact-correct leg) on the same bone, swapped by key.
- 7:07-8:06 Avoids neck bones: mesh with top bound to head, bottom to chest. Optional finger IK with softness, parented under the ball bone for grasping.

### 8bx_bFp1QD4 - Rigging course overview (https://youtu.be/8bx_bFp1QD4)
- Pipeline: Photoshop tags -> PSD importer -> fix draw order (PSD order is kept readable, not drawable) -> organise slots into folders -> mesh body and head -> place bones, bind -> other skins via linked meshes -> proportions skin layer (female narrower shoulders etc., same bones, played as additive animation over any other animation) -> weapon animations with extra hand poses.
- 4:16 "You build a rig, not finish, bring it to 80% and then jump into the animation... most of the times rig is still being adjusted even at the final stages."

### wxC9yiYwg4c - Common Mistakes and Tips (https://youtu.be/wxC9yiYwg4c)
- 1:05 Ask devs: Spine version, whether constraints/meshes are allowed. 1:35 straighten bent cloth/tails before rigging; extra leg/hand states duplicated.
- 3:36 "First thing create a container for the character. Which will serve as a root bone. Do not animate root bone if the character is made for a game."
- 3:36-5:12 Don't make arm IK unless needed; leg IK: reuse existing foot bones as targets, parented outside the leg. "Say no to foot anchors." Few bones as possible ("each bone takes time to animate"), one bone for hair, shearing+scale for 3D effect on flat props (shield).
- 5:12-7:02 Animation: idle is more than breathing - make base idle, duplicate several times, put interesting actions between; timing; poses; everything moves on curved paths; "separate its axis" on hip to get curves. Use posing and ghosting.
- 7:35-9:08 Mesh reset button does 3 things by mode; Alt+drag bone tip pushes children; Ctrl+Shift drag copies frames.

### H2LktmTdxGI - Optimize your project (https://youtu.be/H2LktmTdxGI)
- 1:09-2:53 Resize art before import; rotate/split for packing; [Scale] tag on blurry bits.
- 2:53-4:40 Mesh "should be functional and not looking nice"; more vertices where it bends; hard parts (metal gear on chest) get an extra ring bound with equal weights. Deform keys vs bone weights.
- 4:40-5:55 Demonstration: keying 5 deforms on all meshes of Raptor project in all animations more than doubled JSON size.
- 6:28-7:31 Bone at the cross-section of triangles; weight to minimum number of bones; smooth once or twice, on selected vertices; prune.
- 7:31-9:24 Clipping is expensive. Alternatives first.
- 10:01-10:34 Fewer bones = fewer timelines; constraints are fine ("no real reason to avoid using constraints") but don't build "monster rigs".

### zHvQ_GqJsQQ - Spine 4.3 beta (https://youtu.be/zHvQ_GqJsQQ)
Mostly editor UX: double-middle-click a bone selects descendants; drag multiple slots in the tree at once; folder colours; slot order resettable in animation; convert-to-mesh no longer re-activates inactive attachments; drag skin placeholders/skins onto other skins; "rotate degrees" PSD tag; atlas per skin. Little rigging theory; relevant mostly for tree organisation (folders, multi-drag).

---

## 2. Rigging order of operations (as Arman does it)

1. Before opening Spine: ask devs for Spine version and allowed features (constraints/meshes) (wxC9yiYwg4c 1:05). Check PSD for masks/blend modes. Straighten bent parts (tails, cloth); duplicate alt states (perspective leg, hand poses, face emotions) as separate layers; set root marker guide in Photoshop (8bx / wxC 3:04).
2. Resize art for the highest target device BEFORE import so bone scale is not cranked (H2L 1:09). Rotate/trim for packing.
3. Import PSD; with "ignore hidden layers" you can re-import only new/changed pieces; changed images show an override dialog and keep the attachment (9Zv 0:59, jKz 16:12).
4. Fix draw order (slots) and put slots into folders (8bx 0:57).
5. Create the character container/root-substitute bone first; never animate real `root` (wxC 3:36; GujtDSo2pvM 0:56).
6. Create `pelvis` as the first child at the centre of mass (Ctrl+click on the hip image), then `hip`, then legs (`leg`, `foot`), then spine upward `waist -> chest -> head` (9Zv 0:29-8:41). He builds the main driver chain (pelvis...) and only afterwards animates anything else (GujtDSo2pvM 1:25).
7. Move simple pieces into bones: select region slots -> P -> click bone. Do rigid props (highlights, palm, eyes) this way; no meshing.
8. Mesh only what must bend (legs, hip/trousers, arms, torso covers, shadow). Make the mesh as you place bones, so you can "test right away".
9. Bind and weight: 100% for rigid portions, narrow blend at joints. Check with Overlay and by rotating the bone.
10. Extra "detail" bones: beak, hair, face (3D fake), teeth, shoulders, bubbles container, secondary controls.
11. IK: redraw the foot touching the shin tip, add IK constraint (stretch on), add a transform constraint to merge IK target and foot for single-bone control. Pull targets out to the container bone.
12. Quick animation test (extreme poses/loops), adjust pivots with Alt-tap, fix weights. "Bring it to 80% and then jump into the animation" (8bx 4:16). Rig is adjusted during animation.
13. Skins (via linked meshes), proportion skin, weapon animations come after the main rig.

---

## 3. Bone placement

- Root: leave `root` untouched; first user bone is a "character"/container bone that gets animated for jumps/exaggerations (GujtDSo2pvM 1:25, wxC 3:36). Reason: devs move the character via root translation; animated root conflicts.
- Pelvis: the driver of the character. In 9Zv it is placed in the middle of the pelvis image and made bigger; in Tracer it is "a little bit behind" the body so rotation feels right. `hip` can be a child below it so leg root is distinct from pelvis (9Zv).
- Spine chain is short: `pelvis -> waist -> chest -> head`, optional neck skipped: "most of the time I avoid making neck bones. I just create a mesh bind the top section to the head bone and bottom to the chest" (GujtDSo2pvM 7:07). Only 3 spine bones for a cartoon: waist, chest, head.
- Pivots: put bones where the joint is in the artwork (middle of the circular knee / hip ball). Trade-off on legs: lower pivot = better foot contact but weirder bending; pick the middle (9Zv 2:00). For long meshes (rope, tail, hair), bones at the "cross section of the triangles" to improve bending (H2L 6:28).
- Finding the right pivot: pose extreme and opposite extreme, loop and preview; hold Alt with Create tool and tap anywhere to re-draw the bone with the pivot at that point; adjust until no artefacts (GujtDSo2pvM 5:16).
- Ends: a bone at the end of a segment must reach the next joint so IK and stretch do not slide (9Zv 15:02).
- Naming: he keeps default names mostly ("Let's not rename anything here" 0:29) but names key ones: pelvis, hip, leg/foot, waist, chest, head, face, beak, teeth, foot IK. Helper icon: "change its icon, make it super big, make it yellow" for the body-bend control (jKz 31:05). He gives bones custom colours/icons to find controls.
- Bone-count heuristic: "as less bones as possible since each bone takes time to animate" (wxC 4:38); one bone for a hair mass; no bones for each finger - one 3-bone finger and the rest faked; no neck; face as a single `face` bone + `head`. Typical rig from Part 1: ~ pelvis, hip, 2x(leg, foot), waist, chest, head, face, beak, hair, 2x(arm 3 bones), bubbles, 2 IK, shoulder, teeth, helper (about 25-30 bones for a cartoon brute). (my count, inferred)
- Helper / not tied to images:
  - Character container bone (replaces root).
  - Foot IK target bone that is also the foot controller; parented to container, not to the leg.
  - `face` bone (scales to fake a 3D turn, holds eyes/nose/mouth slots).
  - Shoulder bone (separate so shoulder can scale/expand).
  - Yellow helper bone with big icon that bends the torso via weights (jKz 31:05).
  - Bubbles container with nested child bones for "extra layer" circular motion (jKz 13:11).
  - Teeth bone for threatening shake.
  - Slider driver (a bone whose rotation drives an animation) for shadow fade.
- Inherit settings: Turn off Inherit Rotation on shoulders, head, straps so the torso does not carry their rotation (GujtDSo2pvM 2:22). Compensation / inherit-scale/rotation off for nested bubble bones (jKz 13:11).
- Slot grouping: put many region attachments into one bone via slot P-parenting, and use slot folders in the tree to organise draw order (8bx 0:57, zHv 3:20). 4.3 adds folder colours.
- Foot: two leg attachments in one slot on the same bone (standing vs ground-contact leg) (GujtDSo2pvM 6:12).

---

## 4. Meshes and weights

- When: only where something must bend or squash (legs/knees, hips, arms, torso, cloth, scarred arm, shadow). Rigid pieces (palm, highlights, eyes) stay region attachments in a bone. "I don't care about the rest really... it's not going to be bent" (9Zv 2:50). Don't over-slice limbs: "think twice why you need to cut this"; cloth arm as one mesh bends nicely (GujtDSo2pvM 4:16). Cut pieces should end in round shapes so they overlap cleanly when rotated.
- Vertex placement:
  - Create points at the origin of the joint bone; more detail at the inside of the bend (knee), fewer at the collapsing outside/back.
  - Fingers: 3 vertices on the outer edge where bending happens, 2 on the inner; produces rigid phalanges (GujtDSo2pvM 3:47).
  - Triangles must not cross details you want intact (scar), then bind that region 100% to one bone (9Zv 14:33).
  - Keep mesh functional, not pretty (H2L 2:53); plan ahead whether it bends uniformly or turns in 3D.
  - Hard parts (metal gear) get an extra ring and equal weights per vertex (H2L).
  - Dragging out the mesh from the bone origin may be "totally enough" (9Zv 6:18).
- Weights:
  - Parts away from joints = 100% to one bone ("exactly need to be 100% bound... otherwise it's going to stretch weirdly" 3:20).
  - Blend zone is narrow at the joint; "I take this value... and I reduce it as it gets closer to this part."
  - Use Overlay to see; test by rotating bones; the middle vertex at the pivot "doesn't matter" because it barely moves.
  - Foot bone must control the heel region.
  - Few bones per vertex: fewer transforms, easier edits. Smooth once or twice, on selected vertices; Prune; recalc per-bone (H2L 6:28-7:31).
  - Weight swap button to move weights from one bone to another (jKz 2:25).
  - Weld meshes together (shoulder/torso shared edge) so they deform together; then add the shoulder bone weights.
  - Draw order fix beats an extra vertex when a piece "cuts in" (9Zv 7:16).
- 3D-fake with weights: Head + `face` bone; face mesh weights head 100% to `face` portion so scaling `face` shortens it; add a bone for beak; shadow mesh weights partly to head so it slides (jKz 1:55-4:18). Chest widening/contracting by moving arms.
- Deform keys (direct vertex animation): flexible with soft select and custom pivot, but (1) only one timeline per mesh, (2) interpolates vertices in straight lines (rotation shrinks mid-way), (3) heavy memory and file size - keying 5 deforms on all meshes doubled the JSON. Use sparingly; never as patch-ups across every animation (H2L 3:59-5:55).
- Smoothness vs rigid swap: bones with a short blend band + a stretch IK + scale = squash-stretch from a single mesh instead of swapping sprites. Rigid swapping is only used for alternate attachments (leg pose, mouth).
- Linked meshes for skins: parts identical in shape but different texture reuse the same mesh; new shapes get new meshes and bindings (8bx 1:26).

---

## 5. Constraints

- IK (legs): 2-bone IK with Stretch on, target = the foot control bone. Foot bone redrawn to touch the shin end so scale does not slide. Legs slightly bent before IK to avoid knee flip. IK can be toggled off in an animation for FK/floating (9Zv 18:25; jKz 19:36).
- Transform constraint: used to make the IK target also rotate/scale the foot so there is "only one bone to move and rotate" (9Zv 16:00-18:25). Mixing rotate and scale in the constraint; "match" off if bones are aligned. Alternative: parent the foot controller outside the leg and use the same bone as IK target (wxC 4:08).
- Arm IK: avoid unless needed, it limits rotation (wxC 3:36). Finger IK optional with softness for grasp (GujtDSo2pvM 7:36).
- Slider constraint: bone rotation drives a short "shadow" animation (alpha fade on a mesh, 5 frames, 0..5 mapped to 0..-200 rotation) (jKz 6:45-8:20). He treats it as optional.
- Path / physics: not used in these videos.
- Stance: constraints are fine ("no real reason to avoid using constraints"), but no "monster rigs" (H2L 10:34). Face needs no constraints (GujtDSo2pvM 2:51).

---

## 6. Animation process

- Treat the rig as 80% done; refine while animating (8bx 4:16).
- Idle = who is the character first. Heavy angry brute in a chill pose -> calm breathing but with menace (teeth shake, tiny face 3D).
- Breathing: 60-frame loop, whole body up/down, then a chest-expansion bone, optional pelvis motion; then add offsets on arms by separating rotation timelines and shifting keys (Alt+Ctrl offset); soften with graph; "I don't want them to make [it] noticeable, but I also don't want to make them static" (jKz 21:08).
- Idle variants (wxC 5:12): duplicate the base idle several times and add an interesting move in between so it doesn't repeat: weight shift to one foot, step, face turn to camera, mouth swap, squash, blink (jKz 21:44-34:58).
- Technique for the variant: key everything with Ctrl+Shift+L (key all to setup/current) at transition boundaries so before/after segments stay unchanged; clear in-betweens; pose; faster transition with ease-out ("starts quickly then slows down"); move the hip earlier than the foot (8 frames) so weight leads; copy start keys to end to loop; remove face-3D when not needed.
- Loops of different lengths: bubble animation 320-600 frames matched to the idle length; each element on its own length so they never sync; X and Y timelines separated and offset to make circles; "put them in a container with another layer of motion" and the bone-trail display (keys -> motion -> bones) to check arcs (jKz 11:20-14:40).
- Curves: "everything moves in a curved path" - split the hip's X and Y timelines and offset them (wxC 6:27). Slow down only on strong poses, not on overlapping silhouettes. Use roller-coaster timing (slow-fast contrast). Graph editor for the scale/translate fixes (jKz 33:00).
- Offsets / follow-through: offset timelines of limbs, shoulders, hair, teeth; "move this left and right to avoid that synchro movement" (jKz 29:03).
- Dopesheet: Ctrl+Shift drag copies keys; Ctrl+Shift+L keys all; Alt+drag bone tip; Posing and Ghosting used "all the time" (wxC 7:02).
- Be patient: "some things might actually look broken, this knee snap... you need to be patient" (jKz 26:01).
- Deliver idle animation separately from VFX loops so client can play them on a different track.

---

## 7. Gotchas and rules

- Do not animate the real root bone; use a container (wxC 3:36).
- IK foot sliding when the foot bone does not touch the shin end (9Zv 15:02).
- Legs straight at IK creation: knees flip / no knee info. Keep a slight bend (jKz 19:36).
- Targets under the leg itself make the target move with the leg; parent targets outside (wxC 4:08).
- Heel region must be weighted to the foot bone (9Zv 4:48).
- Mesh with overlapping triangles: reorder triangles (GujtDSo2pvM 4:16).
- Selection priority: meshes beat regions; bones beat attachments; use Ctrl+box select to lock type (9Zv 9:09-10:34).
- Animation snaps when keys exist in only one segment: key everything with Ctrl+Shift+L on both sides (jKz 24:05).
- Don't patch deform keys across all animations; they bloat file (H2L 5:55).
- Don't over-rig the face; may not be needed, complicates emotions (wxC 2:33).
- Don't put hair strand per bone; one or few (wxC 4:38).
- Shields/flat props: shear and scale instead of mesh/constraints (wxC 5:12).
- Transparency 0 still draws; hide attachment instead; scale root to 0 hides but still sends draw (H2L 9:00).
- Clipping is CPU expensive; minimise (H2L 7:31).
- Resize art before import; avoid scaled-up bones (H2L 1:09).
- Spine only supports 3 additional blend modes from Photoshop (wxC 1:35).
- Bones count -> timelines count -> data; clean keys on export (H2L 10:01).
- Don't treat rig as final: expect revisits.

---

## 8. SCREENSHOT PICKS

| videoId | m:ss | What should be on screen | Why |
|---|---|---|---|
| 9Zv-Mb7zi2U | 0:29-1:00 | Create tool Ctrl+click on pelvis image, bone named `pelvis`, tree with hip below | Shows bone placed at the image centre and first hierarchy step |
| 9Zv-Mb7zi2U | 2:21-3:20 | Leg mesh with dense points at the knee and sparse at the back; bone origins visible | Vertex placement rule for bending |
| 9Zv-Mb7zi2U | 4:48-5:50 | Weights Overlay on the foot/leg showing 100% regions and the gradient at knee/heel | Concrete weight painting pattern |
| 9Zv-Mb7zi2U | 8:12-8:41 | Finished spine chain pelvis->waist->chest->head in viewport and tree | Spine bone count/placement |
| 9Zv-Mb7zi2U | 14:33 | Arm mesh triangles avoiding the scar, 100% weight on scar | Mesh planning around details |
| 9Zv-Mb7zi2U | 17:24-18:25 | IK constraint + transform constraint panels on the foot IK and foot bone | How single-bone foot control is built |
| jKzIo566gnk | 1:26-1:55 | `face` bone selected, face slots inside it, mesh weights head vs face | 20-second fake-3D face rig |
| jKzIo566gnk | 6:45-7:44 | Slider constraint panel (animation + bone + rotation range) | Only slider example |
| jKzIo566gnk | 13:11-14:40 | Bubble container with nested bones, bone trail display on | Layered motion and arc checking |
| jKzIo566gnk | 23:08-25:34 | Dopesheet/graph during idle variation, with Ctrl+Shift+L keys and ease curve | Key-all technique and transition curves |
| jKzIo566gnk | 31:05-32:02 | Yellow oversized helper bone and its weight paint on waist/chest | Helper body-bend control |
| GujtDSo2pvM | 1:25-2:22 | Bone tree with character container, pelvis, foot targets under the container | Hierarchy for IK targets and root substitute |
| GujtDSo2pvM | 3:47-4:16 | Finger mesh with 3 outer / 2 inner vertices bending | Finger meshing recipe |
| GujtDSo2pvM | 5:16-5:44 | Alt-tap pivot re-drawing in Create mode with preview | Pivot-finding workflow |
| H2LktmTdxGI | 6:28-7:00 | Weights panel, rope/tail with bones at triangle cross sections; vertex transform count | Optimization rule on weights |

---

## 9. Takeaways for our pipeline (python JSON generation)

1. Add a character container bone below root (never animate root); pelvis as child; chain pelvis -> waist -> chest -> head (no neck; mesh bridges chest/head).
2. Place bones at the visual joint centres (hip ball, knee, ankle); legs: hip/leg/foot with a foot target bone parented to the container + IK (stretch) + transform constraint (rotate/scale) so a single control bone moves and rotates the foot.
3. Only mesh bending parts (legs, torso/trousers, arms, cloth); dense verts at inner bends, few elsewhere; 100% weights away from joints with a narrow blend band; max 2 bones per vertex.
4. Use helper bones: `face` (scale = fake 3D turn), shoulder, torso-bend helper, teeth/jaw/beak, container for secondary loops. Turn off inherit rotation on shoulders/head if the torso should not carry them.
5. Idle recipe: breathing (chest expansion + body up/down), separate X/Y on hip with offsets, per-limb rotation offsets, differing loop lengths, a variation with weight shift keyed with key-all on both sides.
