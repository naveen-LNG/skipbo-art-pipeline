#!/usr/bin/env python3
"""comfy.py - drive the SkipBo ComfyUI server from any agent or shell.

Standard library only (Python 3.9+), so it runs unchanged on macOS, Windows and Linux.

  python comfy.py status
  python comfy.py lint prompt.txt --engine zimage
  python comfy.py run nb-pro --prompt-file brief.txt --image 1=char.png --image 2=style.png --tag moose
  python comfy.py run zimage-t2i --prompt-file p.txt --var WIDTH=1024 --var HEIGHT=1024 --n 2 --tag icon
  python comfy.py sheet runs/moose
  python comfy.py fetch <prompt_id> --tag moose

Environment:
  COMFY_URL        server (default https://skipbo.comfyui.liquidnitro.games)
  COMFY_USER       short name used in client_id, upload folder and output prefix (default: OS user)
  COMFY_RUNS_DIR   where outputs and job records go (default ./runs)
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import html
import json
import mimetypes
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"
DEFAULT_URL = "https://skipbo.comfyui.liquidnitro.games"
SEED_CAP = 2  # identical prompt+inputs may run at most this many times per tag (rule R5)


def env_user() -> str:
    name = os.environ.get("COMFY_USER") or getpass.getuser() or "agent"
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "agent"


def server() -> str:
    return os.environ.get("COMFY_URL", DEFAULT_URL).rstrip("/")


def runs_dir() -> Path:
    return Path(os.environ.get("COMFY_RUNS_DIR", "runs"))


# --------------------------------------------------------------------------- HTTP

def http(method: str, path: str, body: bytes | None = None, headers: dict | None = None, timeout: int = 120) -> bytes:
    req = urllib.request.Request(server() + path, data=body, method=method,
                                 headers={"User-Agent": "skipbo-comfy-cli/1", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:2000]
        raise SystemExit(f"HTTP {e.code} on {method} {path}\n{detail}")


def get_json(path: str):
    return json.loads(http("GET", path))


def post_json(path: str, payload: dict):
    return json.loads(http("POST", path, json.dumps(payload).encode(), {"Content-Type": "application/json"}))


def upload(path: Path, subfolder: str) -> str:
    """Upload an input image; returns the name LoadImage should use. Content-addressed, so re-uploads are no-ops."""
    data = path.read_bytes()
    digest = hashlib.sha1(data).hexdigest()[:10]
    name = f"{re.sub(r'[^A-Za-z0-9._-]+', '_', path.stem)[:40]}_{digest}{path.suffix.lower()}"
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts = []
    for key, value in (("subfolder", subfolder), ("type", "input"), ("overwrite", "true")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
                 f"Content-Type: {ctype}\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    res = json.loads(http("POST", "/upload/image", b"".join(parts),
                          {"Content-Type": f"multipart/form-data; boundary={boundary}"}))
    return f"{res['subfolder']}/{res['name']}" if res.get("subfolder") else res["name"]


# --------------------------------------------------------------------------- lint

NEGATION = re.compile(r"(?i)(--avoid\b|\bavoid\b|\bno\s+\w+|\bnot\b|\bwithout\b|\bdon'?t\b|\bnever\b|\bnone\b|\bnothing\b|\bexclude\b)")
HISTORY = re.compile(r"(?i)(last attempt|previous attempt|earlier attempt|was rejected|been rejected|rejected (?:three|twice|again)|"
                     r"an earlier (?:version|render)|on every previous|the last render|again,? this time)")
IMAGE_REF = re.compile(r"(?i)\b(?:image[ _]?)(\d{1,2})\b")


def lint(text: str, engine: str, wired_images: set[int] | None = None) -> list[str]:
    problems = []
    if engine == "zimage":
        for m in NEGATION.finditer(text):
            ctx = text[max(0, m.start() - 30): m.end() + 30].replace("\n", " ")
            problems.append(f"negation '{m.group(0).strip()}' is positive conditioning at cfg 1: ...{ctx}...")
        words = len(text.split())
        if words > 260:
            problems.append(f"{words} words; Z-Image prompts work best at ~80-200 visual words, most important first")
    elif engine == "nb":
        for m in HISTORY.finditer(text):
            problems.append(f"revision-history phrase '{m.group(0)}' - describe the target instead of past attempts")
        if wired_images is not None:
            mentioned = {int(n) for n in IMAGE_REF.findall(text)}
            for n in sorted(mentioned - wired_images):
                problems.append(f"prompt mentions IMAGE {n} but no image is wired to image_{n}")
    return problems


# --------------------------------------------------------------------------- templates

def load_template(name: str) -> dict:
    path = Path(name) if name.endswith(".json") else TEMPLATES / f"{name}.api.json"
    if not path.exists():
        raise SystemExit(f"template not found: {path} (available: {', '.join(sorted(p.name.split('.')[0] for p in TEMPLATES.glob('*.api.json')))})")
    return json.loads(path.read_text(encoding="utf-8"))


def fill(graph: dict, values: dict) -> dict:
    """Replace {{NAME}} placeholders. A whole-string placeholder takes the value's type.
    LoadImage nodes whose image placeholder has no value are removed with every link to them."""
    missing_nodes = set()
    for nid, node in graph.items():
        if node.get("class_type") == "LoadImage":
            m = re.fullmatch(r"\{\{(\w+)\}\}", str(node["inputs"].get("image", "")))
            if m and m.group(1) not in values:
                missing_nodes.add(nid)
    for nid in missing_nodes:
        del graph[nid]

    def sub(v):
        if isinstance(v, str):
            m = re.fullmatch(r"\{\{(\w+)\}\}", v)
            if m:
                if m.group(1) not in values:
                    raise SystemExit(f"template needs --var {m.group(1)}=...")
                return values[m.group(1)]
            return re.sub(r"\{\{(\w+)\}\}", lambda mm: str(values.get(mm.group(1), mm.group(0))), v)
        if isinstance(v, list):
            if len(v) == 2 and isinstance(v[0], str) and v[0] in missing_nodes:
                return None  # link to a removed node
            return [sub(x) for x in v]
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        return v

    out = {}
    for nid, node in graph.items():
        node = sub(node)
        node["inputs"] = {k: v for k, v in node["inputs"].items() if v is not None}
        out[nid] = node
    return out


def coerce(value: str):
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            pass
    return {"true": True, "false": False}.get(value.lower(), value)


# --------------------------------------------------------------------------- run

class GpuBusy(Exception):
    """The shared GPU ran out of memory (someone else's models are loaded). Worth retrying later."""


def wait(prompt_id: str, timeout: int) -> dict:
    start, last = time.time(), ""
    while time.time() - start < timeout:
        hist = get_json(f"/history/{prompt_id}")
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                msgs = [m for m in status.get("messages", []) if m[0] == "execution_error"]
                detail = msgs[0][1] if msgs else status
                if "OutOfMemory" in str(detail.get("exception_type", "")) or "out of memory" in str(detail.get("exception_message", "")):
                    raise GpuBusy(prompt_id)
                raise SystemExit(f"job {prompt_id} failed: {json.dumps(detail)[:1500]}")
            if status.get("completed", True):
                return entry
        q = get_json("/queue")
        running = [j[1] for j in q.get("queue_running", [])]
        pending = [j[1] for j in q.get("queue_pending", [])]
        # the host routes to worker processes, so /queue may not list our job; fall back to elapsed time
        msg = "running" if prompt_id in running else (f"queued, position {pending.index(prompt_id) + 1}" if prompt_id in pending else "in progress")
        elapsed = int(time.time() - start)
        if msg != last or elapsed % 30 < 3:
            print(f"  {prompt_id[:8]} {msg} ({elapsed}s)", file=sys.stderr)
            last = msg
        time.sleep(3)
    raise SystemExit(f"timed out after {timeout}s waiting for {prompt_id}; fetch later with: comfy.py fetch {prompt_id}")


def download_outputs(entry: dict, dest: Path, stem: str) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    for node_id, out in (entry.get("outputs") or {}).items():
        for i, im in enumerate(out.get("images", [])):
            q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im.get("subfolder", ""), "type": im.get("type", "output")})
            data = http("GET", f"/view?{q}")
            suffix = Path(im["filename"]).suffix or ".png"
            path = dest / f"{stem}_n{node_id}_{i:02d}{suffix}"
            path.write_bytes(data)
            saved.append(path)
        for key in ("text", "string"):
            if out.get(key):
                (dest / f"{stem}_n{node_id}_{key}.txt").write_text("\n".join(map(str, out[key])), encoding="utf-8")
    return saved


