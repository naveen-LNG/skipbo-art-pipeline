# SkipBo art pipeline (ComfyUI + agents)

Goal: anyone on the team can generate SkipBo images **in the project's art style on the first or second pass**, from Claude Code or another agent, on macOS or Windows, and get **rig-ready parts for Spine**.

Server: `https://skipbo.comfyui.liquidnitro.games` (ComfyUI 0.18.2, one T4). Details are in [`docs/server.md`](docs/server.md).

## Install the skill (Claude Code, macOS or Windows)

From a clone of this folder:

```bash
claude plugin marketplace add ./
```

```bash
claude plugin install skipbo-art@skipbo-tools
```

Then just ask, for example "make Spine parts for this character" or "an icon for Honey Dew Mushroom Pot". The skill drives `plugin/skills/skipbo-art/scripts/comfy.py`, which needs Python 3.9+ (`python3` on macOS, `py -3` on Windows) and nothing else. The Spine scripts `spine_rig.py`, `rig_annotations.py` and `spine_qa.py` also need numpy and Pillow: `uv run` installs them automatically; otherwise `pip install numpy pillow`. Optional environment variables: `COMFY_URL`, `COMFY_USER`, `COMFY_RUNS_DIR`, and `TYPESAFE_API_KEY` for the optional Jev review steps (also read from `~/.config/typesafe/typesafe.env`; without it they skip).

Without an agent: open **SKIPBO - Character to Spine parts (Nano Banana Pro)** in the ComfyUI web UI. Its how-to note is on the canvas.

## Layout

```text
comfy/
├── plugin/                       the shareable Claude Code plugin (marketplace: .claude-plugin/)
│   └── skills/skipbo-art/
│       ├── SKILL.md              routing table, per-job loop, common mistakes
│       ├── scripts/comfy.py      CLI: status, lint, run, sheet, size, scale, fetch (stdlib only)
│       ├── scripts/spine_rig.py  parts + master (+ confirmed annotations) → Spine 4.2 skeleton/atlas/preview (numpy + pillow)
│       ├── scripts/spine_qa.py   frame-by-frame animation QA, master contract check
│       ├── scripts/rig_annotations.py  annotate pieces and the master: propose, check (snap, normalise, overlays), confirm
│       ├── scripts/joint_crops.py  rig and master pixel-aligned, cropped at every joint (contact sheet for review)
│       ├── scripts/jev_{qa,facing,hands,client}.py  optional Jev (TypeSafe) review beside spine_qa: joints and frames against approved rigs, gesture holds, palm/back of hand pieces
│       ├── scripts/rig_{snap,hands,place,overlay}.py  helpers: point snapping, thumb/mirror rule, placement from joints, overlay pictures
│       ├── scripts/rig_worn.py   worn items: a boot cut at its ankle opening into a back part and a shell
│       ├── scripts/rig_mesh.py   whole-sleeve weighted meshes: strip, width fit, fold-free elbow weights
│       ├── scripts/rig_{roles,image,match}.py  spine_rig basics: part roles and layers, image cleaning, colour matching
│       ├── scripts/rig_{frame,pieces,colours,chain,cut,bones}.py  spine_rig placement: full-res frame, piece moves, colour classes, generated limbs, --cut-from-master, pivots and bones
│       ├── scripts/rig_{slots,variants,anim,sleeves,output}.py  spine_rig stages: slots and draw order, variants, animations, sleeve meshes, JSON/atlas/preview output
│       ├── scripts/rig_props.py  props not in the master (a held flag, a hurdle, garden props): own bones, hidden at rest
│       ├── scripts/rig_{trousers,shaft}.py  one-piece trousers (`leg: in_hips`) and the hidden boot shaft for leg-less feet
│       ├── scripts/rig_rest_legs.py  the rig's own rest legs on grey, the reference for a whole-legs sheet
│       ├── templates/            API graphs: nb-pro, nb2-flash, zimage-t2i/img2img/inpaint, cutout, parts-split, spine-parts, keyposes
│       └── references/           engines.md, spine-parts.md, styles/<style>/{block.md,refs/}, prompts/spine/*.txt, characters/*.md
├── workflows/                    snapshot of the server workflows (+ new/ for the one we added)
├── prompts/                      the original default prompts split into style blocks and examples
├── references/                   style refs, shipped Blocks atlases, rig screenshots, usage reports, job history
├── experiments/                  dated experiments with their runs and results
│   ├── 2026-10-11-moose-parts/   character → Spine parts: what worked, what didn't, deliverable
│   └── …                         one dated folder per experiment, each with a README (the Status list links them)
├── tests/                        pytest suite for the rig scripts (synthetic characters): `uv run --with pytest --with numpy --with pillow pytest tests`
├── docs/                         server facts, prompt-efficiency rules, design notes
└── tools/
    ├── comfy_snapshot.py         read-only sync of workflows, input images and job history
    ├── build_spine_workflow.py   builds the Spine-parts template and the server workflow from one definition
    ├── build_keypose_workflow.py builds the key-poses template and the "Master key poses" server workflow
    └── render_frames.py          labelled grid of chosen rig frames, for checking poses by eye
```

## Five things to know before generating anything

