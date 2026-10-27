"""tools/build_gallery.py: atlas parsing, packing, and an end-to-end build of a tiny rig."""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import build_gallery as bg  # noqa: E402


def test_pack_no_overlap_inside_pot_pages():
    sizes = {i: (17 + (i * 37) % 300, 11 + (i * 53) % 260) for i in range(60)}
    pages = bg.pack(sizes, max_size=1024, pad=4)
    placed = {}
    for p in pages:
        W, H = p["size"]
        assert W & (W - 1) == 0 and H & (H - 1) == 0
        rects = list(p["rects"].items())
        for k, (x, y, w, h) in rects:
            assert (w, h) == sizes[k]
            assert x >= 0 and y >= 0 and x + w <= W and y + h <= H
            placed[k] = True
        for i, (_, a) in enumerate(rects):
            for _, b in rects[i + 1:]:
                assert a[0] + a[2] + 4 <= b[0] or b[0] + b[2] + 4 <= a[0] or \
                       a[1] + a[3] + 4 <= b[1] or b[1] + b[3] + 4 <= a[1], (a, b)
    assert len(placed) == len(sizes)


def test_pack_rejects_oversize():
    with pytest.raises(ValueError):
        bg.pack({"big": (3000, 10)}, max_size=2048)


def test_parse_atlas_spine4_and_offsets():
    text = ("p0.png\nsize: 64,32\nfilter: Linear,Linear\na\nbounds: 0,0,10,20\nb\nbounds: 10,0,8,4\n"
            "offsets: 1,2,12,9\nrotate: 90\n\np1.png\nsize: 16,16\npma: true\nc\nbounds: 0,0,16,16\nindex: 3\n")
    pages = bg.parse_atlas(text)
    assert [p["name"] for p in pages] == ["p0.png", "p1.png"]
    assert pages[0]["size"] == (64, 32) and pages[1]["pma"] is True
    a, b = pages[0]["regions"]
    assert a["bounds"] == (0, 0, 10, 20) and b["offsets"] == (1, 2, 12, 9) and b["rotate"] == 90
    assert pages[1]["regions"][0]["index"] == 3


def test_anim_duration_finds_deepest_key():
    anim = {"bones": {"b": {"rotate": [{"time": 0.5}, {"time": 1.25, "value": 3}]}},
            "attachments": {"default": {"s": {"m": {"deform": [{"time": 2.0}]}}}}}
    assert bg.anim_duration(anim) == 2.0
    assert bg.anim_duration({}) == 0.0


def _tiny_rig(d: Path):
    (d / "images").mkdir(parents=True)
    atlas = []
    for name, (w, h), col in [("body", (40, 60), (200, 40, 40, 255)), ("arm", (30, 12), (40, 200, 40, 255))]:
        Image.new("RGBA", (w, h), col).save(d / "images" / f"{name}.png")
        atlas += [f"images/{name}.png", f"size: {w},{h}", "filter: Linear,Linear", name, f"bounds: 0,0,{w},{h}", ""]
    (d / "toy.atlas").write_text("\n".join(atlas))
    skel = {"skeleton": {"spine": "4.2.00", "x": -20, "y": 0, "width": 50, "height": 60, "images": "./images/"},
            "bones": [{"name": "root"}], "slots": [{"name": "body", "bone": "root", "attachment": "body"},
                                                    {"name": "arm", "bone": "root", "attachment": "arm"}],
            "skins": [{"name": "default", "attachments": {
                "body": {"body": {"width": 40, "height": 60}},
                "arm": {"arm": {"type": "mesh", "uvs": [0, 0, 1, 0, 1, 1, 0, 1], "triangles": [0, 1, 2, 0, 2, 3],
                                "vertices": [0, 0, 30, 0, 30, 12, 0, 12], "hull": 4, "width": 30, "height": 12}}}}],
            "animations": {"idle": {"bones": {"root": {"rotate": [{"time": 0}, {"time": 1.5, "value": 5}]}}}}}
    (d / "toy.json").write_text(json.dumps(skel))
    (d / "qa").mkdir()
    (d / "qa" / "report.json").write_text(json.dumps({"structure": {"pass": True}, "idle": {"pass": False}}))


