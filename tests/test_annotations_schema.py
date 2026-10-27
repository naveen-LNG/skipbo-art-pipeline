import json

import pytest

import rig_annotations as ra
from rig_annotations import (Annotations, AnnotationError, Master, Output, Piece,
                             Point, load, save, unconfirmed, validate, piece_image)

MASTER_PTS = {name: (0.5, 0.5) for name in ra.MASTER_POINTS}


def master(status="confirmed", layers=None):
    return Master(image="fox_master.png", points=dict(MASTER_PTS),
                  hands={"l": {"thumb_side": "lateral", "facing": "palm"}},
                  layers=layers if layers is not None else {"upperarm": "over_torso"},
                  status=status)


def pts(role, **overrides):
    out = {}
    for name in ra.ROLES[role] + ra.OPTIONAL_POINTS.get(role, ()):
        out[name] = Point(name, (0.5, 0.5), ra.DEFAULT_KIND[f"{role}.{name}"])
    out.update(overrides)
    return out


def piece(key, role, status="confirmed", points=None, **kw):
    kw.setdefault("name", role)
    kw.setdefault("variant", None)
    kw.setdefault("side", "l")
    kw.setdefault("facing", None)
    kw.setdefault("confidence", 0.9)
    return Piece(key=key, role=role, status=status,
                 points=points if points is not None else pts(role), **kw)


def ann(pieces, path, m=None):
    return Annotations(version=1, character="fox", master=m or master(),
                       pieces={p.key: p for p in pieces}, path=path)


def test_roundtrip(tmp_path):
    path = tmp_path / "annotations.json"
    hand = piece("fox-hands-parts/05", "hand", status="proposed", variant="point",
                 side="either", facing="palm", confidence=0.6, note="thumb partly hidden",
                 points={
                     "wrist": Point("wrist", (0.48, 0.05), "opening", snapped=(0.4812, 0.0533),
                                    width=41.25, depth=12.5, snap="ok"),
                     "thumb_tip": Point("thumb_tip", (0.2, 0.4), "point"),
                     "fingertip": Point("fingertip", (0.5, 0.9), "point", snap="failed")})
    hand.outputs = [Output(name="hand_point_l", file="hand_point_l.png", mirrored=True, rotated=-12.5,
                           points={"wrist": (10.25, 3.5)}, widths={"wrist": 40.5}, depths={"wrist": 9.75})]
    foot = piece("fox-poses-parts/04", "foot", variant="tiptoe", mirror=True, painted_as="l",
                 name="hoof")
    a = ann([hand, foot, piece("fox-body-parts/01", "torso")], path)
    assert validate(a) == []
    save(a)
    text = path.read_text()
    assert json.loads(text)["pieces"]["fox-hands-parts/05"]["points"]["wrist"]["snap"] == "ok"
    b = load(path)
    assert b == a
    save(b)
    assert path.read_text() == text


def test_point_without_kind_takes_default(tmp_path):
    path = tmp_path / "annotations.json"
    a = ann([piece("x/01", "torso"), piece("x/02", "hips")], path)
    save(a)
    raw = json.loads(path.read_text())
    for k in ("x/01", "x/02"):
        for p in raw["pieces"][k]["points"].values():
            del p["kind"]
    path.write_text(json.dumps(raw))
    b = load(path)
    assert b.pieces["x/01"].points["neck"].kind == "point"
    assert b.pieces["x/01"].points["shoulder_l"].kind == "point"      # the agent's socket point, not snapped
    assert b.pieces["x/02"].points["hip_l"].kind == "opening"


