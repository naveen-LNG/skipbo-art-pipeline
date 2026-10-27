# The SkipBo ComfyUI server

Facts gathered on 2026-10-11 from read-only GET requests. Re-check with `GET /system_stats` and `GET /object_info` if something looks off.

## Host

| | |
|---|---|
| URL | `https://skipbo.comfyui.liquidnitro.games` |
| ComfyUI | 0.18.2, frontend 1.41.21, Python 3.10, PyTorch 2.10 + CUDA 12.8 |
| GPU | **1× Tesla T4, 16 GB VRAM**, 32 GB RAM. Jobs run one at a time; Z-Image Turbo takes about 100 s per 1024² image |
| Auth | **None.** Every endpoint below answers without credentials (see *Security* below) |
| History retention | About 3 days / ~600 jobs. Older prompts and seeds are gone; only the output files remain |
| Output folder | `/mnt/comfy-output/8189`; Claude's earlier runs used the `lngtile/` subfolder prefix |

## Models installed

| Folder | Files |
|---|---|
| `diffusion_models` | `z_image_turbo_bf16.safetensors`, `flux1-dev.safetensors` |
| `checkpoints` | `albedobaseXL_v31Large.safetensors` (SDXL), `v1-5-pruned-emaonly.safetensors` |
| `text_encoders` | `qwen_3_4b.safetensors` (Z-Image), `t5xxl_fp16.safetensors` + `clip_l.safetensors` (Flux) |
| `vae` | `ae.safetensors` |
| `loras` | `Disney_IZT_ATK_V1_000000750` (Z-Image), `pixel_art_style_z_image_turbo`, `flux1D_Cards` (Flux) |

API-backed image nodes that cost money per call: `NanoBananaAIO` (Gemini 3 Pro Image), `NanoBanana2AIO` (Gemini 3.1 Flash Image, up to 14 reference images, 512px–4K, aspect ratios down to 1:8), `GeminiNanoBanana2`, Flux Kontext/Pro, Recraft, Bria, Stability.

Nodes that matter for the asset pipeline:

- **Background removal:** `easy imageRemBg` with modes `RMBG-2.0`, `RMBG-1.4` (used so far), `Inspyrenet` and `BEN2`; `BriaRemoveImageBackground`; `RecraftRemoveBackgroundNode`.
- **Masks and inpaint:** `SetLatentNoiseMask`, `GrowMask`, `FeatherMask`, `ImageCompositeMasked`, `JoinImageWithAlpha`, `SplitImageWithAlpha`, the Impact-Pack SAM/SEGS detectors and `SAMLoader`.
- **Layers:** `EmptyQwenImageLayeredLatentImage` (Qwen-Image-Layered RGBA decomposition). The node exists but **no Qwen-Image model is installed**, so it can't run yet.
- **Style and identity:** the IPAdapter suite (SDXL/SD1.5 only, so it won't drive Z-Image).

## API cheat sheet

These are the ComfyUI REST endpoints the skill will use. Everything is plain HTTP+JSON, so it works the same from macOS, Windows or Linux.

| Purpose | Call | Side effect |
|---|---|---|
| Health and VRAM | `GET /system_stats` | none |
| List saved workflows | `GET /api/userdata?dir=workflows&recurse=true&split=false&full_info=true` | none |
| Download a workflow | `GET /api/userdata/workflows%2F<urlencoded name>` | none |
| Node schemas | `GET /object_info` (2 MB) or `GET /object_info/<NodeClass>` | none |
| Model lists | `GET /api/models/<folder>` | none |
| Job history | `GET /history?max_items=N`, `GET /history/<prompt_id>` | none |
| Queue status | `GET /queue`, `GET /prompt` | none |
| Fetch an image | `GET /view?filename=<f>&subfolder=<s>&type=output\|input\|temp` | none |
| **Upload an input image** | `POST /upload/image` (multipart `image`, `overwrite`, `subfolder`) | **writes to the server** |
| **Queue a job** | `POST /prompt` `{"prompt": <API-format graph>, "client_id": "<id>"}` → `{"prompt_id"}` | **runs GPU / spends API credits** |
| Live progress | `WS /ws?clientId=<id>` | none |
| Cancel | `POST /interrupt`, `POST /queue {"delete":[ids]}` | changes the queue |

**UI format vs API format.** The files in `workflows/originals/` are *UI* format (`nodes` + `links` + `widgets_values`). `POST /prompt` takes *API* format (`{node_id: {class_type, inputs}}`). To convert, use "Export (API)" in the ComfyUI menu, or map each node's `widgets_values` to input names with `object_info`. `tools/comfy_snapshot.py` already does that mapping (`widget_names()`).

**Client ID.** Earlier runs used `client_id = "claude-lngtile"`, which is what made the 8–11 Oct usage report possible. Keep a stable, per-person client ID (for example `claude-<user>`) so usage can be attributed later.

## Security

The server is open to the internet with no authentication. Anyone who has the URL can:

- queue jobs, including Nano Banana Pro calls billed to the server's Gemini key;
- read every prompt in the history and download every input and output image (unreleased game art);
- overwrite input images with `POST /upload/image`.

Recommended before the skill is shared outside the core team: put the host behind Cloudflare Access or basic auth. The skill's client can then read a token from an environment variable (`COMFY_TOKEN`) without changing anything else.