def resolve(path: str) -> Path:
    """Paths may be given relative to the cwd or to the skill folder (references/..., templates/...)."""
    p = Path(path)
    if p.exists() or p.is_absolute():
        return p
    alt = HERE.parent / path
    return alt if alt.exists() else p


def cmd_run(a) -> int:
    graph = load_template(a.template)
    meta = graph.pop("_meta", {})
    engine = meta.get("engine", "")
    user = env_user()
    tag = re.sub(r"[^A-Za-z0-9_-]+", "-", a.tag)
    dest = runs_dir() / tag

    values = {**meta.get("defaults", {}), **{k: coerce(v) for k, v in (kv.split("=", 1) for kv in a.var)}}
    count_var = meta.get("count_var")  # engines without a seed (Nano Banana) make variants inside one call
    if count_var:
        values[count_var] = a.n
    prompt = None
    if a.prompt_file:
        prompt = resolve(a.prompt_file).read_text(encoding="utf-8").strip()
    elif a.prompt:
        prompt = a.prompt
    if prompt is not None:
        prompt = re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), m.group(0))), prompt)
        left = re.findall(r"\{\{(\w+)\}\}", prompt)
        if left:
            raise SystemExit(f"prompt has unfilled placeholders: {', '.join(sorted(set(left)))} (pass --var NAME=...)")
        values["PROMPT"] = prompt
    values.setdefault("PREFIX", f"agent/{user}/{tag}")

    images = {}
    for spec in a.image:
        slot, path = spec.split("=", 1)
        images[int(slot)] = resolve(path)
    for n, p in images.items():
        if not p.exists():
            raise SystemExit(f"image {n} not found: {p}")

    if prompt is not None and engine:
        problems = lint(prompt, engine, set(images) if engine == "nb" else None)
        if problems:
            print("lint:\n  - " + "\n  - ".join(problems), file=sys.stderr)
            if not a.force:
                raise SystemExit("lint failed; fix the prompt or pass --force")

    # seed cap (R5): identical prompt + inputs + vars, counted in this tag's ledger
    fingerprint = hashlib.sha1(json.dumps([a.template, prompt, sorted((k, str(v)) for k, v in values.items() if k not in ("SEED", "PREFIX")),
                                           [hashlib.sha1(images[k].read_bytes()).hexdigest() for k in sorted(images)]]).encode()).hexdigest()[:12]
    ledger = dest / "ledger.jsonl"
    previous = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()] if ledger.exists() else []
    same = sum(1 for r in previous if r.get("fingerprint") == fingerprint)
    if same + a.n > SEED_CAP and not a.force:
        raise SystemExit(f"seed cap: this exact prompt+inputs already ran {same}x in '{tag}'. Change the words, mask, "
                         f"reference or denoise instead of re-rolling (or pass --force).")

    if a.dry_run:
        for n, p in images.items():
            values[f"IMAGE_{n}"] = f"<upload {p.name}>"
        values.setdefault("SEED", 0)
        print(json.dumps(fill(json.loads(json.dumps(graph)), values), indent=2, ensure_ascii=False))
        return 0

    for n, p in images.items():
        values[f"IMAGE_{n}"] = upload(p, f"agent/{user}")
    if meta.get("billed"):
        print(f"note: {a.template} calls a paid API ({meta['billed']}) - {a.n} call(s)", file=sys.stderr)

    dest.mkdir(parents=True, exist_ok=True)
    client_id = f"claude-{user}"
    results = []
    base_seed = a.seed if a.seed is not None else random.randint(1, 2**31)
    jobs = []
    for i in range(1 if count_var else a.n):
        v = dict(values, SEED=base_seed + i)
        g = fill(json.loads(json.dumps(graph)), v)
        res = post_json("/prompt", {"prompt": g, "client_id": client_id})
        if res.get("node_errors"):
            raise SystemExit(f"node errors: {json.dumps(res['node_errors'])[:2000]}")
        jobs.append((res["prompt_id"], v["SEED"], g))
        print(f"queued {res['prompt_id']} seed={v['SEED']}", file=sys.stderr)

    for prompt_id, seed, g in jobs:
        t0 = time.time()
        for attempt in range(4):
            try:
                entry = wait(prompt_id, a.timeout)
                break
            except GpuBusy:
                if attempt == 3:
                    raise SystemExit("the shared GPU is still out of memory after 3 retries; try again later")
                pause = 60 * (attempt + 1)
                print(f"  GPU out of memory (shared server busy); retrying in {pause}s", file=sys.stderr)
                time.sleep(pause)
                prompt_id = post_json("/prompt", {"prompt": g, "client_id": client_id})["prompt_id"]
        stem = f"{time.strftime('%m%d_%H%M%S')}_s{seed}"
        files = download_outputs(entry, dest, stem)
        record = {"prompt_id": prompt_id, "template": a.template, "engine": engine, "seed": seed, "fingerprint": fingerprint,
                  "prompt": prompt, "vars": {k: v for k, v in values.items() if k != "PROMPT"},
                  "inputs": {str(k): str(p) for k, p in images.items()}, "criteria": a.criteria,
                  "outputs": [str(f) for f in files], "seconds": round(time.time() - t0, 1), "client_id": client_id}
        (dest / f"{stem}.job.json").write_text(json.dumps({**record, "graph": g}, indent=2, ensure_ascii=False), encoding="utf-8")
        with ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        results.append(record)
        for p in files:
            print(p)
    return 0