def test_stored_kind_is_ignored_for_a_known_role(tmp_path):
    path = tmp_path / "annotations.json"
    save(ann([piece("x/01", "torso"), piece("x/02", "hips")], path))
    raw = json.loads(path.read_text())
    raw["pieces"]["x/01"]["points"]["shoulder_l"]["kind"] = "opening"    # an old file, from when it was one
    raw["pieces"]["x/02"]["points"]["hip_l"]["kind"] = "point"
    path.write_text(json.dumps(raw))
    b = load(path)
    assert b.pieces["x/01"].points["shoulder_l"].kind == "point"
    assert b.pieces["x/02"].points["hip_l"].kind == "opening"


def test_missing_required_point(tmp_path):
    p = piece("fox-body-parts/01", "torso")
    del p.points["waist"]
    a = ann([p], tmp_path / "a.json")
    save(a)
    with pytest.raises(AnnotationError) as e:
        load(a.path)
    assert "torso" in str(e.value) and "waist" in str(e.value)


def test_unknown_point_name(tmp_path):
    pt = pts("hand")
    pt["elbow"] = Point("elbow", (0.5, 0.5), "point")
    a = ann([piece("x/05", "hand", variant="fist", points=pt)], tmp_path / "a.json")
    errs = validate(a)
    assert any("elbow" in e for e in errs)
    save(a)
    with pytest.raises(AnnotationError, match="elbow"):
        load(a.path)


def test_coordinate_out_of_range(tmp_path):
    pt = pts("torso")
    pt["neck"] = Point("neck", (1.2, 0.5), "point")
    a = ann([piece("x/01", "torso", points=pt)], tmp_path / "a.json")
    save(a)
    with pytest.raises(AnnotationError, match="neck"):
        load(a.path)


def test_either_needs_hand_or_painted_as(tmp_path):
    a = ann([piece("x/02", "leg", side="either")], tmp_path / "a.json")
    assert any("either" in e for e in validate(a))
    a.pieces["x/02"].painted_as = "l"
    assert validate(a) == []
    hand = ann([piece("x/03", "hand", variant="fist", side="either")], tmp_path / "a.json")
    assert validate(hand) == []


def test_fist_needs_no_fingertip(tmp_path):
    for variant in ("fist", "thumbsup"):
        a = ann([piece("x/05", "hand", variant=variant)], tmp_path / "a.json")
        assert "fingertip" not in a.pieces["x/05"].points
        assert validate(a) == []
    a = ann([piece("x/05", "hand", variant="point")], tmp_path / "a.json")
    errs = validate(a)
    assert any("fingertip" in e for e in errs)
    a.pieces["x/05"].points["fingertip"] = Point("fingertip", (0.5, 0.9), "point")
    assert validate(a) == []


def test_unconfirmed_lists_proposed_and_master(tmp_path):
    a = ann([piece("x/01", "torso", status="proposed"), piece("x/02", "hips", status="confirmed"),
             piece("x/03", "head", status="fixed"), piece("x/04", "tail", status="proposed")],
            tmp_path / "a.json", m=master(status="proposed"))
    assert unconfirmed(a) == ["x/01", "x/04", "master"]
    a.master.status = "confirmed"
    assert unconfirmed(a) == ["x/01", "x/04"]


def test_missing_piece_file_is_error(tmp_path):
    a = ann([piece("fox-hands-parts/05", "hand", variant="fist")], tmp_path / "annotations.json")
    with pytest.raises(AnnotationError, match="fox-hands-parts/05"):
        piece_image(a, "fox-hands-parts/05")
    d = tmp_path / "runs" / "fox-hands-parts"
    d.mkdir(parents=True)
    f = d / "00123_05.png"
    f.write_bytes(b"")
    assert piece_image(a, "fox-hands-parts/05") == f
    (d / "00124_05.png").write_bytes(b"")
    with pytest.raises(AnnotationError, match="fox-hands-parts/05"):
        piece_image(a, "fox-hands-parts/05")


