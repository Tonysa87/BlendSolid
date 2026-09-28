"""Fillet and chamfer edge cases (docs/research/2026-09-28-fillet-edge-cases.md, section 5: T1-T23): what works
keeps working, and what OCCT can't do fails on the feature's line with a message that says what would work.
Geometry: Box(40, 30, 20) centred (x -20..20, y -15..15, z -10..10)."""
import math

import pytest

import runner  # worker module, imported as the worker does

BOX = 40 * 30 * 20


def run(body, op):
    """A part script: `body` (statements inside BuildPart as `p`), then `op` as its last line (line 3)."""
    source = f"with BuildPart() as p:\n    {body}\n    {op}\nresult = p.part\n"
    return runner.run_script(source)


def largest(error):
    return float(error.rsplit("the largest that works is ", 1)[1].split(" mm")[0])


TOP = "p.edges().group_by(Axis.Z)[-1]"
LONG_TOP = f"{TOP}.filter_by(Axis.X)"
CORNER = "p.edges().filter_by_position(Axis.X, 20, 20).filter_by_position(Axis.Y, 15, 15) + " \
         "p.edges().filter_by_position(Axis.X, 20, 20).filter_by_position(Axis.Z, 10, 10) + " \
         "p.edges().filter_by_position(Axis.Y, 15, 15).filter_by_position(Axis.Z, 10, 10)"
L_SHAPE = "Box(40, 30, 20)\n    with Locations((10, 0, 5)):\n        Box(20, 30, 10, mode=Mode.SUBTRACT)"
CONCAVE = "p.edges().filter_by(Axis.Y).filter_by_position(Axis.X, 0, 0).filter_by_position(Axis.Z, 0, 0)"


@pytest.mark.parametrize("op, faces", [
    (f"fillet({CORNER}, radius=5)", 10),                     # T1: a corner of three fillets
    ("fillet(p.edges(), radius=9.9)", 26),                    # all 12 edges just under the limit
    ("chamfer(p.edges(), length=5)", 26),
])
def test_corners_and_many_edges_work(op, faces):
    r = run("Box(40, 30, 20)", op)
    assert r.ok and r.faces == faces


@pytest.mark.parametrize("op, size, limit", [
    (f"fillet({LONG_TOP}, radius={{}})", 15, 15),                    # T3: two fillets meet across the 30 mm top
    (f"fillet({LONG_TOP}.sort_by(Axis.Y)[-1], radius={{}})", 25, 20),  # T5: bigger than the 20 mm side face
    ("fillet(p.edges(), radius={})", 10, 10),                        # T6: all edges, 20 mm faces
    (f"chamfer({LONG_TOP}.sort_by(Axis.Y)[-1], length={{}})", 25, 20),  # T21
    (f"chamfer({LONG_TOP}, length={{}})", 15, 15),                   # T23: two chamfers meet
])
def test_too_large_gives_the_limit_on_the_feature_line(op, size, limit):
    r = run("Box(40, 30, 20)", op.format(size))
    assert not r.ok and r.line == 3 and " is too large for " in r.error
    found = largest(r.error)
    assert limit * 0.99 < found < limit
    assert run("Box(40, 30, 20)", op.format(found)).ok


def test_just_under_the_limit_works():  # T4
    assert run("Box(40, 30, 20)", f"fillet({LONG_TOP}, radius=14.9)").ok


def test_cylinder_rim_up_to_its_radius():  # T7, T8
    r = run("Cylinder(10, 20)", "fillet(p.edges().group_by(Axis.Z)[-1], radius=10)")
    assert r.ok and r.faces == 3 and r.volume == pytest.approx(math.pi * 100 * 10 + 2 / 3 * math.pi * 1000, rel=1e-3)
    r = run("Cylinder(10, 20)", "fillet(p.edges().group_by(Axis.Z)[-1], radius=10.5)")
    assert not r.ok and r.line == 3 and 9.9 < largest(r.error) <= 10


def test_a_seam_has_nothing_to_round():  # T9
    r = run("Cylinder(10, 20)", "fillet(p.edges().filter_by(GeomType.LINE), radius=1)")
    assert not r.ok and r.line == 3 and r.error == "this edge is a seam inside one face: there is nothing to round"


ROUNDED = "Box(40, 30, 20)\n    fillet(p.edges().filter_by(Axis.Z), radius=5)"


def test_edges_between_tangent_faces_have_nothing_to_round():  # T10
    r = runner.run_script(f"with BuildPart() as p:\n    {ROUNDED}\n"
                          f"    fillet(p.edges().filter_by(Axis.Z), radius=1)\nresult = p.part\n")
    assert not r.ok and r.line == 4
    assert r.error == "these 8 edges are between tangent faces: there is nothing to round"


