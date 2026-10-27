# Engines on the SkipBo server

| | Z-Image Turbo (`zimage-*`) | Nano Banana Pro (`nb-pro`) / Nano Banana 2 (`nb2-flash`) |
|---|---|---|
| What it is | Local 6B diffusion model with a Qwen3-4B text encoder, on a T4 | Gemini 3 Pro Image / 3.1 Flash Image via API (billed per call) |
| Settings | 8 steps, cfg 1.0, `res_multistep`/`simple`, shift 3, zeroed negative | `TEMP` 0.35–0.6 for faithful edits, 0.6–1.0 for new pictures; `SIZE` 1K/2K/4K; `ASPECT` |
| Reads instructions | **No.** It encodes a description; every word you write pulls toward that thing | **Yes.** It follows numbered lists, image roles, counts and exclusions |
| References | Only as latents: img2img (`DENOISE` 0.3–0.6 keeps composition) or masked inpaint | Up to 6 (`nb-pro`) or 10 (`nb2-flash`) images, each given a role in the prompt |
| Variants | `--n` runs consecutive seeds | `--n` sets `image_count` in one call; there's no seed (identical inputs are cached) |
| Time | ~100 s per 1024² | ~40–70 s per 2K image |

## Z-Image prompt recipe
Subject → shape/pose → colours/materials → style words → camera → background. Use 80–200 words, positive only, with the most important thing first.

```text
A chunky clay honey pot with a wide rounded body and a short neck, three glossy brown mushrooms
poking out of golden honey, a wooden dipper resting across the rim. Warm amber and cream with
soft hue-shifted shading, thin slightly darker coloured outlines. 2D hand-painted casual mobile
game icon, bold simple shapes, seen from a 45 degree high angle with a long lens. Centered on a
plain flat pale cream background.
```

## Nano Banana prompt recipe
```text
IMAGE ROLES:
image_1 = <role>. Take from it only <what>.
image_2 = <role>. ...

<STYLE BLOCK pasted verbatim from references/styles/<style>/block.md>

TASK / SUBJECT / SCENE: <only this image>

FINAL CHECK:
1. ... (at most 6 items, each a checkable fact)
```

## Image roles that worked
- `image_1 = CHARACTER DESIGN … take only species, proportions, costume, colours` + `image_2/3 = ART STYLE (shipped atlases) … take only how things are painted`.
- `image_1 = THE CHARACTER, finished and approved. Every piece is cut from this exact character` + `image_2 = ATLAS FORMAT`.
- `image_1 = LAYOUT REFERENCE` + `image_2 = ART STYLE REFERENCE ONLY` (NanoBananaTest on the server).

Feeding a *generated sheet* back in as a reference caused faint "ghost" copies of its pieces to appear. Prefer the approved master as the reference.
