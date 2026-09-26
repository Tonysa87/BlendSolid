"""Tool 2 without the mouse: the drawing geometry and the operator's execute() (what the modal ends with and
what Blender's redo re-runs). The interactive part is in the manual GUI test."""
import math

import bpy
import pytest
from mathutils import Euler, Matrix, Vector

from blendsolid import drawing, ops_draw, part, script_model
from conftest import mm3, up_to_date, wait_for

F = 0.001  # unit factor of the default (metre) scene: 1 mm = 0.001 Blender units


def box_part(location=(0, 0, 0), rotation=(0, 0, 0)):
    bpy.context.scene.cursor.location, bpy.context.scene.cursor.rotation_euler = location, rotation
    bpy.ops.blendsolid.add_box(length=40, width=30, height=20)  # x -20..20, y -15..15, z 0..20 mm
    bpy.context.scene.cursor.location, bpy.context.scene.cursor.rotation_euler = (0, 0, 0), (0, 0, 0)
    obj = bpy.context.view_layer.objects.active
    bpy.context.view_layer.update()
    return obj


# -- geometry ---------------------------------------------------------------------------------------------------

def test_plane_on_the_top_face_follows_the_part_axes():
    obj_matrix = Matrix.Translation((1, 2, 3)) @ Euler((0, 0, math.radians(30))).to_matrix().to_4x4()
    normal = Vector((0.0, 1e-6, 1.0)).normalized()  # float32 noise from the tessellation
    plane = drawing.plane_on_face((1, 2, 3.02), normal, obj_matrix)
    assert plane.col[2].xyz == Vector((0, 0, 1))                       # snapped to the part's Z exactly
    assert (plane.col[0].xyz - obj_matrix.col[0].xyz).length < 1e-9      # the part's X
    assert (plane.translation - Vector((1, 2, 3.02))).length < 1e-9
    _, rotation = drawing.placement(plane, obj_matrix, F)
    assert rotation == pytest.approx((0, 0, 0), abs=1e-9)             # "a top face gives a rotation of zero"


def test_plane_on_a_side_face_uses_the_part_y_axis():
    plane = drawing.plane_on_face((0.02, 0, 0.01), (1, 0, 0), Matrix.Identity(4))
    assert plane.col[2].xyz == Vector((1, 0, 0)) and plane.col[0].xyz == Vector((0, 1, 0))


def test_plane_at_cursor():
    cursor = Matrix.Translation((0, 0, 1)) @ Euler((math.radians(90), 0, 0)).to_matrix().to_4x4()
    plane = drawing.plane_at_cursor(cursor)
    assert (plane.col[2].xyz - Vector((0, -1, 0))).length < 1e-6 and plane.translation == Vector((0, 0, 1))


def test_mouse_ray_to_plane_coordinates_and_height():
    plane = drawing.plane_at_cursor(Matrix.Identity(4))
    assert drawing.plane_coords(plane, (0.3, -0.2, 5), (0, 0, -1)) == pytest.approx((0.3, -0.2))
    assert drawing.plane_coords(plane, (0, 0, 5), (1, 0, 0)) is None     # parallel to the plane
    center = Vector((0.1, 0, 0))
    assert drawing.height_along_normal(plane, center, (5, 0, 0.25), (-1, 0, 0)) == pytest.approx(0.25)
    assert drawing.height_along_normal(plane, center, (5, 0, -0.1), (-1, 0, 0)) == pytest.approx(-0.1)


def test_drawn_box_and_cylinder_with_snapping():
    plane = drawing.plane_at_cursor(Matrix.Identity(4))
    box = drawing.drawn_solid("BOX", plane, (0.0, 0.0), (0.0402, -0.0198), 0.0101, F, step_mm=1.0)
    assert (box.length, box.width, box.height) == pytest.approx((40.0, 20.0, 10.0))
    assert (box.frame.translation - Vector((0.020, -0.010, 0))).length < 1e-9
    cyl = drawing.drawn_solid("CYLINDER", plane, (0.01, 0.0), (0.013, 0.004), -0.005, F)
    assert (cyl.radius, cyl.height) == pytest.approx((5.0, -5.0))
    assert (cyl.frame.translation - Vector((0.01, 0, 0))).length < 1e-9


