"""Worn items (rig_worn, spine_rig.py --annotations): a boot drawn over the leg/hips is cut at its ankle opening into a
back part (the inside and the back half of the rim, drawn behind the leg) and a shell (drawn in front); the hand layer
key; spine_qa with the extra back slots."""
import json
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

import rig_annotations as ra
import rig_place
import rig_worn
import spine_qa
import spine_rig
from conftest import ROOT, SCRIPTS
from synth_character import C, SCALE, foot, make_character, render_raw


# ------------------------------------------------------------------ the cut, on the synthetic boot

def _boot(kind="boot"):
    """The synthetic boot as normalise writes it: (image, ankle point, width, depth) in output px."""
    part = foot(kind, "l")
    img, to_px = render_raw(part, SCALE)
    w = part.widths["ankle"] * SCALE
    return img, to_px(part.points["ankle"]), w, 0.35 * w, to_px


def _class(arr, colour, tol=6):
    """Solid pixels painted `colour` (the flat colours of synth_character)."""
    return (np.abs(arr[..., :3].astype(int) - np.array(colour)).max(2) <= tol) & (arr[..., 3] > 250)


RIM_BOOT = {"body": (230, 120, 20), "rim": (250, 160, 50), "hole": (150, 70, 10)}


def _rim_boot():
    """A boot like the fox's: a shaft and toe, an elliptical light rim (outer 40 x 14 px around (60, 30)) with a 5-7 px
    lip all round its dark inside (32 x 8 around (60, 29)), its ankle point snapped near the top edge as on the fox.
    Returns (image, ankle point, width, depth)."""
    from PIL import ImageDraw
    ss, w, h = 4, 140, 130
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)

    def box(cx, cy, a, b):
        return [(cx - a) * ss, (cy - b) * ss, (cx + a) * ss, (cy + b) * ss]
    d.rectangle([20 * ss, 30 * ss, 100 * ss, 110 * ss], fill=RIM_BOOT["body"] + (255,))
    d.ellipse(box(85, 100, 45, 18), fill=RIM_BOOT["body"] + (255,))
    d.ellipse(box(60, 30, 40, 14), fill=RIM_BOOT["rim"] + (255,))
    d.ellipse(box(60, 29, 32, 8), fill=RIM_BOOT["hole"] + (255,))
    return big.resize((w, h), Image.BOX), (60.0, 20.0), 80.0, 28.0


def test_split_boot_with_a_visible_rim():
    img, at, w, d = _rim_boot()
    shell, back, info = rig_worn.split(img, at, w, d)
    assert info["method"] == "inside"
    src, sh, bk = (np.asarray(x) for x in (img, shell, back))
    assert shell.size == back.size == img.size
    in_shell, in_back = sh[..., 3] > 127, bk[..., 3] > 127
    solid = src[..., 3] > 127
    s_, b_ = sh[..., 3] / 255, bk[..., 3] / 255
    assert ((s_ + b_ * (1 - s_))[solid] * 255 > 126).all()              # nothing lost at the cut
    hole, rim, body = (_class(src, RIM_BOOT[k]) for k in ("hole", "rim", "body"))
    yy = np.mgrid[:src.shape[0], :src.shape[1]][0] + 0.5
    back_rim, front_lip = rim & (yy < 29), rim & (yy > 31)
    assert hole.sum() > 600 and back_rim.sum() > 200 and front_lip.sum() > 200
    # the inside and the back half of the rim go behind; the front lip and the boot stay in front
    assert (hole & in_back & ~in_shell).sum() >= 0.97 * hole.sum()
    assert (back_rim & in_back & ~in_shell).sum() >= 0.95 * back_rim.sum()
    assert (front_lip & in_shell & ~(np.asarray(img)[..., 3] < 255)).sum() >= 0.8 * front_lip.sum()
    assert (body & in_shell).sum() >= 0.99 * body.sum()
    # counts: back = the inside plus the rim above the centre line
    behind = int((in_back & ~in_shell).sum())                          # what only the back part draws
    # (plus the anti-aliased pixels between the flat colours and the rim's two rows at the centre line)
    assert hole.sum() + back_rim.sum() <= behind <= hole.sum() + back_rim.sum() + 0.5 * front_lip.sum()
    assert behind <= info["back_px"] <= behind + 0.5 * front_lip.sum()
    assert info["shell_px"] == int(in_shell.sum())
    assert info["shell_px"] >= body.sum() + 0.8 * front_lip.sum()
    # the inside ellipse is the painted hole (not the ellipse around the snapped point)
    ex, ey, ea, eb = info["ellipse"]
    assert abs(ex - 60) <= 1 and abs(ey - 29) <= 1 and abs(ea - 32) <= 1.5 and abs(eb - 8) <= 1.5


