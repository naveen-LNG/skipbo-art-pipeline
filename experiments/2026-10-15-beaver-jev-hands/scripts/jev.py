"""Minimal Jev (TypeSafe System One) client for the hand-direction experiment. Stdlib only.

ask(state, questions, images) -> response dict. `images` maps a placeholder name used in state/questions
(e.g. "{hand}") to a file path; each placeholder is replaced by a fresh UUID reference and the file goes in `assets`.
run_many(jobs, out_path, workers) runs (id, state, questions, images, meta) jobs concurrently, appends one JSON line per
answered job to out_path and skips ids already there (resumable). Retries 429/5xx with backoff.
Key: TYPESAFE_API_KEY from ~/.config/typesafe/typesafe.env (mode 600) or the environment; never printed."""
import base64, json, os, threading, time, urllib.error, urllib.request, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = os.environ.get("JEV_MODEL", "jev-1.14.0")
_envf = Path.home() / ".config/typesafe/typesafe.env"
KEY = (dict(l.strip().split("=", 1) for l in open(_envf) if "=" in l).get("TYPESAFE_API_KEY")
       if _envf.exists() else None) or os.environ.get("TYPESAFE_API_KEY")


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


def ask(state, questions, images=None, model=MODEL, tries=5):
    if not KEY:
        raise SystemExit("No TypeSafe key: put TYPESAFE_API_KEY=... in ~/.config/typesafe/typesafe.env")
    images = images or {}
    refs = {k: f"img-{uuid.uuid4()}" for k in images}
    assets = {refs[k]: {"type": "image", "format": "png" if str(p).endswith(".png") else "jpg",
                        "data_base64": base64.b64encode(Path(p).read_bytes()).decode()} for k, p in images.items()}
    body = json.dumps({"model": model, "state": _sub(state, refs), "assets": assets,
                       "questions": _sub(questions, refs)}).encode()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"}
    if images:
        headers["TypeSafe-Danger-Zone-Images"] = "true"
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(URL, body, headers), timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 ** i + 1); continue
            raise RuntimeError(f"HTTP {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError):
            if i < tries - 1:
                time.sleep(2 ** i + 1); continue
            raise


def run_many(jobs, out_path, workers=4):
    out_path = Path(out_path)
    done = {json.loads(l)["id"] for l in open(out_path)} if out_path.exists() else set()
    todo = [j for j in jobs if j[0] not in done]
    print(f"{len(todo)} to run ({len(done)} done) -> {out_path.name}", flush=True)
    lock, n = threading.Lock(), [0]

    def one(job):
        jid, state, qs, imgs, meta = job
        t0 = time.time()
        try:
            res = ask(state, qs, imgs)
        except Exception as e:                       # noqa: BLE001 - logged, the job is retried on the next run
            print(jid, "ERROR", e, flush=True); return
        row = {"id": jid, **meta, "latency_s": round(time.time() - t0, 2), "usage": res.get("usage"),
               "model": res.get("model"), "answers": res.get("answers")}
        with lock:
            with open(out_path, "a") as f:
                f.write(json.dumps(row) + "\n")
            n[0] += 1
            if n[0] % 25 == 0:
                print(f"  {n[0]}/{len(todo)}", flush=True)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    print("done", flush=True)
