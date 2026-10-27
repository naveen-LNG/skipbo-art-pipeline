# Experiment 2026-10-11: Moose → Spine parts in the shipped Blocks style

**Question:** given a character reference, can the server produce rig-ready parts that are (a) in the shipped Blocks style and (b) consistent with each other?
**Answer:** yes. Deliverable: [`moose-spine-v1/`](moose-spine-v1/).

| | |
|---|---|
| Design input | `references/characters/moose/moose_turn_00006_.png` (the old off-style turnaround) |
| Style input | shipped Hippo + Raccoon atlases (`references/style-refs/blocks-characters/`) |
| Output | master + 20 body parts + 9 expression heads, transparent PNGs |
| Proof of consistency | [`moose-spine-v1/assembly-check.png`](moose-spine-v1/assembly-check.png): the parts reassembled (right) beside the master (left), at one scale |
| Cost of the whole exploration | 17 Nano Banana Pro calls (18 images), ~35 cheap split/scale/cut-out jobs, 0 Z-Image jobs |
| Cost per new character from here | 3 Nano Banana Pro calls (+1–2 if the master needs a second pass), ~2–4 minutes |

## What was tried, in order

| Step | Run tag | Result | Lesson |
|---|---|---|---|
| Restyle the design into a Blocks master, 2 variants | `moose-master` | Both on-style first time; variant 01 had arms clear of the body | Image roles + verbatim style block + shipped atlases as style refs is enough |
| Body sheet, Moose-specific list | `moose-body-sheet` (1st) | 16 pieces: sleeves and legs merged | Ask for the cut explicitly ("each arm in THREE pieces") |
| Face sheet (separate features) | `moose-face-sheet` | 12 clean pieces | — |
| Split server-side: rembg → MaskToSEGS | `split-test-face` | 1 piece | `drop_size` is a min width *and* height; 400 dropped everything |
| … `drop_size 20` | `split-test-face` | 12 + 2 junk | A faint fringe on the image border forms a giant contour → threshold the mask |
| Decompose SEGS + JoinImageWithAlpha | `split2-face` | Inverted alpha | `JoinImageWithAlpha` expects ComfyUI's inverted mask |
| Soft alpha × segment mask | `split3-face`, `split3-body` | Clean parts, soft edges | Final `parts-split` template |
| Body sheet, explicit rows + "THREE pieces" | `moose-body-sheet` (2nd) | Exactly 20 | — |
| Full chain with *generic* prompts | `e2e-moose` | 23 body / 15 face; ghosts | Feeding a generated sheet back in as a reference creates faint ghost copies |
| Generic v2 | `e2e-moose-v2` | 18 body: one antler, trousers whole | Generic categories don't bind → PIECES list per character |
| PIECES slot + precise face list | `v3-body`, `v3-face`, `e2e-moose-v3` | 20 + 13, twice | Final body-sheet prompt |
| Face features fit check | `moose-spine-v1/_superseded-face-features/face-fit-check.png` | Features ~2× too large | Nano Banana won't hold exact relative sizes between separate pieces |
| "Measure against image_1" wording | `v4-face` | Still too large | Wording doesn't fix it |
| **Whole-face expression heads** | `v5-face-heads` | 9 identical heads (596–600 px), master proportions | Final face-sheet prompt; scale by width to `head_base` |

## Spine skeleton (added later the same day)
`scripts/spine_rig.py` places every part on the master by masked colour matching. Each part is restricted to its body-layout band; forearms are searched between the upper arm and the hand. It then fixes left/right, derives pivots and writes a Spine 4.2 rig: [`moose-spine-v1/rig/`](moose-spine-v1/rig/README.md). The rig loads in the official Spine web player, and the idle, blink, wave and emotions animations play.

Matcher problems hit and fixed along the way:
- Cream sleeves matched the light-grey background → added a background penalty.
- A "claimed pixels" penalty pushed the scarf and bell off the body → replaced with layout bands.
- The `ear` pattern matched "forearm" → part roles now match whole name tokens.
- A cache-busting query string made the web player read the JSON as binary.

## Rig v2: what was wrong with v1, and how it's checked now
The v1 rig was reported as working after a single still frame of the wave. It wasn't. The user saw the waving forearm hanging off the arm, the hands not joined to the sleeves, and the motion snapping at keyframes. The causes:
- Pivots were guessed from part outlines, and some ended up on the wrong end (reversed forearm and hoof bones).
- The generated sleeve pieces were each almost a full arm long, so they overlapped and didn't line up.
- The wave used sparse linear keys.

v2 changes:
- Limbs and hips are cut from the master with round joint caps.
- Pivots are true joints.
- Animations use eased target angles keyed every frame.
- `scripts/spine_qa.py` renders every frame and gates on structure, attachment, stitching, joint holes, smoothness and the setup-pose match.

Two defects that passed the metrics were then found by inspecting the frames by eye: a sliver of vest riding on the upper arm, and faint fringe lines. Both were fixed, and a stray-pixel check was added that catches them. v1 failed these checks: reversed or off-joint pivots, the upper arm's stitching overlap dropping to 0, and velocity jumps of 12–16°/frame. v2 passes all of them.

## Known limitations
- Bright, pale parts (the cream brows in the superseded set) can keep a faint grey halo from BEN2.
- 2K sheets give parts of roughly 120–600 px. Use `SIZE=4K` if the rig needs more resolution.
- The texture inside each round joint cap rotates with its limb (invisible on these plain sleeves).
- The rig needs colour contrast at every cut (sleeve vs vest, hand vs sleeve, hoof vs trouser). A character with bare arms in body colour would need a different wrist and shoulder cut.
- The starter `wave` is the only gesture; other actions need hand-animating in Spine.
