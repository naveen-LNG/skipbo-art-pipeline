"""Golden tests: building the committed fox and moose rigs (legacy, no annotations) must reproduce the committed spine
json, and every image the build writes must hash as recorded in tests/golden/rig_images.json (decoded pixels, so a
change of PNG encoder alone does not count). The image hashes were taken from 280d088's scripts; regenerate them
with RIG_GOLDEN_REGEN=1 only when a change to the legacy images is intended (and say so in the commit)."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from conftest import ROOT, SCRIPTS

IMAGES_GOLDEN = Path(__file__).resolve().parent / "golden" / "rig_images.json"

EXP = "experiments/2026-10-11-part-variants"

CASES = {
    "fox": [
        "--master", "experiments/2026-10-11-fox-parts/fox_master.png",
        "--body", f"{EXP}/fox/body",
        "--heads", "experiments/2026-10-11-fox-parts/fox-spine/face-heads",
        "--variants", f"{EXP}/fox/variants",
    ],
    "moose": [
        "--master", "experiments/2026-10-11-moose-parts/moose-spine-v1/moose_master.png",
        "--body", f"{EXP}/moose/body",
        "--heads", "experiments/2026-10-11-moose-parts/moose-spine-v1/face-heads",
        "--variants", f"{EXP}/moose/variants",
    ],
}


def _close(a, b, tol=0.01, path="$"):
    """Equal structure; numbers within tol."""
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), f"{path}: keys differ {set(a) ^ set(b)}"
        for key in a:
            _close(a[key], b[key], tol, f"{path}.{key}")
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            _close(x, y, tol, f"{path}[{i}]")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        assert abs(a - b) <= tol, f"{path}: {a} != {b}"
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


def _build_and_compare(name, tmp_path):
    out = tmp_path / name
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), *CASES[name], "--name", name, "--out", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    built = json.loads((out / f"{name}.json").read_text())
    golden = json.loads((ROOT / EXP / name / "rig" / f"{name}.json").read_text())
    _close(built["bones"], golden["bones"])
    _close(built["skins"], golden["skins"])
    _compare_images(name, out)


def image_hashes(out: Path) -> dict:
    """sha256 of every image a build wrote (rig/images/*.png and placement.png): mode, size and decoded pixels."""
    files = sorted((out / "images").glob("*.png")) + [out / "placement.png"]
    got = {}
    for f in files:
        with Image.open(f) as im:
            got[str(f.relative_to(out))] = hashlib.sha256(
                f"{im.mode} {im.size}".encode() + im.tobytes()).hexdigest()
    return got


def _compare_images(name, out):
    got = image_hashes(out)
    if os.environ.get("RIG_GOLDEN_REGEN"):
        data = json.loads(IMAGES_GOLDEN.read_text()) if IMAGES_GOLDEN.exists() else {}
        data[name] = got
        IMAGES_GOLDEN.parent.mkdir(exist_ok=True)
        IMAGES_GOLDEN.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    want = json.loads(IMAGES_GOLDEN.read_text())[name]
    assert sorted(got) == sorted(want), f"images differ: {sorted(set(got) ^ set(want))}"
    changed = sorted(f for f in got if got[f] != want[f])
    assert not changed, f"{name}: these images changed: {changed}"


@pytest.mark.slow
def test_fox_rig_unchanged(tmp_path):
    _build_and_compare("fox", tmp_path)


@pytest.mark.slow
def test_moose_rig_unchanged(tmp_path):
    _build_and_compare("moose", tmp_path)