def test_build_end_to_end(tmp_path, capsys):
    rig = tmp_path / "toy" / "rig"
    _tiny_rig(rig)
    out = tmp_path / "gallery"
    args = ["--only-rigs", "--rig", f"toy:legacy={rig}", "--out", str(out), "--format", "png"]
    assert bg.main(args) == 0
    man = json.loads((out / "manifest.json").read_text())
    (e,) = man["rigs"]
    assert e["id"] == "toy-legacy" and e["animations"] == [{"name": "idle", "duration": 1.5}]
    assert e["qa"]["status"] == "fail" and e["qa"]["failing"] == ["idle"]
    assert e["missing_regions"] == [] and e["counts"]["meshes"] == 1
    pages = bg.parse_atlas((out / e["atlas"]).read_text())
    assert len(pages) == 1
    regions = {r["name"]: r for r in pages[0]["regions"]}
    assert regions["body"]["bounds"][2:] == (20, 30) and regions["arm"]["bounds"][2:] == (15, 6)
    page = Image.open(out / "assets" / "toy-legacy" / pages[0]["name"])
    assert page.size == pages[0]["size"]
    x, y, w, h = regions["body"]["bounds"]
    assert page.getpixel((x + w // 2, y + h // 2))[:3] == (200, 40, 40)
    skel = json.loads((out / e["json"]).read_text())
    assert skel["skins"][0]["attachments"]["body"]["body"]["width"] == 40  # attachment size untouched

    # unchanged sources -> nothing rebuilt; removed rig -> its assets go away
    capsys.readouterr()
    assert bg.main(args) == 0
    assert "unchanged" in capsys.readouterr().out
    assert bg.main(["--only-rigs", "--out", str(out)]) == 0
    assert not (out / "assets" / "toy-legacy").exists()


def test_broken_rig_is_reported_not_fatal(tmp_path):
    good, bad = tmp_path / "a" / "rig", tmp_path / "b" / "rig"
    _tiny_rig(good)
    bad.mkdir(parents=True)
    (bad / "toy.atlas").write_text("images/missing.png\nsize: 4,4\nx\nbounds: 0,0,4,4\n")
    (bad / "toy.json").write_text("{not json")
    out = tmp_path / "g"
    assert bg.main(["--only-rigs", "--rig", f"a:legacy={good}", "--rig", f"b:legacy={bad}", "--out", str(out)]) == 0
    man = json.loads((out / "manifest.json").read_text())
    assert [r["id"] for r in man["rigs"]] == ["a-legacy"]
    assert man["errors"][0]["id"] == "b-legacy"


def test_webp_pages_are_written_and_referenced(tmp_path):
    rig = tmp_path / "toy" / "rig"
    _tiny_rig(rig)
    out = tmp_path / "g"
    assert bg.main(["--only-rigs", "--rig", f"toy:legacy={rig}", "--out", str(out)]) == 0
    e = json.loads((out / "manifest.json").read_text())["rigs"][0]
    assert e["pages"] and all(p.endswith(".webp") for p in e["pages"])
    (page,) = bg.parse_atlas((out / e["atlas"]).read_text())
    im = Image.open(out / "assets" / "toy-legacy" / page["name"])
    assert im.format == "WEBP" and im.size == page["size"]
    x, y, w, h = {r["name"]: r for r in page["regions"]}["body"]["bounds"]
    r, g, b, a = im.convert("RGBA").getpixel((x + w // 2, y + h // 2))
    assert abs(r - 200) < 8 and abs(g - 40) < 8 and a == 255


def test_region_whitespace_is_trimmed_into_offsets_meshes_are_not(tmp_path):
    rig = tmp_path / "toy" / "rig"
    _tiny_rig(rig)
    # body: 40x60 with only a 20x20 opaque square, 4 px from the left and 6 px from the bottom
    im = Image.new("RGBA", (40, 60), (0, 0, 0, 0))
    im.paste((200, 40, 40, 255), (4, 34, 24, 54))
    im.save(rig / "images" / "body.png")
    Image.new("RGBA", (30, 12), (0, 0, 0, 0)).save(rig / "images" / "arm.png")  # mesh: must stay full size
    out = tmp_path / "g"
    assert bg.main(["--only-rigs", "--rig", f"toy:legacy={rig}", "--out", str(out), "--format", "png",
                    "--scale", "1"]) == 0
    e = json.loads((out / "manifest.json").read_text())["rigs"][0]
    (page,) = bg.parse_atlas((out / e["atlas"]).read_text())
    regions = {r["name"]: r for r in page["regions"]}
    x, y, w, h = regions["body"]["bounds"]
    assert (w, h) == (22, 22)  # 20 px + 1 px safety border each side
    assert regions["body"]["offsets"] == (3, 5, 40, 60)
    assert "offsets" not in regions["arm"] and regions["arm"]["bounds"][2:] == (30, 12)