1. **There are two engines and they need different prompts.** Z-Image (local, cfg 1) reads text as a description, so `no X` *adds* X. Nano Banana Pro follows instructions and uses reference images by role. See `plugin/skills/skipbo-art/references/engines.md`.
2. **Style is frozen text plus reference images.** Characters use the shipped Blocks atlases (`styles/blocks-characters`); scenes use LR render; sketches use LS. Paste the block verbatim and don't re-describe the style.
3. **Most of the past cost was retries:** 65% of generations, mostly seed re-rolls. The CLI caps identical re-runs at two and lints prompts before sending ([`docs/prompt-efficiency.md`](docs/prompt-efficiency.md)).
4. **Build parts from one master,** with every piece named for that character. Every rig piece is generated art with round joint ends; the master is only the placement reference. Faces are whole-face expression heads; hands, raised sleeves, tiptoe feet and tails are swappable pose variants. No rig or animation counts as done until `spine_qa.py` passes and someone has looked at the frames (`tools/render_frames.py`) ([experiment](experiments/2026-10-11-part-variants/README.md)).
5. **The server has no auth.** You're raising that separately ([`docs/server.md`](docs/server.md#security)).

## Status

- [x] Snapshot of the workflows, default prompts, refs and history (2026-10-11)
- [x] Audit of the prompts and the past usage
- [x] Blocks character style pack from the shipped Hippo/Raccoon atlases
- [x] CLI + templates + skill + plugin manifest
- [x] Character → Spine parts: proven on the Moose and published as a new server workflow
- [x] Spine skeleton with true joints, expression-head swaps and starter animations (`scripts/spine_rig.py`, v2)
- [x] Frame-by-frame animation QA (`scripts/spine_qa.py`) plus a master-contract checker; the Moose and Fox rigs pass every check and spot-checks match the Spine 4.2 web player
- [x] Second character (Fox, with a tail) through the whole pipeline, plus a `cheer_jump` animation ([experiment](experiments/2026-10-11-fox-parts/README.md))
- [x] Generated parts and pose variants instead of master cut-outs (hands ×5 poses, raised sleeve, tiptoe, tail up), new `thumbs_up`/`point`/`hold_card` animations; Fox and Moose pass all QA ([experiment](experiments/2026-10-11-part-variants/README.md))
- [x] Hands and poses sheets in the `spine-parts` template and server workflow (5 Nano Banana Pro calls), published to the server 2026-10-11
- [x] Rig annotations with confirmation checkpoints: the agent annotates the master and every part, the user confirms, `spine_rig.py --annotations` places from joints; new QA checks `thumbs`, `sockets`, `landmarks`, `seams` ([design](docs/superpowers/specs/2026-10-11-rig-annotations-design.md))
- [x] Rigs built from user-confirmed annotations: checkpoints in the skill, worn boots, anatomical hand mirroring, weighted-mesh sleeves; fox and moose approved, all 15 QA checks pass, with 6 new ones: `thumbs`, `sockets`, `landmarks`, `seams`, `layer_order`, `mesh_fold` ([experiment](experiments/2026-10-11-rig-annotations/README.md))
- [x] Third character from text only (Beaver), all 15 QA checks pass; Jev joint review against the master and approved rigs, palm/back from visual cues (AUROC 0.89); Jev (TypeSafe) judges hand direction and pose: finger and thumb direction, "thumb up" at holds (AUROC 0.99) and mirrored hands via the anatomy rule (TPR 0.91, FPR 0.07), while palm/back asked directly stays at chance ([experiment](experiments/2026-10-15-beaver-jev-hands/README.md))
- [x] Body moves for every rig: `walk`, `run`, `squat`, plus `jump_hurdle` and `wave_flag` with props (`--props`); fox, moose and beaver pass all 20 QA checks
- [x] Pipeline fixes from three new characters (bear, rabbit, red panda): one-piece trousers (`leg: in_hips`, `rig_trousers.py`), a hidden boot shaft for leg-less feet (`rig_shaft.py`), the keyable contract and `scale_disagree` checks ([fixes](experiments/2026-10-16-cast/PIPELINE_FIXES.md))
- [x] Garden moves: props with `use` add `plant_seed`, `water` and `grow_<n>` (a plant growing on track 1) ([experiment](experiments/2026-10-16-garden-grow/README.md))
- [x] Lip sync: Kokoro's per-phoneme durations drive a `mouth_patch` slot, `talk_<line>` on track 1 over any body move; experiment scripts only, not in the skill yet ([experiment](experiments/2026-10-17-lip-sync/README.md))
- [x] Key poses of an approved master: the `keyposes` template and the **SKIPBO - Master key poses** server workflow, the targets a new animation must reach ([experiment](experiments/2026-10-16-keypose-refs/README.md))
- [x] Whole-legs pose variants for squats and jumps: painted legs sheets (`legs-inbetweens.txt`, `legs-midpoint.txt`), the `legs` role, swaps by progress with cross-fades ([experiment](experiments/2026-10-16-legs-variants/README.md))
- [ ] Legs drawings hold 2–3 frames each (about 10–12 fps against the body's 30). Finer in-betweens and bones stitched onto the drawings were tried and rejected (parked branches `claude/legs-more-inbetweens`, `claude/legs-variants-smooth`)
- [ ] Positive-only rewrite of the icon style block (Z-Image), tested
- [ ] Windows smoke test of `comfy.py` on a real Windows machine
