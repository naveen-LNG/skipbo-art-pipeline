#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pillow"]
# ///
"""Build the review gallery: every rig, every animation, one page.

  python3 tools/build_gallery.py                       # discover rigs, rebuild what changed
  python3 tools/build_gallery.py --rig fox:pro=path/to/rig_pro   # add / override one rig
  python3 tools/build_gallery.py --list                # show what would be built, build nothing

For each rig (<dir>/<name>.json + <name>.atlas + page images) this writes gallery/assets/<char>-<variant>/:
  <name>.json        the skeleton, minified (attachment sizes untouched: region attachments keep their JSON
                     width/height so the runtime scales the smaller texture up; meshes map through UVs)
  <name>.atlas       Spine 4.x atlas text for the new pages
  <name>_<n>.webp    the regions, downscaled (--scale, default 0.5) and packed into few power-of-two pages
                     (webp q92 by default, --format png for exact pixels)
and gallery/manifest.json describing every rig (animations + durations, bounds, QA status, source).

Idempotent: a rig whose sources did not change since the last build is not rebuilt. Rigs that disappear
are dropped. A rig that fails to read (e.g. half-written by another job) keeps its previous build and
is listed under "errors" in the manifest.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # plain `python3` without Pillow: re-run under uv, which reads the header above
    if os.environ.get("BUILD_GALLERY_REEXEC") or not shutil.which("uv"):
        raise SystemExit("build_gallery.py needs Pillow: `uv run tools/build_gallery.py` or `pip install pillow`")
    os.environ["BUILD_GALLERY_REEXEC"] = "1"
    os.execvp("uv", ["uv", "run", "--quiet", "--with", "pillow", "python3", __file__, *sys.argv[1:]])

ROOT = Path(__file__).resolve().parent.parent
BUILDER_VERSION = 4

# (glob relative to repo root, variant). Later matches for the same character+variant win, so the
# newest experiment folders come last.
DEFAULT_SOURCES = [
    ("experiments/2026-10-11-rig-annotations/*/rig", "legacy"),
    ("experiments/2026-10-15-beaver-jev-hands/*/rig", "legacy"),
    ("experiments/2026-10-16-spine-pro/*/rig_legacy", "legacy"),
    ("experiments/2026-10-16-spine-pro/*/rig_pro", "pro"),
    ("experiments/2026-10-16-cast/*/rig", "legacy"),
    ("experiments/2026-10-16-cast/*/rig_legacy", "legacy"),
    ("experiments/2026-10-16-cast/*/rig_pro", "pro"),
]
CHAR_ORDER = ["fox", "moose", "beaver", "rabbit", "redpanda", "bear"]
VARIANT_ORDER = ["legacy", "pro"]


# ----------------------------------------------------------------------------------------------- atlas

def parse_atlas(text: str) -> list[dict]:
    """Spine 4.x atlas text -> [{name, size, filter, pma, regions: [{name, bounds, offsets, rotate, index}]}]."""
    pages, page, region = [], None, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            page, region = None, None
            continue
        if ":" in line:
            key, val = (s.strip() for s in line.split(":", 1))
            vals = [v.strip() for v in val.split(",")]
            target = region if region is not None else page
            if target is None:
                continue
            if region is None:  # page field
                if key == "size":
                    page["size"] = (int(vals[0]), int(vals[1]))
                elif key == "filter":
                    page["filter"] = val
                elif key == "pma":
                    page["pma"] = val == "true"
                else:
                    page.setdefault("extra", {})[key] = val
            else:
                if key == "bounds":
                    region["bounds"] = tuple(int(v) for v in vals)
                elif key == "offsets":
                    region["offsets"] = tuple(int(v) for v in vals)
                elif key == "rotate":
                    region["rotate"] = 90 if val == "true" else (0 if val == "false" else int(val))
                elif key == "index":
                    region["index"] = int(val)
                elif key in ("xy", "size", "orig", "offset"):  # legacy 3.x style fields
                    region.setdefault("legacy", {})[key] = tuple(int(v) for v in vals)
                else:
                    region.setdefault("extra", {})[key] = val
            continue
        if page is None:
            page = {"name": line, "regions": [], "pma": False}
            pages.append(page)
            region = None
        else:
            region = {"name": line, "rotate": 0, "index": -1}
            page["regions"].append(region)
    for p in pages:
        for r in p["regions"]:
            if "bounds" not in r and "legacy" in r:
                lg = r["legacy"]
                r["bounds"] = (*lg["xy"], *lg["size"])
                if "orig" in lg:
                    r["offsets"] = (*lg.get("offset", (0, 0)), *lg["orig"])
    return pages


def extract_regions(rig_dir: Path, pages: list[dict]) -> list[dict]:
    """Crop every region out of its source page, un-rotated. Returns [{name, index, image, offsets}]."""
    out = []
    for p in pages:
        im = Image.open(rig_dir / p["name"]).convert("RGBA")
        sx = im.width / p["size"][0] if "size" in p else 1.0  # tolerate a page saved at another size
        sy = im.height / p["size"][1] if "size" in p else 1.0
        for r in p["regions"]:
            x, y, w, h = r["bounds"]
            rot = r.get("rotate", 0)
            fw, fh = (h, w) if rot in (90, 270) else (w, h)
            crop = im.crop((round(x * sx), round(y * sy), round((x + fw) * sx), round((y + fh) * sy)))
            if rot == 90:
                crop = crop.transpose(Image.Transpose.ROTATE_90)
            elif rot == 270:
                crop = crop.transpose(Image.Transpose.ROTATE_270)
            elif rot == 180:
                crop = crop.transpose(Image.Transpose.ROTATE_180)
            if crop.size != (w, h):
                crop = crop.resize((w, h), Image.Resampling.LANCZOS)
            offsets = r.get("offsets") or (0, 0, w, h)
            out.append({"name": r["name"], "index": r.get("index", -1), "image": crop, "offsets": offsets})
    return out


# ---------------------------------------------------------------------------------------------- packer

def _pot_sizes(max_size: int):
    sizes, s = [], 64
    while s <= max_size:
        sizes.append(s)
        s *= 2
    combos = [(w, h) for w in sizes for h in sizes if max(w, h) <= 2 * min(w, h)]
    return sorted(combos, key=lambda wh: (wh[0] * wh[1], wh[1]))


def _maxrects_fill(items: list, W: int, H: int, pad: int) -> dict:
    """MaxRects (best short side fit), no rotation. items: [(key, w, h)] -> {key: (x, y)} for those that fit.
    Each item occupies w+pad x h+pad; the page border gets pad/2 so neighbours never touch."""
    free = [(pad // 2, pad // 2, W - pad // 2, H - pad // 2)]  # x0, y0, x1, y1 (exclusive)
    placed = {}
    for key, w, h in items:
        ww, hh = w + pad, h + pad
        best, best_score = None, None
        for fx0, fy0, fx1, fy1 in free:
            fw, fh = fx1 - fx0, fy1 - fy0
            # the last row/column of the page doesn't need trailing padding
            need_w = ww if fx0 + ww <= W - pad // 2 else w
            need_h = hh if fy0 + hh <= H - pad // 2 else h
            if need_w <= fw and need_h <= fh:
                score = (min(fw - need_w, fh - need_h), max(fw - need_w, fh - need_h))
                if best_score is None or score < best_score:
                    best, best_score = (fx0, fy0, need_w, need_h), score
        if best is None:
            continue
        bx, by, bw, bh = best
        placed[key] = (bx, by)
        used = (bx, by, bx + bw, by + bh)
        new_free = []
        for f in free:
            if used[0] >= f[2] or used[2] <= f[0] or used[1] >= f[3] or used[3] <= f[1]:
                new_free.append(f)
                continue
            if used[0] > f[0]:
                new_free.append((f[0], f[1], used[0], f[3]))
            if used[2] < f[2]:
                new_free.append((used[2], f[1], f[2], f[3]))
            if used[1] > f[1]:
                new_free.append((f[0], f[1], f[2], used[1]))
            if used[3] < f[3]:
                new_free.append((f[0], used[3], f[2], f[3]))
        # prune rectangles contained in others
        new_free = [a for i, a in enumerate(new_free)
                    if a[2] > a[0] and a[3] > a[1]
                    and not any(j != i and b[0] <= a[0] and b[1] <= a[1] and b[2] >= a[2] and b[3] >= a[3]
                                and (b != a or j < i) for j, b in enumerate(new_free))]
        free = new_free
    return placed


def pack(sizes: dict, max_size: int = 2048, pad: int = 4) -> list[dict]:
    """sizes: {key: (w, h)} -> [{size: (W, H), rects: {key: (x, y, w, h)}}]; few power-of-two pages."""
    for k, (w, h) in sizes.items():
        if w + pad > max_size or h + pad > max_size:
            raise ValueError(f"region {k} ({w}x{h}) does not fit a {max_size}px page")
    remaining = sorted(sizes, key=lambda k: (-max(sizes[k]), -sizes[k][0] * sizes[k][1], str(k)))
    pages = []
    while remaining:
        items = [(k, *sizes[k]) for k in remaining]
        area = sum((w + pad) * (h + pad) for _, w, h in items)
        chosen = None
        for W, H in _pot_sizes(max_size):
            if W * H < area:
                continue
            placed = _maxrects_fill(items, W, H, pad)
            if len(placed) == len(items):
                chosen = (W, H, placed)
                break
        if chosen is None:  # fill one full page, continue with the rest
            placed = _maxrects_fill(items, max_size, max_size, pad)
            chosen = (max_size, max_size, placed)
        W, H, placed = chosen
        pages.append({"size": (W, H), "rects": {k: (*placed[k], *sizes[k]) for k in placed}})
        remaining = [k for k in remaining if k not in placed]
    return pages


def write_packed(regions: list[dict], out_dir: Path, base: str, scale: float, max_size: int, pad: int,
                 filter_: str, fmt: str = "png", quality: int = 92, trim: set | None = None) -> tuple[str, list[str]]:
    """Downscale + pack regions, save the pages into out_dir (png, or webp at `quality`; webp_lossless).
    Regions named in `trim` (used only by region attachments) get their transparent border stripped and
    recorded as atlas offsets, which the runtime honours: same picture, smaller pages, and skeleton bounds
    that follow the visible pixels. Returns (atlas text, page file names)."""
    scaled = {}
    for i, r in enumerate(regions):
        im = r["image"]
        w, h = max(1, round(im.width * scale)), max(1, round(im.height * scale))
        ox, oy, ow, oh = r["offsets"]
        ow, oh = max(w, round(ow * scale)), max(h, round(oh * scale))
        ox, oy = min(round(ox * scale), ow - w), min(round(oy * scale), oh - h)
        small = im.resize((w, h), Image.Resampling.LANCZOS) if (w, h) != im.size else im
        if trim and r["name"] in trim:
            box = small.getchannel("A").point(lambda a: 255 if a > 2 else 0).getbbox()
            if box:
                l, t, rr, b = max(0, box[0] - 1), max(0, box[1] - 1), min(w, box[2] + 1), min(h, box[3] + 1)
                if (rr - l) * (b - t) < 0.95 * w * h:
                    small = small.crop((l, t, rr, b))
                    ox, oy = ox + l, oy + (h - b)  # Spine offsets: x from the left, y from the bottom
                    w, h = rr - l, b - t
        scaled[i] = {"r": r, "im": small, "offsets": (ox, oy, ow, oh)}
    layout = pack({i: s["im"].size for i, s in scaled.items()}, max_size, pad)
    lines, files = [], []
    for n, page in enumerate(layout):
        fname = f"{base}_{n}.{'png' if fmt == 'png' else 'webp'}"
        canvas = Image.new("RGBA", page["size"], (0, 0, 0, 0))
        lines += [fname, f"size: {page['size'][0]},{page['size'][1]}", f"filter: {filter_}"]
        for i in sorted(page["rects"], key=lambda k: (scaled[k]["r"]["name"], scaled[k]["r"]["index"])):
            x, y, w, h = page["rects"][i]
            s = scaled[i]
            canvas.paste(s["im"], (x, y))
            lines += [s["r"]["name"], f"bounds: {x},{y},{w},{h}"]
            ox, oy, ow, oh = s["offsets"]
            if (ox, oy, ow, oh) != (0, 0, w, h):
                lines.append(f"offsets: {ox},{oy},{ow},{oh}")
            if s["r"]["index"] != -1:
                lines.append(f"index: {s['r']['index']}")
        lines.append("")
        if fmt == "png":
            canvas.save(out_dir / fname, optimize=True)
        elif fmt == "webp_lossless":
            canvas.save(out_dir / fname, lossless=True, method=6)
        else:
            canvas.save(out_dir / fname, quality=quality, alpha_quality=100, method=6)
        files.append(fname)
    return "\n".join(lines), files


# -------------------------------------------------------------------------------------------- skeleton

def anim_duration(anim) -> float:
    """Largest key time anywhere in a Spine JSON animation."""
    best = 0.0
    stack = [anim]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            t = node.get("time")
            if isinstance(t, (int, float)):
                best = max(best, float(t))
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return round(best, 4)


def attachment_names(skel: dict) -> dict:
    """{region/path name: type} for every textured attachment the skeleton references."""
    names = {}
    for skin in skel.get("skins", []):
        for atts in skin.get("attachments", {}).values():
            for name, a in atts.items():
                t = a.get("type", "region")
                if t not in ("region", "mesh", "linkedmesh"):
                    continue
                path = a.get("path", name)
                if "sequence" in a:
                    seq = a["sequence"]
                    digits, start, count = seq.get("digits", 0), seq.get("start", 1), seq.get("count", 1)
                    for k in range(count):
                        names[f"{path}{str(start + k).zfill(digits)}"] = t
                else:
                    names[path] = t
    return names


def mesh_names(skel: dict) -> set:
    """Region names used by any mesh (never trimmed: mesh UVs span the whole original image)."""
    return {n for n, t in attachment_names(skel).items() if t != "region"} | {
        a.get("path", name) for skin in skel.get("skins", []) for atts in skin.get("attachments", {}).values()
        for name, a in atts.items() if a.get("type") in ("mesh", "linkedmesh")}


def qa_status(rig_dir: Path) -> dict:
    """Summarise a QA report next to the rig, if any."""
    for cand in ["qa/report.json", "qa_report.json", "qa.json", "qa/qa.json", "qa_pro/report.json"]:
        p = rig_dir / cand
        if not p.is_file():
            continue
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        checks = {}
        if isinstance(d, dict):
            src = d.get("checks", d)
            if isinstance(src, dict):
                for k, v in src.items():
                    if isinstance(v, dict) and "pass" in v:
                        checks[k] = bool(v["pass"])
                    elif isinstance(v, bool):
                        checks[k] = v
        if checks:
            failing = [k for k, v in checks.items() if not v]
            return {"status": "fail" if failing else "pass", "failing": failing, "checks": checks,
                    "source": str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)}
    p = rig_dir / "qa_summary.txt"
    if p.is_file():
        checks = {}
        for line in p.read_text().splitlines():
            m = re.match(r"\s*(PASS|FAIL|WARN)\s+(\S+)", line)
            if m:
                checks[m.group(2)] = m.group(1) != "FAIL"
        if checks:
            failing = [k for k, v in checks.items() if not v]
            return {"status": "fail" if failing else "pass", "failing": failing, "checks": checks,
                    "source": str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)}
    return {"status": "none", "failing": [], "checks": {}}


# ----------------------------------------------------------------------------------------------- rigs

def find_skeleton(rig_dir: Path) -> tuple[Path, Path]:
    """<name>.json with a matching <name>.atlas in rig_dir."""
    for atlas in sorted(rig_dir.glob("*.atlas")):
        js = atlas.with_suffix(".json")
        if js.is_file():
            return js, atlas
    raise FileNotFoundError(f"no <name>.json + <name>.atlas pair in {rig_dir}")


def discover(extra: list[str], use_defaults: bool = True) -> dict:
    """{(char, variant): rig_dir}."""
    rigs = {}
    if use_defaults:
        for pattern, variant in DEFAULT_SOURCES:
            for d in sorted(glob.glob(str(ROOT / pattern))):
                d = Path(d)
                if d.is_dir() and any(d.glob("*.atlas")):
                    rigs[(d.parent.name, variant)] = d
    for spec in extra:
        m = re.fullmatch(r"([\w.-]+):([\w.-]+)=(.+)", spec)
        if not m:
            raise SystemExit(f"--rig wants name:variant=path, got {spec!r}")
        p = Path(m.group(3)).expanduser()
        rigs[(m.group(1), m.group(2))] = (p if p.is_absolute() else Path.cwd() / p).resolve()
    return rigs


def source_stamp(rig_dir: Path, js: Path, atlas: Path, opts: dict) -> str:
    h = hashlib.sha1(json.dumps(opts, sort_keys=True).encode())
    h.update(str(BUILDER_VERSION).encode())
    files = [js, atlas] + [rig_dir / p["name"] for p in parse_atlas(atlas.read_text())]
    for f in files:
        st = f.stat()
        h.update(f"{f.name}:{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()[:16]


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def build_rig(char: str, variant: str, rig_dir: Path, out_root: Path, opts: dict, previous: dict | None) -> dict:
    js, atlas = find_skeleton(rig_dir)
    stamp = source_stamp(rig_dir, js, atlas, opts)
    rid = f"{char}-{variant}"
    out_dir = out_root / "assets" / rid
    if previous and previous.get("stamp") == stamp and all((out_root / f).is_file() for f in previous["files"]):
        entry = dict(previous)
        entry["qa"] = qa_status(rig_dir)
        entry["rebuilt"] = False
        return entry

    skel = json.loads(js.read_text())
    if "skeleton" not in skel or "bones" not in skel:
        raise ValueError(f"{js.name} is not a Spine skeleton")
    pages = parse_atlas(atlas.read_text())
    regions = extract_regions(rig_dir, pages)
    have = {r["name"] for r in regions}
    needed = attachment_names(skel)
    missing = sorted(n for n in needed if n not in have)

    tmp = out_root / "assets" / f".{rid}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    base = js.stem
    atlas_text, page_files = write_packed(regions, tmp, base, opts["scale"], opts["max_page"], opts["pad"],
                                          opts["filter"], opts.get("format", "png"), opts.get("quality", 92),
                                          trim={n for n, t in needed.items() if t == "region"} - mesh_names(skel)
                                          if opts.get("trim", True) else None)
    (tmp / f"{base}.atlas").write_text(atlas_text, encoding="utf-8")
    skel_out = dict(skel)
    skel_out["skeleton"] = dict(skel["skeleton"], images="")
    (tmp / f"{base}.json").write_text(json.dumps(skel_out, separators=(",", ":")), encoding="utf-8")
    shutil.rmtree(out_dir, ignore_errors=True)
    tmp.rename(out_dir)

    sk = skel["skeleton"]
    anims = [{"name": n, "duration": anim_duration(a)} for n, a in skel.get("animations", {}).items()]
    files = [f"assets/{rid}/{base}.json", f"assets/{rid}/{base}.atlas"] + [f"assets/{rid}/{f}" for f in page_files]
    src_bytes = sum((rig_dir / p["name"]).stat().st_size for p in pages)
    return {
        "id": rid, "character": char, "variant": variant, "name": base,
        "json": files[0], "atlas": files[1], "pages": files[2:], "files": files,
        "bounds": {k: sk.get(k, 0) for k in ("x", "y", "width", "height")},
        "spine": sk.get("spine", ""),
        "animations": anims,
        "skins": [s.get("name", "default") for s in skel.get("skins", [])],
        "counts": {"bones": len(skel.get("bones", [])), "slots": len(skel.get("slots", [])),
                   "regions": len(regions), "meshes": sum(1 for t in needed.values() if t != "region"),
                   "ik": len(skel.get("ik", [])), "transform": len(skel.get("transform", [])),
                   "path": len(skel.get("path", [])), "physics": len(skel.get("physics", []))},
        "missing_regions": missing,
        "source": rel(rig_dir),
        "source_mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(js.stat().st_mtime)),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "bytes": sum((out_root / f).stat().st_size for f in files),
        "source_image_bytes": src_bytes,
        "stamp": stamp,
        "qa": qa_status(rig_dir),
        "rebuilt": True,
    }


def sort_key(entry: dict):
    c, v = entry["character"], entry["variant"]
    return (CHAR_ORDER.index(c) if c in CHAR_ORDER else len(CHAR_ORDER), c,
            VARIANT_ORDER.index(v) if v in VARIANT_ORDER else len(VARIANT_ORDER), v)


def gallery_size(out_root: Path) -> tuple[int, int]:
    """(bytes, files) of what gets published: everything except _shots/ and dotfiles."""
    total, count = 0, 0
    for p in out_root.rglob("*"):
        parts = p.relative_to(out_root).parts
        if p.is_file() and not any(s.startswith((".", "_")) for s in parts):
            total += p.stat().st_size
            count += 1
    return total, count


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rig", action="append", default=[], metavar="NAME:VARIANT=PATH",
                    help="add or override a rig (repeatable)")
    ap.add_argument("--only-rigs", action="store_true", help="skip discovery, use only --rig entries")
    ap.add_argument("--out", default=str(ROOT / "gallery"), help="gallery folder (default: gallery/)")
    ap.add_argument("--scale", type=float, default=0.5, help="texture scale (default 0.5)")
    ap.add_argument("--max-page", type=int, default=2048, help="max atlas page size, power of two")
    ap.add_argument("--pad", type=int, default=4, help="px between packed regions")
    ap.add_argument("--filter", default="MipMapLinearLinear,Linear", help="atlas filter line")
    ap.add_argument("--format", choices=["webp", "webp_lossless", "png"], default="webp",
                    help="page image format (default webp at --quality; ~6x smaller than png)")
    ap.add_argument("--quality", type=int, default=92, help="webp quality (default 92)")
    ap.add_argument("--no-trim", action="store_true", help="keep transparent borders of region attachments")
    ap.add_argument("--force", action="store_true", help="rebuild every rig even if unchanged")
    ap.add_argument("--list", action="store_true", help="print discovered rigs and exit")
    args = ap.parse_args(argv)

    out_root = Path(args.out).resolve()
    rigs = discover(args.rig, not args.only_rigs)
    if args.list:
        for (c, v), d in sorted(rigs.items()):
            print(f"{c:10s} {v:8s} {rel(d)}")
        return 0
    (out_root / "assets").mkdir(parents=True, exist_ok=True)
    man_path = out_root / "manifest.json"
    prev = {}
    if man_path.is_file():
        try:
            prev = {e["id"]: e for e in json.loads(man_path.read_text()).get("rigs", [])}
        except (ValueError, KeyError):
            prev = {}
    opts = {"scale": args.scale, "max_page": args.max_page, "pad": args.pad, "filter": args.filter,
            "format": args.format, "quality": args.quality, "trim": not args.no_trim}

    entries, errors = [], []
    for (char, variant), rig_dir in sorted(rigs.items()):
        rid = f"{char}-{variant}"
        t0 = time.time()
        try:
            e = build_rig(char, variant, rig_dir, out_root, opts, None if args.force else prev.get(rid))
            entries.append(e)
            what = "built" if e["rebuilt"] else "unchanged"
            warn = f"  MISSING {e['missing_regions']}" if e["missing_regions"] else ""
            print(f"{what:9s} {rid:18s} {len(e['animations']):2d} anims  {len(e['pages'])} page(s)  "
                  f"{e['bytes'] / 1e6:5.2f} MB  qa={e['qa']['status']}  {time.time() - t0:4.1f}s{warn}")
        except Exception as ex:  # keep going; a half-written rig must not break the gallery
            msg = f"{type(ex).__name__}: {ex}"
            errors.append({"id": rid, "source": rel(rig_dir), "error": msg})
            print(f"FAILED    {rid:18s} {msg}", file=sys.stderr)
            if rid in prev and all((out_root / f).is_file() for f in prev[rid]["files"]):
                old = dict(prev[rid], stale=True)
                entries.append(old)
                print(f"          {rid}: keeping previous build from {old.get('built_at')}", file=sys.stderr)

    # a rig folder that still exists but has no skeleton right now is mid-rebuild: keep its last build
    for rid, old in prev.items():
        if rid in {e["id"] for e in entries} or (args.only_rigs and not args.rig):
            continue
        src = Path(old.get("source", ""))
        src = src if src.is_absolute() else ROOT / src
        if old.get("source") and src.is_dir() and all((out_root / f).is_file() for f in old["files"]):
            entries.append(dict(old, stale=True))
            errors.append({"id": rid, "source": old["source"], "error": "no <name>.json + <name>.atlas in the folder "
                           "right now (being rebuilt?); showing the previous build"})
            print(f"kept      {rid:18s} source folder has no skeleton right now; previous build kept", file=sys.stderr)
    keep = {e["id"] for e in entries}
    for d in (out_root / "assets").iterdir():
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d)
    entries.sort(key=sort_key)
    for e in entries:
        e.pop("rebuilt", None)
    chars = []
    for e in entries:
        if e["character"] not in chars:
            chars.append(e["character"])
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "builder_version": BUILDER_VERSION,
        "options": opts,
        "characters": chars,
        "rigs": entries,
        "errors": errors,
    }
    man_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total, count = gallery_size(out_root)
    flag = "" if total < 40e6 and count < 255 else "  OVER BUDGET (40 MB / 255 files)"
    print(f"gallery: {len(entries)} rigs, {len(chars)} characters, {count} files, {total / 1e6:.1f} MB{flag}")
    return 1 if errors and not entries else 0


if __name__ == "__main__":
    sys.exit(main())
