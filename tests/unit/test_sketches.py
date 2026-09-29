"""Sketches, regions and the extrude/revolve of regions (worker, milestone 3a)."""
import math

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
                  '    extrude(regions(sketch_1, (0.0, 0.0)), amount=-1, until=Until.LAST, mode=Mode.SUBTRACT)'
                  '  # feature: hole_1\n')
    assert abs(r.volume - (40 * 30 * 20 - math.pi * 25 * 20)) < 1e-6
    assert any(t == 'face("hole_1", "c")' for t in r.face_refs)


def test_overlapping_entities_make_regions():
    r = run(BOX + '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
                  '        sketch_1.r = Rectangle(20.0, 10.0)\n'
                  '        sketch_1.c = Pos(10.0, 0.0) * Circle(4.0)\n'
                  '        sketch_1.l = Line((-15.0, -3.0), (3.0, 2.0))\n')
    areas = sorted(round(g["area"], 4) for g in r.sketches[0]["regions"])
    # the rectangle minus the circle's half, the two halves of the circle; the dangling line splits nothing
    assert areas == sorted([round(200 - 8 * math.pi, 4), round(8 * math.pi, 4), round(8 * math.pi, 4)])
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
              '    extrude(regions(sketch_1, (9.0, 0.0)), amount=5.0)  # feature: extrude_1\n'
              "result = part.part\n")
    r = runner.run_script(source)
    assert not r.ok and "no closed area" in r.error and r.line == 5


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