def cmd_fetch(a) -> int:
    hist = get_json(f"/history/{a.prompt_id}")
    if a.prompt_id not in hist:
        raise SystemExit("not in history (still running, or older than the ~3 day retention)")
    for p in download_outputs(hist[a.prompt_id], runs_dir() / a.tag, f"fetch_{a.prompt_id[:8]}"):
        print(p)
    return 0


def cmd_status(a) -> int:
    s = get_json("/system_stats")
    q = get_json("/queue")
    dev = s["devices"][0]
    print(f"{server()}  ComfyUI {s['system']['comfyui_version']}")
    print(f"GPU {dev['name'].split(':')[0].strip()}  VRAM free {dev['vram_free'] / 2**30:.1f}/{dev['vram_total'] / 2**30:.1f} GB")
    print(f"queue: {len(q.get('queue_running', []))} running, {len(q.get('queue_pending', []))} pending")
    print("templates:", ", ".join(sorted(p.name.split(".")[0] for p in TEMPLATES.glob("*.api.json"))))
    return 0


def cmd_lint(a) -> int:
    text = Path(a.file).read_text(encoding="utf-8")
    wired = set(int(x) for x in a.wired.split(",")) if a.wired else None
    problems = lint(text, a.engine, wired)
    print("ok" if not problems else "\n".join(f"- {p}" for p in problems))
    return 1 if problems else 0


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"not a png: {path}")
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def cmd_size(a) -> int:
    for f in a.files:
        w, h = png_size(Path(f))
        print(f"{w}x{h}\t{f}")
    return 0


