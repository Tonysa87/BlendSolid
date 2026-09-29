"""Face/edge provenance and references in part scripts (milestone 2 phase B, worker side)."""
import os
import re
from collections import Counter

import pytest

import provenance  # worker module, imported as the worker does

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT = open(os.path.join(ROOT, "blendsolid", "templates", "default_part.py")).read()

BRACKET = """box_1_length = 80.0
box_1_width = 40.0
box_1_height = 10.0
wall_1_height = 30.0
cut_2_radius = 4.0

with BuildPart() as part:
    Box(box_1_length, box_1_width, box_1_height, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with Locations(Location((-40.0, 0.0, 10.0), (0.0, 0.0, 0.0))):  # feature: wall_1
        Box(10.0, box_1_width, wall_1_height, align=(Align.MIN, Align.CENTER, Align.MIN))
    with Locations(Location((-10.0, 0.0, 10.0), (0.0, 0.0, 0.0))):  # feature: cut_1
        Cylinder(4.0, 10.0, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((10.0, 0.0, 10.0), (0.0, 0.0, 0.0))):  # feature: cut_2
        Cylinder(cut_2_radius, 10.0, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    fillet(part.edges().filter_by(Axis.Y).group_by(Axis.Z)[-1], radius=2)  # feature: fillet_1

result = part.part
"""

SLOT = """with BuildPart() as part:
    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with Locations(Location((0.0, 0.0, 20.0), (0.0, 0.0, 0.0))):  # feature: slot_1
        Box(8, 40, 5, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)

result = part.part
"""

ROTATED = """with BuildPart() as part:
    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with Locations(Location((0.0, 0.0, 20.0), (0.0, 90.0, 0.0))):  # feature: boss_1
        Cylinder(5, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))

result = part.part
"""


SKETCHED = """with BuildPart() as part:
    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.rect_1 = Pos(-8.0, 0.0) * Rectangle(12.0, 8.0)
        sketch_1.circle_1 = Pos(10.0, 4.0) * Circle(3.0)
    extrude(regions(sketch_1, (-8.0, 0.0)), amount=6.0, taper=4.0)  # feature: extrude_1
    extrude(regions(sketch_1, (10.0, 4.0)), amount=-1, until=Until.LAST, mode=Mode.SUBTRACT)  # feature: hole_1
    with sketch(on_face(face("box_1", "-X"))) as sketch_2:  # feature: sketch_2
        sketch_2.slot_1 = Pos(0.0, 10.0) * SlotCenterToCenter(10.0, 4.0)
    extrude(regions(sketch_2), amount=-3.0, mode=Mode.SUBTRACT)  # feature: pocket_1
result = part.part
"""


def build(source):
    """(result shape, tracker) of a canonical script run through the instrumented build."""
    tracker = provenance.Tracker()
    ns = provenance.namespace(tracker)
    exec(provenance.instrument(source, "<part>"), ns)
    return ns["result"], tracker


def labels(source):
    _, tracker = build(source)
    return Counter(label for _, label in tracker.labels())


def test_default_part_faces_are_named_by_feature_and_role():
    got = labels(DEFAULT)
    assert sum(got.values()) == 9 and set(got.values()) == {1}
    assert {("box_1", "+Z"), ("box_1", "-Z"), ("box_1", "+X"), ("boss_1", "side"), ("boss_1", "+Z"),
            ("fillet_1", "blend")} <= set(got)


def test_labels_survive_an_upstream_change():
    assert labels(DEFAULT) == labels(DEFAULT.replace("box_1_length = 40.0", "box_1_length = 55.0"))
    assert labels(BRACKET) == labels(BRACKET.replace("cut_2_radius = 4.0", "cut_2_radius = 6.0")
                                     .replace("wall_1_height = 30.0", "wall_1_height = 45.0"))


def test_bracket_faces_are_all_labelled():
    got = labels(BRACKET)
    assert ("cut_1", "side") in got and ("cut_2", "side") in got and got[("fillet_1", "blend")] == 2
    assert all(role != "new" for _, role in got)
    # the wall's -X face is coplanar with the box's -X face: build123d's clean() merges them into one face
    assert got[("box_1", "-X")] == 1 and ("wall_1", "-X") not in got


def test_a_split_face_keeps_its_label_on_both_pieces():
    got = labels(SLOT)
    assert got[("box_1", "+Z")] == 2 and got[("slot_1", "-Z")] == 1


def test_roles_are_in_the_feature_frame():
    got = labels(ROTATED)  # the boss lies on its side: its own +Z points along the part's +X
    assert ("boss_1", "+Z") in got and ("boss_1", "side") in got


def test_edges_are_named_by_their_two_faces():
    shape, tracker = build(DEFAULT)
    seams = [e for e in shape.edges() if len(tracker.edge_faces(e.wrapped)) == 1]
    assert len(seams) == 1  # the boss's side is closed on itself: no pair of faces
    names = Counter(tracker.edge_label(e.wrapped) for e in shape.edges() if e not in seams)
    assert None not in names and set(names.values()) == {1}
    assert (("box_1", "+Z"), ("box_1", "-Y")) in names


def test_a_failing_feature_reports_the_users_line():
    source = DEFAULT.replace("radius=fillet_1_radius", "radius=50")
    with pytest.raises(Exception) as info:
        build(source)
    line = next(n for n, text in enumerate(source.splitlines(), 1) if "radius=50" in text)
    tb = info.tb
    lines = []
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "<part>":
            lines.append(tb.tb_lineno)
        tb = tb.tb_next
    assert lines and lines[-1] == line