def test_shell_over_back_composites_to_the_original():
    """Along the feathered cut the back carries the alpha the shell leaves: no seam where nothing lies between them."""
    img, at, w, d = _rim_boot()
    shell, back, _ = rig_worn.split(img, at, w, d)
    src = np.asarray(img)
    sh, bk = np.asarray(shell), np.asarray(back)
    assert (sh[..., :3] == src[..., :3]).all() and (bk[..., :3] == src[..., :3]).all()    # colours untouched
    s_, b_ = sh[..., 3].astype(float) / 255, bk[..., 3].astype(float) / 255
    comp = s_ + b_ * (1 - s_)
    assert np.abs(comp * 255 - src[..., 3]).max() <= 1.0
    feather = (sh[..., 3] > 0) & (sh[..., 3] < src[..., 3])
    assert feather.sum() > 50                                            # the cut edge is soft


def _decoy_boot():
    """An opening (dark, 40 x 6 around (100, 25)) and, below it, a bigger dark enclosed patch (50 x 9 around
    (100, 50)): both meet every test for an inside; the one nearest the ankle point is the opening."""
    from PIL import ImageDraw
    ss, w, h = 4, 200, 120
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rectangle([20 * ss, 10 * ss, 180 * ss, 110 * ss], fill=(230, 150, 60, 255))
    d.ellipse([60 * ss, 19 * ss, 140 * ss, 31 * ss], fill=(120, 60, 10, 255))
    d.ellipse([50 * ss, 41 * ss, 150 * ss, 59 * ss], fill=(110, 55, 10, 255))
    return big.resize((w, h), Image.BOX), (100.0, 30.0), 120.0, 40.0


def test_inside_is_the_dark_region_nearest_the_point():
    img, at, w, d = _decoy_boot()
    comp = rig_worn.find_inside(np.asarray(img), at, w, d)
    assert comp is not None
    ys, xs = np.nonzero(comp)
    assert 18 <= ys.min() and ys.max() <= 32, (ys.min(), ys.max())      # the opening, not the bigger patch below


def test_split_ignores_where_the_point_snapped():
    """The real fox's ankle point sits at the top edge of its opening: the painted inside still decides."""
    img, at, w, d = _rim_boot()
    _, _, ref = rig_worn.split(img, at, w, d)
    _, _, high = rig_worn.split(img, (at[0], at[1] + 9), w, d)          # the true centre of the opening
    assert high["method"] == "inside" and high["ellipse"] == ref["ellipse"]


def test_split_without_a_painted_inside_uses_the_opening_ellipse():
    img, at, w, d, _ = _boot()
    arr = np.asarray(img).copy()
    arr[..., :3] = np.where((arr[..., 3] > 0)[..., None], np.array(C["boot"], np.uint8), arr[..., :3])   # flat boot
    shell, back, info = rig_worn.split(Image.fromarray(arr), at, w, d)
    assert info["method"] == "ellipse"
    # T19: fitted to the boot's own top (an untilted rim centred on the point): the same opening, to a pixel
    cx, cy, a, b = info["ellipse"]
    assert abs(cx - at[0]) <= 1 and abs(cy - at[1]) <= 1.5 and abs(a - w / 2) <= 1.5 and b == round(d / 2, 2)
    assert abs(info["tilt"]) < 0.02
    yy, xx = np.mgrid[:arr.shape[0], :arr.shape[1]] + 0.5
    in_ell = ((xx - at[0]) / (w / 2)) ** 2 + ((yy - at[1]) / (d / 2)) ** 2 <= 1
    in_back = np.asarray(back)[..., 3] > 127
    solid = arr[..., 3] > 127
    assert (in_back & solid & in_ell).sum() >= 0.98 * (solid & in_ell).sum()
    assert (np.asarray(shell)[..., 3] > 127)[solid & (yy > at[1] + d)].all()


