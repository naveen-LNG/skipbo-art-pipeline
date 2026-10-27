# Room renovate: a makeover-game sequence with the beaver

Goal: recreate the home-makeover ad loop (reference: a "Tile Family" YouTube Short): a fixed camera on a wrecked room, bubble icons with a star cost float over each broken thing, tapping one swaps that thing in place with a poof, and the room warms up step by step until the finale.

Play it: `python3 -m http.server 8770 --directory experiments/2026-10-16-room-renovate/game` (or the `room-renovate` entry in `.claude/launch.json`), then open http://localhost:8770.

## How the art was made (12 Nano Banana Pro calls)

1. **Before room** (`scripts/gen_base.sh`, 2 calls): LR style block + `prompts/room-scene.txt`, 9:16 2K. Six fixable things are placed apart so they don't overlap, with an empty rug in the middle for the character. Picked variant `_01` → `room/base.png`.
2. **One in-place edit per item** (`scripts/gen_edits.sh`, 7 calls, TEMP 0.4): `prompts/edit.txt` + one line per item in `prompts/items.tsv`, image 1 = the base. Every edit kept the frame almost pixel for pixel; each diff map lights up only its own item (`scripts/sheet.py`).
3. **Layers from the diffs** (`scripts/cut_layers.py`): diff vs base → threshold inside a generous region box → open/close (edge-padded), fill holes, grow 6px, feather. The mess needed a lower threshold (the boxes are close to the floor in tone). Writes `game/assets/layers/*.png`, `layout.json`, thumbs, and `room/six-fixed.png`.
4. **Finale** (`scripts/gen_finale.sh`, 3 calls): new cream/sage striped wallpaper, clean ceiling with no cracks or cobwebs, mopped floor, leftover planks gone, warm light. It is edited from `six-fixed.png`, not the base, because a walls edit made from the base fights the window and lamp edits for the same pixels (the wall behind the old curtain, the cobwebs). So the walls are the finale and unlock only after the other six. A touch-up pass polished the floor.
5. **Picture frame** (`scripts/straighten_frame.py`): Nano Banana kept the frame's skewed top edge through three edits, so the frame quad is warped onto a level rectangle → `room/finale.png`.

## The game page (`game/index.html`)

- Base image, six layers (any order), then the finale image on top, all at the art's own 1536×2752 frame.
- The beaver is the Spine rig from `2026-10-15-beaver-jev-hands` (copied into `game/beaver/`), run with spine-player 4.2.100. Its viewport is fixed so it never rescales between animations. It walks (`walk`) to the item, `point`s, and does `cheer_jump` after the swap. At the finale it does `thumbs_up`, `cheer_jump`, then `wave`.
- Juice: puff cloud, sparkles, pop-scale on the new item, synth blips, star fly-in from the + button (stands in for a puzzle level), a cool "gloom" grade that lifts with each fix, lamp glow and fire flicker, a white flash and confetti at the finale.
- Costs: 1–2 stars per item, 3 for the finale; the player starts with 5, and + gives 3.

## Known gaps

- No `sit` animation in the rig, so the beaver can't sit on the new sofa (the ad's mum sits down at the end).
- Layers only have to blend with the base, and they do. The finale is a full-frame crossfade, so lighting stays consistent there too.
