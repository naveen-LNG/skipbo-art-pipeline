# Plan: generating characters as rig-ready parts for Spine

Status: **superseded by results.** See [`experiments/2026-10-11-moose-parts/README.md`](../experiments/2026-10-11-moose-parts/README.md) and the skill reference `plugin/skills/skipbo-art/references/spine-parts.md`. Option A (exploded parts sheet) won; faces became whole-face expression heads. This page keeps the rig-structure analysis of the screenshots.

## What the reference screenshots show

The screenshots in [`../references/rigging-examples/`](../references/rigging-examples/) come from a commercial 2D cartoon rig pack. They are references for *structure*, not for style.

| File | What it teaches |
|---|---|
| `01-control-points-labelled` | Control set: head, neck, shoulders, left/right arm, left/right hand, pelvis, left/right leg, left/right shoe. That is 13 controls on a front-view character |
| `02-bone-skeleton-overlay` | The bone chain under the art: spine, then neck/head; shoulder, upper arm, forearm, hand; hip, thigh, shin, foot. Arms are held away from the body |
| `03-modifier-groups` | Three control families: face, body, arms and legs |
| `04-bone-chains` | Simple two-segment limbs with a mid joint (elbow, knee) and an end effector, which is what Spine IK constraints need |
| `05-face-expression-slots` | The face is a swappable **slot** with up to 15 expressions (eyes, brows and mouth change together) |
| `06-hand-pose-library` | Hands are swappable attachments: fist, one point, two point, thumb up, flat (43 hands and props) |
| `07`, `09`–`11` | Poses built from those parts: wave, akimbo, bow, cheer, salute, jump, lean |
| `08-rigged-cast-lineup` | One construction method across a varied cast: slim tube limbs, separate hands and a clean head–neck seam |

What makes those characters easy to rig, and therefore what our prompts must ask for:

1. **Neutral rest pose:** front view, arms in a relaxed A-pose with clear background between arm and torso, legs slightly apart, feet flat.
2. **Simple joints:** limbs that are tube-like, or have a sleeve or cuff where they meet, so a rotating segment never shows a seam.
3. **Separable face:** the facial features sit on a fairly plain face area, so eyes, brows and mouth can be swapped as flat layers.
4. **Hands as separate units** at the wrist, so a hand library can be drawn once and swapped in.
5. **No baked cast shadows** on the body. The ground shadow is its own part.

## Required part list (one character)

Naming is `<char>_<part>[_<side>][_<variant>].png`, all on one shared canvas size so positions line up on import.

| Group | Parts | Notes |
|---|---|---|
| Body | `torso`, `pelvis`, `neck`, `head`, `hair_back`/`hair_front` or `antler_l`/`antler_r`, `tail` | The torso is drawn complete under where the arms attach; the neck extends up under the head |
| Arms ×2 | `upperarm`, `forearm`, `hand_<pose>` | Round overlap ends at the shoulder and elbow; hand poses: open, fist, point, thumb_up, hold |
| Legs ×2 | `thigh`, `shin`, `foot` | Round overlap ends at the hip and knee |
| Face | `eye_l/r_<open\|half\|closed>`, `pupil_l/r`, `brow_l/r_<neutral\|up\|angry>`, `mouth_<neutral\|smile\|open\|O\|E\|frown>`, `blush` | Drawn on the face base of the master, at master scale |
| Extras | `shadow`, props (`watch`, `lantern`…) | — |

For a 3/4-view rig, the near and far limbs are drawn separately, so there are two of each limb.

## Pipeline (what the skill will run)

1. **Master.** Nano Banana Pro, with the approved style refs plus the character's design refs. Front view, A-pose, flat plain background, 2K. Review against the acceptance list, then lock it.
2. **Expression and hand sheets.** Nano Banana Pro with the master as `image_1`: "the same face at the same scale, N expressions in a grid". Done the same way for hands. This replaces the 30+ separate face-patch inpaints that drifted last time.
3. **Part separation.** Choose by testing which is cleanest:
   - **A, exploded parts sheet:** Nano Banana redraws the master as its separated parts laid out on a grid, with the hidden areas completed and overlaps rounded. It's one call and the model infers the occluded shapes.
   - **B, segment and complete:** SAM masks on the master → cut each part → Z-Image masked inpaint (denoise 0.5–0.7) to extend each part under its neighbour.
   - **C, layer decomposition:** Qwen-Image-Layered. The node exists on the server but the model isn't installed and probably won't fit on a 16 GB T4.
4. **Cut-outs.** Run `easy imageRemBg` with BEN2 or RMBG-2.0 (compare these against the RMBG-1.4 used so far), then trim, rename and save positions.
5. **Spine import.** Write a Spine skeleton JSON directly: one bone per part, with pivots at the joints (shoulder, elbow, wrist, hip, knee, ankle, neck), slots in draw order, and skins/attachments for face and hand variants. Alternatively, build a layered PSD for Spine's Photoshop import.

## Open questions

1. Which Spine version (4.1 or 4.2), and do the rigs use meshes or only rigid parts?
2. Front view only, or front and 3/4?
3. Which characters come first: the Moose host, then the four-character lineup?
4. Where are the shipped Blocks characters to match? This is the same question as in `agent-integration-plan.md`.