def _tilted_boot(tilt=-18.0):
    """A flat-coloured boot seen tilted (as the fox's tiptoe): its shaft's top is the upper half of an ellipse (a 100,
    b 26) turned by `tilt` degrees about (130, 70); no painted inside. The ankle point is centred across the shaft
    but off the tilted arc's peak, as on the fox. Returns (image, ankle point, width, depth)."""
    import math
    from PIL import ImageDraw
    ss, w, h = 4, 260, 260
    th = math.radians(tilt)
    arc = []
    for k in range(0, 181, 3):
        t = math.radians(180 + k)                                   # the upper half, left to right
        x, y = 100 * math.cos(t), 26 * math.sin(t)
        arc.append((130 + x * math.cos(th) - y * math.sin(th), 70 + x * math.sin(th) + y * math.cos(th)))
    poly = arc + [(arc[-1][0] + 4, 230), (arc[0][0] - 4, 230)]
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(big).polygon([(x * ss, y * ss) for x, y in poly], fill=C["boot"] + (255,))
    return big.resize((w, h), Image.BOX), (130.0, 50.0), 200.0, 70.0


def _profile(mask, x0, x1, top=True):
    """Per column x0..x1-1: the topmost (or bottommost) True row, -1 where the column is empty."""
    out = []
    for x in range(x0, x1):
        ys = np.nonzero(mask[:, x])[0]
        out.append((ys.min() if top else ys.max()) if len(ys) else -1)
    return np.array(out)


def test_ellipse_fallback_follows_a_tilted_top():
    """T19: no painted inside (the tiptoe) - the cut follows the piece's own top silhouette: the back part is the band
    between the top contour and a lower arc (a sheared ellipse through the opening's two ends), so both the back lip
    and the front lip are smooth continuous curves across the whole opening, not an L-shaped corner where an ellipse
    centred on the ankle point meets the outline."""
    img, at, w, d = _tilted_boot()
    shell, back, info = rig_worn.split(img, at, w, d)
    assert info["method"] == "ellipse"                              # still a guess: the worn_opening_guessed doubt
    solid = np.asarray(img)[..., 3] > 127
    b, s = np.asarray(back)[..., 3] > 127, np.asarray(shell)[..., 3] > 127
    cols = np.nonzero(solid.any(0))[0]
    lo, hi = int(cols.min()), int(cols.max()) + 1
    span = hi - lo
    x0, x1 = lo + int(0.08 * span), hi - int(0.08 * span)          # all but the opening's two ends
    top, bt, bb = _profile(solid, x0, x1), _profile(b, x0, x1), _profile(b, x0, x1, top=False)
    assert (bt >= 0).all(), "the back runs across the whole opening"
    assert (np.abs(bt - top) <= 1).all(), "the back lip is the piece's own top"
    assert (bb - bt >= 3).all()
    st = _profile(s & ~b, x0, x1)
    assert np.abs(np.diff(bb)).max() <= 3 and np.abs(np.diff(bb, 2)).max() <= 2, "the cut is a smooth arc"
    assert np.abs(np.diff(st)).max() <= 3 and np.abs(np.diff(st, 2)).max() <= 2, "the front lip is a smooth arc"
    mid = (x0 + x1) // 2 - x0                                       # deepest near the middle, shallow at the ends
    assert (bb - bt)[mid] > (bb - bt)[0] + 10 and (bb - bt)[mid] > (bb - bt)[-1] + 10
    assert (bb - bt)[mid] <= d                                      # not deeper than the opening goes
    assert s[200:].sum() == solid[200:].sum()                       # the boot's lower part is all shell
    for im in (shell, back):                                        # the lip's thin ends went behind: no slivers
        assert _stray(np.asarray(im)[..., 3]).sum() <= spine_qa.MAX_STRAY_PX
    a = np.asarray(img)[..., 3].astype(float) / 255                 # the composite is unchanged
    sa, ba = (np.asarray(im)[..., 3].astype(float) / 255 for im in (shell, back))
    assert np.abs(sa + ba * (1 - sa) - a).max() < 2 / 255


