"""Milestone 3a: the Sketch, Extrude and Revolve tools' operators (the drags end by calling them)."""
import json
import math

import bpy
import pytest
from mathutils import Matrix, Vector

from blendsolid import ops_extrude, ops_sketch, part, script_model, sketching
from conftest import mm3, up_to_date, wait_for


def sketch(shape, start, end, target="", sketch_name="", plane="", matrix=None, points=None, closed=False):
    kwargs = dict(shape=shape, start=start, end=end, target=target, sketch=sketch_name, plane=plane)
    if shape == "LINE":  # a two-point path
        kwargs.update(shape="PATH", points=json.dumps([[*start, False], [*end, False]]))
    if points is not None:
        kwargs.update(points=json.dumps(points), closed=closed)
    if matrix is not None:
        kwargs["matrix"] = [v for row in matrix for v in row]
    return bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, **kwargs)


@pytest.fixture
def box(clean):
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)  # 40 x 30 x 20 mm, base centred on the origin
    obj = bpy.context.object
    wait_for(lambda: up_to_date(obj))
    return obj


def test_a_sketch_on_the_cursor_plane_makes_a_part_with_only_a_sketch(clean):
    placed = Matrix.Translation((0.1, 0.0, 0.0)) @ Matrix.Rotation(math.radians(90), 4, "X")
    assert sketch("RECTANGLE", (0.0, 0.0), (20.0, 10.0), matrix=placed) == {"FINISHED"}
    obj = bpy.context.object
    assert "with sketch(Plane.XY) as sketch_1:" in part.source_of(obj)
    assert all(abs(a - b) < 1e-6 for r, q in zip(obj.matrix_world, placed) for a, b in zip(r, q))
    wait_for(lambda: up_to_date(obj))
    assert obj.blendsolid_error == "" and len(obj.data.polygons) == 0
    (drawn,) = ops_sketch.sketches_of(obj)
    assert drawn["name"] == "sketch_1" and not drawn["used"] and len(drawn["regions"]) == 1
    assert drawn["regions"][0]["area"] == pytest.approx(200.0)
    # extrude it: the part gets its first solid, the sketch is used
    assert bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target=obj.name, sketch="sketch_1", seed=(10.0, 5.0),
                                      amount=5.0, operation="ADD") == {"FINISHED"}
    wait_for(lambda: up_to_date(obj))
    assert obj.blendsolid_error == "" and mm3(obj) == pytest.approx(1000.0, rel=1e-6)
    assert ops_sketch.sketches_of(obj)[0]["used"]


def test_sketch_on_a_face_then_cut_through_and_undo(box):
    assert sketch("CIRCLE", (5.0, 0.0), (8.0, 0.0), target=box.name, plane='on_face(face("box_1", "+Z"))') \
        == {"FINISHED"}
    assert sketch("RECTANGLE", (-15.0, -5.0), (-5.0, 5.0), target=box.name, sketch_name="sketch_1") == {"FINISHED"}
    source = part.source_of(box)
    assert [e.name for e in script_model.sketch_entities(source, "sketch_1")] == ["circle_1", "rect_1"]
    wait_for(lambda: up_to_date(box))
    (drawn,) = ops_sketch.sketches_of(box)
    assert len(drawn["regions"]) == 3 and drawn["plane"][0] == [0.0, 0.0, 20.0]  # and the rest of the face
    assert bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target=box.name, sketch="sketch_1", seed=(5.0, 0.0),
                                      amount=-1.0, operation="SUBTRACT", extent="LAST") == {"FINISHED"}
    wait_for(lambda: up_to_date(box))
    assert mm3(box) == pytest.approx(24000 - math.pi * 9 * 20, rel=1e-3)
    # the seed carries the picked area's bounding curves (R11: never re-bound silently)
    assert 'regions(sketch_1, area((5.0, 0.0), inside=("circle_1", "face")))' in part.source_of(box)
    bpy.ops.ed.undo()
    obj = bpy.data.objects["Box"]  # references die on undo
    wait_for(lambda: up_to_date(obj))
    assert "extrude(" not in part.source_of(obj) and mm3(obj) == pytest.approx(24000, rel=1e-6)


def test_tapered_boss(box):
    sketch("RECTANGLE", (-5.0, -5.0), (5.0, 5.0), target=box.name, plane='on_face(face("box_1", "+Z"))')
    bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target=box.name, sketch="sketch_1", seed=(0.0, 0.0),
                               amount=10.0, operation="ADD", taper=5.0)
    wait_for(lambda: up_to_date(box) or box.blendsolid_error)
    assert box.blendsolid_error == ""
    k = math.tan(math.radians(5))
    boss = sum((10 - 2 * k * (i + 0.5) / 100) ** 2 / 100 for i in range(1000))
    assert box.blendsolid_error == "" and mm3(box) == pytest.approx(24000 + boss, rel=1e-3)
    assert "extrude_1_taper = 5.0" in part.source_of(box)


