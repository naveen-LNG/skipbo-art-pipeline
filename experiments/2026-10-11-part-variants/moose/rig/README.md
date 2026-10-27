# Moose Spine rig (generated parts + pose variants)

Built by `plugin/skills/skipbo-art/scripts/spine_rig.py` from `../body/`, `../variants/` and the expression heads, with the master as the placement reference only. `spine_qa.py` passes every check; the numbers are in `qa/report.json`.

- **Import into Spine:** Import Data → `moose.json` (Spine 4.2). Images load from `./images/`.
- **Preview:** `python3 -m http.server 8766 --directory .`, then open `http://localhost:8766/preview.html?anim=cheer_jump`.
- **Swappable attachments:** hands (open, fist, point, thumbsup, grip), `upperarm_*_raised`, tiptoe feet. The animations key them; in the Spine editor they're in each slot's attachment list.
- **Animations:** `idle`, `blink`, `wave`, `cheer_jump`, `thumbs_up`, `point`, `hold_card`, `emotions`.