def _tilted_with(tilt, extra):
    """_tilted_boot with something drawn on top: extra(draw, ss) in image px x ss."""
    from PIL import ImageDraw
    img, at, w, d = _tilted_boot(tilt)
    ss = 4
    big = img.resize((img.width * ss, img.height * ss), Image.NEAREST)
    extra(ImageDraw.Draw(big), ss)
    return big.resize(img.size, Image.BOX), at, w, d


@pytest.mark.parametrize("what", ["loop", "notch"])
def test_arc_fit_sanity_falls_back_to_the_ellipse(what):
    """T19 fix: a pull-on loop rising from the top centre, or a notch cut into it, captures the run of columns around
    the ankle point: the fit spans far less than the opening (2a < ARC_MIN_SPAN x width) and is refused, so the cut
    falls back to the snapped opening's ellipse (still "ellipse", the worn_opening_guessed doubt)."""
    def loop(dr, ss):
        dr.rectangle([123 * ss, 25 * ss, 137 * ss, 70 * ss], fill=C["boot"] + (255,))

    def notch(dr, ss):
        dr.rectangle([110 * ss, 0, 150 * ss, 75 * ss], fill=(0, 0, 0, 0))
    img, at, w, d = _tilted_with(0.0, loop if what == "loop" else notch)
    solid = np.asarray(img)[..., 3] > 127
    assert rig_worn.top_arc(solid, at, w, d) is None
    shell, back, info = rig_worn.split(img, at, w, d)
    assert info["method"] == "ellipse" and "tilt" not in info
    assert info["ellipse"] == [round(at[0], 2), round(at[1], 2), round(w / 2, 2), round(d / 2, 2)]


def test_arc_fit_refused_when_the_chord_is_far_from_the_point():
    """A chord more than `depth` from the ankle point's height is not this opening's top."""
    img, at, w, d = _tilted_boot(0.0)
    solid = np.asarray(img)[..., 3] > 127
    assert rig_worn.top_arc(solid, at, w, d) is not None
    assert rig_worn.top_arc(solid, (at[0], at[1] - 1.2 * d), w, d) is None


@pytest.mark.parametrize("tilt", [0.0, -18.0, -35.0])
def test_tilted_tops_still_use_the_arc(tilt):
    img, at, w, d = _tilted_boot(tilt)
    _, _, info = rig_worn.split(img, at, w, d)
    assert "tilt" in info and 2 * info["ellipse"][2] >= rig_worn.ARC_MIN_SPAN * w


def test_real_fox_tiptoes_use_the_arc():
    """The committed fox tiptoes (no painted inside, tilted tops) pass the fit's sanity checks: the arc cut, no
    slivers."""
    root = ROOT / "experiments" / "2026-10-11-rig-annotations" / "fox"
    if not (root / "annotations.json").exists():
        pytest.skip("the committed fox annotations are missing")
    ann = json.loads((root / "annotations.json").read_text())
    outs = [o for p in ann["pieces"].values() if p.get("role") == "foot" and p.get("variant") == "tiptoe"
            for o in p["outputs"]]
    assert len(outs) == 2
    for o in outs:
        img = spine_rig.solidify(Image.open(root / o["file"]), spine_rig.TRUST_ALPHA_ANNOTATED)
        shell, back, info = rig_worn.split(img, o["points"]["ankle"], o["widths"]["ankle"], o["depths"]["ankle"])
        assert info["method"] == "ellipse" and "tilt" in info, (o["name"], info)
        for im in (shell, back):
            assert _stray(np.asarray(im)[..., 3]).sum() <= spine_qa.MAX_STRAY_PX, o["name"]


def test_lip_ends_go_behind():
    """T19: where the arc cut meets the outline, the shell's thin wedge touching the back goes behind whole; thin bits
    of the shell away from the cut stay."""
    back = np.zeros((60, 120), np.uint8)
    back[10:25, 30:90] = 255
    shell = np.zeros_like(back)
    shell[25:50, 10:110] = 255                                       # the shell's body, below the cut
    shell[10:25, 28:30] = 255                                        # a 2 px wedge beside the back's end
    shell[0:25, 100:102] = 255                                       # a thin bit away from the cut: not a lip end
    a = np.maximum(shell, back)
    s2, b2, moved = rig_worn.drop_thin_lip_ends(shell, back, a)
    assert (s2[10:21, 28:30] == 0).all() and (b2[10:21, 28:30] == 255).all()   # > TIP_NEAR from the body: behind
    assert (s2[21:25, 28:30] == 255).all() and moved == 22
    assert (s2[0:25, 100:102] == 255).all() and (b2[0:25, 100:102] == 0).all()
    assert (s2[25:] == shell[25:]).all() and (b2[10:25, 30:90] == 255).all()


