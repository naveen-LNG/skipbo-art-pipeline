# D - Spine primitives (Armanimation): bones, meshes, IK, face, lipsync, slider

Source: 8 auto-caption transcripts (read in full). Quotes are lightly cleaned. Items marked (inferred) are my reading of garbled captions or standard Spine behaviour not stated verbatim.

---------------------------------------------------------------------
## 1. Per-video summary

**_TikdZ9LCGs - Tips & Tricks: Mastering Bones** - https://youtu.be/_TikdZ9LCGs
- 0:04 Re-position a bone without touching hierarchy: select bone, Create tool, hold Alt, draw new pos/rot -> replaces the old bone, children/attachments stay.
- 0:38 Create-bone-at-tip menu (needs the two auto modes on; with World axis it spawns at 0,0). Pose tool recommended, esp. for 2-bone chains (arms/legs); can pose bones across different chains at once.
- 1:46-4:19 Inherit Rotation / Inherit Scale unchecks: head does not rotate with chest; for breathing, uncheck scale inherit on shoulders+neck so the chest scales but shoulders/head only displace. "Same animation, 2 timelines, 6 keys" gives natural result. Cannot be unchecked on bones in an IK chain.
- 4:19-6:39 Hide/show bones (dot toggles, Ctrl+H show all, Ctrl+B hide all bones), tree hotkeys (Ctrl+Up = parent).
- 6:39-9:43 Number fields do math (type `+30`, `*2`; for minus type `+` then `-45`). Copy/paste a bone's transform (position+rotation, multi-bone too) - used to snapshot bone pose before binding meshes, and to "hold" an IK foot planted: copy transform, paste/key it on following frames. Bone length by dragging tip.

**qEc-mKRTfHY - Tips & Tricks: Working with meshes** - https://youtu.be/qEc-mKRTfHY
- 0:00 Manual (yellow/orange) edges force topology = better bending. 0:58 Mesh tools soft selection brush (size, feather 100% = falloff, "hold vertices" keeps the outline fixed while moving inner verts - for adjusting a face without breaking silhouette).
- 1:53-4:22 Rotate/scale a vertex selection about a movable origin point; works across multiple meshes at once; selecting partial verts from several meshes + feathered brush rotates all with falloff.
- 4:51 Draw order of a mesh part-by-bone: in Weights window reorder the bone list (move to top) to make a part go in front of another. 5:20 Duplicate a mesh (new slot, weights preserved) and delete verts to keep only e.g. the eye -> recolour/blend mode without re-weighting. Not a linked mesh, so later weight edits must be repeated.
- 6:46 Wireframe to place bones exactly on vertices ("each bone is located at some vertices -> nice bending"). 7:45 Reset button: setup mode reverts weights+deform; animation mode resets to setup pose per vertex. Vertex colours: blue selected, grey unselected, purple modified.
- 8:45 Shift+click selects a vertex ring along connections. 9:16 Save vertex selection to number (Ctrl+1), Ctrl+C/V positions to restore e.g. eye verts after face edit (world axis).
- 10:17 Smooth weights propagate only along edges (blue or yellow) - isolated verts won't smooth; build "bridges". 11:11 Prune: max-bones + threshold; removed 123 weights - good for perf, bad for smoothness.

**Z_9Rydrxd90 - Why use orange lines (manual edges)** - https://youtu.be/Z_9Rydrxd90
- Eight benefits: (1) grab and move/scale/rotate edges in setup pose with moving pivot (0:00); (2) Shift-click selects a whole loop/ring (0:31; 4.2 also in weights); (3) control triangulation without adding verts (1:00); (4) weight smoothing only crosses edges (1:56-2:51) - key one; (5) edge creation snaps to midpoint, Shift disables snap, Shift also locks axes (3:19); (6) only way to delete part of a mesh - must close a loop of edges first, then delete (3:47); (7) wireframe view shows them when mesh unselected (4:17), helpful as guides for placing bones; (8) Dim the texture to see orange pixels vs edges (1:26).

