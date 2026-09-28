"""ADR 0011: the arrows of one focused feature, only on an active, selected, visible part; cutters put away in a
collection after a boolean and brought back."""
import bpy
from mathutils import Vector

from blendsolid import focus, gizmos, ops_boolean, ops_draw, part
from conftest import mm3, select, up_to_date, wait_for
from test_boolean import HOLE, PLATE, plate_and_pin
from test_draw_solid import box_part

F = 0.001


def params_shown(obj):
    return {p for p, _, _ in gizmos.arrow_matrices(obj)}


def poll():
    return gizmos.BLENDSOLID_GGT_parameters.poll(bpy.context)


def cut_box():
    box = box_part()
    bpy.ops.blendsolid.draw_solid(shape="CYLINDER", mode="CUT", target=box.name, location=(5, 5, 20),
                                  rotation=(0, 0, 0), radius=3, height=5)
    return box


def test_default_focus_is_the_first_feature(clean):
    obj = part.new_part(bpy.context)  # box_1, boss_1, fillet_1
    assert focus.focused(obj) == "box_1"
    assert params_shown(obj) == {"box_1_length", "box_1_width", "box_1_height"}
    obj.blendsolid_focus = "gone_1"  # a feature removed from the script: back to the first
    assert focus.focused(obj) == "box_1"


def test_draw_solid_focuses_the_new_feature(clean):
    box = cut_box()
    assert box.blendsolid_focus == "cut_1"
    assert params_shown(box) == {"cut_1_radius", "cut_1_height"}


def test_arrows_only_on_an_active_selected_visible_part(clean):
    obj = part.new_part(bpy.context)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    assert poll()
    obj.select_set(False)  # a click in empty space keeps the part active but deselects it
    assert not poll()
    obj.select_set(True)
    obj.hide_set(True)
    assert not poll()


def test_clicking_a_face_focuses_the_feature_that_made_it(clean):
    box = cut_box()
    select(box)
    wait_for(lambda: up_to_date(box))
    depsgraph = bpy.context.evaluated_depsgraph_get()

    def click(x, y, z_from=1.0, direction=(0, 0, -1)):
        found = ops_draw._first_hit(bpy.context, depsgraph, Vector((x * F, y * F, z_from)), Vector(direction))
        return focus.focus_at(bpy.context, box, found[2])

    assert click(-10, -10) == "box_1" and box.blendsolid_focus == "box_1"  # the top face
    assert params_shown(box) == {"box_1_length", "box_1_width", "box_1_height"}
    assert click(5, 5) == "cut_1"  # the bottom of the hole
    assert params_shown(box) == {"cut_1_radius", "cut_1_height"}


def test_feature_of_a_reference():
    assert focus.feature_of_reference('face("cut_1", "wall")') == "cut_1"
    assert focus.feature_of_reference("nearest_face((1, 2, 3))") is None
    assert focus.feature_of_reference(None) is None


def test_focus_operator_is_undoable(clean):
    obj = part.new_part(bpy.context)
    bpy.ops.ed.undo_push(message="before")
    bpy.ops.blendsolid.focus_feature("EXEC_DEFAULT", True, part_name=obj.name, feature="boss_1")
    assert bpy.data.objects[obj.name].blendsolid_focus == "boss_1"
    bpy.ops.ed.undo()
    assert focus.focused(bpy.data.objects["Part"]) == "box_1"


# -- cutters ---------------------------------------------------------------------------------------------------------

def test_a_boolean_puts_the_cutter_away(clean):
    plate, pin = plate_and_pin()
    home = pin.users_collection[0]
    world = pin.matrix_world.copy()
    select(plate, pin)
    bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    bpy.context.view_layer.update()
    assert [c.name for c in pin.users_collection] == [ops_boolean.CUTTERS]
    assert pin.users_collection[0].hide_render and pin not in home.objects[:]
    assert pin.parent == plate and (pin.matrix_world.translation - world.translation).length < 1e-9
    assert pin.hide_get() and not pin.visible_get() and not pin.hide_viewport  # hide_set, never hide_viewport
    assert pin.display_type == "WIRE" and pin.hide_render
    assert plate.blendsolid_focus == "bool_1"
    wait_for(lambda: up_to_date(plate) and up_to_date(pin))
    assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01


def test_moving_the_target_carries_its_hidden_cutter(clean):
    plate, pin = plate_and_pin()
    select(plate, pin)
    bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    wait_for(lambda: up_to_date(plate) and up_to_date(pin))
    plate.location = (0.1, 0.05, 0.0)
    bpy.context.view_layer.update()
    assert (pin.matrix_world.translation - Vector((0.105, 0.05, -0.005))).length < 1e-7
    wait_for(lambda: up_to_date(plate))
    assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01  # the hole moved with the plate


def test_show_cutters_toggle_and_select_cutter(clean):
    plate, pin = plate_and_pin()
    select(plate, pin)
    bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    select(plate)
    assert bpy.ops.blendsolid.show_cutters(show=True) == {"FINISHED"} and pin.visible_get()
    assert bpy.ops.blendsolid.show_cutters(show=False) == {"FINISHED"} and not pin.visible_get()
    bpy.ops.blendsolid.select_cutter(part_id=part.part_id(pin))
    assert pin.visible_get() and pin.select_get() and bpy.context.object == pin


def test_select_cutter_shows_a_switched_off_collection(clean):
    plate, pin = plate_and_pin()
    select(plate, pin)
    bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    layer = next(lc for lc in bpy.context.view_layer.layer_collection.children if lc.name == ops_boolean.CUTTERS)
    layer.hide_viewport = True  # the user switched the whole collection off with its eye
    bpy.ops.blendsolid.select_cutter(part_id=part.part_id(pin))
    assert pin.visible_get()


def test_remove_boolean_brings_the_cutter_back(clean):
    plate, pin = plate_and_pin()
    home = plate.users_collection[0]
    select(plate, pin)
    bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
    bpy.context.view_layer.update()
    world = pin.matrix_world.copy()
    bpy.ops.blendsolid.remove_boolean(target=plate.name, feature="bool_1")
    bpy.context.view_layer.update()
    assert list(pin.users_collection) == [home] and pin.parent is None
    assert (pin.matrix_world.translation - world.translation).length < 1e-9
    assert pin.visible_get() and pin.display_type == "TEXTURED" and not pin.hide_render


def test_boolean_put_away_is_one_undo_step(clean):
    plate, pin = plate_and_pin()
    select(plate, pin)
    bpy.ops.ed.undo_push(message="before")
    bpy.ops.blendsolid.boolean("EXEC_DEFAULT", True, operation="DIFFERENCE")
    bpy.ops.ed.undo()
    pin = bpy.data.objects["Cylinder"]
    assert pin.parent is None and pin.visible_get() and ops_boolean.CUTTERS not in [c.name for c in pin.users_collection]
