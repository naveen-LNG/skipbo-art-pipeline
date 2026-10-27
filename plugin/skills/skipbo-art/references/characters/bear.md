# Character: Bear (baker)

- **Design ref:** none. The master came from text alone (`references/prompts/spine/master-textonly.txt`, the two style atlases as image_1 and image_2), like the beaver.
- **Approved Blocks master:** (repo) `experiments/2026-10-16-cast/bear/bear_master.png` (2026-10-16, variant 00 of 2; both passed `spine_qa.py --contract`; 01 drew a bib apron). Rig: `experiments/2026-10-16-cast/bear/rig/`: all 20 `spine_qa` checks pass. Rebuild with `bear/rebuild.sh`.
- **Body type:** chunky and wide (the shirt is about half the image width), short stubby arms and legs. It tests how the pipeline handles wide proportions; see "What to know" below.

## CHARACTER (master prompt)

~~~~text
A big friendly brown bear baker with a chunky, heavy, round body, wide and stout: warm honey-brown fur, a round light-tan muzzle with a dark-brown nose, small round ears, and a big round belly. A white long-sleeved baker's shirt whose sleeves are pushed up a little: each white sleeve ends in a soft rolled cuff on the forearm, and a short band of honey-brown furry forearm shows between the cuff and the paw. A short red-and-white checked apron tied at the waist with a red waistband over the shirt, covering the front of the hips and ending just below the crotch. Wide brown trousers on short sturdy legs, the two trouser legs a little apart below the apron. Dark-brown wooden clogs. Dark chocolate-brown mitten paws, darker than the fur. No hat. Both paws are empty: no tools or props. The bear has no visible tail.
~~~~

The sheets use a second CHARACTER that describes the approved master as painted (sleeves rolled to the elbow, bare fur forearms), because the sheets' CHARACTER NOTES override image_1. PIECES, HANDS, POSES, SLEEVE and PROPS: `experiments/2026-10-16-cast/bear/prompts/bear.env`.

## What to know before regenerating
- **Colour contrast:** shirt and sleeve are the same white (arms go `under_torso`, as the beaver's knit). The paws are asked "dark chocolate-brown, darker than the fur" so the wrist cut against the bare honey forearm has contrast. Clogs are darker than the trousers.
- **Arms:** one whole arm per side (white sleeve, rolled cuff at the elbow, bare fur forearm) from `bear/prompts/arms-pair.txt`, a copy of `sleeves-pair.txt` that asks for the arm down to a furry wrist. It still painted a honey fur paw on each arm's end; `bear/make_parts.py` cuts it off at the narrowest row and rounds the end. The dark mitten is drawn over it (`hand: over_forearm`), as in the master: its oven-mitt cuff is wider than the forearm.
- **Torso:** at the rig's scale (set by neck-to-waist) the body sheet's shirt is ~1.2x the master's width; `make_parts.py` narrows it 0.86 across. Expect a wide character's torso to come back wider than its height allows.
- **Lower body (the apron):** planned as part of the hips, not its own piece: the apron is tied at the waist and only lies over the trousers, so one hips piece (waistband + apron + trousers to the hems) over the clogs (`foot: under_hips`) needs no new role. The body sheet's "whole lower body as ONE piece" came back as shorts at 2/3 of the master's height (the beaver's first failure again), so the piece is cut from the master (it has no cut joint edge: the shirt hem lies over its top, its hems over the clogs). The clogs' toe caps lie over the hems in the master; that notch is repainted.
- **Clogs:** the body sheet's side-view clogs, widened 1.10, each with a hidden honey-fur ankle stub above the heel and the pivot raised into it. Their tops sat only ~50 px under the wide hems, so the hips' bob in walk/run and the tuck in jump_hurdle broke `unstitched`.
- **No tiptoe:** the poses sheet's tilted side-view clog came out 3.2x too big in the rig (a giant clog in cheer_jump in the Spine player), so it is dropped. Ask for a front-view tiptoe clog, or skip that row.
- **Hands:** fist and point were asked palm-facing in `HANDS`. The fist came back palm-facing, but the point came back back-facing (knuckles, thumb tucked behind) on both rows. The rig uses `bear-point-palm-parts/00` from `hands-point-palm.txt`, 1 call. Use row 1 (the character's left hand, wrist up): row 2 painted the open hand, fist and grip upside down.
- **No tail**, no hat; the face heads include the ears, so the ear pieces are dropped.
