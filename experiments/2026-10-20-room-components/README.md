# Room components: the makeover room built from standalone assets

A variation beside [`2026-10-16-room-renovate`](../2026-10-16-room-renovate/), not an edit of it. That experiment
builds the room **subtractively**: one in-place Nano Banana edit per fixable item, then a diff against the base cut
into a layer. This one builds the same room **additively**: each fitting is painted on its own, alone on flat grey,
as a standalone transparent asset that drops into a fixed box.

Play it: `python3 -m http.server 8771 --directory experiments/2026-10-20-room-components/game` (or the
`room-components` entry in `.claude/launch.json`), then open http://localhost:8771.

## Why vary the method at all

`Blocks_scene_progression_rules.md` §12 measured where the subtractive method breaks, and it breaks on classes, not
on individual props: **the hero**, **a large structure**, **a large flat ground element** each survive a bulk removal
and need their own blunt hop; and **a strung decoration** cannot be removed by any prompt in either direction — the
only remedy is to put it mid-ladder so an automatic hop catches it. §11.3 adds that the completed base must already
*contain* a distributed arrangement, "because the subtractive method can only reveal an arrangement the base already
has."

That last sentence is the whole case for components. An edit can only rearrange pixels the room already has, so:

- it can never introduce an object the room never contained, and
- every one of §12's four classes is a property of *removal*, which a component never performs.

A component has to earn something else instead: **the match**. A sofa painted in isolation does not sit in the
room's camera. So the prompt spends its words on exactly five things — the room's camera and eye level, the
component's own vanishing direction, its measured footprint in the frame, the room's single light direction, and the
LR style block — and nothing on what the object is beyond one sentence.

## What was built

| | |
|---|---|
| `tools/build_components_workflow.py` | builds the workflow, `--publish` saves it to the server |
| `plugin/skills/skipbo-art/templates/components.api.json` | API format, 28 nodes, used by `comfy.py run components` |
| `workflows/new/SKIPBO - Room components (Nano Banana Pro).json` | UI format for the site, 29 nodes / 27 links |
| `plugin/skills/skipbo-art/references/prompts/components.txt` | the prompt, 2522 words, 5 slots |
| `tools/test_components_workflow.py` | checks the graph's concat chain rebuilds `components.txt` exactly |
| `prompts/room.txt` | the room paragraph, written once and reused for every component |
| `prompts/items.tsv` | per item: component, perspective, placement, check |
| `scripts/gen_components.sh` | seven parallel Nano Banana Pro calls |
| `scripts/compose.py` | components → layers, `out/final.png`, `out/strip.png`, `out/sequence.gif` |
| `scripts/compare.py` | `out/compare.png`: v1 cut-out vs v2 component vs v2 in the room |

The graph is `LoadImage ×3 → (prompt concat chain) → NanoBananaAIO → SaveImage (flat) → easy imageRemBg → SaveImage
(transparent)`. Both saves are kept on purpose: the flat render is the only way to see what the matte ate.

### The style block

`components.txt` carries the LR render block from `references/styles/lr-render/block.md` **verbatim**, minus its five
scene-composition paragraphs: `FRAME AND EYE LEVEL`, `THE THREE BANDS`, `SIDE FRAMING`, `SAFE AREAS`, `GROUPING`.
Those place things inside a 9:16 scene; here one object fills the frame and image_1 fixes the camera, so keeping them
would have fought the brief. No sentence was reworded — the file is assembled by splitting the block on blank lines
and dropping those five, so a future edit to `block.md` flows straight through.

### The seventh component: a television

The user asked for a TV specifically, and it is the sharpest test available: **the before-room contains no
television at all**, so the v1 in-place-edit method structurally cannot produce one. Its box is
`x 1020, y 2360, w 480, h 360`.

Why there. The six item boxes cover 85.7% of the frame, and against the bounding boxes alone the only free rectangle
of any size is (0, 0, 591, 495) — ceiling. Measured instead against the *painted silhouettes* of the five object
layers plus the rug, the largest free region below the ceiling band is the near-foreground floor,
**(0, 2413, 1536, 339)**, the full width of the frame in front of the rug. The TV box is the right-hand half of that
region, pushed 53 px up into the rug bounding box's empty corner; the whole 480 × 360 rectangle was checked pixel by
pixel and contains no paint from any of the six items. In the before-room it holds only the tipped bucket and the
plaster lumps, which the `mess` component clears. It is also the right place in game terms: it faces the sofa across
the rug, and foreground scale makes the screen legible.

It overlaps the `mess` box, and that is not a collision: `mess` is the floor plane, and v1's own layout already nests
`rug` **entirely inside** `mess` for the same reason. Things stand on the floor.

## Call count