def test_bad_layer_value(tmp_path):
    a = ann([piece("x/01", "torso")], tmp_path / "a.json", m=master(layers={"upperarm": "behind"}))
    assert any("behind" in e for e in validate(a))
    a.master.layers = {"forearm": "under_torso"}
    assert any("forearm" in e for e in validate(a))
    a.master.layers = {"upperarm": "under_torso"}
    assert validate(a) == []
    for v in ("over_hips", "under_hips"):
        a.master.layers = {"upperarm": "over_torso", "foot": v}
        assert validate(a) == []
    a.master.layers = {"foot": "under_torso"}                       # each key has its own values
    assert any("under_torso" in e for e in validate(a))
    a.master.layers = {"upperarm": "over_hips"}
    assert any("over_hips" in e for e in validate(a))


def test_other_rules(tmp_path):
    a = ann([piece("x/01", "torso", confidence=1.5), piece("x/02", "wizard", points={})],
            tmp_path / "a.json")
    a.version = 2
    errs = "\n".join(validate(a))
    assert "confidence" in errs and "wizard" in errs and "version" in errs
    p = piece("x/03", "torso")
    p.points["neck"].kind = "blob"
    assert any("blob" in e for e in validate(ann([p], tmp_path / "a.json")))
    assert ra.CONFIDENCE_DOUBT == 0.7


# --- fix round 1: drafts vs gate, hand-only points, malformed input, default kinds ---

def draft(key="x/09", **kw):
    return Piece(key=key, role=kw.pop("role", ""), name="", status=kw.pop("status", "proposed"), variant=None, side="",
                 points=kw.pop("points", {}), facing=None, confidence=0.0, **kw)


def test_draft_with_empty_role_loads(tmp_path):
    a = ann([draft()], tmp_path / "a.json")
    assert validate(a) == []
    save(a)
    assert load(a.path).pieces["x/09"].role == ""


def test_proposed_missing_point_loads_but_confirmed_fails(tmp_path):
    p = piece("x/01", "torso", status="proposed")
    del p.points["waist"]
    a = ann([p], tmp_path / "a.json")
    save(a)
    load(a.path)
    p.status = "confirmed"
    assert any("waist" in e for e in validate(a))
    p.status = "fixed"
    assert any("waist" in e for e in validate(a))


def test_draft_still_checks_names_ranges_kinds(tmp_path):
    p = piece("x/01", "torso", status="proposed")
    p.points["elbow"] = Point("elbow", (0.5, 0.5), "point")
    p.points["neck"] = Point("neck", (1.5, 0.5), "blob")
    p.side = "up"
    errs = "\n".join(validate(ann([p], tmp_path / "a.json")))
    assert "elbow" in errs and "1.5" in errs and "blob" in errs and "'up'" in errs
    d = draft(points={"x": Point("x", (2.0, 0.0), "point")})
    assert any("2.0" in e for e in validate(ann([d], tmp_path / "a.json")))


def test_confirmed_master_needs_every_point(tmp_path):
    m = master()
    del m.points["elbow_l"]
    a = ann([piece("x/01", "torso")], tmp_path / "a.json", m=m)
    assert any("elbow_l" in e for e in validate(a))
    m.status = "fixed"
    assert any("elbow_l" in e for e in validate(a))
    m.status = "proposed"
    m.points = {"neck": (0.5, 0.5)}
    assert validate(a) == []


def test_fingertip_only_on_hands(tmp_path):
    p = piece("x/01", "torso")
    p.points["fingertip"] = Point("fingertip", (0.5, 0.5), "point")
    assert any("fingertip" in e for e in validate(ann([p], tmp_path / "a.json")))
    p2 = piece("x/02", "forearm")
    p2.points["thumb_tip"] = Point("thumb_tip", (0.5, 0.5), "point")
    assert any("thumb_tip" in e for e in validate(ann([p2], tmp_path / "a.json")))
    assert "torso.fingertip" not in ra.DEFAULT_KIND
    assert ra.DEFAULT_KIND["hand.fingertip"] == "point"


