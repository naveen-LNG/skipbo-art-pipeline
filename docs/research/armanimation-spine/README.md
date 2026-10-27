# How Spine animators rig a character (Armanimation study)

Research only, nothing built. Main source: the [Armanimation](https://www.youtube.com/c/Armanimation_spine) channel by Arman, a professional Spine animator. I catalogued 180 long-form videos and shortlisted 28 on rigging, non-human characters, Photoshop prep and Spine primitives, and read every one through its timestamped transcript.

A second pass added 9 more Armanimation videos and the most-viewed parts-splitting tutorials on YouTube (§6), which cover how to turn one flat image into rig-ready layers. The stills (`frames/`) now number 93. For the second pass, YouTube rate-limited caption downloads, so those learnings were read off the captured frames (`evidence: on-screen`). Transcript-backed learnings are added when the captions unblock.

| File | What it is |
|---|---|
| `README.md` | This summary: the workflow, the rig template per bucket, the gaps in our pipeline, shortcuts |
| `learnings.jsonl` | 112 learnings, each tagged with **bucket**, **style** (cartoon / anime / realistic / semi-realistic / painterly / flat-vector), **stage**, **primitive**, source video and timestamp, evidence level, and the frame it was seen in. This is the annotation file |
| `frames/` | Video stills. The filename prefix is the bucket (`quad-`, `human-`, `realistic-`, `creature-`, `prop-`, `face-`, `psd-`, `split-` for master-splitting), followed by the videoId and the second |
| `source-notes/` | The four long extraction notes (A: PSD prep, B: rig setup, C: non-human, D: primitives) |

Interpretation: by "the function we're not leveraging" I understood **mesh deformation + weights**. That is the reason our output feels rigid. Every part in our rigs is a rigid image, 100% on one bone, so nothing can bend, squash or curve.

---

## 1. Buckets: keep these separate

Every learning carries exactly one bucket. Learnings from humanoid rigs are not reused for animals unless they were also observed on an animal.

| Bucket | Observed on | Count |
|---|---|---|
| `quadruped-animal` | pig, cow, sheep, rabbit, cat head, fantasy fox (cartoon to semi-realistic, talking/expressive) | 26 |
| `cartoon-humanoid` | mutant brute, lipsync girl, old man with cane, frontal walker, anime/VTuber parts-splitting examples (`style: anime`) | 41 |
| `realistic-humanoid` | Tracer, armoured hare warrior, Dragonborn, snake-man | 13 |
| `creature` | raptor + rider, owl wing and tail, spider leg, crab, turtle face | 10 |
| `props-fx` | slot-game stones, balloon skins, shield, lantern ropes, book page | 5 |
| `environment` | painted background split into layers | 5 |
| `universal-tool` | tool mechanics that don't depend on body type (PSD tags, mesh edges, IK limits, sliders) | 12 |

`style` is a second axis. Filter on `bucket` **and** `style` when you need, for example, cartoon humanoid rules without the anime-specific ones.

**Our cast doesn't fit one bucket.** Beaver, fox and moose have a biped humanoid body with an animal head and face. The channel has no clean example of a cartoon *biped* animal. The rabbit sits like a quadruped, and the hare warrior is realistic. My recommendation is a seventh bucket, `anthro-biped-animal`, for our own annotations, filled from two sources:
- body and limbs from `cartoon-humanoid`
- head, ears, eyelids, snout and mouth from `quadruped-animal`

Each annotation should record which source bucket it came from.

---

## 2. The animator's workflow, stage by stage

The visual version is the published workflow map. Order as Arman works:

1. **Plan.** He asks the developers for the Spine version and whether meshes and constraints are allowed. He decides what the animations are (idle, jump, talk) *before* cutting: "understand who your character is". Rule: cut only what the animation needs.
2. **Photoshop prep.**
   - One layer per independently moving part, uniquely named. The layer name becomes the bone, slot and attachment name.
   - Joint ends are drawn round so a rotating part never shows a seam.
   - Curved parts (hair, tail, cloth) get a **straightened copy** made with Puppet Warp or Liquify.
   - Joints are tested in Photoshop by holding Alt and dragging the transform pivot.
   - The art is resized to the target resolution first.
   - The ground point is set with ruler guides or an `[origin]` layer.
3. **Import.** Either the Photoshop-to-Spine script (JSON + PNG) or the native PSD import (stays linked, refreshes). Tags: `[bone] [slot] [skin] [merge] [folder] [ignore] [path:name]`, plus the newer `[mesh] [mesh:source] [skin:name] [overlay] [origin]`. **Pivots are never set in the PSD**; placing them is the animator's job in Spine.
4. **Skeleton.**
   - `root` is never animated. The first bone is a `character` container.
   - Then `pelvis`, placed at the centre of mass (Ctrl+click on the hip image).
   - Then a short spine (waist, chest, head) and the limb chains.
   - Pivot = the middle of the round joint piece.
   - No neck bone: a mesh bridges chest and head.
5. **Helper pivots: the smoothness layer.** These are bones that hold no image of their own:
   - hip/chest split
   - `face` bone (scale = fake 3D turn)
   - reverse back-of-head bone (transform constraint at −100% for parallax)
   - ear chains of up to 3 bones
   - eyelid curve bones
   - chin and mouth-scale bones
   - torso-bend helper (`chest2`) and extra pelvis pivots
   - tail chain, IK target bones, shadow bones

   Inherit-rotation is turned off on the head and shoulders, and inherit-scale off on shoulders and neck for breathing.
6. **Meshes + weights.**
   - Mesh only what bends. Props, eyes and highlights stay rigid.
   - Dense vertices on the inside of a bend, sparse elsewhere, with bones sitting on vertex rows.
   - Weights are 100% on one bone away from a joint, with a narrow blend band at the joint.
   - Paint one bone at a time with the others locked, then Smooth (it spreads only along edges, so add manual edges as routes).
   - Avoid long thin triangles and triangles that cross details.
7. **Constraints.**
   - 2-bone IK with Stretch on legs only (external contact).
   - IK + transform constraint so one control bone moves *and* rotates the foot.
   - Transform constraints for ears, back of head, half-follow chains and an airborne target follow.
   - Sliders (4.3) to drive pose libraries.
   - Arms: no IK.
8. **Organize.**
   - Controllers red with big icons.
   - IK targets and rarely used bones go in a named selection, hidden.
   - Images live inside bones.
   - Slot folders keep draw order manageable.
9. **Animate.**
   - Bring the rig to 80% and start animating; the rig keeps changing.
   - Idle = 60-frame breathing plus offset limb rotations, then duplicated variations (weight shift, face turn, blink).
   - Hip X and Y timelines are split for curved paths.
   - Ghosting and onion skin are used constantly.

---

## 3. Rig template per bucket

### quadruped-animal (cow / pig / rabbit / sheep)
```
root
└ character (container) ─ everything except shadow
  ├ body
  │ ├ spine_back > hips ─┬ rear legs (2-bone IK, stretch) + hand-moved "reversed bone"
  │ │                    └ tail1 > tail2 > ... (tip 100% rigid)
  │ └ spine_front > chest ─┬ front legs (IK target = child of paw)
  │                        └ head ─┬ back_head (transform -100, parallax)
  │                                ├ ear_L > ear_L1 (> ear_L2)   ≤3 bones, follow head via transform
  │                                ├ cheek_L/R, eyebrows, whiskers, nostrils
  │                                ├ eye_L/R (ball IK target, lid curve bones, closed/happy-closed swap)
  │                                └ snout > mouth > chin
  └ IK targets (built from root, outside the chains; hidden in a selection)
shadow (2 bones, 1 mesh, outside container)
```
Frames: `quad-cow-tree-*`, `quad-pig-*`, `face-cat-tree-backhead-eyes_*`.

Second pass:
- **Eyes:** the eyes sit in *empty sockets*. The head is painted with skin under them, and each eye is stacked as ball, closed lid, lid, shine, pupil. Both pupils hang off short bone chains aimed by **one shared `target` bone** (`quad-cat-eye-*`).
- **Fur:** semi-realistic furry quadrupeds add dozens of small fur and mane bones for secondary motion (`quad-fantasy-fox-*`).

### cartoon-humanoid (mutant brute)
```
root
└ character
  ├ shadow
  ├ pelvis ─┬ hip > leg_L > leg_L2 > foot_L   (mesh: 5 verts can be enough)
  │         ├ pelvis2 / pelvis3 / pelvis5 / pelvis7   (extra pivots: shoulders, scar, feathers)
  │         └ waist > chest ─┬ chest2 (yellow bend helper, light weights)
  │                          └ head ─┬ head (face mesh) / face (scale = 3D turn)
  │                                  └ beak > mouth > teeth > mouths(swap)
  └ target / foot_L_IK   (IK + "target-to-foot" transform = one control bone)
```
Frames: `human-mutant-*`.

Second pass:
- **Elbow helper:** an elbow helper bone at the sleeve fold (`human-oldman-*`).
- **Arm IK for contact:** a hand gripping a cane gets arm IK (external contact) plus a hand base with f1–f5 finger bones.
- **Front-view walk rig:** front and three-quarter-view hand attachments in the same slot, plus in-front and behind-leg trouser slots for layering (`human-frontal-*`).

### realistic-humanoid (Tracer, hare warrior)
- The pelvis sits slightly *behind* the body.
- Foot IK targets are the ball bones, moved under the container.
- One real 3-bone finger chain; the other fingers are faked.
- Two leg attachments in one slot (standing vs ground contact).
- The face is a `face_3D` bone. The complex "ring" face (≈1 h of work) is only for hero-size heads.
- Digitigrade legs: a 3-bone chain plus foot, with the IK target at the toe (Dragonborn).
- **A prop drives the hand:** the hand is a child of the staff bone and the arm IK targets that hand, so animating the prop moves the arm.
- Secondary bones for pouches and collars. A collar is one mesh weighted along a chain of about 9 bones.
- Body and outfit are separate skin sets (`old/young × outfit-old/young`), combined at runtime (snake-man).

### creature (wing / spider / raptor)
- Joints are *siblings* under the shoulder, each with a red control bone.
- Transform constraints at 50% give half-follow.
- Spine 4.3 additive and clamped transform constraints turn hip motion into a procedural step.
- Long bodies get orange edges across every bone.
- Lip curves ride a **path constraint**, with a row of bones on the path and the lip mesh weighted to them (turtle).
- Each feather row is its own bone chain. Tail feathers splay through IK *with* high softness, which is avoided on legs.

### environment (painted background)
- One flat painting is cut into element layers, and the area each element covered is repainted.
- The elements become slots; clouds ride a path constraint.

---

## 4. What this means for our pipeline

What our rigs lack, ordered by the visible stiffness each one causes:

| Gap | Fix the animators use | Can our generator emit it? |
|---|---|---|
| Every part rigid, 100% on one bone | Meshes on bending parts + 2-bone blend bands at joints | Yes. The Spine JSON supports weighted meshes; the hard part is auto-placing vertices and weights |
| No helper pivots | hip/chest split, `face`, back_head (−100 transform), ear chains, chest-bend helper | Yes. Pure bone/constraint JSON |
| Head/shoulders inherit every torso rotation | `inheritRotation:false` on head/shoulders, `inheritScale:false` for breathing | Trivial |
| Legs are FK | 2-bone IK + stretch, target-to-foot transform | Yes |
| Root animated | `character` container under root | Trivial |
| Faces swap whole heads | Lid curve bones + closed/happy-closed swap; mouth = container + 30% scale bone + chin | Partly. Needs separated face parts, which our exploded-sheet step can provide |

### The feedback loop
The workflow above gives a clean place to capture the animator's edits:
- We emit a first-pass Spine project with our guess at pivots, helpers and meshes.
- The animator opens it in Spine and fixes it: Alt-redraws pivots, adds helpers, re-meshes, repaints weights.
- They export JSON.

A JSON diff (bones moved, bones added, weights changed, constraints added) gives one labelled correction per item. Tag each one with the same `bucket` and `stage` used in `learnings.jsonl` and it becomes training/rule data, one bucket at a time.

**Licence check first.** Meshes, weights, IK and all constraints need **Spine Professional**; Spine Essential cannot open or author them. Spine isn't installed on this machine.

### Photoshop: what the first pass did *not* cover
The second pass answered this from outside the channel (§6). None of the first 28 videos covers:
- deriving parts from a single flat master
- painting hidden areas ("overdraw")
- joint overlap padding

Arman always starts from an already-separated PSD. The useful prep tips are:
- straighten curved parts
- end joints round
- test pivots with Alt-drag
- name layers = bones
- don't over-cut (one mesh bends better than 3 pieces)
- recolour a part with Ctrl+U, and reapply the same settings to another layer with Ctrl+Alt+U

Our exploded-parts-sheet step (Nano Banana) is still the right answer for the master → parts step. These videos tell us *what the parts should look like* so an animator can rig them.

---

## 5. Shortcuts and multi-action moves

Caption-derived. Spine on Windows; on a Mac, Ctrl ≈ Cmd.

| Shortcut | What it does | Source |
|---|---|---|
| Create tool + **Ctrl+click** an image | New bone centred on that image (one step: place + size) | 9Zv 0:29 |
| Create tool + **Alt** + draw over a bone | Redraw a bone's position and rotation; children and attachments kept | _Tik 0:04, GujtD 5:16 |
| **Alt** + drag a bone tip | Lengthen a bone and push all children along its axis | wxC 8:37 |
| Select slots → **P** → click a bone | Re-parent many attachments into a bone at once | 9Zv 9:09 |
| **Ctrl** + box-select | Box-select one object type only (regions, not bones/meshes) | 9Zv 10:06 |
| **Ctrl+Shift+L** | Key everything visible. Used at both edges of a transition so before/after stay untouched | jKz 23:08 |
| **Ctrl+Shift+J** | (caption) Paste setup-pose values back into the timeline to return to idle | fsrP 27:54 |
| **Ctrl+Shift** + drag keys | Copy keyframes in the dopesheet | wxC 9:08 |
| **Ctrl+Alt** + drag keys | Offset timelines (overlap) | jKz 12:44 |
| **Shift**-click a vertex | Select the whole connected ring (also in Weights since 4.2) | Z_9 0:31, qEc 8:45 |
| **Ctrl+Shift**-click ring | Add a second ring to the selection | qEc 9:16 |
| **Ctrl+1** then **Ctrl+C / Ctrl+V** | Store a vertex selection, copy positions, restore them after a broad edit (world axis) | qEc 9:45 |
| **Shift** while drawing an edge | Disable midpoint snap / lock to horizontal or vertical | Z_9 3:19 |
| **Ctrl+B** / **Ctrl+H** | Hide all bones / show all | _Tik 5:30 |
| **Ctrl+Up** | Jump to the parent in the tree; **Alt** + expander collapses or expands the subtree | _Tik 6:02 |
| Number fields: `+30`, `*2` | Math in transform fields | _Tik 6:39 |
| **Double middle-click** a bone (4.3) | Select all its descendants | zHv 1:25 |
| Shift + scrub | Scrub the timeline to find mesh stretching between frames | cT8 6:09 |
| Photoshop **Ctrl+U** then **Ctrl+Alt+U** | Hue/Sat on one part, then reapply the same settings to another layer | Y01 4:12 |
| Photoshop **Ctrl+R**, guides | Ruler guides = Spine root point (lost when the PSD is closed; use `[origin]`) | Y01 7:11 |
| Photoshop custom hotkey for the export script | He binds Ctrl+Alt+Shift+Q to Photoshop-to-Spine | Y01 7:47 |

---

## 6. Splitting a flat master into parts

Most of the deep material on this is outside Spine. In the Live2D/VTuber community, "parts separation" of one finished illustration is a core skill: the top tutorials have 150k–730k views. The Spine and After Effects tutorials add the joint rules. Ranked by usefulness to us:

| Video | Views | What it shows |
|---|---|---|
| [Enma Akatsuki: From flat image to Live2D-ready](https://youtu.be/DiKCdwQrjig) | 246k | Exactly our case: one finished illustration → separated, completed layers |
| [chupuko: VTuber model separation guide](https://youtu.be/WGpvSTThQUU) | 149k | Exploded breakdowns of the face, sleeves and hair; the **underfill** technique |
| [Mari Yume: How to separate VTuber art for Live2D](https://youtu.be/ieiioJaznXc) | 734k | Layer naming and the eye stack |
| [Cat Athenya: Separate art for animation (game sprites)](https://youtu.be/MvglJnAL1Po) | 34k | Hair painted complete under the face; simple vs standard method for eyes and mouth |
| [Armanimation: Photoshop separating into layers](https://youtu.be/ZFToB04inQU) | 2k (stream) | Painterly art: Select and Mask, then the Clone Stamp to rebuild what was hidden |
| [Armanimation: Preparing a background for Spine](https://youtu.be/xfH7dqez5FA) | — | One flat painting → element layers, repainting what each element covered |
| [Jafar Fazel: Preparing any character for rigging (AE)](https://youtu.be/2od39YJc4zc) | 101k | Circle joint caps on flat vector limbs |
| [Anipalooza: Spine beginner guide, art prep](https://youtu.be/C4YZQbqhIHk) | 48k | Turnaround sheet, straightened copies, PhotoshopToSpine settings |
| [Kira Omori](https://youtu.be/NXx8xbBYFh4) · [Jueri Haan](https://youtu.be/rhDTAiIcyxU) · [Kappako](https://youtu.be/FS5FY_NWXSw) · [Hanacue short](https://youtu.be/-LIeTTT9PXY) | 150k–1.1M | Same discipline, more examples (queued for transcripts) |
| [Qwen-Image-Layered explained](https://youtu.be/wAjNpPMaDv0) · [in ComfyUI](https://youtu.be/4TJl7Iz2MCY) | 100k / 14k | The automatic route: one image → RGBA layers |

**The rules they agree on.** The `split-*` frames show each one.
1. **Every part is painted complete, including what was hidden.** The torso is repainted under the arms, the back hair is painted as a whole shape under the face, and the ground is repainted behind the cut-out wheel. Moving a part must never reveal a hole. The Clone Stamp works for painterly art; repainting works for clean art.
2. **Underfill.** A flat, darker copy of a part's silhouette sits under it, so a gap that opens during motion reads as shadow rather than background. This is cheap insurance, and something a generator could emit automatically.
3. **Round joint caps.** Draw a circle on each pivot (hip, knee, elbow, shoulder) and merge it into both limb ends, so the overlap stays round as the limb rotates. The same rule appears in Arman's "end joints round" tip.
4. **Split by what moves.** Face pieces: skin, outline ring, blush, hair shadow. Eye pieces: white, iris/pupil, highlight, upper lash, lower lash, lid, brow. Mouth pieces: lips, teeth, tongue, interior. Long hair is cut into segments (A/B/C) so each segment can bend. Sleeves come apart into fills and ribbons.
5. **Groups mirror the skeleton.** Head / Body (Neck, Torso, R Arm, L Arm) / Lower Body / Back Hair. Layer names become bone and slot names.
6. **Soft cuts for painterly art.** Use Select and Mask or Color Range, not a hard lasso, so the brush texture survives at the edges.
7. **Extra deliverables.** Straightened copies of curved parts, alternative views (front, three-quarter, side, back), and an outline per part where pieces overlap.

**What this means for our generator.** The exploded-parts sheet already covers rule 4. Rules 1, 2 and 3 are the ones it misses today:
- **Rule 1:** prompt each part as *complete* (occluded areas painted in).
- **Rule 2:** emit an underfill layer per part.
- **Rule 3:** check that limb ends are round around the pivot.

Qwen-Image-Layered is the automatic alternative. It was in our original plan as Option C, but it doesn't fit on the T4. These tutorials give us the acceptance checklist for whichever route produces the parts.

---

## 7. Videos read

Photoshop/import: [_1mkFeOG6RE](https://youtu.be/_1mkFeOG6RE) · [btrOAIZPWNY](https://youtu.be/btrOAIZPWNY) · [Y01o76_WfqI](https://youtu.be/Y01o76_WfqI) · [NSiQXuka5aQ](https://youtu.be/NSiQXuka5aQ) · [myur8TsuwjI](https://youtu.be/myur8TsuwjI) · [aFVV7dbFwG4](https://youtu.be/aFVV7dbFwG4) · [B7Zk1bx-tqg](https://youtu.be/B7Zk1bx-tqg)
Rig setup/animation: [9Zv-Mb7zi2U](https://youtu.be/9Zv-Mb7zi2U) · [jKzIo566gnk](https://youtu.be/jKzIo566gnk) · [GujtDSo2pvM](https://youtu.be/GujtDSo2pvM) · [8bx_bFp1QD4](https://youtu.be/8bx_bFp1QD4) · [wxC9yiYwg4c](https://youtu.be/wxC9yiYwg4c) · [H2LktmTdxGI](https://youtu.be/H2LktmTdxGI) · [zHvQ_GqJsQQ](https://youtu.be/zHvQ_GqJsQQ)
Non-human: [ByNy6OI118k](https://youtu.be/ByNy6OI118k) · [A-2rGB-1rJY](https://youtu.be/A-2rGB-1rJY) · [T_jJ6LsZiWU](https://youtu.be/T_jJ6LsZiWU) · [fsrP1TFH9N0](https://youtu.be/fsrP1TFH9N0) · [fuHw_Mys2tg](https://youtu.be/fuHw_Mys2tg) · [DQwVU3nhT4Q](https://youtu.be/DQwVU3nhT4Q)
Primitives: [_TikdZ9LCGs](https://youtu.be/_TikdZ9LCGs) · [qEc-mKRTfHY](https://youtu.be/qEc-mKRTfHY) · [Z_9Rydrxd90](https://youtu.be/Z_9Rydrxd90) · [l3HizZDk8nQ](https://youtu.be/l3HizZDk8nQ) · [WAzVsoCLZYY](https://youtu.be/WAzVsoCLZYY) · [oSWqlXwfAlE](https://youtu.be/oSWqlXwfAlE) · [cT8xcHa1ccY](https://youtu.be/cT8xcHa1ccY) · [bHWx9gwGg_c](https://youtu.be/bHWx9gwGg_c)

Second pass (stills captured; transcripts queued): [Eye rig with IK](https://youtu.be/pyjYqNMiDWo) · [Rig Explained 1](https://youtu.be/Ytu2d9MwwRE) · [2](https://youtu.be/o09Kjh8Srw4) · [3](https://youtu.be/gBvFR7Ir1Cg) · [4](https://youtu.be/p1JA9Zs8saU) · [5](https://youtu.be/vlsU3DnY_Tk) · [Dragonborn](https://youtu.be/dy5At7Qh8yI) · [Frontal rig + walk](https://youtu.be/-Bwj0fkduqI) · [Background prep](https://youtu.be/xfH7dqez5FA), plus the parts-splitting videos in §6.

Originally listed as next to read (now covered by the second pass):
- [Frontal Rigging + Walk, 1h29](https://youtu.be/-Bwj0fkduqI)
- [Rig Explained parts 1–5](https://youtu.be/Ytu2d9MwwRE)
- [Rigging Dragonborn](https://youtu.be/dy5At7Qh8yI)
- [Preparing Background in Photoshop](https://youtu.be/xfH7dqez5FA)
- [Eye rigging with IK](https://youtu.be/pyjYqNMiDWo)

**Caveats.**
- Auto-captions are noisy. The cow and rabbit streams have long silent stretches.
- `evidence: inferred` marks a rule I reconstructed from the captions rather than heard. The knee-controller recipe is the main one.
- Stills are 800×450 grabs. Tree panels were magnified before capture.