**l3HizZDk8nQ - How to create IK constraints** - https://youtu.be/l3HizZDk8nQ
- 0:32-2:36 FK vs IK; 1 or 2 bones max. "A common mistake is to create an IK for an arm just to control it using one bone" - you lose lower-arm follow-through. Add IK only when an external force exists (ground, table, wall, two-handed sword, hand on waist). IK can be turned off per animation.
- 3:11-4:40 Creation: select bone(s), New > IK Constraint, click to create target (or click child tip for 2-bone). Target can never be a child of constrained bones.
- 5:10-8:23 Settings: Compress/Stretch off by default (compress only for 1-bone), Uniform, Mix (0 = off; animatable), Softness (kills end-of-reach snap but "looks like walking on snow"; author never uses it on legs), Bend Positive (keyable; chain must be straight before flipping).
- 8:23-10:26 Setup-IK tricks: IK target parented inside another bone to drive shoulder/butt-cheek deformation (not animated, just "enhance the rig"); IK + transform constraint = knee.
- 10:26-14:24 One target bone for multiple IK chains (ball squash/stretch, snake); constraint order matters ("reset the order automatically... if not, order manually"); path constraint for smooth spines/strings; IK chains bound to path.
- 14:24-16:27 Scale bones briefly to fix weird rotation when one bone is much larger; horse legs: foot bone reversed, IK target inside it; eyebrows = 2-bone IK on shared target at max softness; pupils IK. Limits: one bone must be child of other; Inherit rotation+scale must be on; softness > 0 disables stretch.

**WAzVsoCLZYY - Rigging Leg with IK + Knee joint** - https://youtu.be/WAzVsoCLZYY
- 0:00 Two stacked IK constraints on a 2-bone chain (thigh/shin) - one per bone, set compress+stretch (1-bone IK each); these are the bones meshes bind to.
- 1:00 Duplicate that set; IK the duplicate chain to the same existing target (renamed) = the actual leg; a Transform constraint makes the first-set bone follow the knee joint (translate only is enough); reset constraint (Reset in tree) and lower IK mix slightly -> knee ball moves while IK still holds. (inferred; transcript is terse and garbled - see Section 4 for my reconstruction.)

**oSWqlXwfAlE - How to rig a face in Spine 2D** - https://youtu.be/oSWqlXwfAlE
- 1:59-8:24 Complex face rig (long-face character): control bone rotates; two circular "container" bones skewed into a ring (aligned with ear/cheekbone/nose); head bones are in a skewed reference frame so rotation fakes 3D. Author: "mostly I don't do this way."
- 4:30 Default approach: ONE bone over medium portion of face, meshes weighted 100% centre -> low at edges; scale/shear emphasise the move.
- 8:55-19:09 Weight rule: tip/centre 100%, nose ~80% (depth-based), fall to ~0-5% at ears. Lock-all, paint on one bone only; fix holes at eyes with Direct select + overlay view.
- 19:38-24:32 "Medium" rig: add reverse "back head" bone, transform constraint with translate mix -100% (mirror) so back-of-head parts counter-move = parallax.
- 29:07 Blink: close in 1 frame, reopen over 5-6 frames; pupils drift down on close and recover slightly faster than lids. Keep holes in head mesh so pupils hide behind (masks are heavy - avoid).
- 30:15 Bonus: additive-blend + black-normal duplicate trick for glare/shine confined to the character (needs matching background). Scale: "100-200 soldiers - totally not worth it, just simple movement or don't do at all."

