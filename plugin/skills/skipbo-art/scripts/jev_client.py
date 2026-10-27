#!/usr/bin/env python3
"""jev_client.py - the Jev (TypeSafe System One) client behind the optional Jev review steps. Stdlib only.

Jev answers typed questions about a state that may hold images: `choice` ({"choice", "probabilities"}), `noul`
({"noul": P(true)}) and `score` ({"score": 0..n}). A state or question refers to an image by a placeholder such as
"{hand}"; ask() replaces it with a fresh reference and sends the image in `assets`.

  available()                     True when a key is set; every Jev step skips cleanly without one
  ask(state, questions, images)   one request -> the response dict (retries 429/5xx and network errors)
  run(jobs, cache=..., workers=4) many requests at once -> {job id: answers}

The key: TYPESAFE_API_KEY in the environment, else in ~/.config/typesafe/typesafe.env (mode 600). It is never
printed. Answers are cached by content (model, state, questions, image bytes) in a JSONL file, so re-running a
check on unchanged pictures costs nothing. The model is jev-1.14.0 (JEV_MODEL overrides it): the one the
2026-10-15 beaver experiment calibrated every threshold on. Images should be at least 320 px a side.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = os.environ.get("JEV_MODEL", "jev-1.14.0")
KEY_FILE = Path("~/.config/typesafe/typesafe.env")
SKIP = "SKIP  jev: no TYPESAFE_API_KEY (environment or ~/.config/typesafe/typesafe.env)"
USAGE = {"calls": 0, "cached": 0, "input_tokens": 0}      # this process's totals, for the reports


class JevError(RuntimeError):
    pass


def api_key():
    if os.environ.get("TYPESAFE_API_KEY"):
        return os.environ["TYPESAFE_API_KEY"]
    f = KEY_FILE.expanduser()
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            k, _, v = line.strip().partition("=")
            if k.strip() == "TYPESAFE_API_KEY" and v.strip():
                return v.strip().strip("'\"")
    return None


def available() -> bool:
    return api_key() is not None


def _image_bytes(src) -> bytes:
    return src if isinstance(src, (bytes, bytearray)) else Path(src).read_bytes()


def _sub(obj, refs):
    if isinstance(obj, str):
        for k, v in refs.items():
            obj = obj.replace(k, v)
        return obj
    if isinstance(obj, list):
        return [_sub(x, refs) for x in obj]
    if isinstance(obj, dict):
        return {k: _sub(v, refs) for k, v in obj.items()}     # keys stay text (the API never replaces them)
    return obj


def ask(state, questions, images=None, model=None, tries=5) -> dict:
    """One request. `images` maps a placeholder used in state/questions to a PNG path or PNG bytes."""
    key = api_key()
    if not key:
        raise JevError(SKIP)
    images = images or {}
    refs = {k: f"img-{uuid.uuid4()}" for k in images}
    assets = {refs[k]: {"type": "image", "format": "png", "data_base64": base64.b64encode(_image_bytes(p)).decode()}
              for k, p in images.items()}
    body = json.dumps({"model": model or MODEL, "state": _sub(state, refs), "assets": assets,
                       "questions": _sub(questions, refs)}).encode()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    if images:
        headers["TypeSafe-Danger-Zone-Images"] = "true"
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(URL, body, headers), timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 ** i + 1)
                continue
            raise JevError(f"HTTP {e.code}: {detail}") from None
        except (OSError, http.client.HTTPException, ValueError) as e:     # dropped connection, DNS, timeout, bad JSON
            if i < tries - 1:
                time.sleep(2 ** i + 1)
                continue
            raise JevError(f"network: {e}") from None
    raise JevError("no answer")


def job_key(state, questions, images, model=None) -> str:
    """Content hash of one request: placeholders and image bytes, not file names, so a re-render that changes no
    pixel hits the cache."""
    h = hashlib.sha1(json.dumps([model or MODEL, state, questions], sort_keys=True).encode())
    for k in sorted(images or {}):
        h.update(k.encode())
        h.update(hashlib.sha1(_image_bytes(images[k])).digest())
    return h.hexdigest()


def _load_cache(path):
    out = {}
    if path and Path(path).is_file():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                out[row["key"]] = row["answers"]
            except (ValueError, KeyError):
                continue                  # a half-written line from an interrupted run
    return out


def run(jobs, cache=None, workers=4, quiet=False) -> dict:
    """jobs: [(id, state, questions, images)]. Returns {id: answers} for every job answered (from the cache or
    Jev); a job that still fails after the retries is left out and reported on stderr."""
    store = _load_cache(cache)
    keys = {jid: job_key(st, qs, im) for jid, st, qs, im in jobs}
    out = {jid: store[k] for jid, k in keys.items() if k in store}
    USAGE["cached"] += len(out)
    todo = [j for j in jobs if j[0] not in out]
    if not todo:
        return out
    if cache:
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    def one(job):
        jid, st, qs, im = job
        try:
            res = ask(st, qs, im)
        except JevError as e:
            print(f"jev: {jid}: {e}", file=sys.stderr)
            return
        answers = res.get("answers") or {}
        with lock:
            out[jid] = answers
            USAGE["calls"] += 1
            USAGE["input_tokens"] += (res.get("usage") or {}).get("input_tokens", 0)
            if cache:
                with open(cache, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"key": keys[jid], "id": jid, "answers": answers}) + "\n")

    if not quiet:
        print(f"jev: {len(todo)} call(s), {len(out)} cached", file=sys.stderr, flush=True)
    with ThreadPoolExecutor(max(1, workers)) as ex:
        list(ex.map(one, todo))
    return out
