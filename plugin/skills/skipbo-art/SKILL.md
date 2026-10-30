---
name: skipbo-art
description: Use when generating, editing or fixing SkipBo game art on the SkipBo ComfyUI server (skipbo.comfyui.liquidnitro.games) - characters, character parts, Spine rigs and skeletons, starter animations, expressions, icons, scenes, backgrounds, sketches - or when an image keeps coming back off-style, re-rolls are piling up, "no X" in a prompt keeps producing X, or a rig, animation or GIF looks broken (parts detached, limbs dangling, jerky motion).
---

# SkipBo art on ComfyUI

## Overview
The house style already exists as **reference images plus frozen style text**. Your job is to choose the right engine, paste the frozen style, describe only *this* image, and close each target in one or two passes. Most past waste came from re-describing style, writing negations for a model that can't read them, and re-rolling seeds.

Paths under `references/`, `templates/` resolve from the skill folder. Image jobs run through one stdlib-only script (macOS `python3`, Windows `py -3`):
`python3 <this-skill-dir>/scripts/comfy.py --help`. Outputs and a job ledger go to `./runs/<tag>/`. The rig, annotation and animation QA scripts (`spine_rig.py`, `rig_annotations.py`, `spine_qa.py`) need numpy and Pillow: run them with `uv run`, which installs both, or `pip install numpy pillow` first. Optional second reviewer: with `TYPESAFE_API_KEY` set (environment or `~/.config/typesafe/typesafe.env`), `scripts/jev_qa.py` reviews a built rig beside `spine_qa` and `rig_annotations.py check --jev` checks hand pieces' palm/back with Jev; without a key both say SKIP and go on. `scripts/joint_crops.py` (no key needed) puts the rig and the master side by side at every joint.

## Routing (decide before writing a word)