def test_placement_round_trip():
    frame = Matrix.Translation((0.01, 0.02, 0.03)) @ Euler((0.1, 0.2, 0.3), "ZYX").to_matrix().to_4x4()
    location, rotation = drawing.placement(frame, None, F)
    assert location == pytest.approx((10, 20, 30))
    back = drawing.frame_matrix(location, rotation, F)
    assert all(abs(back[i][j] - frame[i][j]) < 1e-6 for i in range(4) for j in range(4))


def test_preview_lines_outline_the_solid():
    plane = drawing.plane_at_cursor(Matrix.Identity(4))
    box = drawing.drawn_solid("BOX", plane, (0, 0), (0.04, 0.02), 0.01, F)
    lines = drawing.preview_lines(box, F)
    assert len(lines) == 12  # base, top, 4 verticals
    zs = sorted({round(p.z, 9) for line in lines for p in line})
    assert zs == [0.0, 0.01]


# -- the operator ---------------------------------------------------------------------------------------------------

def test_new_part_on_the_grid(clean):
    assert bpy.ops.blendsolid.draw_solid(shape="BOX", mode="NEW", location=(10, 20, 0), rotation=(0, 0, 0),
                                         length=40, width=30, height=20) == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    assert obj.name == "Box" and (obj.matrix_world.translation - Vector((0.01, 0.02, 0))).length < 1e-7
    wait_for(lambda: up_to_date(obj))
    assert abs(mm3(obj) - 24000) < 50


def test_cut_into_the_top_face(clean):
    box = box_part()
    assert bpy.ops.blendsolid.draw_solid(shape="CYLINDER", mode="CUT", target=box.name, location=(5, 5, 20),
                                         rotation=(0, 0, 0), radius=3, height=5) == {"FINISHED"}
    feats = script_model.features(part.source_of(box))
    assert [(f.name, f.kind, f.mode) for f in feats] == [("box_1", "box", "ADD"), ("cut_1", "cylinder", "SUBTRACT")]
    assert feats[1].location == (5.0, 5.0, 20.0) and feats[1].align == ("CENTER", "CENTER", "MAX")
    wait_for(lambda: up_to_date(box))
    expected = 40 * 30 * 20 - math.pi * 9 * 5
    assert abs(mm3(box) - expected) / expected < 0.01


def test_union_on_the_top_face(clean):
    box = box_part()
    bpy.ops.blendsolid.draw_solid(shape="BOX", mode="UNION", target=box.name, location=(0, 0, 20),
                                  rotation=(0, 0, 0), length=10, width=10, height=5)
    assert script_model.features(part.source_of(box))[1].name == "box_2"
    wait_for(lambda: up_to_date(box))
    assert abs(mm3(box) - (24000 + 500)) < 20


@pytest.mark.parametrize("up, mode, expected", [(True, "UNION", 24000 + math.pi * 16 * 6),
                                                 (False, "CUT", 24000 - math.pi * 16 * 6)])
def test_drag_on_a_rotated_part_face(clean, up, mode, expected):
    """The whole pipeline minus the mouse: hit on the top face of a moved and rotated part, drag a circle,
    pull up or push down, then the operator with the resulting properties."""
    box = box_part(location=(0.5, 0.2, 0.0), rotation=(0, 0, math.radians(30)))
    top_center = box.matrix_world @ Vector((0.005, 0.0, 0.020))
    plane = drawing.plane_on_face(top_center, box.matrix_world.to_3x3() @ Vector((0, 0, 1)), box.matrix_world)
    drawn = drawing.drawn_solid("CYLINDER", plane, (0.0, 0.0), (0.004, 0.0), 0.006 if up else -0.006, F)
    props = ops_draw.drawn_properties(drawn, box, F)
    assert props["mode"] == mode and props["target"] == box.name
    assert props["location"] == pytest.approx((5, 0, 20), abs=1e-4)
    assert props["rotation"] == pytest.approx((0, 0, 0), abs=1e-6)
    assert bpy.ops.blendsolid.draw_solid(**props) == {"FINISHED"}
    wait_for(lambda: up_to_date(box))
    assert abs(mm3(box) - expected) / expected < 0.01


