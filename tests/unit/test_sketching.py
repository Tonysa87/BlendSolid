"""The Sketch/Extrude tools' pure geometry and the script text they write, run through the worker."""
import math

import pytest

import runner
from blendsolid import script_model as sm, sketching


def test_entity_specs():
    assert sketching.entity_spec("RECTANGLE", (0, 0), (10, 4)).code == \
        "Pos(5.0, 2.0) * Rectangle({name}_width, {name}_height)"
    assert sketching.entity_spec("CIRCLE", (1, 2), (4, 6)).params == (("radius", 5.0),)
    assert sketching.entity_spec("LINE", (0, 0), (0, 0.0001)) is None
    assert sketching.entity_spec("LINE", (0, 0), (1, 2)).code == "Line((0.0, 0.0), (1.0, 2.0))"


def test_point_in_loops_with_a_hole():
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    hole = [[4, 4], [6, 4], [6, 6], [4, 6]]
    assert sketching.point_in_loops([square, hole], (2, 2))
    assert not sketching.point_in_loops([square, hole], (5, 5))
    assert not sketching.point_in_loops([square, hole], (12, 5))


def test_plane_round_trip():
    sketch = {"plane": [[0, 0, 20], [1, 0, 0], [0, 1, 0], [0, 0, 1]]}
    assert sketching.to_plane(sketch, sketching.from_plane(sketch, (3, 4))) == (3, 4, 0)
    assert sketching.same_plane(sketch["plane"], [[5, 5, 20], [0, 1, 0], [-1, 0, 0], [0, 0, 1]])
    assert not sketching.same_plane(sketch["plane"], [[0, 0, 21], [1, 0, 0], [0, 1, 0], [0, 0, 1]])


def _run(source):
    r = runner.run_script(source)
    assert r.ok, (r.error, r.line)
    return r


def _sketched_box():
    source, _ = sm.new_script(sm.FeatureSpec("box", (("length", 40.0), ("width", 30.0), ("height", 20.0)),
                                             "Box({name}_length, {name}_width, {name}_height, "
                                             "align=(Align.CENTER, Align.CENTER, Align.MIN))"))
    source, sketch, _ = sm.append_sketch(source, 'on_face(face("box_1", "+Z"))',
                                         sketching.entity_spec("CIRCLE", (5, 0), (8, 0)))
    return source, sketch


def test_extrude_specs_build():
    source, sketch = _sketched_box()
    cases = [
        (dict(amount=4.0), 24000 + math.pi * 9 * 4),
        (dict(amount=-4.0, operation="SUBTRACT"), 24000 - math.pi * 9 * 4),
        (dict(amount=4.0, symmetric=True, operation="SUBTRACT"), 24000 - math.pi * 9 * 4),
        (dict(amount=-1.0, extent="LAST", operation="SUBTRACT"), 24000 - math.pi * 9 * 20),
        (dict(amount=-1.0, extent="NEXT", operation="SUBTRACT"), 24000 - math.pi * 9 * 20),
    ]
    for kwargs, volume in cases:
        spec = sketching.extrude_spec(sketch, (5.0, 0.0), **kwargs)
        built, _ = sm.append_feature(source, spec)
        assert abs(_run(built).volume - volume) < 1e-6, (kwargs, spec.call)


def test_tapered_extrude_spec_has_a_taper_parameter():
    source, sketch = _sketched_box()
    spec = sketching.extrude_spec(sketch, (5.0, 0.0), 5.0, taper=3.0)
    assert dict(spec.params) == {"amount": 5.0, "taper": 3.0}
    built, name = sm.append_feature(source, spec)
    assert f"{name}_taper = 3.0" in built
    assert _run(built).volume < 24000 + math.pi * 9 * 5


def test_revolve_spec_builds():
    source, sketch, _ = sm.new_sketch_script("Plane.XZ", sketching.rect_spec((15, 0), (19, 10)))
    source, _ = sm.add_entity(source, sketch, sketching.line_spec((0, -20), (0, 20)))
    r = _run(source)
    assert sketching.line_entities(r.sketches[0]) == ["line_1"]
    spec = sketching.revolve_spec(sketch, (17.0, 5.0), "line_1", 180.0)
    built, _ = sm.append_feature(source, spec)
    assert abs(_run(built).volume - math.pi * 17 * 40) < 1e-6


def test_region_at_and_entity_at_on_worker_display():
    source, sketch = _sketched_box()
    source, _ = sm.add_entity(source, sketch, sketching.rect_spec((0, -5), (20, 5)))
    display = _run(source).sketches[0]
    areas = sorted(round(r["area"], 3) for r in display["regions"])
    assert len(areas) == 3  # the circle, the rectangle around it, and the rest of the box's top face
    i = sketching.region_at(display, (5.0, 0.0))
    assert i is not None and display["regions"][i]["area"] < 200
    assert sketching.entity_at(display, (8.0, 0.0), 0.1) == "circle_1"
    assert sketching.nearest_point(display["points"], (19.9, 5.1), 0.5) == [20.0, 5.0]


