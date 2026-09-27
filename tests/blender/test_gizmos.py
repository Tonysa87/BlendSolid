"""Tool 1 gizmos: arrow placement (world space, following the object) and writes through the panel path.
Dragging itself needs a window: see the manual GUI test."""
import math

import bpy
from mathutils import Euler, Vector

from blendsolid import gizmos, part, primitives, script_model
from conftest import wait_for


def tip(basis, value_mm, scale, factor):
    return basis @ Vector((0.0, 0.0, value_mm * scale * factor))


def add_box():
    bpy.ops.blendsolid.add_box(length=40, width=30, height=20)
    return bpy.context.view_layer.objects.active


def test_gizmo_group_is_registered(addon):
    assert "bl_rna" in gizmos.BLENDSOLID_GGT_parameters.__dict__  # set by register_class()


def test_arrow_tips_sit_on_the_faces_and_follow_the_object(clean):
    obj = add_box()
    obj.location = (0.5, 0.0, 0.0)
    obj.rotation_euler = Euler((0.0, 0.0, math.radians(90)))
    bpy.context.view_layer.update()
    f = part.unit_factor()
    got = {p: tip(m, {"box_1_length": 40, "box_1_width": 30, "box_1_height": 20}[p], s, f)
           for p, m, s in gizmos.arrow_matrices(obj)}
    faces = {"box_1_length": (20, 0, 10), "box_1_width": (0, 15, 10), "box_1_height": (0, 0, 20)}
    for param, local_mm in faces.items():
        expected = obj.matrix_world @ (Vector(local_mm) * f)
        assert (got[param] - expected).length < 1e-6, param


def test_arrows_of_a_placed_cut_feature(clean):
    obj = add_box()
    source, _ = script_model.append_feature(part.source_of(obj), primitives.feature_spec(
        "cylinder", {"radius": 3.0, "height": 5.0}, mode="SUBTRACT", align=primitives.TOP,
        location=(10.0, 5.0, 20.0), rotation=(0.0, 0.0, 0.0)))
    obj.blendsolid_script.from_string(source)
    f = part.unit_factor()
    got = {p: (m, s) for p, m, s in gizmos.arrow_matrices(obj)}
    m, s = got["cut_1_height"]
    assert (tip(m, 5.0, s, f) - Vector((10, 5, 15)) * f).length < 1e-6  # the bottom of the hole


def test_no_arrows_for_non_canonical_scripts(clean):
    obj = part.new_part(bpy.context, "size = 10.0\nresult = Box(size, size, size)\n")
    assert gizmos.arrow_matrices(obj) == []


def test_set_writes_the_parameter_like_the_panel(clean):
    obj = add_box()
    runtime_tick_until_synced(obj)
    f = part.unit_factor()
    assert abs(gizmos.arrow_get(obj.name, "box_1_height", 1.0) - 20 * f) < 1e-9
    gizmos.arrow_set(obj.name, "box_1_height", 1.0, 25 * f)
    assert "box_1_height = 25.0\n" in part.source_of(obj)
    gizmos.arrow_set(obj.name, "box_1_length", 0.5, -1.0)  # dragged through zero: clamped, never negative
    assert f"box_1_length = {gizmos.MIN_VALUE}\n" in part.source_of(obj)
    wait_for(lambda: part.applied_hash(obj) == part.current_tag(obj))


def test_set_on_a_deleted_object_does_nothing(clean):
    obj = add_box()
    name = obj.name
    bpy.data.objects.remove(obj)
    gizmos.arrow_set(name, "box_1_height", 1.0, 0.03)
    assert gizmos.arrow_get(name, "box_1_height", 1.0) == 0.0


def runtime_tick_until_synced(obj):
    from blendsolid import runtime
    runtime.tick()
    assert obj.blendsolid_params.get("box_1_height") is not None


def _set_tool(idname):
    win = bpy.context.window
    area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name=idname)


def test_arrows_hide_while_the_draw_solid_tool_is_active(clean):
    # Found in the manual GUI test: a selected part's arrows took the click meant to start a drawing.
    obj = add_box()
    try:
        _set_tool("blendsolid.draw_solid_tool")
        assert bpy.context.workspace.tools.from_space_view3d_mode("OBJECT").idname == "blendsolid.draw_solid_tool"
        assert not gizmos.BLENDSOLID_GGT_parameters.poll(bpy.context)
    finally:
        _set_tool("builtin.select_box")
    assert obj.select_get() and gizmos.BLENDSOLID_GGT_parameters.poll(bpy.context)
