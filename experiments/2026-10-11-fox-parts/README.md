# Experiment 2026-10-11: Fox, a second character, plus a cheerful jump

**Goals:**
1. Test the proposed master-prompt change on a new character.
2. Run a character with a tail through the whole pipeline.
3. Add a `cheer_jump` animation, gated by the frame-by-frame QA.

## 1. Master prompt A/B ([`../2026-10-11-fox-master-ab/`](../2026-10-11-fox-master-ab/))

Design ref: the fox in dungarees from an earlier lineup (`references/characters/fox/`). Same character notes for both arms; 2 variants each.

| Variant | Leg gap (% of height) | Arm-gap rows L/R | Contract |
|---|---|---|---|
| A00, old prompt | 22.7 | 37 / 37 | PASS |
| A01, old prompt | 18.0 | 25 / 19 | PASS |
| B00, new prompt (leg gap + colour contrast) | 22.2 | 26 / 26 | PASS |
| B01, new prompt | 25.7 | 50 / 49 | PASS |

All four met the contract; two samples per side can't separate the prompts. The art director preferred the old prompt's look, so **the old prompt stays**, and A00 (front-facing head) became the master.

What the A/B did find: the checker, and the rig, located the centre line from the whole silhouette's centre of mass, and a tail drags that sideways. Both now use the head and torso only.

## 2. Pipeline

- Master A00 → body sheet (15 pieces; each sleeve came as a single piece) → face sheet. The first face sheet had 3 faded "ghost" heads; the re-roll was clean.
- **Rig changes this character forced** (each is general, not fox-specific):
  - Lower body from the master's geometry, not the generated leg pieces.
  - Tails get a layout band; hands are searched near the end of their own sleeve.
  - The tail colour test is local, so it no longer punches holes in boots.
  - Single-sleeve arms are accepted.
  - Expression heads are placed by matching against the master, and ear pieces the heads already include are dropped.
  - Master cuts keep only their main connected body.
  - Raised-arm poses are computed to clear the whole head assembly.
- **Server:** one split job hit GPU out-of-memory because the shared T4 was busy; `comfy.py` now retries.

## 3. QA

Final: [`fox-spine/rig/`](fox-spine/rig/). `spine_qa.py` passes every check:
- **structure**;
- **setup IoU 0.964**;
- **all five animations**: idle, blink, wave, cheer_jump and emotions.

The Moose rig was rebuilt with the same code and also passes everything (setup IoU 0.976), so nothing regressed. The fox's `cheer_jump` at t=0.95 s was spot-checked in the Spine 4.2 web player and matches the QA renderer.

Defects found by **looking at frames** after the metrics passed:
- arms passing behind the head;
- a floating paw-coloured fragment;
- a stiff T-pose cheer.

The first two now have automated checks (`occluded`, `fragments`). The third is fixed by the clearance-based pose search, but "does the pose read" still needs eyes.

Cost: 2 (A/B) + 3 (body and face sheets from B00, plus a face re-roll) + 2 (sheets regenerated from the preferred A00) = **7 Nano Banana Pro calls**, plus about 6 split jobs.
