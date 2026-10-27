# Character: Rabbit (gardener)

- **Design ref:** none. The master came from text alone (`references/prompts/spine/master-textonly.txt`), third wording, variant 00.
- **Approved Blocks master:** (repo) `experiments/2026-10-16-cast/rabbit/rabbit_master.png` (2026-10-16): the generated master with only its background recoloured (`make_master_bg.py`; the untouched picture is `rabbit_master_orig.png`). It passes `spine_qa.py --contract` except `arm_gaps` (the paws hang close to the body). Rig: `experiments/2026-10-16-cast/rabbit/rig/`, all 20 QA checks pass. Rebuild with `rabbit/rebuild.sh`. Self-reviewed overnight, not yet seen by the art director.

## CHARACTER

~~~~text
A cheerful young rabbit gardener: soft medium silver-grey fur, clearly darker than the pale background, with a white muzzle, a small pink nose, and two long ears with pink inner ears that stand straight up above the head, side by side with plain background between them, both fully inside the frame; a short round white cotton tail that peeks out beside one hip. A grass-green long-sleeved shirt whose sleeves end in a soft rolled cuff at the wrist; denim-blue dungaree trousers with a bib and two shoulder straps fastened by two round brass buttons, the trouser legs tucked into orange rubber boots. Silver-grey mitten paws, each a chunky mitten with four short fat rounded fingers. Both paws are empty: no tools or props.
~~~~

PIECES, HANDS, SLEEVE, PROPS and the palm-facing POINT: `experiments/2026-10-16-cast/rabbit/prompts/rabbit.env`.

## What to know before regenerating
- **Fur colour:** "light-grey fur" painted the fur, muzzle and paws within 0.03 of the light-grey background. The pipeline keys the master by distance from the border colour (> 0.06), so the head and paws read as holes. Say "medium silver-grey, clearly darker than the pale background", and run `tools/key_check.py` (experiment) on the master. The white muzzle still keys as a hole on grey, so the master's background is recoloured to sand yellow before rigging.
- **Sleeves:** asked for long sleeves, every variant painted sleeves ending near the elbow in a fat rolled cuff, with a forearm-long mitten below. The rig treats the cuff as the wrist: one whole sleeve per arm, widened toward the cuff (`make_sleeve_wide.py`, 2.05x / 2.25x), and the big mitten is the hand.
- **Torso:** the body sheet painted an open armhole on one shoulder; `make_torso.py` mirrors the closed side. The torso's neck-to-waist sets the global scale, so its waist point sits at 0.72: the torso and trouser widths need 1.35 master px per part px.
- **Trousers:** one piece with both legs (no leg pieces), boots `over_hips`. The leg openings are filled with cloth and the legs narrowed 0.92 at the hems (`make_trousers.py`), so the boots' front lip hides the hems.
- **Tail:** the cotton ball's rim is painted in the background's own grey and the paw hides half of it, so the matcher can't place it. It is painted into the trousers piece, behind the right hip.
- **Ears:** separate long pieces behind the head (the expression heads have no ears), roots stretched 1.6x down (`make_ears.py`) so enough tucks behind the head. Ready for ear bones.
- **Hands:** the fist and point are palm-facing (`rabbit-hands-parts/10`, `rabbit-point-palm-parts/01`). The grip reads right only as `back`: labelled palm, its thumb pointed 170 deg from up.
- **hold_card:** the paw is longer than the sleeve's forearm half, so it reaches the bib before the sleeve does. `tools/fix_draworder.py` lifts the arm over the torso 0.15 s earlier.
