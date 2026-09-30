"""Sketches, regions and the extrude/revolve of regions (worker, milestone 3a)."""
import math

import numpy as np
import pytest

import provenance
import runner


def run(body, params=""):
    source = f"{params}\nwith BuildPart() as part:\n{body}\nresult = part.part\n"
    r = runner.run_script(source)
    assert r.ok, (r.error, r.line)
    return r


def resolve_all(source):
    """Every face reference of the result resolves back to its own face (ADR 0009 contract)."""
    r = runner.run_script(source)
    assert r.ok, r.error
    return r


BOX = '    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'


def test_sketch_on_face_extrude_volume_and_roles():
    r = run(BOX + '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.rect_1 = Pos(5.0, 0.0) * Rectangle(10.0, 6.0)\n'
                  '    extrude(regions(sketch_1, (5.0, 0.0)), amount=8.0)  # feature: extrude_1\n')
    assert abs(r.volume - (40 * 30 * 20 + 10 * 6 * 8)) < 1e-6
    refs = set(r.face_refs)
    assert 'face("extrude_1", "end")' in refs
    sides = [t for t in r.face_refs if t.startswith('face("extrude_1", "rect_1"')]
    assert len(sides) == 4 and all("near=" in t for t in sides)


def test_sketch_plane_origin_is_the_part_origin_projected():
    # the box grows: a sketch at (15, 0) stays at x = 15 in the part (Plane(face) would move it with the centre)
    for length in (40.0, 60.0):
        r = run(f'    Box({length}, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
                '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                '        sketch_1.c = Pos(15.0, 0.0) * Circle(2.0)\n')
        plane = r.sketches[0]["plane"]
        assert plane[0] == [0.0, 0.0, 20.0] and plane[1] == [1.0, 0.0, 0.0] and plane[3] == [0.0, 0.0, 1.0]


def test_cut_up_to_last_goes_through():
    r = run(BOX + '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.c = Circle(5.0)\n'
                  '    extrude(regions(sketch_1, (0.0, 0.0)), dir=-sketch_1.plane.z_dir, until=Until.LAST, mode=Mode.SUBTRACT)'
                  '  # feature: hole_1\n')
    assert abs(r.volume - (40 * 30 * 20 - math.pi * 25 * 20)) < 1e-6
    assert any(t == 'face("hole_1", "c")' for t in r.face_refs)


def test_overlapping_entities_make_regions():
    r = run(BOX + '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.r = Rectangle(20.0, 10.0)\n'
                  '        sketch_1.c = Pos(10.0, 0.0) * Circle(4.0)\n'
                  '        sketch_1.l = Line((-15.0, -3.0), (3.0, 2.0))\n')
    areas = sorted(round(g["area"], 4) for g in r.sketches[0]["regions"])
    # the rectangle minus the circle's half, the two halves of the circle (the dangling line splits nothing), and
    # the rest of the face the sketch is on
    assert areas == sorted([round(200 - 8 * math.pi, 4), round(8 * math.pi, 4), round(8 * math.pi, 4),
                            round(1200 - 200 - 8 * math.pi, 4)])
    assert r.sketches[0]["used"] is False


def test_region_with_hole_extrudes_a_ring():
    r = run(BOX + '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.outer = Circle(10.0)\n'
                  '        sketch_1.inner = Circle(4.0)\n'
                  '    extrude(regions(sketch_1, (7.0, 0.0)), amount=5.0)  # feature: extrude_1\n')
    assert abs(r.volume - (24000 + math.pi * (100 - 16) * 5)) < 1e-6


def test_seed_outside_every_region_is_an_error_on_its_line():
    source = ("with BuildPart() as part:\n" + BOX +
              '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.c = Circle(5.0)\n'
              '    extrude(regions(sketch_1, (90.0, 0.0)), amount=5.0)  # feature: extrude_1\n'
              "result = part.part\n")
    r = runner.run_script(source)
    assert not r.ok and "no closed area" in r.error and "(90.0, 0.0)" in r.error and r.line == 5


def test_seed_on_a_boundary_warns():
    r = run(BOX + '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.r = Rectangle(10.0, 10.0)\n'
                  '    extrude(regions(sketch_1, (5.0, 0.0)), amount=5.0)  # feature: extrude_1\n')
    assert any("boundary" in text for _, text in r.warnings)


@pytest.mark.parametrize("taper", [5.0, -5.0])
def test_taper_gives_planes_and_exact_volume(taper):
    r = run(BOX + '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.r = Rectangle(20.0, 10.0)\n'
                  f'    extrude(regions(sketch_1, (0.0, 0.0)), amount=10.0, taper={taper})  # feature: extrude_1\n')
    k = math.tan(math.radians(taper))
    boss = sum((20 - 2 * k * z) * (10 - 2 * k * z) * 0.001 for z in (i * 0.001 + 0.0005 for i in range(10000)))
    assert abs(r.volume - 24000 - boss) < 1e-3
    assert not any("bspline" in t for t in r.face_refs)
    assert len([t for t in r.face_refs if t.startswith('face("extrude_1", "r"')]) == 4


def test_taper_of_an_l_shape_keeps_sharp_corners():
    r = run(BOX + '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.l = Polygon((0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10), align=None)\n'
                  '    extrude(regions(sketch_1, (1.0, 1.0)), amount=5.0, taper=3.0)  # feature: extrude_1\n')
    assert r.faces == 6 + 6 + 1  # the box, the L's six sides (no rounded reflex corner) and its end
    assert not any("side" in t or "bspline" in t for t in r.face_refs)


def test_symmetric_extrude_from_a_plane():
    r = run('    with sketch(Plane.XZ) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.r = Rectangle(20.0, 10.0)\n'
            '    extrude(regions(sketch_1), amount=5.0, both=True)  # feature: extrude_1\n')
    assert abs(r.volume - 20 * 10 * 10) < 1e-6


def test_part_with_only_a_sketch_is_ok_and_empty():
    r = run('    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n'
            '        sketch_1.r = Rectangle(20.0, 10.0)\n')
    assert r.faces == 0 and len(r.verts) == 0 and len(r.sketches) == 1
    assert r.sketches[0]["name"] == "sketch_1" and len(r.sketches[0]["regions"]) == 1


def test_revolve_about_a_sketch_line():
    r = run('    with sketch(Plane.XZ) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.r = Pos(17.0, 5.0) * Rectangle(4.0, 10.0)\n'
                  '        sketch_1.axis = Line((0.0, -20.0), (0.0, 20.0))\n'
            '    revolve(regions(sketch_1, (17.0, 5.0)), axis=sketch_1.axis("axis"), revolution_arc=360)'
            '  # feature: revolve_1\n')
    assert abs(r.volume - 2 * math.pi * 17 * 40) < 1e-6
    assert any(t.startswith('face("revolve_1", "r"') for t in r.face_refs)


def test_partial_revolve_has_start_and_end_caps():
    r = run('    with sketch(Plane.XZ) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.r = Pos(17.0, 5.0) * Rectangle(4.0, 10.0)\n'
                  '        sketch_1.axis = Line((0.0, -20.0), (0.0, 20.0))\n'
            '    revolve(regions(sketch_1, (17.0, 5.0)), axis=sketch_1.axis("axis"), revolution_arc=90)'
            '  # feature: revolve_1\n')
    assert abs(r.volume - 2 * math.pi * 17 * 40 / 4) < 1e-6
    assert 'face("revolve_1", "start")' in r.face_refs and 'face("revolve_1", "end")' in r.face_refs


def test_side_references_survive_an_upstream_change():
    def source(width):
        return (f"w = {width}\nwith BuildPart() as part:\n" + BOX +
                '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.rect_1 = Rectangle(w, 6.0)\n'
                  '        sketch_1.c = Pos(12.0, 0.0) * Circle(2.0)\n'
                '    extrude(regions(sketch_1, (0.0, 0.0)), amount=8.0, taper=2.0)  # feature: extrude_1\n'
                '    fillet(edge_between(face("extrude_1", "end"), face("extrude_1", "rect_1", near=(0.0, 3.0, 28.0))),'
                ' radius=1.0)  # feature: fillet_1\n'
                "result = part.part\n")
    for width in (10.0, 14.0):
        r = runner.run_script(source(width))
        assert r.ok, r.error
        assert not r.warnings, r.warnings


def test_extrude_of_a_face_still_works():
    r = run(BOX + '    extrude(face("box_1", "+Z"), amount=5.0, mode=Mode.ADD)  # feature: push_1\n')
    assert abs(r.volume - 40 * 30 * 25) < 1e-6


def test_on_face_refuses_a_curved_face():
    source = ("with BuildPart() as part:\n"
              "    Cylinder(10, 20)  # feature: cylinder_1\n"
              '    with sketch(on_face(face("cylinder_1", "side"))) as sketch_1:  # feature: sketch_1\n'
              "        sketch_1.c = Circle(1.0)\n"
              "result = part.part\n")
    r = runner.run_script(source)
    assert not r.ok and "flat face" in r.error and r.line == 3


def test_lines_meeting_at_rounded_ends_close_an_area():
    # a triangle whose corner is 6-decimal rounded differently on its two lines (4e-7 mm apart)
    r = run('    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n'
            '        sketch_1.a = Line((0.0, 0.0), (10.0, 0.0))\n'
            '        sketch_1.b = Line((10.0, 0.0), (3.333333, 6.666667))\n'
            '        sketch_1.c = Line((3.3333334, 6.6666666), (0.0, 0.0))\n'
            '    extrude(regions(sketch_1, (4.0, 2.0)), amount=1.0)  # feature: extrude_1\n')
    assert abs(r.volume - 0.5 * 10 * 6.666667) < 1e-4
    points = r.sketches[0]["points"]
    assert [0.0, 0.0] in points and [10.0, 0.0] in points


def test_new_sketch_script_runs():
    from blendsolid import script_model as sm
    source, _, _ = sm.new_sketch_script("Plane.XY", sm.EntitySpec(
        "circle", (("radius", 3.0),), "Pos(1.0, 2.0) * Circle({name}_radius)"))
    source, _ = sm.append_feature(source, sm.FeatureSpec(
        "extrude", (("amount", 4.0),), "extrude(regions(sketch_1, (1.0, 2.0)), amount={name}_amount)"))
    r = runner.run_script(source)
    assert r.ok, r.error
    assert abs(r.volume - math.pi * 9 * 4) < 1e-6 and r.sketches[0]["used"] is True
    assert [1.0, 2.0] in r.sketches[0]["points"]


STACK = ('    Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: low_1\n'
         '    with Locations(Location((0.0, 0.0, 20.0), (0.0, 0.0, 0.0))):  # feature: high_1\n'
         '        Box(40, 30, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))\n')
STACK_VOLUME = 40 * 30 * 15


def _stack_until(face, until, mode, down):
    direction = ", dir=-sketch_1.plane.z_dir" if down else ""
    return run(STACK + f'    with sketch(on_face(face("{face}", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                       '        sketch_1.r = Rectangle(10.0, 10.0)\n'
                       f'    extrude(regions(sketch_1, (1.0, 1.0)){direction}, until=Until.{until}, mode=Mode.{mode})'
                       '  # feature: extrude_1\n')


def test_union_up_to_next_fills_the_gap():
    assert abs(_stack_until("low_1", "NEXT", "ADD", False).volume - (STACK_VOLUME + 100 * 10)) < 1e-6


def test_union_up_to_last_reaches_the_farthest_face():
    assert abs(_stack_until("low_1", "LAST", "ADD", False).volume - (STACK_VOLUME + 100 * 10)) < 1e-6


def test_cut_up_to_next_cuts_the_first_stretch_only():
    assert abs(_stack_until("high_1", "NEXT", "SUBTRACT", True).volume - (STACK_VOLUME - 100 * 5)) < 1e-6


def test_cut_up_to_last_cuts_through_everything():
    assert abs(_stack_until("high_1", "LAST", "SUBTRACT", True).volume - (STACK_VOLUME - 100 * 15)) < 1e-6


def test_union_up_to_next_with_nothing_ahead_is_an_error():
    source = ("with BuildPart() as part:\n" + STACK +
              '    with sketch(on_face(face("high_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
              '        sketch_1.r = Rectangle(10.0, 10.0)\n'
              '    extrude(regions(sketch_1, (1.0, 1.0)), until=Until.NEXT)  # feature: extrude_1\n'
              "result = part.part\n")
    r = runner.run_script(source)
    assert not r.ok and "nothing ahead" in r.error and r.line == 7


def test_union_up_to_a_slanted_face_is_exact():
    r = run('    with Locations(Location((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))):  # feature: base_1\n'
            '        Box(40, 30, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))\n'
            '    with Locations(Location((0.0, 0.0, 20.0), (0.0, 10.0, 0.0))):  # feature: roof_1\n'
            '        Box(60, 40, 2, align=(Align.CENTER, Align.CENTER, Align.MIN))\n'
            '    with sketch(on_face(face("base_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
            '        sketch_1.r = Rectangle(10.0, 10.0)\n'
            '    extrude(regions(sketch_1, (0.0, 0.0)), until=Until.NEXT)  # feature: extrude_1\n')
    base = 40 * 30 * 5 + 60 * 40 * 2
    # the roof's lower plane passes through (0, 0, 20) tilted 10° about Y: z = 20 - x tan(10°) under the column
    assert abs(r.volume - base - 10 * 10 * 15) < 1e-6


# -- paths, face regions, grooves and ribs ---------------------------------------------------------------------------

GROOVE_BOX = '    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
# on the top face: line 20, tangent semicircle r 5, line 20, sharp 90° corner, line 7 (research note, section 6)
GROOVE_PATH = ('    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
               '        sketch_1.path_1 = path((-15.0, -5.0), (5.0, -5.0), arc_to((5.0, 5.0)), (-15.0, 5.0), '
               '(-15.0, -2.0))\n')
PATH_LENGTH = 47 + 5 * math.pi


def test_path_with_a_tangent_arc():
    r = run(GROOVE_BOX + GROOVE_PATH)
    curves = r.sketches[0]["curves"]["path_1"]
    assert len(curves) == 4  # one polyline per edge
    assert [5.0, 5.0] in r.sketches[0]["points"] and [-15.0, -2.0] in r.sketches[0]["points"]


def test_a_path_cannot_start_with_an_arc():
    source = ("with BuildPart() as part:\n" + GROOVE_BOX +
              '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
              '        sketch_1.path_1 = path((0.0, 0.0), arc_to((5.0, 5.0)))\n'
              "result = part.part\n")
    r = runner.run_script(source)
    assert not r.ok and "start with an arc" in r.error and r.line == 4


@pytest.mark.parametrize("profile, corners, removed", [
    ("rect", "mitre", 2 * 2 * PATH_LENGTH),
    ("rect", "round", 2 * (2 * PATH_LENGTH - 1 + math.pi / 4)),  # the sharp corner's outside rounded off
    ("v", "mitre", 2 * 2 / 2 * PATH_LENGTH),
])
def test_grooves_along_a_path(profile, corners, removed):
    r = run(GROOVE_BOX + GROOVE_PATH +
            f'    groove(sketch_1.path_1, width=2.0, depth=2.0, profile="{profile}", corners="{corners}")'
            '  # feature: groove_1\n')
    assert abs(8000 - r.volume - removed) < 1e-3, (8000 - r.volume, removed)


def test_round_groove_and_pipe_rib():
    r = run(GROOVE_BOX + GROOVE_PATH +
            '    groove(sketch_1.path_1, width=2.0, depth=2.0, profile="round")  # feature: groove_1\n')
    u = (2 * 1 + math.pi / 2) * PATH_LENGTH  # a 1 mm deep rectangle 2 wide over a half circle r 1, along the path
    assert abs(8000 - r.volume - u) < 0.05 * u
    r = run(GROOVE_BOX + GROOVE_PATH +
            '    groove(sketch_1.path_1, width=3.0, depth=0.0, profile="circle", corners="round", mode=Mode.ADD)'
            '  # feature: rib_1\n')
    assert r.volume > 8000 and abs(r.volume - 8000 - math.pi * 2.25 * PATH_LENGTH / 2) < 0.05 * 8 * PATH_LENGTH


def test_rib_stands_out_of_the_face():
    r = run(GROOVE_BOX +
            '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
            '        sketch_1.path_1 = path((-10.0, 0.0), (10.0, 0.0))\n'
            '    groove(sketch_1.path_1, width=2.0, depth=3.0, mode=Mode.ADD)  # feature: rib_1\n')
    assert abs(r.volume - 8000 - 2 * 3 * 20) < 1e-6


def test_closed_path_groove():
    r = run(GROOVE_BOX +
            '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
            '        sketch_1.path_1 = path((-10.0, -5.0), (10.0, -5.0), (10.0, 5.0), (-10.0, 5.0), closed=True)\n'
            '    groove(sketch_1.path_1, width=2.0, depth=2.0)  # feature: groove_1\n')
    assert abs(8000 - r.volume - 2 * 2 * 60) < 1e-6


def test_a_line_across_a_face_splits_it_into_regions():
    r = run('    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
            '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
            '        sketch_1.line_1 = Line((0.0, -15.0), (0.0, 15.0))\n'
            '    extrude(regions(sketch_1, (10.0, 0.0)), amount=5.0)  # feature: extrude_1\n'
            '    extrude(regions(sketch_1, (-10.0, 0.0)), amount=-4.0, mode=Mode.SUBTRACT)  # feature: step_1\n')
    areas = sorted(round(g["area"], 6) for g in r.sketches[0]["regions"])
    assert areas == [400.0, 400.0]
    assert abs(r.volume - (8000 + 400 * 5 - 400 * 4)) < 1e-6


def test_snap_points_are_exact_vertices_midpoints_and_centres():
    r = run(BOX + '    with Locations((10, 0, 20)):\n        Cylinder(3, 5, mode=Mode.SUBTRACT)\n')
    pts = {(round(x, 9), round(y, 9), round(z, 9)): int(k) for x, y, z, k in r.snaps}
    assert pts[(20.0, 15.0, 20.0)] == 0 and pts[(-20.0, -15.0, 0.0)] == 0  # box corners
    assert pts[(0.0, 15.0, 20.0)] == 1 and pts[(20.0, 0.0, 0.0)] == 1  # edge midpoints
    assert pts[(10.0, 0.0, 20.0)] == 2  # the hole's centre on the top face
    assert r.snaps.dtype == np.float64 and (20.0, 15.0, 20.0, 0.0) in [tuple(row) for row in r.snaps]  # exact
    assert len(pts) == len(r.snaps)  # no duplicates