| Asset | Template | Style source |
|---|---|---|
| Character, or character → Spine parts and skeleton | `spine-parts` (whole chain, 5 calls) or `nb-pro` per stage (master, body, hands, poses, face sheets), then annotate and confirm the parts with `scripts/rig_annotations.py` (propose, check, confirm), then `scripts/spine_rig.py --annotations … [--props props.json]` (`--name` defaults to its character; props add `jump_hurdle` and `wave_flag`, garden props with `use` add `plant_seed`, `water` and `grow_<n>` with events `seed` / `pour`), then `scripts/spine_qa.py` (optionally `scripts/jev_qa.py`) | `references/styles/blocks-characters/` + `references/spine-parts.md` |
| Character that arrives as a layered PSD (parts already cut and placed by an artist) → Spine rig and starter animations | No generation: `scripts/psd_rig.py --list <psd>` to see the layers, a `<name>.psdrig.json` mapping layer → part/bone (tools `"tool": true`; missing tools under `extra_tools`, painted with `nb-pro` using the PSD's own tools as style refs), then `scripts/psd_rig.py <cfg> --out rig/` (idle, cheer, talk, one animation per tool, keyed at the poses with Bezier curves), then `scripts/spine_qa.py rig/<name>.json --master rig/master.png`. Seams FAIL on hand-painted outlines is expected; look at the GIFs | the PSD itself |
| Key poses of an approved master (what a new animation must reach, before rigging it) | `keyposes` (3 key frames: master + optional prop; `references/prompts/spine/keypose.txt`). Measure drops ("the belt half as high") or the knees stay straight | `experiments/2026-10-16-keypose-refs/README.md` |
| Bent-knee moves on a rig (squat, tucked jump): whole-legs drawings | `nb-pro` per movement with `legs-inbetweens.txt` (master + key pose + `scripts/rig_rest_legs.py` rest legs), `legs-midpoint.txt` for big steps, then rebuild: the `legs` role swaps them by progress with cross-fades | `references/spine-parts.md` stage 3d |
| Talking (lip sync) | Not in the skill yet: Kokoro phoneme timing, one mouth sheet, a `mouth_patch` slot and `talk_<line>` on track 1 | `experiments/2026-10-17-lip-sync/README.md` |
| Final colour scene / background | `nb-pro` (9:16, 4K) | `references/styles/lr-render/` |
| Pencil concept sketch | `nb-pro` (4:3) | `references/styles/ls-sketch/` |
| Restyle or recolour an existing image | `nb-pro`, image_1 = source, TEMP 0.35–0.6 | the style that image should end in |
| Small local fix on an approved image | `zimage-inpaint` (transparent pixels = repaint), DENOISE 0.5–0.75 | — |
| Item icon | `zimage-t2i`, `--n 2` | `references/styles/icon/block-zimage.md` (subject first, then the block) |
| Cut out / split a sheet into parts | `cutout` / `parts-split` | — |

Engine grammar: `references/engines.md`. **Z-Image (zimage-*) reads no negations: "no X" draws X.** Nano Banana (nb-*) follows instructions and image roles.

## Every job
1. Write 3–6 acceptance criteria; pass them as `--criteria`.
2. Nano Banana prompt = `IMAGE ROLES` (one line per wired image) → style block **verbatim** → the subject → `FINAL CHECK` (≤ 6 items). Describe the target, never past attempts.
3. `comfy.py run <template> --prompt-file p.txt --image 1=… --tag <asset> [--n 2]`. Lint and the seed cap run automatically; don't `--force` past them.
4. Show the user the outputs (contact sheet: `comfy.py sheet runs/<tag>`), ask for keep-numbers plus one sentence per rejection.
5. Fix by changing words, mask, reference or denoise. Never a third seed of the same prompt.

## Common mistakes
| Mistake | Fix |
|---|---|
| "no text, no shadow, not pink" in a Z-Image prompt | Describe what fills the slot: "plain flat #E8EEF4 background", "tan muzzle" |
| Re-describing the style in your own adjectives | Paste the block file verbatim and wire its refs |
| "The last attempt was wrong because…" in a brief | Rewrite the brief as the target |
| Mentioning IMAGE 2 with only image_1 wired | Wire it or delete the sentence (lint catches this) |
| Generating eyes/mouths/limbs one by one from text | Parts come from one approved master: `references/spine-parts.md` |
| Cutting arms, legs or hips out of the master for the rig | Generate them (body sheet v2) plus hand/pose variants; cut-outs leave flat seams that look glued on when a limb moves |
| One drawing per hand, rotated into every pose | Hands sheet (open, fist, point, thumbs-up, grip) swapped in by the animation, like the expression heads |
| Naming, mirroring or turning parts by hand in a prep script | Annotate and confirm: `rig_annotations.py propose` / `check` / `confirm`. `normalise` derives names, mirrors and rotations, and the thumb rule picks each hand's mirror |
| Building a rig from `proposed` annotations | Confirm at the checkpoints first (master, each sheet, rig review). `spine_rig.py` refuses `proposed`; `--allow-proposed` is for experiments only (it prints a WARNING listing them) |
| Renaming a hand `paw` or the torso `body` in the annotations | Torso, hips, upperarm, forearm, arm, hand, leg and head keep their role as name (validation refuses others); feet, hats, tails, neckwear and props take any name, and their role sets the layer and parent |
| Calling the rig reviewed without `tools/render_frames.py` | Outside the repo, show `rig/qa/<anim>_strip.png`, `rig/qa/<anim>.gif` and `rig/qa/setup_vs_master.png` at checkpoint 6; everywhere, the joints, onion and motion sheets `rig/qa/{joints,onion,motion}.png` (`scripts/joint_crops.py`) and, when it ran, the `jev_qa.py` summary |
| Generic part lists ("head items") | Name every piece for this character, row by row |
| Fist and point painted back-facing (the sheet's default every time so far) | Ask for them palm-facing in `HANDS`; re-roll just that pose with `hands-fist-palm.txt` / `hands-point-palm.txt`. A raised back fist shows its back in cheer_jump |
| Trusting setup IoU (0.88+) for proportions | Look at `rig/qa/onion.png`: too-wide trousers, thin sleeves and boots 30 px out all passed every check on the beaver |
| Gating a rig on one Jev score ("P(matches master) < 0.5") | Approved rigs score that low too. Compare: `jev_qa.py --ref <approved rigs> --prev <last build>`. Only a point or thumbs-up hold without its thumb up FAILs; the rest is WARN or a ranked list to look at |
| Asking Jev "palm or back?" or "which hand?" | At chance. `check --jev` scores visible cues (`jev_facing.py`, AUROC 0.89); which hand comes from anatomy in code |
| Tuning bones for a pose the rig has no drawing for (a squat on a knee-less trousers piece) | Paint the key poses first (`keyposes`), compare the rig against them, and add the missing drawings (whole-legs crouch / tuck) as swaps |
| Calling a rig/animation "working" from one still frame | `scripts/spine_qa.py` must PASS, then inspect a full-size frame grid or the GIF |
| Approving a master for rigging by eye only | `scripts/spine_qa.py --contract <master>.png` first, then check colour contrast and head direction by eye |
| Retrying a job that failed with GPU out-of-memory | Nothing to do: the shared T4 is busy and `comfy.py` already retries 3 times |
| Acting on a wordless screenshot | Ask one question: what's wrong, and what's already fine? |
| A long two-handed tool (shovel, rake, broom) in one paw, waved about | Both paws on the handle, solved with IK (`psd_rig.Kin.reach`), the lower paw drawn in front of the body; the action reads as the real job: stab into the ground, pry, scoop, toss the dirt onto a pile (`props`: dirt mound + clod) |
| A tool action that is just the arm waving (no hand choice, no body, no face) | Put the tool in the hand the brief names (`tool_hands` in the psdrig config; the wrench defaults to the character's right, picture left, on the `tool_r` grip) and draw that paw in front of the body. Anticipate first (rise, ease the tool back, breathe in), then bend and dip the torso into the effort, then release; the face acts it: brows down, eyes squeezed shut, jaw clenched, eyes on the work (`psd_rig.WRENCH`) |
| A held tool tucked in front of the belly | Pose it the way the artist does: the arm reaches out to the side, the fist grips a wrench by its middle with a jaw either side and the paw over it, the tool nearly level (`WRENCH_BOLT` out at the side so IK straightens the arm). When the brief says "right hand", it means the character's own right; if a repeat of the same note arrives, ask for a screenshot of the pose rather than guessing again |
| A key on every frame (baked motion) | Key only the poses, with Spine Bezier curves between them (`psd_rig.bake`); add a key only where the curve would drift (a throw). Animators edit these by hand: a dopesheet full of keys can't be touched. `spine_qa.py` reads Bezier curves, so QA still matches the player |
| Holding a long tool steep in front of a short-armed cartoon body | Hold it low and flat (~40°, as the artist painted it), both paws at mid-chest, the blade out to the side; steep, the top paw lands at the mouth and the arms cross the face |

## When the user corrects you
Every correction becomes a rule here so it never needs saying twice: fix the job, then add or sharpen a row in "Common mistakes" (or the matching reference, prompt or script), log one line in `FEEDBACK.md`, bump the patch version in `.claude-plugin/plugin.json`, and commit and push the repo clone (never the plugin cache).