def test_scripts_without_features_are_not_instrumented():
    assert provenance.instrument("result = Box(1, 2, 3)\n", "<part>") is None


# -- references in part scripts ------------------------------------------------------------------------------------

def with_feature(source, line):
    """`source` with one more feature statement at the end of its BuildPart block."""
    head, tail = source.split("\nresult = part.part", 1)
    return head.rstrip("\n") + "\n    " + line + "\n\nresult = part.part" + tail


def test_fillet_by_reference_equals_the_handwritten_selector():
    by_ref, _ = build(with_feature(SLOT, 'fillet(edge_between(face("box_1", "+X"), face("box_1", "-Y")), radius=2)'
                                         '  # feature: fillet_1'))
    by_hand, _ = build(with_feature(SLOT, 'fillet(part.edges().filter_by(Axis.Z).group_by(Axis.X)[-1]'
                                          '.sort_by(Axis.Y)[0], radius=2)  # feature: fillet_1'))
    assert by_ref.volume == pytest.approx(by_hand.volume, rel=1e-9) and by_ref.volume < 40 * 30 * 20 - 8 * 30 * 5


def test_chamfer_all_edges_of_a_face():
    shape, tracker = build(with_feature(DEFAULT, 'chamfer(edges_of(face("boss_1", "+Z")), length=1)'
                                                 '  # feature: chamfer_1'))
    assert Counter(label for _, label in tracker.labels())[("chamfer_1", "blend")] == 1
    assert shape.is_valid


@pytest.mark.parametrize("line, message", [
    ('fillet(edges_of(face("box_1", "+Q")), radius=1)  # feature: fillet_2', "box_1 has no face '+Q'"),
    ('fillet(edges_of(face("nope_1", "+Z")), radius=1)  # feature: fillet_2', "no feature 'nope_1' before this line"),
    ('fillet(edge_between(face("box_1", "+Z"), face("box_1", "-Z")), radius=1)  # feature: fillet_2',
     "no edge between box_1 +Z and box_1 -Z"),
])
def test_broken_references_name_what_is_missing(line, message):
    source = with_feature(DEFAULT, line)
    with pytest.raises(provenance.BrokenReference, match=re.escape(message)) as info:
        build(source)
    tb, lines = info.tb, []
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "<part>":
            lines.append(tb.tb_lineno)
        tb = tb.tb_next
    assert lines[-1] == source.splitlines().index("    " + line) + 1


def test_near_picks_one_piece_of_a_split_face():
    for x, sign in ((12.0, 1), (-12.0, -1)):
        ns = provenance.namespace(provenance.Tracker())
        exec(provenance.instrument(with_feature(SLOT, f'picked = face("box_1", "+Z", near=({x}, 0.0, 20.0))'
                                                      '  # feature: probe_1'), "<part>"), ns)
        (picked,) = ns["picked"]
        assert picked.center().X * sign > 0
    ns = provenance.namespace(provenance.Tracker())
    exec(provenance.instrument(with_feature(SLOT, 'both = face("box_1", "+Z")  # feature: probe_1'), "<part>"), ns)
    assert len(ns["both"]) == 2


def test_nearest_face_in_a_script_without_features():
    ns = provenance.namespace(provenance.Tracker())
    exec("b = Box(10, 10, 10)\npicked = nearest_face((0, 0, 5), b)\nresult = b\n", ns)
    assert ns["picked"].center().Z == pytest.approx(5)


# -- reference texts: what a click on a face or an edge writes -----------------------------------------------------

@pytest.mark.parametrize("source", [DEFAULT, BRACKET, SLOT, ROTATED, SKETCHED],
                         ids=["default", "bracket", "slot", "rotated", "sketched"])
def test_every_reference_text_resolves_to_its_own_entity(source):
    import tessellate
    shape, tracker = build(source)
    faces, edges = tessellate.face_map(shape.wrapped), tessellate.edge_map(shape.wrapped)
    face_refs, edge_refs = provenance.reference_texts(tracker, faces, edges)
    assert len(face_refs) == len(faces) and len(edge_refs) == len(edges)
    clickable = [t for t in edge_refs if t]
    assert len(set(face_refs)) == len(faces) and len(set(clickable)) == len(clickable)
    assert len(edge_refs) - len(clickable) == sum(1 for e in edges if len(tracker.edge_faces(e)) == 1)  # seams
    assert all(t.startswith("face(") for t in face_refs)  # every face has provenance
    # what a click writes, run in the script after the last feature: the same entity (same index in the maps)
    for texts, mapping in ((face_refs, tessellate.face_map), (edge_refs, tessellate.edge_map)):
        for index, text in enumerate(texts):
            if not text:
                continue
            ns = provenance.namespace(provenance.Tracker())
            exec(provenance.instrument(with_feature(source, f"probe = {text}  # feature: probe_1"), "<part>"), ns)
            got = ns["probe"]
            got = list(got) if isinstance(got, list) else [got]
            assert len(got) == 1 and got[0].wrapped.IsSame(mapping(ns["result"].wrapped)[index]), text


def test_no_reference_texts_without_features():
    tracker = provenance.Tracker()
    exec("result = Box(40, 30, 20)\n", provenance.namespace(tracker))
    assert provenance.reference_texts(tracker, [], []) is None