def test_revolve_about_a_sketch_line(clean):
    sketch("RECTANGLE", (15.0, 0.0), (19.0, 10.0), matrix=Matrix.Identity(4))
    obj = bpy.context.object
    sketch("LINE", (0.0, -20.0), (0.0, 20.0), target=obj.name, sketch_name="sketch_1")
    wait_for(lambda: up_to_date(obj) or obj.blendsolid_error)
    assert obj.blendsolid_error == ""
    assert bpy.ops.blendsolid.revolve("EXEC_DEFAULT", True, target=obj.name, sketch="sketch_1", seed=(17.0, 5.0),
                                      axis="path_1", angle=360.0) == {"FINISHED"}
    wait_for(lambda: up_to_date(obj))
    assert obj.blendsolid_error == "" and mm3(obj) == pytest.approx(2 * math.pi * 17 * 40, rel=1e-2)
    assert 'area((17.0, 5.0), inside="rect_1")' in part.source_of(obj)


def test_pick_sketch_and_region_by_ray(clean):
    sketch("RECTANGLE", (0.0, 0.0), (20.0, 10.0), matrix=Matrix.Identity(4))
    obj = bpy.context.object
    wait_for(lambda: up_to_date(obj))
    factor = part.unit_factor()
    origin, down = Vector((5 * factor, 5 * factor, 1.0)), Vector((0, 0, -1))
    found = ops_extrude.pick_region(bpy.context, origin, down)
    assert found is not None and found[0] == obj and found[2] == pytest.approx((5.0, 5.0), abs=1e-4)
    assert ops_extrude.pick_region(bpy.context, Vector((30 * factor, 5 * factor, 1.0)), down) is None
    target = ops_sketch.pick_target(bpy.context, Vector((24 * factor, 5 * factor, 1.0)), down)
    assert target.obj == obj and target.sketch == "sketch_1"  # near the sketch: drawing adds to it


def test_the_hovered_face_plane_sticks_just_off_the_face(box):
    """The maintainer's GUI test (2026-09-29): a path started just outside the top face went on the cursor's plane.
    After hovering the face, a ray just off it still draws on the face's plane; far away, or after the script
    changes, the cursor's plane is back."""
    factor = part.unit_factor()
    down = Vector((0, 0, -1))

    def ray(x_mm, y_mm):
        return Vector((x_mm * factor, y_mm * factor, 1.0)), down

    ops_sketch._sticky = None
    assert ops_sketch.hover_target(bpy.context, *ray(25.0, 0.0)).obj is None  # never hovered the face: cursor plane
    on_face = ops_sketch.hover_target(bpy.context, *ray(10.0, 0.0))
    assert on_face.obj == box and on_face.plane_code == 'on_face(face("box_1", "+Z"))'
    off = ops_sketch.hover_target(bpy.context, *ray(25.0, 0.0))  # 5 mm past the +X edge
    assert off.obj == box and off.plane_code == on_face.plane_code
    uv, _ = ops_sketch.ray_uv(off.plane, *ray(25.0, 3.0), factor)
    assert uv == pytest.approx((25.0, 3.0), abs=1e-4)  # the point is on the face's plane, off the face
    assert ops_sketch.hover_target(bpy.context, *ray(-25.0, 0.0)).obj == box  # the other side too
    assert ops_sketch.hover_target(bpy.context, *ray(500.0, 0.0)).obj is None  # far away: released
    assert ops_sketch.hover_target(bpy.context, *ray(25.0, 0.0)).obj is None  # and stays released
    # a line drawn from outside one edge to outside the other splits the face (Extrude Sketch then has a piece)
    ops_sketch.hover_target(bpy.context, *ray(10.0, 0.0))
    target = ops_sketch.hover_target(bpy.context, *ray(-25.0, 0.0))
    assert sketch("LINE", (-25.0, 0.0), (25.0, 0.0), target=box.name, plane=target.plane_code) == {"FINISHED"}
    wait_for(lambda: up_to_date(box))
    (drawn,) = ops_sketch.sketches_of(box)
    assert sorted(r["area"] for r in drawn["regions"]) == pytest.approx([600.0, 600.0])
    # the script changed: the stored "new sketch on the face" plane is dropped, the new sketch is found instead
    assert ops_sketch.hover_target(bpy.context, *ray(25.0, 0.0)).sketch == "sketch_1"  # in the sketch's margin
    assert ops_sketch.hover_target(bpy.context, *ray(10.0, 5.0)).sketch == "sketch_1"


