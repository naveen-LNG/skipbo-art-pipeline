# Prompt efficiency: what burned the GPU hours and the rules that fix it

Sources: [`comfyui_prompt_efficiency.html`](../references/usage-reports/comfyui_prompt_efficiency.html) and [`comfyui_image_summary.html`](../references/usage-reports/comfyui_image_summary.html) (the 8–11 Oct session: 603 jobs, 429 generations, 14.5 GPU-hours), the job-history JSONL, and the audit of the six saved workflows in [`../workflows/README.md`](../workflows/README.md).

## The diagnosis in five lines

1. **65% of generations were retries.** 197 were the same prompt run on a new seed and 83 were rewrites chasing the same target. Seed re-rolls alone took 6 GPU-hours.
2. **Negative phrasing can't work on Z-Image at cfg 1.** "no text" (135 times), "no shadow" (78), "not pink, not a pig snout" (11) were all fed in as *positive* conditioning, so each correction asked for the very thing it was trying to remove.
3. **Wordless screenshot feedback cost 17.8 generations per turn**, against 13.5 for turns with a sentence. It produced 321 of the 429 generations.
4. **Style was settled late.** Turns 1–4 went through four different style descriptions (91 generations) before "match the shipped Blocks characters" settled it.
5. **Parts were generated one at a time from text.** The Moose took 104 generations across 54 prompts. Each face patch was its own cluster, and the snout drifted between patches.

## Rules the skill enforces

### R1: Pick the engine first, then use that engine's grammar
| Task | Engine | Why |
|---|---|---|
| New scene or background in house style | Nano Banana Pro + LR style block + 2 style refs | Follows the long style spec; takes style from the images |
| Restyle or recolour an existing image while keeping its layout | Nano Banana Pro, `image_1` = source, temperature 0.35–0.6 | Faithful edits; the human sessions' recolours took 1 pass each |
| Concept sketch | Nano Banana Pro + LS style block | — |
| New character master (full body, A-pose) | Nano Banana Pro with the approved character refs | One coherent design in one call |
| Small local fix on an approved master (eyelid, button) | Z-Image masked inpaint, denoise 0.5–0.75 | Cheap and local; the rest of the image is untouched |
| Many cheap icon variants | Z-Image + icon style block (rewritten positively, see R2) | No API cost |

### R2: Z-Image prompts are positive descriptions only
- Never write `no`, `not`, `without`, `avoid`, `--avoid`, `don't` or `NOT X` in a Z-Image prompt. The lint script will refuse to send them.
- Describe what fills the slot instead:
  - `no text` → *"plain unmarked surfaces"*, or just leave text out.
  - `no shadow` → *"evenly lit, floating on a plain flat #E8EEF4 background"*.
  - `not pink, not a pig snout` → *"a long horse-like tan muzzle ending in a broad dark-brown nose with two wide nostrils"*.
  - `--avoid photorealism, blur, black shadows` → *"2D hand-painted, crisp clean edges, shadows in deep saturated blue-violet"*.
- Order: subject → form/pose → materials/colours → style → camera → background. Put the things that matter most first. Keep it to roughly 80–200 words; the long-prose card prompt (~600 words, much of it audience marketing) mostly diluted the visual tokens.

### R3: Nano Banana prompts are specs, written fresh each time
- Use this structure: `STYLE BLOCK` (verbatim from `skill/references/style-blocks/`, never paraphrased) → `IMAGE ROLES` (`image_1 = …`, `image_2 = …`, one line each) → `SUBJECT / SCENE` → `MUST KEEP` → `CHANGE ONLY` → `FINAL CHECK` (≤ 6 numbered items).
- **No revision history in the prompt.** "The last attempt…", "rejected three times…" and "an earlier version…" turn into conflicting instructions (see the three contradictions in ArtStyle). After each round, rewrite the brief as a clean description of the target.
- Every image the prompt mentions has to be connected. ArtStyle describes an `IMAGE 2` that is never wired in.
- One statement per fact. If a rule appears twice (as `SAFE AREAS` does in LR), the two copies will eventually disagree.

### R4: Set acceptance criteria before generating, not after
Before any job, the agent writes 3–6 checkable criteria. Examples: *"muzzle is long and horse-like, nose dark brown, arms clear of the vest with background visible between, A-pose ~30°"*. Results are reviewed against that list. A target is closed once it passes and is not reopened unless a criterion changes.

### R5: Two seeds at most, then change the words
After two seeds on an identical prompt, the next job must change the prompt or the inputs (mask, reference, denoise). A wrong structure (a fused arm, the wrong snout) is never fixed by re-rolling.

### R6: Batch, then review on one contact sheet
Generate 2–4 variants in one go and show them as a single labelled contact sheet. The user picks one, or gives one sentence per rejection. This replaces the one-asset-at-a-time loop that reopened clusters across 3–5 turns.

### R7: Feedback is a sentence plus a location
A screenshot shows *where*; one line says *what* and *what is already fine*. If the user sends only a screenshot, the agent asks one question ("what's wrong with the circled area?") instead of guessing with several parallel fixes.

### R8: Settle style once and pin it as images
Style is defined by reference images plus a frozen style block, never by adjectives typed fresh each session. Each style lives in `skill/references/styles/<name>/` (refs, block, accepted examples). New work starts by naming one of them.

### R9: Parts come from a master, not from separate text prompts
For rig parts, generate **one** approved full-body master and then derive the parts from it (segment, cut, extend the hidden areas with inpaint at low denoise using the master as context). Never generate an eye or mouth as a fresh text-to-image target. Details are in [`spine-parts-plan.md`](spine-parts-plan.md).

## Quick self-check before queuing (what the skill runs)

```text
[ ] Engine chosen per R1, and the prompt uses that engine's grammar
[ ] Z-Image: lint passes (no negations), ≤ ~200 words, most important thing first
[ ] Nano Banana: style block pasted verbatim, every referenced image wired, no history text
[ ] Acceptance criteria written (3–6 items)
[ ] Not the third seed of an identical prompt
[ ] Output prefix and client_id set so the job can be traced
```