@pytest.mark.parametrize("radius", [2, 8, 12])
def test_a_top_edge_of_a_rounded_box_rounds_the_whole_loop(radius):  # T11, T12
    r = runner.run_script(f"with BuildPart() as p:\n    {ROUNDED}\n"
                          f"    fillet({LONG_TOP}.sort_by(Axis.Y)[-1], radius={radius})\nresult = p.part\n")
    base = runner.run_script(f"with BuildPart() as p:\n    {ROUNDED}\nresult = p.part\n")
    assert r.ok and 0 < base.volume - r.volume < BOX  # the tangent chain: the whole top loop is rounded
    assert r.faces > base.faces + 1


def test_concave_edge_adds_material_up_to_its_step():  # T13, T14
    base = run(L_SHAPE, "pass")
    r = run(L_SHAPE, f"fillet({CONCAVE}, radius=3)")
    assert r.ok and r.volume - base.volume == pytest.approx((9 - 9 * math.pi / 4) * 30, rel=1e-3)
    r = runner.run_script(f"with BuildPart() as p:\n    {L_SHAPE}\n    fillet({CONCAVE}, radius=12)\nresult = p.part\n")
    assert not r.ok and r.line == 5 and 9.9 < largest(r.error) < 10


def test_mixed_corner_works():  # T15: one concave and two convex edges at (0, 15, 0)
    r = runner.run_script(f"with BuildPart() as p:\n    {L_SHAPE}\n"
                          f"    fillet([e for e in p.edges() if min((e.position_at(t) - Vector(0, 15, 0)).length for t in (0, 1))"
                          f" < 1e-6], radius=2)\n"
                          f"result = p.part\n")
    assert r.ok


HOLE_IN_BAND = "Box(40, 30, 20)\n    with Locations((0, 13, 0)):\n        Cylinder(1, 20, mode=Mode.SUBTRACT)"


@pytest.mark.parametrize("radius", [5, 1])
def test_a_hole_inside_the_rounding_is_never_accepted(radius):  # T16, T17
    # OCCT reports success with a self-intersecting solid; the working radii are not an interval (1 mm fails,
    # 1.5 mm works): the message must not say "too large" nor give a "largest" equal to the failing size
    r = runner.run_script(f"with BuildPart() as p:\n    {HOLE_IN_BAND}\n"
                          f"    fillet({LONG_TOP}.sort_by(Axis.Y)[-1], radius={radius})\nresult = p.part\n")
    assert not r.ok and r.line == 5
    assert f"fillet radius {radius} mm " in r.error
    assert "the largest that works is 1 mm" not in r.error and f"the largest that works is {radius} mm" not in r.error
    if radius == 1:  # 1 mm fails (the rounding's edge touches the hole) while larger radii work: say so
        assert "another face is in the way" in r.error and "fails at 1 mm" in r.error and "1.5" in r.error


def test_asymmetric_chamfer_volume():  # T22
    r = run("Box(40, 30, 20)", f"chamfer({LONG_TOP}.sort_by(Axis.Y)[-1], length=5, length2=15)")
    assert r.ok and BOX - r.volume == pytest.approx(0.5 * 5 * 15 * 40, rel=1e-6)


def test_pyramid_apex_four_edges():  # T19: OCCT's documented 4-edge limit, not hit in OCCT 8
    r = runner.run_script("p = Solid.make_wedge(20, 20, 20, 10, 10, 10, 10)\n"
                          "apex = Vector(10, 20, 10)\n"
                          "result = fillet([e for e in p.edges() if min((e.position_at(t) - apex).length"
                          " for t in (0, 1)) < 1e-6], radius=2)\n")
    assert r.ok


def test_a_sliver_is_named():  # T18: a 0.005 mm face left by a boolean
    r = runner.run_script("with BuildPart() as p:\n    Box(40, 30, 20)\n    with Locations((20.0025, 0, -0.005)):\n"
                          "        Box(0.005, 30, 19.99)\n    fillet(p.edges().group_by(Axis.Z)[-1], radius=2)\n"
                          "result = p.part\n")
    assert not r.ok and r.line == 5 and "a 0.005 mm edge, a sliver left by an earlier feature" in r.error


def test_no_edges_keeps_build123d_error():
    r = run("Box(40, 30, 20)", "fillet([], radius=2)")
    assert not r.ok and r.error.startswith("ValueError")


def test_standalone_fillet_works_like_the_builder():
    r = runner.run_script("b = Box(40, 30, 20)\nresult = fillet(b.edges().filter_by(Axis.Z), radius=16)\n")
    assert not r.ok and r.line == 2 and 14.9 < largest(r.error) < 15
