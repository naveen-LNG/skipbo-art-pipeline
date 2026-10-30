# Feedback log

One line per user correction that changed this skill: date, what was wrong, what changed.

- 2026-10-29: set up the feedback loop (this file and the "When the user corrects you" section).
- 2026-10-29: bear shovel was one-handed and didn't read as digging -> psd_rig.py shovel is two-handed (IK on both paws, low flat hold), stab / pry / scoop / toss with a dirt pile and thrown clod; two "Common mistakes" rows added.
- 2026-10-30: animations had a key on every frame, too hard to edit in Spine -> psd_rig.bake keys only the poses with Bezier curves (adds a key only where the curve would drift, drops keys a bone doesn't need; bear 3,383 -> 358 keys, under 0.6 px drift); spine_qa.py now reads Spine Bezier curves; preview.html freeze-frame clears tracks first.
- 2026-10-30: wrench was in the wrong paw with no body or face acting (reference: a worker bent over a wrench) -> wrench on a new right-paw grip (tool_r, IK on a bolt pivot) drawn in front of the body; anticipation, deep bend and dip into the pull, strain, ratchet back; brows down, eyes squeezed, jaw clenched; "Common mistakes" row added.