def test_a_face_target_snaps_to_the_parts_exact_points(box):
    factor = part.unit_factor()
    ops_sketch._sticky = None
    target = ops_sketch.hover_target(bpy.context, Vector((10 * factor, 0.0, 1.0)), Vector((0, 0, -1)))
    assert target.frame is not None and target.frame[0][2] == 20.0
    projected = dict((uv, kind) for uv, kind in reversed(
        sketching.project_points(target.frame, part.snap_points(box))))
    assert projected[(20.0, 15.0)] == 0 and projected[(0.0, 15.0)] == 1  # a top corner, a top edge's middle
    # an existing sketch's target carries the sketch's own plane
    sketch("LINE", (-25.0, 0.0), (25.0, 0.0), target=box.name, plane=target.plane_code)
    wait_for(lambda: up_to_date(box))
    again = ops_sketch.hover_target(bpy.context, Vector((10 * factor, 5 * factor, 1.0)), Vector((0, 0, -1)))
    assert again.sketch == "sketch_1" and tuple(again.frame[0]) == (0.0, 0.0, 20.0)


def test_part_points_follow_the_part_and_the_plane(box):
    # the hover marker asks on every redraw: cached, but a new result or another plane recomputes them
    factor = part.unit_factor()
    ops_sketch._sticky = None
    top = ops_sketch.hover_target(bpy.context, Vector((10 * factor, 0.0, 1.0)), Vector((0, 0, -1)))
    first = ops_sketch.part_points(top)
    assert first == sketching.project_points(top.frame, part.snap_points(box))
    assert ops_sketch.part_points(top) is first
    assert ((20.0, 15.0), 0) in first
    part.set_param(box, "box_1_length", 60.0)
    wait_for(lambda: up_to_date(box))
    again = ops_sketch.part_points(top)
    assert again is not first and ((30.0, 15.0), 0) in again and ((20.0, 15.0), 0) not in again
    assert ops_sketch.part_points(ops_sketch.Target(top.plane)) == []  # a new part: nothing to snap to


def test_sketch_on_a_curved_face_is_refused_by_the_worker(clean):
    bpy.ops.blendsolid.add_cylinder("EXEC_DEFAULT", True)
    obj = bpy.context.object
    wait_for(lambda: up_to_date(obj))
    sketch("CIRCLE", (0.0, 0.0), (1.0, 0.0), target=obj.name, plane='on_face(face("cylinder_1", "side"))')
    wait_for(lambda: obj.blendsolid_error != "")
    assert "flat face" in obj.blendsolid_error


def test_a_path_with_an_arc_then_a_groove_and_a_rib(box):
    points = [[-15.0, -5.0, False], [5.0, -5.0, False], [5.0, 5.0, True], [-15.0, 5.0, False]]
    assert sketch("PATH", (0, 0), (0, 0), target=box.name, plane='on_face(face("box_1", "+Z"))', points=points) \
        == {"FINISHED"}
    assert "sketch_1.path_1 = path((-15.0, -5.0), (5.0, -5.0), arc_to((5.0, 5.0)), (-15.0, 5.0))" \
        in part.source_of(box)
    wait_for(lambda: up_to_date(box))
    length = 40 + 5 * math.pi
    assert bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, target=box.name, sketch="sketch_1", entity="path_1",
                                     width=2.0, depth=1.5, operation="SUBTRACT") == {"FINISHED"}
    wait_for(lambda: up_to_date(box))
    assert box.blendsolid_error == "" and mm3(box) == pytest.approx(24000 - 3 * length, rel=1e-4)
    assert bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, target=box.name, sketch="sketch_1", entity="path_1",
                                     width=2.0, depth=2.0, profile="v", operation="SUBTRACT") == {"FINISHED"}
    wait_for(lambda: up_to_date(box))
    assert box.blendsolid_error == ""


def test_a_line_across_a_face_splits_it(box):
    sketch("LINE", (0.0, -20.0), (0.0, 20.0), target=box.name, plane='on_face(face("box_1", "+Z"))')
    wait_for(lambda: up_to_date(box))
    (drawn,) = ops_sketch.sketches_of(box)
    assert sorted(round(r["area"], 6) for r in drawn["regions"]) == [600.0, 600.0]
    bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target=box.name, sketch="sketch_1", seed=(10.0, 0.0),
                               amount=-5.0, operation="SUBTRACT")
    wait_for(lambda: up_to_date(box))
    assert mm3(box) == pytest.approx(24000 - 600 * 5, rel=1e-6)


