# Fox Spine rig (generated)

Built by `plugin/skills/skipbo-art/scripts/spine_rig.py` from `../fox_master.png`, `../body/` and `../face-heads/`, and checked with `spine_qa.py`: every check passes; setup IoU against the master 0.964.

- **Import into Spine:** Import Data → `fox.json` (Spine 4.2). Images load from `./images/`.
- **Preview:** `python3 -m http.server 8766 --directory .`, then open `http://localhost:8766/preview.html?anim=cheer_jump`.
- **Skeleton:** 15 bones.
  - root → hips → torso → head_base.
  - torso → upperarm → forearm → hand, on each side.
  - hips → leg → boot, on each side.
  - hips → tail.
- **Ears:** the expression heads already include them, so there are no separate ear pieces.
- **Cut from the master:** arms, paws, legs, boots, hips. **Generated:** torso, head, tail.
- **Animations:** `idle`, `blink`, `wave`, `cheer_jump`, `emotions`.
  - In `cheer_jump`, the arms rise only as far as the wide cheeks allow (upper arm 15°, forearm 65°), and the tail follows the jump with a slight lag.
- **QA output:** `qa/*.gif`, `qa/*_strip.png`, `qa/cheer_jump_grid.png`, `qa/wave_grid.png`, `qa/report.json`.
