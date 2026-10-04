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


def test_primitives_need_object_mode(clean):
    bpy.ops.mesh.primitive_cube_add()  # a plain mesh, in Edit Mode: a new part must not be added meanwhile
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        assert bpy.context.mode == "EDIT_MESH"
        for kind in primitives.PRIMITIVES:
            assert not getattr(bpy.ops.blendsolid, f"add_{kind}").poll()
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    assert bpy.ops.blendsolid.add_box.poll()


def test_shift_a_menu_lists_the_primitives(addon):
    assert hasattr(bpy.types, "VIEW3D_MT_blendsolid_add")
    for kind in primitives.PRIMITIVES:
        assert hasattr(bpy.ops.blendsolid, f"add_{kind}")


@pytest.mark.parametrize("older_name, newer_name", [("A", "B"), ("B", "A")])
def test_duplicate_part_ids_are_made_unique(clean, older_name, newer_name):
    """Copy/paste, Append, or copying a Text datablock can produce a separate Text (a different session_uid)
    that still carries the source's bs_part_id. One tick must give every Text but the oldest part's a fresh
    id, so a later part index doesn't collapse the two parts into one (a cutter silently not cutting). The
    oldest part (lowest session_uid) keeps the id whichever way the names sort."""
    older = part.new_part(bpy.context, name=older_name)
    newer = part.new_part(bpy.context, name=newer_name)
    assert older.session_uid < newer.session_uid
    older_id = part.part_id(older)
    newer.blendsolid_script = older.blendsolid_script.copy()  # Text.copy() keeps the id (unlike copy_script())
    runtime.tick()
    assert part.part_id(older) == older_id
    assert part.part_id(newer) not in (None, older_id)


@pytest.mark.parametrize("kind", sorted(primitives.PRIMITIVES))
def test_computed_primitive_is_smooth_shaded(clean, cursor, kind):
    # Curved BRep faces must not render faceted: every triangle smooth, normals interpolated per vertex.
    cursor.location, cursor.rotation_euler = (0, 0, 0), (0, 0, 0)
    getattr(bpy.ops.blendsolid, f"add_{kind}")()
    obj = bpy.context.view_layer.objects.active
    wait_for(lambda: up_to_date(obj))
    assert all(p.use_smooth for p in obj.data.polygons)


def test_typed_size_keys_are_blender_event_types():
    # the keypad's digits are NUMPAD_0..NUMPAD_9: a wrong name (NUMPAD_ZERO) is silently never matched
    from blendsolid import ops_add
    types = {item.identifier for item in bpy.types.Event.bl_rna.properties["type"].enum_items}
    assert set(ops_add.TYPED_KEYS) <= types, set(ops_add.TYPED_KEYS) - types
    assert sorted(v for k, v in ops_add.TYPED_KEYS.items() if k.startswith("NUMPAD_") and v.isdigit()) == \
        [str(i) for i in range(10)]


def test_confirming_a_new_size_keeps_the_part_on_screen_at_that_size(clean, cursor):
    # Add's placement shows the new size by scaling the object; on confirm the scale goes back to 1 and the script
    # gets the size, but the worker's mesh at that size comes later: until then the old mesh at scale 1 showed the
    # part small for a moment (the maintainer's GUI test, 2026-10-04: "da solid piccolo alla dimensione definita").
    from types import SimpleNamespace

    from blendsolid import ops_add
    cursor.location, cursor.rotation_euler = (0, 0, 0), (0, 0, 0)
    bpy.ops.blendsolid.add_box(**primitives.sized_values("box", 10.0))
    obj = bpy.context.view_layer.objects.active
    wait_for(lambda: up_to_date(obj))
    placement = ops_add._Placement()
    placement.prim, placement.obj, placement.handle, placement.typed = primitives.PRIMITIVES["box"], obj, None, "35"
    placement.matrix = obj.matrix_world.copy()
    placement.written, placement.size = 10.0, 35.0
    obj.scale = (3.5, 3.5, 3.5)
    area = SimpleNamespace(header_text_set=lambda text: None, tag_redraw=lambda: None)
    op = SimpleNamespace()
    event = SimpleNamespace(type="NUMPAD_ENTER", value="PRESS")
    assert placement.modal(op, SimpleNamespace(area=area), event) == {"FINISHED"}
    assert tuple(obj.scale) == (1.0, 1.0, 1.0)
    assert not up_to_date(obj)  # the worker's mesh at 35 mm is still to come...
    assert mm3(obj) == pytest.approx(35.0 ** 3, rel=1e-4)  # ...and the part already shows that size
    wait_for(lambda: up_to_date(obj))
    assert mm3(obj) == pytest.approx(35.0 ** 3, rel=1e-6)


def _placement_typing(kind, keys):
    """A _Placement of a new `kind` part started at 10 mm, after typing `keys` (event types), then Enter."""
    from types import SimpleNamespace

    from blendsolid import ops_add
    getattr(bpy.ops.blendsolid, f"add_{kind}")(**primitives.sized_values(kind, 10.0))
    obj = bpy.context.view_layer.objects.active
    placement = ops_add._Placement()
    placement.prim, placement.obj, placement.handle, placement.typed = primitives.PRIMITIVES[kind], obj, None, ""
    placement.matrix = obj.matrix_world.copy()
    placement.written = placement.size = 10.0
    context = SimpleNamespace(area=SimpleNamespace(header_text_set=lambda text: None, tag_redraw=lambda: None))
    for key in keys:
        placement.modal(SimpleNamespace(), context, SimpleNamespace(type=key, value="PRESS"))
    label = placement.label()
    result = placement.modal(SimpleNamespace(), context, SimpleNamespace(type="RET", value="PRESS"))
    return placement, label, result, obj


@pytest.mark.parametrize("kind, keys, size, finished", [
    ("box", ["ONE", "PERIOD", "TWO", "PERIOD", "THREE"], 1.23, True),  # a second point is refused
    ("box", ["ZERO"], 10.0, False),  # too small: not taken, Enter waits for a usable size
    ("box", ["PERIOD"], 10.0, False),
    ("box", ["ZERO", "PERIOD", "ZERO", "ZERO", "ZERO", "ZERO", "ZERO", "ZERO", "ONE"], 10.0, False),
    ("torus", ["ZERO", "PERIOD", "ZERO", "ZERO", "FIVE"], 10.0, False),  # its minor radius would be 0.0005
    ("box", ["ZERO", "PERIOD", "ZERO", "ZERO", "FIVE"], 0.005, True),
])
def test_typed_sizes_the_script_can_hold(clean, cursor, kind, keys, size, finished):
    # typed sizes were only checked > 0: 1e-7 wrote a 0 mm box (Standard_DomainError), sizes under 0.001 mm went
    # below the operator's own minimum, "1.2.3" confirmed 1.2 (bug sweep, 2026-10-04)
    placement, label, result, obj = _placement_typing(kind, keys)
    assert placement.size == size
    assert (result == {"FINISHED"}) == finished, label
    if not finished:
        assert "at least" in label
    else:
        wait_for(lambda: up_to_date(obj))
        assert obj.blendsolid_error == ""