**cT8xcHa1ccY - Lipsync rigging mouth** - https://youtu.be/cT8xcHa1ccY
- 0:00-0:55 Mouth states as artist-supplied images swapped by attachment; if character is large on screen, add bones for smoothness: one for chin (up/down) and one for scaling. Two open-mouth states + idle covers basic talking.
- 0:55-3:28 Mesh keeps teeth and lips as separate meshes so they don't stretch. Bind to two bones: a container bone and a scale bone. Remove auto-weights -> all to container; then give scale bone a fixed 30% and LOCK that weight; paint the lower lip fully to the up/down bone; Smooth. Keep container lower in bind list to limit triangle overlap.
- 4:27-6:37 Second mouth state done identically; closed state must be near idle for easy transitions; scale to match sizes. Shift-scrub to find stretching between frames; break interpolation (stepped) to avoid it.
- 6:37 Chin bone bound last with small weight while mouth is closed.

**bHWx9gwGg_c - Hand poses with Slider Constraint** - https://youtu.be/bHWx9gwGg_c
- 0:01 Spine 4.3 sliders. Telescoping limbs: extra bones constrained to a single axis to shorten/lengthen arm; elbow can be pulled out and rotated 360 degrees.
- 1:26 Build an animation "L" with one key per hand state (attachments, deform, anything); Create Slider from the animation, bone = controller, property = rotate; rotating the controller scrubs through hand states. Spine auto-detects start/end frame.
- 3:22 Use world (not local) transform of the controller (local did not work) - gives consistent angle in world space.
- 4:25 Why not just attachment-switch: a state groups finger slots, thumb, wristband, deformation under one frame. Add a frame for e.g. big-thumb variant.
- 5:21 Slider overrides attachments, so disable the slider constraint (per-animation) when editing. 5:48 Skins + constraints for different proportions (male/female) using same rig; offsets via constraints.

---------------------------------------------------------------------
## 2. Bones