@pytest.mark.parametrize("tool", ["extrude", "groove"])
def test_dragging_down_on_a_part_that_is_only_a_sketch_never_cuts(clean, monkeypatch, tool):
    # the drag chose join/rib or cut from the part's live mesh, which is the drag's own preview: once the first
    # preview arrived, a drag going on downwards turned into a cut of nothing ("Nothing to subtract from") and the
    # part failed (bug sweep, 2026-10-04)
    from types import SimpleNamespace

    from blendsolid import drawing, ops_draw
    if tool == "extrude":
        assert sketch("RECTANGLE", (0.0, 0.0), (20.0, 10.0), matrix=Matrix.Identity(4)) == {"FINISHED"}
    else:
        assert sketch("LINE", (0.0, 0.0), (20.0, 0.0), matrix=Matrix.Identity(4)) == {"FINISHED"}
    obj = bpy.context.object
    wait_for(lambda: up_to_date(obj))
    (drawn,) = ops_sketch.sketches_of(obj)
    factor = part.unit_factor()
    drag = {"mm": 0.0}
    monkeypatch.setattr(ops_draw, "_mouse_ray", lambda context, event: (None, None))
    monkeypatch.setattr(drawing, "height_along_normal", lambda *args: drag["mm"] * factor)
    cls = ops_extrude.BLENDSOLID_OT_extrude if tool == "extrude" else ops_extrude.BLENDSOLID_OT_groove
    op = SimpleNamespace(_obj=obj, _sketch=drawn, _uv=(5.0, 5.0), _seed=(5.0, 5.0), _name="path_1", _plane=None,
                         _start=None, _factor=factor, _source=part.source_of(obj), _amount=0.0, _snap=0.0,
                         _solid=ops_extrude.has_solid(obj), width=2.0, profile="rect", corners="mitre")
    if tool == "groove":
        op._operation = lambda amount: cls._operation(op, amount)
    event = SimpleNamespace(ctrl=False, shift=False)
    for mm in (-1.0, -3.0):
        drag["mm"] = mm
        cls._update(op, bpy.context, event)
        assert "SUBTRACT" not in part.source_of(obj), (mm, part.source_of(obj))
        wait_for(lambda: up_to_date(obj))
        assert obj.blendsolid_error == "" and len(obj.data.polygons) > 0


def _drive_path(monkeypatch, clicks):
    """The Sketch tool's Path modal, driven by clicks at (x, y) mm on the 3D cursor's plane seen from above (one
    region pixel = 0.1 mm); returns the operator after the last click."""
    import types

    from blendsolid import ops_draw
    monkeypatch.setattr(ops_draw, "mouse_ray", lambda context, p: (
        Vector((p[0] * 0.1e-3, p[1] * 0.1e-3, 1.0)), Vector((0.0, 0.0, -1.0))))
    monkeypatch.setattr(ops_draw, "_pixel_size", lambda region, rv3d, p: 0.1e-3)
    monkeypatch.setattr(ops_draw, "_near_rays", lambda context, p, radius=4: [])
    c = bpy.context
    area = types.SimpleNamespace(type="VIEW_3D", header_text_set=lambda text: None, tag_redraw=lambda: None)
    context = types.SimpleNamespace(
        area=area, region=None, region_data=object(), scene=c.scene, preferences=c.preferences, window=c.window,
        window_manager=types.SimpleNamespace(modal_handler_add=lambda op: None), view_layer=c.view_layer,
        collection=c.collection, evaluated_depsgraph_get=c.evaluated_depsgraph_get, mode="OBJECT", object=c.object,
        selected_objects=[], visible_objects=list(c.visible_objects), workspace=None)
    cls = ops_sketch.BLENDSOLID_OT_sketch_entity
    op = types.SimpleNamespace(shape="PATH", target="", sketch="", plane="", start=(0.0, 0.0), end=(0.0, 0.0),
                               points="", closed=False, matrix=[0.0] * 16, exact="", report=lambda *a: None)
    for name in dir(cls):  # the operator's own methods, bound to the stand-in
        if isinstance(getattr(cls, name, None), types.FunctionType) and name not in ("invoke", "modal"):
            setattr(op, name, types.MethodType(getattr(cls, name), op))

    def event(kind, value, x, y):
        return types.SimpleNamespace(type=kind, value=value, mouse_region_x=10 * x, mouse_region_y=10 * y,
                                     ctrl=False, shift=False, oskey=False, alt=False)
    results = [cls.invoke(op, context, event("LEFTMOUSE", "PRESS", *clicks[0]))]
    results.append(cls.modal(op, context, event("LEFTMOUSE", "RELEASE", *clicks[0])))
    for x, y in clicks[1:]:
        results.append(cls.modal(op, context, event("LEFTMOUSE", "PRESS", x, y)))
        results.append(cls.modal(op, context, event("LEFTMOUSE", "RELEASE", x, y)))
    return op, results


