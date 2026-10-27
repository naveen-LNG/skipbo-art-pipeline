# References

| Folder | What | Origin |
|---|---|---|
| `style-refs/` | The 7 input images the saved workflows load (style references and source images) | Downloaded from the server's `input/` folder on 2026-10-11 |
| `rigging-examples/` | 11 screenshots of a commercial 2D rig pack: control points, bones, face slots, hand library, pose presets | Local screenshots, renamed by content (originally `Screenshot 2026-10-11 at 12.xx.xx PM.png`) |
| `usage-reports/` | Two HTML reports of the 8–11 Oct Claude session, plus the server's job history as JSONL (615 jobs: prompt, model, sampler, inputs, outputs) | Reports provided; JSONL from `GET /history` before the ~3-day retention window dropped it |

## style-refs

| File | Size | Used by | Role |
|---|---|---|---|
| `EXAMPLE_LR_block_01.png` | 1152×2048 | LR render | Colour style ref: beach scene, 9:16, no outlines, soft two-zone shading |
| `EXAMPLE_LR_block_02.png` | 1152×2048 | LR render | Colour style ref (second) |
| `LEO_SKETCH_STYLE_REF_1.png` | 1296×730 | LS sketch | Pencil style ref: bulldog rapper on a street corner |
| `LEO_SKETCH_STYLE_REF_2.png` | 1376×768 | LS sketch | Pencil style ref (second) |
| `2.png` | 1115×994 | ArtStyle | **Source** image being revised: hazelnut/chocolate shop room. It has outlines, which the brief removes |
| `The Blossom Fairground Sunny Day (1).png` | 1024×1024 | NanoBananaTest | Layout source (`image_1`) |
| `image (11).png` | 1143×1137 | NanoBananaTest | Style source (`image_2`): a lush fantasy village |

## rigging-examples

| File | Shows |
|---|---|
| `01-control-points-labelled.png` | The 13 named controls on a front-view character |
| `02-bone-skeleton-overlay.png` | The bone chain under the art |
| `03-modifier-groups.png` | Face / body / arms-and-legs control groups |
| `04-bone-chains.png` | Two-segment limb chains with joints |
| `05-face-expression-slots.png` | Whole-face expression swap slots (15) |
| `06-hand-pose-library.png` | Swappable hand poses (fist, point, thumb up, flat) |
| `07-emotion-pose-animations.png` | Emotion poses (furious, so what, protest…) |
| `08-rigged-cast-lineup.png` | 12 characters built the same way |
| `09/10/11-preset-poses-*.png` | Preset poses (bow, wave, akimbo, salute, cheer, thumb up…) |
