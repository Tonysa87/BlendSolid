"""Milestone 3a: the Sketch, Extrude and Revolve tools' operators (the drags end by calling them)."""
import json
import math

import bpy
import pytest
from mathutils import Matrix, Vector

from blendsolid import ops_extrude, ops_sketch, part, script_model
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