def test_a_single_line_path_is_not_closed_back_over_itself(clean, monkeypatch):
    # A, B, then a click on A closed the path with two points: a line back over the first one, so any groove
    # along it failed ("turns 180°"), as did the Closed option of Adjust Last Operation (bug sweep, 2026-10-04)
    op, results = _drive_path(monkeypatch, [(-10.0, 0.0), (10.0, 0.0), (-10.0, 0.0)])
    assert {"FINISHED"} not in results and len(op._path) == 2  # the click is ignored, the path goes on
    ops_sketch.BLENDSOLID_OT_sketch_entity._end(op, bpy.context, None)
    with pytest.raises(RuntimeError, match="at least three points"):
        sketch("PATH", (0.0, 0.0), (0.0, 0.0), matrix=Matrix.Identity(4), points=[[-10.0, 0.0, False],
                                                                                   [10.0, 0.0, False]], closed=True)


def test_the_sketch_panel_keeps_a_rectangle_out_of_path(clean):
    # the panel of a Rectangle or Circle offered Shape: Path, which failed and left only "Closed" in the panel
    rows = []

    class Layout:
        use_property_split = False

        def row(self, align=False):
            return self

        def prop(self, owner, name, **kwargs):
            rows.append(name)

        def prop_enum(self, owner, name, value, **kwargs):
            rows.append(f"{name}={value}")

        def label(self, text=""):
            pass
    import types
    op = types.SimpleNamespace(shape="RECTANGLE", layout=Layout())
    ops_sketch.BLENDSOLID_OT_sketch_entity.draw(op, bpy.context)
    assert "shape" not in rows and "shape=RECTANGLE" in rows and "shape=CIRCLE" in rows


def test_revolve_refuses_a_failing_part_before_the_axis_click(clean, monkeypatch):
    # the refusal came only from execute(), after the axis had been picked (bug sweep, 2026-10-04)
    import types
    assert sketch("RECTANGLE", (5.0, 0.0), (10.0, 5.0), matrix=Matrix.Identity(4)) == {"FINISHED"}
    obj = bpy.context.object
    assert sketch("LINE", (0.0, -5.0), (0.0, 10.0), target=obj.name, sketch_name="sketch_1") == {"FINISHED"}
    wait_for(lambda: up_to_date(obj))
    (drawn,) = ops_sketch.sketches_of(obj)
    obj.blendsolid_script.from_string(part.source_of(obj).replace("result = part.part", "result = part.part / 0"))
    wait_for(lambda: obj.blendsolid_error != "")
    monkeypatch.setattr(ops_extrude, "pick_region", lambda context, o, d: (obj, drawn, (7.0, 2.0), 0))
    from blendsolid import ops_draw
    monkeypatch.setattr(ops_draw, "_mouse_ray", lambda context, event: (None, None))
    reports = []
    op = types.SimpleNamespace(report=lambda kind, text: reports.append(text))
    context = types.SimpleNamespace(area=types.SimpleNamespace(type="VIEW_3D"), region_data=object())
    assert ops_extrude.BLENDSOLID_OT_revolve.invoke(op, context, None) == {"CANCELLED"}
    assert reports and "fails" in reports[0]


def test_narrowing_the_rectangle_past_the_extruded_point_is_an_error(box):
    # R11 as the maintainer will try it: the extrude picked the rectangle at (4, 0); narrowed to 6 mm the point lies
    # in the rest of the face, which was extruded silently before
    sketch("RECTANGLE", (-5.0, -5.0), (5.0, 5.0), target=box.name, plane='on_face(face("box_1", "+Z"))')
    wait_for(lambda: up_to_date(box))
    assert bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target=box.name, sketch="sketch_1", seed=(4.0, 0.0),
                                      amount=5.0, operation="ADD") == {"FINISHED"}
    wait_for(lambda: up_to_date(box))
    source = part.source_of(box)
    assert 'area((4.0, 0.0), inside=("face", "rect_1"))' in source and box.blendsolid_error == ""
    width = [line for line in source.splitlines() if line.startswith("sketch_1_rect_1_width")]
    assert width, source
    box.blendsolid_script.from_string(source.replace(width[0], "sketch_1_rect_1_width = 6.0"))
    wait_for(lambda: box.blendsolid_error != "")
    assert "pick the area again" in box.blendsolid_error