def test_no_islands_either_side():
    img, at, w, d, _ = _boot()
    shell, back, _ = rig_worn.split(img, at, w, d)
    for im in (shell, back):
        comps = rig_worn.components(np.asarray(im)[..., 3] > 127)
        assert len(comps) == 1 or comps[1].sum() < 0.003 * comps[0].sum()


def _stray(a8):
    """spine_qa's slivers measure on one image's alpha: faint or thin pixels away from its opened body."""
    solid = a8 > 127
    core = spine_qa.dilate(~spine_qa.dilate(~solid, 3), 3)
    return (a8 > 8) & ~spine_qa.dilate(core, 4)


def test_thin_tips_of_the_back_go_to_the_shell():
    """T18: the back's crescent band thins at the rim's ends; those tips (faint after the feathered cut) were slivers
    on the real fox (54 / 69 px against spine_qa's 40). They move to the shell whole; the composite is unchanged."""
    a8 = np.zeros((60, 120), np.uint8)
    a8[10:50, 10:110] = 255
    back = np.zeros_like(a8)
    back[20:40, 30:70] = 255                                  # the inside and the thick middle of the band
    back[28:30, 70:100] = 200                                 # a 2 px tip running along the rim
    back[29, 100:104] = 40                                    # its faint feathered end
    shell = np.where(back > 0, 0, a8).astype(np.uint8)
    assert _stray(back).sum() > 0
    s2, b2, moved = rig_worn.drop_thin_tips(shell, back, a8)
    assert not _stray(b2).any()
    tips = (back > 0) & (b2 == 0)
    assert moved == int(tips.sum()) > 0 and (s2[tips] == a8[tips]).all()
    assert (b2[20:40, 30:70] == 255).all() and (s2[20:40, 30:70] == 0).all()   # the body of the back stays
    assert (s2[~tips] == shell[~tips]).all() and (b2[~tips] == back[~tips]).all()   # nothing else changes


def test_split_back_has_no_slivers():
    img, at, w, d, _ = _boot()
    shell, back, info = rig_worn.split(img, at, w, d)
    assert not _stray(np.asarray(back)[..., 3]).sum() > spine_qa.MAX_STRAY_PX
    assert "tips_px" in info


# ------------------------------------------------------------------ layers

def test_apply_layers_hand_over_forearm():
    base = list(spine_rig.LAYERS)
    out = rig_place.apply_layers({"hand": "over_forearm"}, base)
    assert out.index("hand") == out.index("forearm") + 1
    assert rig_place.apply_layers({"hand": "under_forearm"}, base) == base
    both = rig_place.apply_layers({"hand": "over_forearm", "upperarm": "under_torso"}, base)
    assert both.index("arm") < both.index("torso") < both.index("forearm") < both.index("hand")
    assert base == spine_rig.LAYERS


def test_hand_layer_validates(tmp_path):
    ann = ra.load(make_character(tmp_path))
    for v in ("over_forearm", "under_forearm"):
        ann.master.layers = {"hand": v}
        assert ra.validate(ann) == []
    ann.master.layers = {"hand": "over_torso"}
    assert any("over_torso" in e for e in ra.validate(ann))


# ------------------------------------------------------------------ the rig