def test_torso_shoulders_are_optional(tmp_path):
    """The upper arm hangs from the master's shoulder; the torso's own shoulder points are only a cross-check."""
    assert ra.ROLES["torso"] == ("neck", "waist")
    assert ra.OPTIONAL_POINTS["torso"] == ("shoulder_l", "shoulder_r")
    bare = piece("x/01", "torso")
    del bare.points["shoulder_l"], bare.points["shoulder_r"]
    assert validate(ann([bare], tmp_path / "a.json")) == []
    full = piece("x/02", "torso")                                     # still allowed, still plain points
    assert set(full.points) == {"neck", "waist", "shoulder_l", "shoulder_r"}
    assert validate(ann([full], tmp_path / "a.json")) == []
    assert ra._required_points(full) == ("neck", "waist")
    odd = piece("x/03", "torso")
    odd.points["shoulder"] = Point("shoulder", (0.5, 0.5), "point")   # an upper arm's name, not the torso's
    assert any("shoulder" in e for e in validate(ann([odd], tmp_path / "a.json")))


def test_default_kind_membership():
    kinds = ra.DEFAULT_KIND
    round_end = {k for k, v in kinds.items() if v == "round_end"}
    opening = {k for k, v in kinds.items() if v == "opening"}
    assert round_end == {"upperarm.shoulder", "upperarm.elbow", "forearm.elbow", "leg.hip", "arm.shoulder"}
    assert opening == {"hips.hip_l", "hips.hip_r", "foot.ankle", "hand.wrist", "forearm.wrist", "leg.hem", "arm.wrist"}
    assert kinds["arm.elbow"] == "point"                              # a whole sleeve bends there: nothing to snap
    assert kinds["torso.shoulder_l"] == kinds["torso.shoulder_r"] == "point"
    assert kinds["hand.thumb_tip"] == "point" and kinds["foot.ground"] == "point"


@pytest.mark.parametrize("mutate", [
    lambda raw: raw["master"].update(hands={"l": "palm"}),
    lambda raw: raw["master"].update(points=[1, 2]),
    lambda raw: raw["master"].update(layers=["upperarm"]),
    lambda raw: raw["master"]["points"].update(neck=["a", "b"]),
    lambda raw: raw["master"]["points"].update(neck=[0.5]),
    lambda raw: raw["pieces"]["x/01"]["points"]["neck"].update(at=0.5),
    lambda raw: raw["pieces"]["x/01"]["points"]["neck"].update(at=["a", "b"]),
    lambda raw: raw["pieces"]["x/01"].update(points=[]),
    lambda raw: raw["pieces"]["x/01"].update(confidence="high"),
])
def test_malformed_input_is_annotation_error(tmp_path, mutate):
    a = ann([piece("x/01", "torso")], tmp_path / "a.json")
    save(a)
    raw = json.loads(a.path.read_text())
    mutate(raw)
    a.path.write_text(json.dumps(raw))
    with pytest.raises(AnnotationError):
        load(a.path)


# --- T10b: spare pieces the rig does not use ---

def test_ignored_piece_validates_with_any_or_empty_role_and_no_points(tmp_path):
    for role in ("", "wing", "torso"):
        a = ann([draft(role=role, status="ignored")], tmp_path / "a.json")
        assert validate(a) == [], role
        save(a)
        got = load(a.path).pieces["x/09"]
        assert (got.status, got.role, got.points) == ("ignored", role, {})
    p = draft(role="torso", status="ignored")    # a draft's rough top/bottom points may stay on it
    p.points = {"top": Point("top", (0.5, 0.1), "round_end"), "bottom": Point("bottom", (0.5, 0.9), "round_end")}
    p.side = "either"
    assert validate(ann([p], tmp_path / "a.json")) == []