def test_path_spec_and_preview():
    pts = [(0.0, 0.0, False), (10.0, 0.0, False), (10.0, 10.0, True)]
    assert sketching.path_spec(pts).code == "path((0.0, 0.0), (10.0, 0.0), arc_to((10.0, 10.0)))"
    assert sketching.path_spec(pts, closed=True).code.endswith(", closed=True)")
    # the arc from (10, 0) leaving along +X to (10, 10): a half circle of radius 5 bulging to x = 15
    line = sketching.path_polyline(pts)
    assert max(p[0] for p in line) == pytest.approx(15.0, abs=1e-6)
    assert sketching.end_tangent(pts) == pytest.approx((-1.0, 0.0))


def test_groove_specs_build():
    source, _ = sm.new_script(sm.FeatureSpec("box", (("length", 40.0), ("width", 20.0), ("height", 10.0)),
                                             "Box({name}_length, {name}_width, {name}_height, "
                                             "align=(Align.CENTER, Align.CENTER, Align.MIN))"))
    pts = [(-15.0, -5.0, False), (5.0, -5.0, False), (5.0, 5.0, True), (-15.0, 5.0, False)]
    source, sketch, entity = sm.append_sketch(source, 'on_face(face("box_1", "+Z"))', sketching.path_spec(pts))
    assert entity == "path_1"
    length = 40 + 5 * math.pi
    for kwargs, delta in [(dict(), -4 * length), (dict(profile="v"), -2 * length),
                          (dict(operation="ADD", depth=3.0), 6 * length)]:
        spec = sketching.groove_spec(sketch, entity, 2.0, kwargs.pop("depth", 2.0), **kwargs)
        built, name = sm.append_feature(source, spec)
        assert _run(built).volume - 8000 == pytest.approx(delta, abs=1e-3), spec.call


def test_part_snap_points_project_on_the_sketch_plane_nearest_first():
    top = ((0.0, 0.0, 20.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    projected = sketching.project_points(top, [((20.0, 15.0, 0.0), 0), ((20.0, 15.0, 20.0), 0),
                                               ((10.0, 0.0, 20.0), 2)])
    assert projected[0][0] == (20.0, 15.0) and projected[-1] == ((20.0, 15.0), 0)  # the bottom one comes last
    assert ((10.0, 0.0), 2) in projected
    candidates = [((0.0, 0.0), "point"), ((0.5, 0.0), "vertex")]
    assert sketching.nearest_snap(candidates, (0.4, 0.0), 1.0) == ((0.5, 0.0), "vertex")
    assert sketching.nearest_snap(candidates, (0.25, 0.0), 1.0) == ((0.0, 0.0), "point")  # a tie: the first
    assert sketching.nearest_snap(candidates, (5.0, 0.0), 1.0) is None


def test_angle_lock():
    assert sketching.angle_locked((1.0, 2.0), (11.0, 2.7)) == (11.0, 2.0)  # horizontal: v exact
    assert sketching.angle_locked((1.0, 2.0), (1.3, -8.0)) == (1.0, -8.0)  # vertical: u exact
    u, v = sketching.angle_locked((0.0, 0.0), (10.0, 6.0))  # 31° -> 30°
    assert math.degrees(math.atan2(v, u)) == pytest.approx(30.0, abs=1e-5)
    assert math.hypot(u, v) == pytest.approx(10 * math.cos(math.radians(30)) + 6 * math.sin(math.radians(30)))
    u, v = sketching.angle_locked((0.0, 0.0), (-10.0, -9.0))  # 222° -> 225°
    assert math.degrees(math.atan2(v, u)) % 360 == pytest.approx(225.0, abs=1e-5)


def test_extrude_spec_writes_the_picked_areas_bounding_curves():
    # R11: the seed carries the curves bounding the clicked area, written like the worker's own area() repr
    import sketches
    source, sketch = _sketched_box()
    display = _run(source).sketches[0]
    bounds = sketching.region_bounds(display, (5.0, 0.0))
    assert len(bounds) == 1 and list(bounds.values()) == [["inside"]]
    spec = sketching.extrude_spec(sketch, (5.0, 0.0), 4.0, bounds=bounds)
    area = sketches.Area((5.0, 0.0), **{side: tuple(n for n, s in bounds.items() if side in s)
                                         for side in sketches.SIDES})
    assert f"regions({sketch}, {area!r})" in spec.call
    built, _ = sm.append_feature(source, spec)
    r = _run(built)
    assert abs(r.volume - (24000 + math.pi * 9 * 4)) < 1e-6 and not r.warnings
    outside = sketching.region_bounds(display, (15.0, 10.0))
    assert outside == {"face": ["inside"], **{n: ["outside"] for n in bounds}}
    assert sketching.region_text(sketch, (1.0, 2.0)) == f"regions({sketch}, (1.0, 2.0))"
    assert sketching.region_text(sketch, (1.0, 2.0), {"b": ["left"], "a": ["inside"], "face": ["inside"]}) == \
        f'regions({sketch}, area((1.0, 2.0), inside=("a", "face"), left="b"))'
