"""Face/edge provenance and references in part scripts (milestone 2 phase B, worker side)."""
import os
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
    names = Counter(tracker.edge_label(e.wrapped) for e in shape.edges())
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
