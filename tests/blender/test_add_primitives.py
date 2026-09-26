"""Tool 1: Shift+A > BlendSolid primitives, as new parts at the 3D cursor."""
import math

import bpy
import pytest
from mathutils import Euler, Vector

from blendsolid import part, primitives, runtime, script_model
from conftest import mm3, up_to_date, wait_for

VOLUMES = {
    "box": lambda v: v["length"] * v["width"] * v["height"],
    "cylinder": lambda v: math.pi * v["radius"] ** 2 * v["height"],
    "sphere": lambda v: 4 / 3 * math.pi * v["radius"] ** 3,
    "cone": lambda v: math.pi * v["height"] / 3 * (v["bottom_radius"] ** 2 + v["bottom_radius"] * v["top_radius"]
                                                   + v["top_radius"] ** 2),
    "torus": lambda v: 2 * math.pi ** 2 * v["major_radius"] * v["minor_radius"] ** 2,
    "wedge": lambda v: (v["length"] + v["top_length"]) / 2 * v["height"] * v["width"],
}


@pytest.fixture
def cursor():
    c = bpy.context.scene.cursor
    saved = c.location.copy(), c.rotation_euler.copy()
    yield c
    c.location, c.rotation_euler = saved


@pytest.mark.parametrize("kind", sorted(primitives.PRIMITIVES))
def test_add_each_primitive(clean, cursor, kind):
    cursor.location, cursor.rotation_euler = (0, 0, 0), (0, 0, 0)
    values = {s: d * 0.5 for s, _, d in primitives.PRIMITIVES[kind].params}  # not the defaults
    assert getattr(bpy.ops.blendsolid, f"add_{kind}")(**values) == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    assert obj.name == primitives.PRIMITIVES[kind].label and obj.select_get()
    source = part.source_of(obj)
    assert [f.name for f in script_model.features(source)] == [f"{kind}_1"]
    assert part.part_id(obj) is not None and len(part.part_id(obj)) == 32
    wait_for(lambda: up_to_date(obj))
    expected = VOLUMES[kind](values)
    assert abs(mm3(obj) - expected) / expected < 0.02  # tessellated
    assert obj.blendsolid_error == ""
    assert [p.name for p in obj.blendsolid_params] == [f"{kind}_1_{s}" for s, _, _ in
                                                       primitives.PRIMITIVES[kind].params]


def test_new_part_takes_the_cursor_location_and_rotation(clean, cursor):
    cursor.location = (0.1, 0.2, 0.3)
    cursor.rotation_euler = Euler((0.0, math.radians(90), 0.0))
    bpy.ops.blendsolid.add_box(length=40, width=30, height=20)
    obj = bpy.context.view_layer.objects.active
    assert (obj.matrix_world.translation - Vector((0.1, 0.2, 0.3))).length < 1e-6
    assert (obj.matrix_world.to_3x3() @ Vector((0, 0, 1)) - Vector((1, 0, 0))).length < 1e-6
    assert not part.is_scaled(obj)
    obj.scale = (2, 1, 1)
    bpy.context.view_layer.update()
    assert part.is_scaled(obj)


def test_redo_with_other_values_replaces_the_part(clean, cursor):
    """Adjust Last Operation = undo, then the same operator with the new properties."""
    bpy.ops.ed.undo_push(message="before")  # background mode: the undo stack starts on the first push
    bpy.ops.blendsolid.add_cylinder("EXEC_DEFAULT", True, radius=5, height=10)
    bpy.ops.ed.undo()
    assert "Cylinder" not in bpy.data.objects
    bpy.ops.blendsolid.add_cylinder("EXEC_DEFAULT", True, radius=6, height=10)
    obj = bpy.data.objects["Cylinder"]
    assert "cylinder_1_radius = 6.0\n" in part.source_of(obj)
    wait_for(lambda: up_to_date(obj))
    assert abs(mm3(obj) - math.pi * 36 * 10) / (math.pi * 360) < 0.02


def test_part_id_follows_the_script(clean):
    a = part.new_part(bpy.context)
    linked = a.copy()  # Alt+D: same mesh, same script: the same part
    bpy.context.collection.objects.link(linked)
    independent = a.copy()  # Shift+D: its own mesh; tick gives it its own script, hence its own id
    independent.data = a.data.copy()
    bpy.context.collection.objects.link(independent)
    runtime.tick()
    assert part.part_id(linked) == part.part_id(a)
    assert part.part_id(independent) not in (None, part.part_id(a))


def test_ensure_part_id_on_a_milestone_1_part(clean):
    obj = part.new_part(bpy.context)
    del obj.blendsolid_script[part.PART_ID_KEY]  # as in a file saved by milestone 1
    assert part.part_id(obj) is None
    pid = part.ensure_part_id(obj)
    assert pid == part.part_id(obj) and part.ensure_part_id(obj) == pid


def test_shift_a_menu_lists_the_primitives(addon):
    assert hasattr(bpy.types, "VIEW3D_MT_blendsolid_add")
    for kind in primitives.PRIMITIVES:
        assert hasattr(bpy.ops.blendsolid, f"add_{kind}")


def test_duplicate_part_ids_are_made_unique(clean):
    """Copy/paste, Append, or copying a Text datablock can produce a separate Text (a different session_uid)
    that still carries the source's bs_part_id. One tick must give every Text after the first a fresh id, so
    a later part index doesn't collapse the two parts into one (a cutter silently not cutting)."""
    a = part.new_part(bpy.context, name="A")
    b = part.new_part(bpy.context, name="B")
    a_id = part.part_id(a)
    b.blendsolid_script = a.blendsolid_script.copy()  # Text.copy() keeps the id property (unlike copy_script())
    runtime.tick()
    assert part.part_id(a) == a_id
    assert part.part_id(b) not in (None, a_id)
