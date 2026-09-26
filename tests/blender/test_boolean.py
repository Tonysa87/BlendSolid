"""Tool 3: the Boolean operator (selected parts applied to the active part as live cutters)."""
import math

import bpy
import pytest

from blendsolid import part, script_model
from conftest import mm3, select, up_to_date, wait_for

PLATE = 40 * 30 * 10
HOLE = math.pi * 9 * 10


def plate_and_pin():
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.ops.blendsolid.add_box(length=40, width=30, height=10)
    plate = bpy.context.view_layer.objects.active
    bpy.context.scene.cursor.location = (0.005, 0, -0.005)
    bpy.ops.blendsolid.add_cylinder(radius=3, height=20)
    pin = bpy.context.view_layer.objects.active
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.context.view_layer.update()
    return plate, pin


def test_difference_adds_one_feature_and_makes_the_cutter_wire(clean):
    plate, pin = plate_and_pin()
    select(plate, pin)
    assert bpy.ops.blendsolid.boolean(operation="DIFFERENCE") == {"FINISHED"}
    feats = script_model.features(part.source_of(plate))
    assert [f.name for f in feats] == ["box_1", "bool_1"]
    assert feats[1].kind == "insert" and feats[1].mode == "SUBTRACT" and feats[1].refs == (part.part_id(pin),)
    assert pin.display_type == "WIRE" and pin.hide_render
    wait_for(lambda: up_to_date(plate) and up_to_date(pin))
    assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01


def test_union_and_intersect(clean):
    plate, pin = plate_and_pin()
    select(plate, pin)
    bpy.ops.blendsolid.boolean(operation="INTERSECT")
    wait_for(lambda: up_to_date(plate) and up_to_date(pin))
    assert abs(mm3(plate) - HOLE) / HOLE < 0.02
    source = part.source_of(plate).replace("mode=Mode.INTERSECT", "mode=Mode.ADD")
    plate.blendsolid_script.from_string(source)
    wait_for(lambda: up_to_date(plate))
    assert abs(mm3(plate) - (PLATE + math.pi * 9 * 10)) / PLATE < 0.01  # 10 mm of pin stick out


def test_boolean_is_one_undo_step(clean):
    plate, pin = plate_and_pin()
    select(plate, pin)
    before = part.source_of(plate)
    bpy.ops.ed.undo_push(message="before")
    bpy.ops.blendsolid.boolean("EXEC_DEFAULT", True, operation="DIFFERENCE")
    bpy.ops.ed.undo()
    plate, pin = bpy.data.objects["Box"], bpy.data.objects["Cylinder"]
    assert part.source_of(plate) == before and pin.display_type != "WIRE"
    bpy.ops.ed.redo()
    assert "bool_1" in part.source_of(bpy.data.objects["Box"])


def test_poll_needs_a_target_and_a_cutter(clean):
    plate, pin = plate_and_pin()
    select(plate)
    assert not bpy.ops.blendsolid.boolean.poll()
    select(plate, pin)
    assert bpy.ops.blendsolid.boolean.poll()


def test_refuses_to_make_parts_depend_on_each_other(clean):
    plate, pin = plate_and_pin()
    select(plate, pin)
    bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    select(pin, plate)
    before = part.source_of(pin)
    with pytest.raises(RuntimeError, match="depend on each other"):  # an ERROR report, raised to Python
        bpy.ops.blendsolid.boolean(operation="UNION")
    assert part.source_of(pin) == before


def test_refuses_a_non_canonical_target(clean):
    plate, pin = plate_and_pin()
    plate.blendsolid_script.from_string("size = 10.0\nresult = Box(size, size, size)\n")
    select(plate, pin)
    with pytest.raises(RuntimeError, match="the tools can't add features"):
        bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    assert "ref(" not in part.source_of(plate)


def test_non_canonical_refusal_hides_the_detail_by_default(clean):
    plate, pin = plate_and_pin()
    # this NotCanonical message names a line number (script_model._feature); the default (non-advanced)
    # refusal must not leak it (ADR 0002: no script syntax or line numbers for standard users).
    plate.blendsolid_script.from_string(
        "size = 10.0\n\nwith BuildPart() as part:\n    Box(size, size, size)\n\nresult = part.part\n")
    select(plate, pin)
    with pytest.raises(RuntimeError) as excinfo:
        bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    message = str(excinfo.value)
    assert "the tools can't add features" in message
    assert "line" not in message


def test_refuses_a_scaled_cutter(clean):
    plate, pin = plate_and_pin()
    pin.scale = (1.0, 1.0, 2.0)
    bpy.context.view_layer.update()
    select(plate, pin)
    with pytest.raises(RuntimeError, match="is scaled"):
        bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    assert "ref(" not in part.source_of(plate)


def test_refuses_a_scaled_target(clean):
    plate, pin = plate_and_pin()
    plate.scale = (1.0, 1.0, 2.0)
    bpy.context.view_layer.update()
    select(plate, pin)
    with pytest.raises(RuntimeError, match="is scaled"):
        bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    assert "ref(" not in part.source_of(plate)


def test_milestone_1_parts_get_an_id_when_used(clean):
    plate, pin = plate_and_pin()
    del pin.blendsolid_script[part.PART_ID_KEY]
    select(plate, pin)
    bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    assert part.part_id(pin) is not None
    wait_for(lambda: up_to_date(plate))
    assert plate.blendsolid_error == ""


def test_shortcuts_are_registered(addon):
    kc = bpy.context.window_manager.keyconfigs.addon
    items = [(k.type, k.ctrl, k.properties.operation) for k in kc.keymaps["Object Mode"].keymap_items
             if k.idname == "blendsolid.boolean"]
    assert sorted(items) == [("NUMPAD_ASTERIX", True, "INTERSECT"), ("NUMPAD_MINUS", True, "DIFFERENCE"),
                             ("NUMPAD_PLUS", True, "UNION")]