- **Creation**: Create tool, click-drag from parent (parent = selected bone). Menu "create bone at tip of selected" (needs the two auto-mode toggles on); with World axis it creates at (0,0). Draw bones so the origin sits at the pivot (joint) - the bone origin is the rotation pivot.
- **Replace without rebuild**: Alt + Create tool over existing bone redraws pos/rotation, hierarchy and attachments preserved.
- **Parenting**: bone hierarchy is FK ("child follows parent"). Move "Parent" tool to re-parent. Group helper bones under a container so the container can be rotated/scaled/skewed as a frame of reference (face video: "all inside this inner bone for that select them hit parent").
- **Inherit flags**: Rotation and Scale checkboxes (Inherit panel). Default on. Turn off:
  - Head rotation inherit off -> head stays upright while chest rotates (counter-motion for free).
  - Scale inherit off on shoulders/neck -> breathing scales the chest only; shoulders+head merely displace. Same keys, no extra animation work.
  - Disabled/greyed on bones that are in an IK chain; and IK **requires** rotation+scale inherit on (limit #2 in IK video).
- **Length**: drag the tip (hover icon), length only matters for IK chain solving, display, auto-weights, tip-creation. Turn on bone names for clarity.
- **Transform axes**: World / Parent / Local. World for copying vertex positions (Ctrl+C/V) and slider source ("local did not work"); local when you want motion along bone axis.
- **Telescoping bones** (slider video): separate bones constrained to move in a single axis shorten/lengthen limb; supports pulling elbow out.
- **Tips**:
  - Pose tool (not just Rotate) - poses 2-bone chains and multi-selected bones across chains.
  - Copy/paste transform to stash a good pose while binding; paste back after. Also to key an IK foot to an exact planted position.
  - Math in fields; hide bones by Dot / Ctrl+B / Ctrl+H; Ctrl+Up to jump to parent.
  - Box-select bones and click dot to hide without hiding images.
  - Use distinct icons/colours for controller bones ("changed icon to something more visible... so people don't move it mistakenly").
  - Shear/scale on a container bone to build skewed reference frames (face).

---------------------------------------------------------------------
## 3. Meshes

- **Create from image**: Mesh tool on attachment -> Edit; click to add hull points around the silhouette, then internal vertices (green/internal) where deformation needed. Mesh auto-triangulates. (Hull/internal terminology is standard Spine; only implied in these videos via "outline" and "hold vertices".)
- **Hull vs internal**: Soft-selection brush "Hold vertices" (default on) pins the hull/outline while you move inner verts - "adjust the face... don't want the outline to break". Turn it off to move edge verts too.
- **Orange/yellow manual edges** (author calls them orange lines in one video, yellow in another - same thing): created by dragging between verts and releasing. Why:
  1. Weight smoothing flows ONLY along edges (auto or manual). Isolated verts cannot be smoothed. For a long limb attachment, a bridge edge is required for Smooth to carry weights.
  2. Force triangle layout ("make nice bending") without adding vertices.
  3. Shift-click loops/rings -> select a whole ring of verts (also in weight mode since 4.2).
  4. Delete part of mesh: close a loop with manual edges first, then delete.
  5. Midpoint snapping when drawing edge (Shift disables, Shift locks axes).
  6. Wireframe view shows topology as guide for placing bones exactly on vertices.
  7. Dim texture for visibility.
- **Vertex density rules (author's practice)**: no numeric rule given. Observed: dense ring of verts at joints (elbow, knee) with bone origin placed ON a vertex row ("each bone is located at some vertices... nice bending"); keep teeth/lips as separate meshes so they don't stretch; add points when a region needs more volume ("add more vertices here so I can give more volume"); for massed crowds (100-200 characters) skip face rigs entirely.
- **Weights**:
  - Bind: select mesh + bones in Weights window (bind), auto-weights as starting point (author often discards: "just automatic weights so let's remove it by binding it all to this container bone").
  - Painting: Lock all, paint only the target bone ("proper way would be to lock everything and only paint on this bone because we don't want to take off from the ear bones"). Direct/overlay view for precision. Tip of influence = 100%, tapering to ~0-5% at far edge.
  - **Lock a bone weight**: mouth: scale bone fixed at 30%, locked so later painting can't change it -> consistent scalability.
  - **Smooth**: propagates along edges; select verts then Smooth.
  - **Prune**: set max bones per vertex + threshold; "removed 123 weights... good for performance, not good for smoothness".
  - **Bind order** in Weights window controls draw order of that part relative to other meshes' bones (move bone to top -> part in front). Keep container bone low to avoid triangle overlap.
- **Deform keys vs weights**: Weights = persistent, from bones; Deform keys = per-vertex animation in animation mode (purple verts = modified). Reset in animation mode returns to setup pose (not original image) per vertex; in setup mode reverts weights+deform. Deform keys are for local fixes; the author prefers adding bones/weights when something breaks ("add more bones and more weights"). Path and mesh deform can both be keyed.
- **Duplicate vs linked mesh**: Duplicating a mesh keeps weights; delete verts to isolate e.g. the eye, change colour/blend. It is NOT linked: weight edits must be repeated. Linked meshes (not covered here) would share edges/weights.
- **Vertex-tool tricks**: movable origin for rotate/scale of vertices; multi-mesh simultaneous selection and edit; Ctrl+1 store selection, Ctrl+C/V copy positions (world axis) to restore verts after a broad edit; feathered brush rotation; Shift-click ring.

---------------------------------------------------------------------
## 4. IK constraints

- **1 vs 2 bone**: max 2. 2-bone: one bone must be direct child of the other. "Unfortunately there is no way to create IK for more than 2 bones." Use path constraint or chained bones with transform constraints for longer.
- **Create**: select bone(s) > New > IK Constraint; click empty space = new target bone (or click child tip for 2-bone, target at tip). Target icon opens constraint settings. Target can never be a child of the constrained bones.
- **When to use**: only with an external force (ground, wall, table, weapon, hand on waist). Not for "control with one bone" - loses follow-through. Can be turned off per animation (mix 0).
- **Bend direction**: "Positive" checkbox. Keyable; make sure the chain is straight before keying the flip or you get an ugly flip. Pole is NOT used - bend is controlled by Positive + bone pose.
- **Mix**: 0 = off; animatable, so you can blend IK<->FK smoothly or have multiple IK constraints with different mix on the same bones.
- **Stretch/Compress**: off by default. Compress only meaningful for 1 bone. Stretch for 2-bone. "Uniform" ties X/Y scale (author never uses).
- **Softness**: removes end-of-reach snap; feel like walking on snow; with softness > 0 stretch stops working. Author never uses on legs; avoids fully straight legs instead. Uses max softness for eyebrow IK to get a soft limit.
- **Knee/elbow controller bone (WAzVsoCLZYY, reconstructed)**:
  1. Hip-knee-ankle chain A (two bones). Create 1-bone IK on each bone (compress+stretch). These are the "mesh-bound" bones.
  2. Duplicate set (chain B). Create 2-bone IK on chain B to same foot target.
  3. Transform constraint: chain A bone (the knee/lower bone) constrained to chain B's joint with translate link (can leave other sliders at 0). Reset constraint; lower IK mix slightly -> the knee joint can be moved/pose in perspective while the IK still holds.
  Author also states in IK video: "Combining IK with transform constraints we can rig a knee along with the leg IK allowing us to move knee while using IK."
- **Target placement tricks**: parent target inside another bone (e.g. arm bone) so shoulder/butt-cheek deformation follows (non-animated); multiple IK chains share one target (squash/stretch ball, snake body); horse/spider legs: reversed foot bone with target inside; IK for pupils and eyebrows (eyebrows: 2-bone with max softness to a shared target).
- **Ordering**: constraints are solved in list order - "it happens a lot when rigs get complex": use the reset-order button then manual.
- **Mixing with path constraint**: snake spine - bones along path, IK for head, path bound to bones/deform keys.
- **Limitations**: child relation; inherit rotation/scale must be on; softness>0 disables stretch.

---------------------------------------------------------------------
## 5. Face rig

- **Three levels (author's own)**
  1. *Simple (default)*: ONE bone over the medium portion of the face; all face meshes weighted to it: 100% in centre, falling to ~0-5% at ears. Move + scale + shear gives fake 3D. "Mostly I use this way."
  2. *Medium*: add "reverse"/back-head bone constrained to the head bone via transform constraint with translate mix = -100% (mirror). Back-of-head parts (hair, scarf, ears) bind to the reverse bone ("this bone is only for mesh weighting"); parallax from opposite motion. Per-vertex weight depth: tip 100%, nose ~80%.
  3. *Complex*: container bones in a ring (ear/cheekbone/nose) arranged inside a skewed/scaled parent so rotation of the control bone orbits the points around a face ("rotation of a 3D head"), with transform constraints to keep rotation; ~1 hour setup; for large on-screen heroes only. Two pivot points are used for lizard/realistic characters.
- **Control bones count and place** (from the videos): 1 face-control bone (centre of face); cheekbone bones (partial emotions); eyebrow bones (one each, simple); eye container bones (eye rig from previous video: IK target for pupils; blink via lid meshes); whisker bones (1 per whisker); ear bones; reverse bone; up to 4 ring bones in complex mode.
- **Eye rig** (this group's video only touches it): pupil with IK target; eye containers hold shine layers; "better to have holes in the head so you can hide the pupils behind them" rather than clipping masks (heavy). Blink 1 frame closed / 5-6 frames open; pupils drift down on close, recover quicker than lids.
- **Gaps in the transitions**: need rings/eye openings bound exactly to the same bone so no holes appear; fix with locked weights + Direct selection.
- **Mouth/lipsync (cT8xcHa1ccY)**:
  - Default: attachment swap among 3 states (idle/open1/open2) = enough for smaller characters. 
  - For large-on-screen characters: mesh each mouth state (lips & teeth separate meshes) and bind to **two bones**: container bone (carries the position/follows face, 70%) and scale bone (30% locked, scale the mouth open/closed). Plus a chin bone for jaw up/down, bound with small value, while mouth closed.
  - Closed pose should be near idle; scale states to match; scrub with Shift to spot stretching, use stepped interpolation where needed.
- **Fake "3D" shading effect**: additive-blend copy over a black normal-blend copy of a glare image, clipped to a background silhouette (30:15) - shine only appears on character pixels; no masks.
- **Scale guidance**: for crowds (100+ chars) skip face rigs.

---------------------------------------------------------------------
## 6. Slider constraint, hand poses, transform constraints

- **Slider constraint (4.3, from bHWx9gwGg_c)**: a constraint that maps a bone property (e.g. rotation) onto the playhead of an animation. Workflow: (1) make an animation per hand with one keyed frame per pose (attachments, deform, any property); (2) "Select animation > Create slider"; (3) choose a controller bone and the property (rotate); (4) spine sets start/end frames; (5) rotate the controller -> hand pose switches; range adjustable (slower/faster). Use world transform of the controller (local didn't work). Add extra frames for variants. Disable the slider constraint in animations where you need to edit the underlying attachments.
- **Why use sliders over attachment keying**: poses group hand base + fingers + wristband + deformation; one control; poses can have a different set of slots visible.
- **Telescoping/gesture limbs**: extra single-axis bones to lengthen/shorten limb without losing elbow control.
- **Skin-specific proportions**: same rig different skins; constraints save per-skin offsets (female shoulder joint position etc). Duplicate animation for variation.
- **Transform constraints in the other videos**: (a) follow-joint for the knee setup; (b) translate mix -100% to mirror back-head; (c) keep rotation when head rotates in complex face; (d) move IK target with the head for the snake; (e) drive a bone from another with offsets (skin constraints).
- **Order of constraints**: reset-order button, then manual.

---------------------------------------------------------------------
## 7. Glossary

| Spine primitive | What it does | When the author reaches for it | Our rigid-parts equivalent |
|---|---|---|---|
| Bone | pivot+hierarchy | everything; origin at joint | one bone per part (we have) |
| Inherit rotation/scale off | stop parent rot/scale propagation | head upright while torso rotates; breathing scale | none; we could set inheritRotation=false on head/hat props in JSON |
| Alt-redraw bone | move bone preserving hierarchy | fix pivot after meshing | edit bone x/y/rotation in Python |
| Copy/paste transform | snapshot bone pose | binding, planting foot | no equivalent; use setup pose |
| Region attachment | rigid image | simple parts, mouth state swaps | what we use now |
| Mesh (hull + internal verts) | deformable image | any part that bends (limb, face, hair) | missing - biggest gap |
| Manual edge | force topology / smoothing route / delete | long limb, bend regions, deleting parts | n/a (need verts first) |
| Weights (bind) | per-vertex bone influence | all deformation | none - every part is 100% on 1 bone |
| Lock weight | freeze one bone's share | mouth scale 30% | n/a |
| Smooth / Prune | blend weights along edges / drop small | after painting / for perf | n/a |
| Deform key | per-vertex anim | local fixes, hair flutter | n/a |
| Draw order via bind order | layer one part in front | head overlap | slot order |
| Duplicate mesh | recolour w/ same weights | eye colour | duplicate region |
| IK 1-bone | bone points at target; compress/stretch | squash, eyebrow, pupil | none (could use for eyes/arms w/ target) |
| IK 2-bone | solves bend between two bones | legs/arms against ground/props | none |
| IK mix | animatable IK/FK blend | switch IK off in some anims | n/a |
| IK softness | smooth reach limit | eyebrows (max); NOT legs | n/a |
| IK bend positive | flip knee | turn around | n/a |
| Shared IK target | one bone drives several chains | squash ball, snake | n/a |
| Transform constraint | copy/mirror/offset bone props with mix | knee joint, reverse back-head (-100%), follower | none |
| Path constraint | bones along a curve | spine, strings, tail | none |
| Slider constraint | animation timeline driven by a bone | hand poses, expressions | manual attachment keys |
| Skins + constraints | proportions variants | male/female same rig | n/a |
| Helper/container bones | frames of reference | face ring, mouth container | none |
| Wireframe, dim | visual aids | place bones | n/a |

---------------------------------------------------------------------
## 8. Gotchas

- Smoothing weights does nothing across vertices without an edge connection (caption: "it can't be smoothed because there is no connection").
- Orange pixels in art are hard to see against orange edges: use Dim.
- Mesh part deletion is impossible until edge loop is closed.
- Duplicated mesh is not linked: later weight edits are not mirrored.
- Reset button differs: setup mode reverts weights+deform; animation mode resets verts to setup pose.
- Pasting vertex positions: use World axis.
- IK: target cannot be child of constrained bones; inherit rotation/scale must be on; no inherit toggles in IK chain; softness > 0 kills stretch; contraction unavailable for 2-bone; flipping Bend Positive with a bent chain flips ugly; constraint order matters; mix can be animated.
- Slider overrides what you key on the controlled attachments - disable it while editing the hand animations; use world (not local) bone transform.
- Rotate/scale of a lone vertex or mesh with no origin move behaves oddly: move the origin first.
- Prune too hard loses smoothness.
- Auto-weights often bad - author discards them.
- Hull verts move with soft-selection unless "Hold vertices" on.
- Mask clipping is expensive; prefer holes behind.
- Don't over-engineer faces on crowd characters.
- Face "rotation" with a single bone is fake: moving + scale/shear; true rotation needs the ring-of-bones skewed frame.
- Scaling bones briefly then restoring fixes IK rotation pops when bones differ strongly in size.
- Keying `Positive` needs straight chain.
- Caption caveat: knee video terse; reconstruction may not be exact.

---------------------------------------------------------------------
## 9. SCREENSHOT PICKS

| videoId | m:ss | what should be on screen | why it matters |
|---|---|---|---|
| qEc-mKRTfHY | 0:00-0:29 | mesh with orange/yellow manual edges and wireframe, triangles redistributed | what a good manual-edge topology looks like |
| qEc-mKRTfHY | 6:46-7:17 | mesh wireframe with bones placed on vertex rows | vertex/bone relationship for bending |
| qEc-mKRTfHY | 10:44-11:11 | smoothing blocked vs working after a bridge edge | edges as smoothing route |
| qEc-mKRTfHY | 11:38 | prune window (max bones, threshold) | prune parameters |
| Z_9Rydrxd90 | 1:56-2:51 | two vertex pairs painted 100% blue, smooth with/without orange line | clearest weights-color demo |
| Z_9Rydrxd90 | 3:47 | closed edge loop and delete-mode | how to delete portions |
| l3HizZDk8nQ | 5:10-6:56 | IK constraint settings panel (mix, softness, bend, compress, stretch, uniform) | full IK parameter list |
| l3HizZDk8nQ | 8:23-9:03 | chest + 2-bone IK with target parented inside arm, mesh bound | shoulder deformation helper |
| l3HizZDk8nQ | 14:55-15:28 | horse leg, eyebrow 2-bone IK | non-obvious IK uses |
| WAzVsoCLZYY | 0:29-1:58 | tree with duplicated chains, IK + transform constraint, knee joint | knee setup |
| oSWqlXwfAlE | 3:00 | complex face: bones in ring arrangement w/ images hidden | face control bone layout |
| oSWqlXwfAlE | 8:55-9:54 | face mesh with weight gradient from centre to ears | weight falloff for fake 3D |
| cT8xcHa1ccY | 0:55-2:21 | mouth mesh (lips/teeth) with container + scale bones, 30% locked | lipsync rig |
| bHWx9gwGg_c | 1:53 | Create Slider dialog, bone and property, animation list | slider setup |