def test_ignored_piece_still_rejects_malformed_structure(tmp_path):
    p = draft(status="ignored")
    p.side, p.confidence = "up", 1.5
    p.points = {"x": Point("x", (2.0, 0.0), "blob")}
    errs = "\n".join(validate(ann([p], tmp_path / "a.json")))
    assert "'up'" in errs and "confidence" in errs and "2.0" in errs and "blob" in errs
    assert any("discarded" in e for e in validate(ann([draft(status="discarded")], tmp_path / "a.json")))


def test_unconfirmed_excludes_ignored(tmp_path):
    a = ann([piece("x/01", "torso", status="proposed"), draft("x/05", status="ignored")],
            tmp_path / "a.json", m=master(status="proposed"))
    assert unconfirmed(a) == ["x/01", "master"]


def test_master_cannot_be_ignored(tmp_path):
    a = ann([piece("x/01", "torso")], tmp_path / "a.json", m=master(status="ignored"))
    assert any(e.startswith("master") and "ignored" in e for e in validate(a))


# --- T17b: the master's thumb side and painted side must agree (lateral <=> palm, medial <=> back) ---

@pytest.mark.parametrize("ts,fc,ok", [("lateral", "palm", True), ("medial", "back", True),
                                      ("lateral", "back", False), ("medial", "palm", False)])
def test_master_hand_thumb_side_matches_facing(tmp_path, ts, fc, ok):
    m = master()
    m.hands = {"r": {"thumb_side": ts, "facing": fc}}
    errs = [e for e in validate(ann([], tmp_path / "a.json", m=m)) if "hands" in e]
    assert (errs == []) is ok, errs
    if not ok:
        assert "thumb_side" in errs[0] and fc in errs[0]
    draft_m = master(status="proposed")                   # a draft master: a doubt at the checkpoint instead
    draft_m.hands = dict(m.hands)
    a = ann([], tmp_path / "a.json", m=draft_m)
    assert not [e for e in validate(a) if "hands" in e]
    d = [x for x in ra.doubts(a) if x["key"] == "master"]
    assert bool(d) is (not ok), d


# --- final review: names are free-form except the structural ones ---

@pytest.mark.parametrize("role", sorted(ra.STRUCTURAL_ROLES))
def test_structural_roles_need_their_own_name(tmp_path, role):
    p = piece("x/05", role, name="paw", side="l" if role not in ("torso", "hips", "head") else "")
    errs = [e for e in validate(ann([p], tmp_path / "a.json")) if "name" in e]
    assert len(errs) == 1 and "'paw'" in errs[0] and f"must be '{role}'" in errs[0] and "structural" in errs[0], errs
    p.status = "proposed"                                   # a draft too: the name decides its output files
    assert any("'paw'" in e for e in validate(ann([p], tmp_path / "a.json")))


def test_structural_names_are_reserved(tmp_path):
    errs = validate(ann([piece("x/01", "foot", name="hand")], tmp_path / "a.json"))
    assert len(errs) == 1 and "'hand'" in errs[0] and "reserved" in errs[0], errs


@pytest.mark.parametrize("role,name", [("foot", "sneaker"), ("hat", "beanie"), ("neckwear", "neckwear"),
                                       ("tail", "brush"), ("prop", "bell"), ("ear", "lug")])
def test_other_roles_take_any_name(tmp_path, role, name):
    assert validate(ann([piece("x/01", role, name=name)], tmp_path / "a.json")) == []


def test_name_shapes(tmp_path):
    for bad in ("boot_l", "boot_r", "", "a/b", "b*"):
        errs = validate(ann([piece("x/01", "foot", name=bad)], tmp_path / "a.json"))
        assert any(f"name {bad!r}" in e for e in errs), (bad, errs)
    two = [piece("x/01", "foot", name="boot"), piece("x/02", "prop", name="boot", side="")]
    errs = validate(ann(two, tmp_path / "a.json"))
    assert any("'boot'" in e and "foot" in e and "prop" in e for e in errs), errs
    assert validate(ann([draft(status="ignored")], tmp_path / "a.json")) == []     # an unused spare: no name