SCALE_GRAPH = {
    "1": {"class_type": "LoadImage", "inputs": {"image": "{{IMAGE_1}}"}},
    "2": {"class_type": "ImageScaleBy", "inputs": {"image": ["1", 0], "upscale_method": "lanczos", "scale_by": "{{BY}}"}},
    "3": {"class_type": "MaskToImage", "inputs": {"mask": ["1", 1]}},
    "4": {"class_type": "ImageScaleBy", "inputs": {"image": ["3", 0], "upscale_method": "bilinear", "scale_by": "{{BY}}"}},
    "5": {"class_type": "ImageToMask", "inputs": {"image": ["4", 0], "channel": "red"}},
    "6": {"class_type": "JoinImageWithAlpha", "inputs": {"image": ["2", 0], "alpha": ["5", 0]}},
    "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "{{PREFIX}}"}},
}


def cmd_scale(a) -> int:
    """Rescale transparent parts on the server (keeps alpha). Ratio from --by, or target/anchor widths."""
    if a.match_width:
        by = None  # per file, below
    elif a.by:
        by = a.by
    elif a.anchor and a.target:
        by = png_size(Path(a.target))[0] / png_size(Path(a.anchor))[0]
    else:
        raise SystemExit("give --match-width <png>, --by, or --anchor and --target")
    if by is not None:
        print(f"scale factor {by:.4f}", file=sys.stderr)
    user = env_user()
    target_w = png_size(Path(a.match_width))[0] if a.match_width else None
    factors = {}
    dest = runs_dir() / a.tag
    dest.mkdir(parents=True, exist_ok=True)
    for f in a.files:
        src = Path(f)
        factor = by if by is not None else target_w / png_size(src)[0]
        factors[src.name] = round(factor, 4)
        g = fill(json.loads(json.dumps(SCALE_GRAPH)), {"IMAGE_1": upload(src, f"agent/{user}"), "BY": factor,
                                                       "PREFIX": f"agent/{user}/{a.tag}/{src.stem}"})
        res = post_json("/prompt", {"prompt": g, "client_id": f"claude-{user}"})
        entry = wait(res["prompt_id"], a.timeout)
        for out in (entry.get("outputs") or {}).values():
            for im in out.get("images", []):
                q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im.get("subfolder", ""), "type": "output"})
                target = dest / src.name
                target.write_bytes(http("GET", f"/view?{q}"))
                print(target)
    (dest / "scale.json").write_text(json.dumps({"scale_by": by, "match_width": a.match_width, "anchor": a.anchor, "target": a.target, "factors": factors}, indent=2), encoding="utf-8")
    return 0


