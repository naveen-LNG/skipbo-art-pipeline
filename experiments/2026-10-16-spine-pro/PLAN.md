# Spine Pro + new cast (2026-10-16)

Goal for the morning review: a more Spine-native rig system that uses the primitives the Armanimation
study found we skip (`docs/research/armanimation-spine/README.md` §4), new characters made by the
pipeline, and **one gallery page that plays every animation of every character at once**.

Rule: **nothing that exists today changes behaviour.** Legacy `spine_rig.py` output for fox, moose and
beaver stays byte-identical (the golden test in `tests/` proves it), existing experiment folders are
read-only, and all new work is on branch `spine-pro-cast` in this worktree.

## Workstreams (one subagent each, disjoint files)

| # | Workstream | Writes only to |
|---|---|---|
| A | **Spine Pro rig**: post-processor that upgrades a built rig with container, underfill, tail chain mesh, torso breathing mesh, face/ear helpers, planted feet (IK), bone organisation, secondary motion; QA support for the new constructs; `spine_diff.py` feedback loop | `plugin/skills/skipbo-art/scripts/spine_pro.py`, `scripts/pro_*.py`, `scripts/spine_diff.py`, additive changes in `scripts/spine_qa.py` (or a new `scripts/qa_*.py` it imports), `tests/test_spine_pro*.py`, `tests/test_spine_diff.py`, `experiments/2026-10-16-spine-pro/{fox,moose,beaver}/`, `experiments/2026-10-16-spine-pro/README.md` |
| B | **Rabbit** (long ears) through the existing pipeline | `experiments/2026-10-16-cast/rabbit/`, `plugin/skills/skipbo-art/references/characters/rabbit.md` (new file) |
| C | **Red panda** (big striped bushy tail) | `experiments/2026-10-16-cast/redpanda/`, `references/characters/redpanda.md` (new file) |
| D | **Bear** (big, round, no visible tail) | `experiments/2026-10-16-cast/bear/`, `references/characters/bear.md` (new file) |
| E | **Gallery**: packer + one page, all characters x all animations, legacy vs pro toggle | `tools/build_gallery.py`, `gallery/` |

Shared rules:
- Don't `git commit`; the orchestrator commits.
- Don't edit another workstream's files. If you hit a bug in a shared script, work around it locally and
  write it in your README under "Pipeline issues found"; the orchestrator decides.
- Long commands (`uv run` builds, QA) can take minutes; run them in the background when over ~2 min.
- `uv run --with pytest --with numpy --with pillow pytest tests` must keep passing.