def test_drag_down_on_the_grid_makes_a_part_below(clean):
    plane = drawing.plane_at_cursor(Matrix.Identity(4))
    drawn = drawing.drawn_solid("BOX", plane, (0.0, 0.0), (0.01, 0.01), -0.01, F)
    props = ops_draw.drawn_properties(drawn, None, F)
    assert props["mode"] == "NEW" and props["height"] == pytest.approx(10)
    bpy.ops.blendsolid.draw_solid(**props)
    obj = bpy.context.view_layer.objects.active
    wait_for(lambda: up_to_date(obj))
    zs = [(obj.matrix_world @ v.co).z for v in obj.data.vertices]
    assert min(zs) == pytest.approx(-0.01, abs=1e-6) and max(zs) == pytest.approx(0.0, abs=1e-6)


def test_redo_can_switch_cut_to_union(clean):
    box = box_part()
    before = part.source_of(box)
    bpy.ops.ed.undo_push(message="before")
    kwargs = dict(shape="CYLINDER", target=box.name, location=(0, 0, 20), rotation=(0, 0, 0), radius=3, height=5)
    bpy.ops.blendsolid.draw_solid("EXEC_DEFAULT", True, mode="CUT", **kwargs)
    bpy.ops.ed.undo()
    box = bpy.data.objects["Box"]
    assert part.source_of(box) == before
    bpy.ops.blendsolid.draw_solid("EXEC_DEFAULT", True, mode="UNION", **kwargs)
    box = bpy.data.objects["Box"]
    assert [f.name for f in script_model.features(part.source_of(box))] == ["box_1", "cylinder_1"]


def test_errors_are_reported_not_raised_into_the_scene(clean):
    with pytest.raises(RuntimeError, match="need the part"):
        bpy.ops.blendsolid.draw_solid(mode="CUT")
    with pytest.raises(RuntimeError, match="no BlendSolid part named"):
        bpy.ops.blendsolid.draw_solid(mode="UNION", target="Nothing")
    box = box_part()
    box.blendsolid_script.from_string("size = 10.0\nresult = Box(size, size, size)\n")
    with pytest.raises(RuntimeError, match="the tools can't add features"):
        bpy.ops.blendsolid.draw_solid(mode="UNION", target=box.name)


def test_millimetre_scene(clean):
    units = bpy.context.scene.unit_settings
    saved = units.scale_length
    units.scale_length = 0.001  # 1 Blender unit = 1 mm: the placement numbers stay millimetres
    try:
        bpy.ops.blendsolid.draw_solid(shape="BOX", mode="NEW", location=(10, 20, 0), rotation=(0, 0, 0),
                                      length=40, width=30, height=20)
        box = bpy.context.view_layer.objects.active
        assert (box.matrix_world.translation - Vector((10, 20, 0))).length < 1e-5
        bpy.context.view_layer.update()
        bpy.ops.blendsolid.draw_solid(shape="CYLINDER", mode="CUT", target=box.name, location=(5, 5, 20),
                                      rotation=(0, 0, 0), radius=3, height=5)
        wait_for(lambda: up_to_date(box))
        expected = 40 * 30 * 20 - math.pi * 9 * 5
        assert abs(mm3(box) - expected) / expected < 0.01
        plane = drawing.plane_on_face(box.matrix_world @ Vector((5, 5, 20)), (0, 0, 1), box.matrix_world)
        drawn = drawing.drawn_solid("BOX", plane, (0, 0), (4, 2), 3, part.unit_factor())
        assert (drawn.length, drawn.width, drawn.height) == pytest.approx((4, 2, 3))  # 1 unit = 1 mm
        props = ops_draw.drawn_properties(drawn, box, part.unit_factor())
        assert props["mode"] == "UNION" and props["target"] == box.name
        assert props["location"] == pytest.approx((7, 6, 20), abs=1e-4)  # millimetres, in the part's frame
    finally:
        units.scale_length = saved