def cmd_sheet(a) -> int:
    folder = Path(a.folder)
    images = sorted(p for p in folder.rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    cards = []
    for i, p in enumerate(images, 1):
        rel = p.relative_to(folder).as_posix()
        cards.append(f'<figure><img src="{html.escape(rel)}" loading="lazy"><figcaption><b>{i}</b> {html.escape(rel)}</figcaption></figure>')
    page = f"""<!doctype html><meta charset="utf-8"><title>{html.escape(folder.name)} contact sheet</title>
<style>body{{font:13px system-ui;margin:16px;background:#f2f2f2}}main{{display:grid;grid-template-columns:repeat(auto-fill,minmax({a.size}px,1fr));gap:12px}}
figure{{margin:0;background:repeating-conic-gradient(#ddd 0 25%,#fff 0 50%) 0 0/16px 16px;border:1px solid #ccc;border-radius:6px;overflow:hidden}}
img{{width:100%;display:block}}figcaption{{background:#fff;padding:4px 6px;word-break:break-all}}</style>
<h1>{html.escape(folder.name)} — {len(images)} images</h1><p>Reply with the numbers to keep and one sentence per rejection.</p><main>{''.join(cards)}</main>"""
    out = folder / "sheet.html"
    out.write_text(page, encoding="utf-8")
    print(out)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)

    p = sub.add_parser("lint")
    p.add_argument("file")
    p.add_argument("--engine", choices=["zimage", "nb"], required=True)
    p.add_argument("--wired", help="comma list of wired image slots, e.g. 1,2 (nb only)")
    p.set_defaults(fn=cmd_lint)

    p = sub.add_parser("run")
    p.add_argument("template")
    p.add_argument("--prompt-file")
    p.add_argument("--prompt")
    p.add_argument("--image", action="append", default=[], metavar="N=PATH")
    p.add_argument("--var", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--tag", required=True, help="asset name; groups outputs, ledger and seed cap")
    p.add_argument("--n", type=int, default=1, help="variants (consecutive seeds)")
    p.add_argument("--seed", type=int)
    p.add_argument("--criteria", action="append", default=[], help="acceptance criterion (repeatable), stored with the job")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="override lint and seed cap")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("fetch")
    p.add_argument("prompt_id")
    p.add_argument("--tag", default="fetched")
    p.set_defaults(fn=cmd_fetch)

    p = sub.add_parser("size", help="print png width x height (no server call)")
    p.add_argument("files", nargs="+")
    p.set_defaults(fn=cmd_size)

    p = sub.add_parser("scale", help="rescale transparent parts, e.g. face parts to the body's head size")
    p.add_argument("files", nargs="+")
    p.add_argument("--by", type=float)
    p.add_argument("--match-width", help="scale every file so its width equals this png's width (e.g. body head base)")
    p.add_argument("--anchor", help="face-sheet head base png (scale anchor)")
    p.add_argument("--target", help="body-sheet head base png")
    p.add_argument("--tag", required=True)
    p.add_argument("--timeout", type=int, default=300)
    p.set_defaults(fn=cmd_scale)

    p = sub.add_parser("sheet")
    p.add_argument("folder")
    p.add_argument("--size", type=int, default=220)
    p.set_defaults(fn=cmd_sheet)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
