# Plan: agent access to the ComfyUI server (skill + CLI, packaged as a plugin)

Status: **built (v0.1, 2026-10-11).** It lives in `plugin/`. Built: CLI (`status`, `lint`, `run` with seed cap and ledger, `sheet`, `size`, `scale`, `fetch`), 8 API templates, the skill and the plugin manifest. Differences from the original plan: Nano Banana variants use `image_count` (there's no seed), and the `spine-parts` chain was added. Decisions 1–2 below are resolved (Blocks atlases provided; test jobs approved); decision 3 is with the user.

## Goal

Anyone on the team, on macOS or Windows, asks their agent for an asset ("an icon for Honey Dew Mushroom Pot", "the Moose master in A-pose") and gets the house style on the first or second pass, with a traceable record of what was sent.

## Recommendation

**One Claude Code plugin that contains a skill and a single-file, stdlib-only Python CLI.** Add an MCP wrapper later only if non-coding clients (Claude Desktop, Cowork) need it.

| Option | Cross-platform | Setup per user | Works in other agents | Verdict |
|---|---|---|---|---|
| **Skill + Python CLI (stdlib only)** | macOS `python3`, Windows `py -3`, no pip install | Install the plugin, done | Yes. Codex or Cursor can call the same CLI, and SKILL.md is plain Markdown | **Start here** |
| MCP server | Yes, but needs a running process and per-client config | Higher | Any MCP client | Later, as a thin wrapper over the same CLI |
| Raw `curl` in the skill | Shell quoting differs between zsh and PowerShell | None | Partly | Too brittle on Windows |
| `comfy-cli` (Comfy-Org) | Yes | pip install | — | Built for managing a local install, not a remote server's job API |

Why stdlib Python: it's already on every Mac and is a one-step install on Windows. `urllib`, `json` and `uuid` cover the whole API. Polling `GET /history/<id>` avoids needing a websocket library.

## Proposed layout (inside this folder)

```text
plugin/
  .claude-plugin/plugin.json            # name: skipbo-art; installable from a git repo marketplace
  skills/skipbo-art/
    SKILL.md                            # routing table (R1), pre-flight checklist, iteration caps, review loop
    references/
      engines.md                        # Z-Image vs Nano Banana grammars (from workflows/README.md)
      prompt-rules.md                   # R1–R9 (from docs/prompt-efficiency.md)
      styles/<style>/                   # block.md (verbatim) + refs/*.png + accepted/*.png
      spine-parts.md                    # part list, naming, pivots (from docs/spine-parts-plan.md)
    templates/                          # API-format graphs with {{PROMPT}}, {{IMAGE_1}}, {{SEED}}… slots
      nb-render.api.json  nb-edit.api.json  zimage-t2i.api.json  zimage-inpaint.api.json  rembg.api.json
    scripts/comfy.py                    # the CLI below
```

`prompts/` and `references/style-refs/` in this repo are the source for `styles/`. `tools/comfy_snapshot.py` keeps them in sync with the server.

## CLI surface (`comfy.py`)

| Command | Does | Server effect |
|---|---|---|
| `status` | GPU, queue length, reachable or not | read |
| `lint <prompt.txt> --engine zimage\|nb` | Blocks negations for Z-Image; flags history phrases ("last attempt", "rejected") and unwired `IMAGE n` mentions for Nano Banana | none |
| `run <template> --prompt-file … --image 1=path … [--seed] [--n 2] --tag moose-master` | lint, upload inputs to `agent/<user>/`, fill the template, queue, poll, download outputs, write `runs/<date>/<tag>/job.json` | **writes and queues** |
| `sheet runs/<date>/<tag>` | Makes a labelled HTML contact sheet for one-pass review (R6) | none |
| `cutout <image> [--mode BEN2\|RMBG-2.0]` | Background removal, returns a transparent PNG | **queues** |
| `fetch <prompt_id>` | Downloads outputs for a job someone else ran | read |

Guardrails built into the CLI rather than relying on the agent's memory:

- **Seed cap (R5):** `run` refuses a third identical prompt-and-inputs hash in the same `runs/` tag unless `--force`.
- **Lint gate (R2, R3):** `run` calls `lint` and stops if it fails.
- **Traceability:** a stable `client_id = claude-<user>`, an output prefix `agent/<tag>/`, and a `job.json` sidecar holding the full prompt, inputs, seed, engine and acceptance criteria.
- **Cost label:** Nano Banana jobs print "API-billed" before queuing. A `--dry-run` shows the filled graph without sending it.

## Build order

1. Convert the 6 saved workflows into API templates. Check each one with a single run, comparing against the history settings.
2. `comfy.py` with `status`, `lint`, `run` and `sheet`, plus a Windows smoke test (PowerShell and `py -3`).
3. Write SKILL.md and its references, then test them with the *writing-skills* method: run a baseline agent without the skill on three real requests (an icon, a scene, a character master), then with it, and count passes to acceptance.
4. Package as a plugin and install it on a second machine.
5. Optional: an MCP wrapper, and a weekly `comfy_snapshot.py --history` so usage can always be audited.

## Decisions needed

1. **Canonical character style.** The "shipped Blocks event characters" reference images aren't on the server. Where are they? They become `styles/blocks-characters/refs/`.
2. **Permission to run test jobs.** Building and testing step 1 needs about 10–20 jobs (a few Nano Banana calls are API-billed). Approve, or name a budget.
3. **Server auth.** The server is currently open to the internet (see `server.md`). Lock it down before the plugin is shared?
