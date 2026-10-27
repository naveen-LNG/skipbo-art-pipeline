# Character: Beaver (carpenter)

- **Design ref:** none. The master came from text alone (`references/prompts/spine/master-textonly.txt`: the master prompt with only the two style atlases wired).
- **Approved Blocks master:** (repo) `experiments/2026-10-15-beaver-jev-hands/beaver/beaver_master.png` (2026-10-15). It passes `spine_qa.py --contract`. Rig: `experiments/2026-10-15-beaver-jev-hands/beaver/rig/` (round 7): all 15 QA checks pass. Rebuild with `beaver/rebuild.sh`.

## CHARACTER

~~~~text
A cheerful young beaver carpenter: warm chestnut-brown fur, a cream muzzle with two big white front teeth showing under a dark-brown nose, small round ears, and a broad flat dark-brown paddle tail. A turquoise knitted long-sleeved sweater with a ribbed collar and ribbed cuffs, mustard-yellow trousers held by a brown belt with a gold buckle, and red boots. Dark-brown mitten paws. Both paws are empty: no tools or props.
~~~~

PIECES, HANDS and POSES: `experiments/2026-10-15-beaver-jev-hands/prompts/beaver.env`.

## What to know before regenerating
- **Arms:** the body sheet painted two-piece arms about 1.3x the master's length, which looked stuck on. The rig uses one whole sleeve (`sleeves-pair.txt`, one mesh per arm, mirrored for the right, under the torso).
  - The master's sleeves are fatter than any sleeve the sheets painted (`sleeve_too_thin`, 1.34), so `beaver/make_sleeve_wide.py` widens the drawing toward the cuff, 1.32x from the elbow down.
  - Annotate the sleeve's points at the measured centres of its top and cuff.
- **Trousers:** the body sheet's hips were long shorts. The rig uses one trousers piece, `beaver/make_trousers.py`:
  - belt-to-crotch hips over the cuffed legs, so the boots stay under the cuffs;
  - painted at the body sheet's scale;
  - hips narrowed 0.88 to the master's belt width;
  - the shorts' bottom edge blended into the legs.
- **Boots:** under the trousers, centred on the master's boot tops (x 0.408 / 0.600), not on the trouser legs.
- **Hands:** fists and points are palm-facing (`beaver-fist-palm-parts/00`, `beaver-point-palm-parts/02`). The back-facing fist showed its back in cheer_jump, and the back-facing point went across the chest and read as a grip. The master's fingertips are set a third of the way from the mitten's own angle toward the sleeve's, so the mitten tucks under the cuff.
- **Tail:** repainted as the master holds it (root up-right); there is no tail-up variant.
- **Squat and jump legs:** the trousers piece has no knees, so the squat, `plant_seed` and `jump_hurdle` swap whole-legs drawings (two `legs-inbetweens.txt` sheets plus four `legs-midpoint.txt` in-betweens: squat 3–4 and 4–5, jump 2–3 and 3–4). The jump sheet came out lankier and is fitted at x0.77. Builder and prompts: `experiments/2026-10-16-legs-variants/make_beaver_legs.py`; key poses: `experiments/2026-10-16-keypose-refs/refs/`.
- **Garden and talking:** the garden props and their fit are in `experiments/2026-10-16-garden-grow`; the mouth patches for lip sync are in `experiments/2026-10-17-lip-sync/beaver`.