def _build(ann_path, out):
    cmd = [sys.executable, str(SCRIPTS / "spine_rig.py"), "--master", str(ann_path.parent / "master.png"),
           "--annotations", str(ann_path), "--name", "synth", "--out", str(out)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return json.loads((out / "synth.json").read_text()), json.loads((out / "report.json").read_text())


@pytest.fixture(scope="module")
def worn_rig(tmp_path_factory):
    root = tmp_path_factory.mktemp("worn")
    ann = make_character(root, pose_variants=True)
    skel, report = _build(ann, root / "rig")
    return root / "rig", skel, report


@pytest.mark.slow
def test_back_slots_below_the_legs(worn_rig):
    _, skel, report = worn_rig
    slots = [s["name"] for s in skel["slots"]]
    bone = {s["name"]: s["bone"] for s in skel["slots"]}
    for s in "lr":
        assert bone[f"boot_{s}_back"] == f"boot_{s}"                  # the same bone as its shell
        assert slots.index(f"boot_{s}_back") < slots.index("leg_l") < slots.index(f"boot_{s}")
    assert slots.index("tail") < slots.index("boot_l_back")
    assert slots[slots.index("leg_l") - 2: slots.index("leg_l")] == ["boot_l_back", "boot_r_back"]
    skin = skel["skins"][0]["attachments"]
    assert skin["boot_l_back"]["synth_boot_l_back"] == skin["boot_l"]["synth_boot_l"]   # same place
    assert skin["boot_l_back"]["synth_boot_l_tiptoe_back"] == skin["boot_l"]["synth_boot_l_tiptoe"]
    setup = {s["name"]: s.get("attachment") for s in skel["slots"]}
    assert setup["boot_l_back"] == "synth_boot_l_back"
    assert report["worn"]["boot_l"]["attachments"]["synth_boot_l"]["method"] == "inside"
    assert not [d for d in report["doubts"] if d["reason"] == "worn_opening_guessed"]   # every opening is painted


@pytest.mark.slow
def test_back_slot_swaps_with_its_shell(worn_rig):
    _, skel, _ = worn_rig
    for anim in skel["animations"].values():
        for s in "lr":
            shell = anim.get("slots", {}).get(f"boot_{s}", {}).get("attachment")
            back = anim.get("slots", {}).get(f"boot_{s}_back", {}).get("attachment")
            if shell is None:
                assert back is None
                continue
            assert [k["time"] for k in back] == [k["time"] for k in shell]
            assert [k["name"] for k in back] == [k["name"] + "_back" for k in shell]
    names = {k["name"] for k in skel["animations"]["cheer_jump"]["slots"]["boot_l_back"]["attachment"]}
    assert "synth_boot_l_tiptoe_back" in names


@pytest.mark.slow
def test_qa_passes_with_back_slots(worn_rig):
    out, skel, _ = worn_rig
    rig = spine_qa.Rig(out / "synth.json")
    assert spine_qa.worn_backs(rig) == {"boot_l_back": "boot_l", "boot_r_back": "boot_r"}
    assert spine_qa.with_back(rig, "boot_l", "synth_boot_l_tiptoe") == {
        "boot_l": "synth_boot_l_tiptoe", "boot_l_back": "synth_boot_l_tiptoe_back"}
    assert spine_qa.with_back(rig, "hand_l", "synth_hand_l_fist") == {"hand_l": "synth_hand_l_fist"}
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    st = spine_qa.check_structure(rig, canvas)      # (the synthetic tail and head have their own known misses)
    for k in ("pivot_off_joint", "reversed_bones", "weak_joints", "slivers", "fragments", "variant_misfit", "draw_order"):
        assert not [n for n in st[k] if "boot" in n], (k, st[k])
    seams = spine_qa.check_seams(rig, canvas, [(None, 0.0), ("cheer_jump", 0.95)])
    assert seams["pass"], seams
    assert not any(k in seams["seams"] for k in ("boot_l/boot_l_back", "boot_r/boot_r_back"))
    cj = spine_qa.check_anim(rig, canvas, "cheer_jump", 30, out / "qa")   # the back part is hidden on purpose
    for k in ("detached", "joint_holes", "unstitched", "occluded"):
        assert not [n for n in cj[k] if "boot" in n], (k, cj[k])
    res = json.loads((out / "annotations.resolved.json").read_text())
    so = spine_qa.check_sockets(rig, canvas, res, ["cheer_jump"])
    assert so["pass"], so


@pytest.mark.slow
def test_occlusion_skips_back_slots(worn_rig, tmp_path):
    """A back part going out of sight is the point of it; its shell is still checked."""
    out, skel, _ = worn_rig
    skel = json.loads(json.dumps(skel))
    names = [s["name"] for s in skel["slots"]]
    back = skel["slots"].pop(names.index("boot_l_back"))
    skel["slots"].insert([s["name"] for s in skel["slots"]].index("torso"), back)   # fully visible at rest
    a_, b_, c_, d_, _, _ = spine_qa.Rig(out / "synth.json").pose(None, 0)[0]["hips"]
    dx, dy = np.linalg.solve([[a_, b_], [c_, d_]], [0.0, -0.62 * skel["skeleton"]["height"]])   # in the hips' frame
    keys = [{"time": t, "x": round(float(dx) * k, 2), "y": round(float(dy) * k, 2)} for t, k in ((0, 0), (0.2, 1), (0.4, 1))]
    skel["animations"] = {"cover": {"bones": {"torso": {"translate": keys}}}}   # the torso slides down over the boots
    d = tmp_path / "rig"
    d.mkdir()
    (d / "synth.json").write_text(json.dumps(skel))
    (d / "images").symlink_to(out / "images")
    rig = spine_qa.Rig(d / "synth.json")
    res = spine_qa.check_anim(rig, spine_qa.Canvas(rig, spine_qa.CHECK_H), "cover", 30, tmp_path / "qa")
    assert "boot_l" in res["occluded"], res["occluded"]
    assert "boot_l_back" not in res["occluded"], res["occluded"]


@pytest.mark.slow
def test_leg_shows_inside_the_opening(worn_rig):
    """Setup pose: where the boot's inside was, the leg now shows (it is drawn over the back part)."""
    out, skel, report = worn_rig
    rig = spine_qa.Rig(out / "synth.json")
    canvas = spine_qa.Canvas(rig, spine_qa.CHECK_H)
    _, _, _, alphas = spine_qa.render(rig, canvas, None, 0)
    back, leg, shell = alphas["boot_l_back"], alphas["leg_l"], alphas["boot_l"]
    hidden = back & ~shell                      # the back part where the shell no longer covers it
    assert hidden.sum() > 20
    assert (hidden & leg).sum() >= 0.5 * hidden.sum()


def _without_legs(ann_path, layer, width_r=True, flat=()):
    """No leg pieces; master.layers foot = layer; width_r=False drops boot_r's ankle widths; outputs named in `flat`
    are repainted one flat colour (no painted inside)."""
    ann = ra.load(ann_path)
    for p in ann.pieces.values():
        if p.role == "leg":
            p.status, p.role, p.points, p.outputs = "ignored", "", {}, []
        if p.role == "foot":
            for o in p.outputs:
                if o.name.startswith("boot_r") and not width_r:
                    o.widths.pop("ankle", None)
                if o.name in flat:
                    arr = np.asarray(Image.open(ann_path.parent / o.file).convert("RGBA")).copy()
                    arr[..., :3] = np.array(C["boot"], np.uint8)
                    Image.fromarray(arr).save(ann_path.parent / o.file)
    ann.master.layers = {"foot": layer}
    ra.save(ann)


@pytest.mark.slow
def test_over_hips_without_legs_and_a_missing_width(tmp_path):
    ann_path = make_character(tmp_path, pose_variants=True)
    _without_legs(ann_path, "over_hips", width_r=False, flat=("boot_l_tiptoe",))
    skel, report = _build(ann_path, tmp_path / "rig")
    slots = [s["name"] for s in skel["slots"]]
    assert slots.index("boot_l_back") + 1 == slots.index("hips") < slots.index("boot_l")
    assert "boot_r_back" not in slots                                    # no width: drawn whole
    assert {"part": "boot_r", "reason": "worn_no_width"} in report["doubts"]
    assert "boot_r" not in report["worn"]
    # a flat-painted opening is cut at the snapped ellipse, and says so
    guessed = [d for d in report["doubts"] if d["reason"] == "worn_opening_guessed"]
    assert [d["part"] for d in guessed] == ["boot_l_tiptoe"], guessed
    info = report["worn"]["boot_l"]["attachments"]["synth_boot_l_tiptoe"]
    assert info["method"] == "ellipse" and guessed[0]["ellipse"] == info["ellipse"]


@pytest.mark.slow
def test_feet_under_the_hips_are_not_cut(tmp_path):
    ann_path = make_character(tmp_path)
    _without_legs(ann_path, "under_hips")
    skel, report = _build(ann_path, tmp_path / "rig")
    assert not [s["name"] for s in skel["slots"] if s["name"].endswith("_back")]
    assert report["worn"] == {}
    assert not list((tmp_path / "rig" / "images").glob("*_back.png"))
