# Character: Red panda (explorer)

- **Design ref:** none. The master came from text alone (`references/prompts/spine/master-textonly.txt`, the two style atlases only).
- **Approved Blocks master:** (repo) `experiments/2026-10-16-cast/redpanda/redpanda_master.png` (2026-10-16, variant 01 of 2; both passed `spine_qa.py --contract`). 01 was picked because its ringed tail curves up beside the body, fully visible; in 00 the tail curls behind the boot. The left mitten overlaps the tail's lower bend. Rig: `experiments/2026-10-16-cast/redpanda/rig/`, rebuilt from scratch by `redpanda/rebuild.sh`.

## CHARACTER

~~~~text
A cheerful young red panda explorer: rusty red-orange fur, a white face mask with white cheeks and a white muzzle, two white eyebrow spots above the eyes, rounded rust ears with white edges, and a dark-brown nose. Dark-brown mitten paws. A big bushy tail with clear alternating rings of rust red and cream: it comes out from behind the hips on the right side of the picture, sweeps out sideways and curves upward in one clean soft shape, its tip ending at about belt height, fully visible beside the body, below the hand and clear of it, with plain background between the tail and the leg and between the tail and the arm. A mustard-yellow long-sleeved field jacket with two flapped chest pockets and plain cuffs, olive-green trousers held by a brown belt, and brown lace-up hiking boots. Both paws are empty: no tools or props.
~~~~

The tail came out taller than asked (tip at head height, not belt height); that is the version approved.

PIECES, HANDS, POSES, SLEEVE, PROPS and the two point re-rolls: `experiments/2026-10-16-cast/redpanda/prompts/redpanda.env`.

## What to know before regenerating
- **Ears:** the body sheet painted both ears as pointed, horn-like shapes turned about 150 deg, which the matcher (+-90 deg) can't fit, and the face sheet's heads have no ears. The rig uses the master's ears (`make_ears.py`): each cut with a 34 px band of head fur under its base, hidden behind the head. A regenerated ear would need "rounded, tip up, wide base at the bottom, as in image_1".
- **Trousers:** the body sheet's "hips" is the whole trousers (belt to hem) at the master's length, so it is used leg-less with the boots under it (no leg pieces). `make_trousers.py` cuts the crotch higher and the leg gap wider (the sheet's read as wide shorts), carries the legs straight down to the hems, and adds a belt-coloured band above the belt that hides under the jacket (the jacket hem and belt otherwise met edge to edge: a weak torso/hips joint).
- **Boots:** as tall as the master's visible boots, so nothing reached under the trousers and the boots came off in `run`. `make_boots.py` stretches the plain shaft above the laces; the master's ankle sits well above the hem (0.745).
- **Sleeves:** `sleeves-pair.txt` on the first try. The master's lower sleeves are 1.32x fatter than the drawing (`sleeve_too_thin`); `make_sleeve_wide.py` widens from the elbow to 1.36x at the cuff (ramp 0.58-0.76: a ramp starting lower left 1.22-1.26, because the fit measures 25-45% below the elbow).
- **Hands:** the fist came back palm-facing from the hands sheet when asked. The point came back back-facing twice (the hands sheet, then `hands-point-palm.txt`; Jev's cue score -0.42). What worked: describing palm cues in `HANDS` ("a slightly lighter brown palm pad", "the short thumb folded across the front of the palm", "fingertips facing the viewer"), `POINT2` in the env file.
  The thumb then lies folded across the palm, so `jev_qa.py` FAILs the point hold (P(thumb up) 0.27) while `spine_qa`'s thumb check passes; ask for "the thumb sticking up along the side of the hand" next time.
- **Tiptoe boots:** scaled to the rest boot by area, so they get the same hidden shaft growth (`make_boots.py`), or they come out 1.2x too big.
- **Mittens:** a 1-2 px grey rim inside their opaque edge failed `seams` over the cream tail; `make_paws.py` recolours it.
- **Props:** the hurdle came back with a ghost boot merged into its left foot; `make_props.py` mirrors its clean right half.
- **Tail:** the body sheet's ringed J fits the master as painted (no repaint, no tail-up variant).