**0 of the 15–25 nb-pro budget was spent.** The GPU server was unreachable for the whole session.

```
$ curl -sv https://skipbo.comfyui.liquidnitro.games/system_stats
* Established connection ... port 443
* schannel: remote party requests renegotiation
* schannel: SSL/TLS connection renegotiated
* Empty reply from server
```

TLS completes, then the backend returns nothing — `000` on every endpoint, from `comfy.py status`, curl and
PowerShell alike, with and without the sandbox, and on ports 80 / 8080 / 8188 / 8189 / 3000 direct to 13.202.244.80.
Polled every 45 s for the length of the session: never once answered. Nothing about this is fixable from here.

## What that means for each deliverable

| Deliverable | State |
|---|---|
| The workflow builder, prompt, templates, test | built and run; the UI workflow is on disk |
| `--publish` to the server | **not done** — the server is down |
| The seven components | **not generated** — the server is down |
| The experiment, the playable fork, the launch entry | built; the page loads, plays and swaps correctly |
| `out/sequence.gif`, `out/strip.png`, `out/final.png` | rendered, **from v1's layers**, stamped as such on every frame |
| `out/compare.png` | rendered; the v1 column is filled, the v2 column says "not generated" |
| The per-item v1-vs-v2 verdict | **cannot be given** — there is no v2 art to look at |

The `out/` renders are the pipeline proving itself on the only art that exists. Every frame carries a red footer
saying so, and `layout.json` records `"source": "v1"`, which the page prints as "Living room (v1 art)". The moment
the server answers:

```sh
experiments/2026-10-20-room-components/scripts/gen_components.sh            # 7 calls
uv run experiments/2026-10-20-room-components/scripts/compose.py           # --source v2 is the default
uv run experiments/2026-10-20-room-components/scripts/compare.py
python tools/build_components_workflow.py --publish
```

### Schemas while the server is down

`to_ui` needs `/object_info`, so the UI workflow could not be built either. `tools/.object_info.json` was
reconstructed by hand from the two already-published workflows and is **checked**: rebuilding the keypose workflow
from it and diffing against `workflows/new/SKIPBO - Master key poses (Nano Banana Pro).json` gives an identical
file — every node field, every link, every widget value. Two real errors surfaced that way and were fixed
(`NanoBananaAIO` has three outputs named `images / thinking / grounding_sources`, not two). `easy imageRemBg`'s three
widgets after `save_prefix` are stored by value only; their names are unknown and do not reach the JSON.
`schemas_for()` asks the server first and overwrites the cache whenever it answers, so the hand-made seed cannot
outlive the outage.

## What v1's layers turn out to be — found while building the control

`out/compare.png` shows the v1 cut-outs on a checkerboard, which the v1 experiment never did, and they are **diff
masks, not objects**:

- **fireplace** — a tall sliver. The unchanged stone of the chimney breast was never cut, because it never differed
  from the base. It only reads as a fireplace when laid back over its own base pixels.
- **mess** — a ragged blob of floor, shaped like the rubbish that was removed.
- **lamp** — carries a halo of the wall's cobweb grey and the glow that was painted around it.
- **window** — the rod bracket and a band of wall come with it; the right edge is ragged.
- **sofa, rug** — the two clean ones, and even the rug keeps brown fringe specks from the old one.

None of the first four could be moved, reused in another room, or scaled. A component is an object; a v1 layer is a
patch. That difference is the strongest argument for the method and it did not need a single GPU call to see.

Also visible in `out/strip.png`: **the two planks leaning against the wall beside the fireplace** stand through every
step of v1 and only disappear at the finale, which is a separate full-frame edit. The `mess` layer's alpha over that
region is 0.0%, and two things cause it: the planks run from about y 1400 to 1760 while the `mess` region box in
`cut_layers.py` starts at y 1553, so their top third was never eligible; and inside the box the edit changed nothing
there, so nothing was cut. Either way the item v1's own `items.tsv` names first among the mess — "the planks leaning
against the wall beside the fireplace" — is still standing, in a step whose README reports every diff as lighting up
only its own item. The rubble around the hearth survives too; the cardboard boxes and the tipped bucket do go. Two
of the five things that one row names are left behind. It is §12.1's "large structure survives the bulk list",
reproducing itself inside v1.

## Known gaps

- No `sit` animation in the rig, inherited from v1.
- The finale is v1's `finale.jpg`, reused as the brief allows. A component-based finale would be three more
  components (walls, ceiling, floor) rather than a full-frame edit, and was out of budget.
- `comfy.py run` only lints when a `--prompt-file` is given. This template builds its prompt inside the graph, so
  `gen_components.sh` sends an unlinted prompt; `components.txt` is linted separately
  (`comfy.py lint ... --engine nb --wired 1,2,3` → ok).
