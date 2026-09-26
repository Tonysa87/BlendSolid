"""Tool 3, runtime side: a part that uses another part through ref() (a live cutter)."""
import math
import os
import tempfile

import bpy
import pytest

from blendsolid import deps, part, primitives, runtime, script_model, trust
from conftest import mm3, up_to_date, wait_for

PLATE = 40 * 30 * 10
HOLE = math.pi * 3 ** 2 * 10  # a radius 3 pin through the 10 mm plate


def primitive(kind, values, name, location=(0.0, 0.0, 0.0)):
    source, _ = script_model.new_script(primitives.feature_spec(kind, values))
    obj = part.new_part(bpy.context, source, name=name)
    obj.location = location
    return obj


def use(target, cutter, mode="SUBTRACT"):
    source, _ = script_model.append_feature(part.source_of(target),
                                            primitives.insert_spec(part.part_id(cutter), mode))
    target.blendsolid_script.from_string(source)


def plate_and_pin(pin_x=0.005):
    """A 40 x 30 x 10 mm plate and a radius 3 mm, 20 mm long pin standing through it (5 mm below)."""
    plate = primitive("box", {"length": 40, "width": 30, "height": 10}, "Plate")
    pin = primitive("cylinder", {"radius": 3, "height": 20}, "Pin", location=(pin_x, 0.0, -0.005))
    bpy.context.view_layer.update()  # matrix_world: headless Blender doesn't evaluate it by itself
    use(plate, pin)
    wait_for(lambda: up_to_date(plate) and up_to_date(pin))
    return plate, pin


def test_cutter_cuts_the_target(clean):
    plate, pin = plate_and_pin()
    assert plate.blendsolid_error == ""
    assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01


def test_moving_the_cutter_recomputes_only_the_target(clean):
    plate, pin = plate_and_pin()
    pin_hash = part.applied_hash(pin)
    pin.location.x = 0.1  # out of the plate
    bpy.context.view_layer.update()
    assert not up_to_date(plate)
    wait_for(lambda: up_to_date(plate))
    assert abs(mm3(plate) - PLATE) / PLATE < 0.01
    assert part.applied_hash(pin) == pin_hash  # the cutter itself didn't change


def test_rotating_the_cutter_recomputes_the_target(clean):
    plate, pin = plate_and_pin(pin_x=0.0)
    pin.location = (-0.03, 0.0, 0.005)
    pin.rotation_euler = (0.0, math.radians(90), 0.0)  # along +X from x = -30 mm: 10 mm inside the plate
    bpy.context.view_layer.update()
    wait_for(lambda: up_to_date(plate))
    assert abs(mm3(plate) - (PLATE - math.pi * 9 * 10)) / PLATE < 0.01


def test_editing_the_cutter_recomputes_the_target(clean):
    plate, pin = plate_and_pin()
    pin.blendsolid_params["cylinder_1_radius"].value = 4.0
    wait_for(lambda: up_to_date(pin) and up_to_date(plate))
    assert abs(mm3(plate) - (PLATE - math.pi * 16 * 10)) / PLATE < 0.01


def test_moving_the_target_with_its_cutter_changes_nothing(clean):
    plate, pin = plate_and_pin()
    tag = part.current_tag(plate)
    for obj in (plate, pin):
        obj.location.y += 0.2
    bpy.context.view_layer.update()
    assert part.current_tag(plate) == tag


def test_deleted_cutter_is_an_error_without_a_loop(clean):
    plate, pin = plate_and_pin()
    pid = part.part_id(pin)
    bpy.data.objects.remove(pin)
    runtime.tick()
    assert "no longer exists" in plate.blendsolid_error
    # ADR 0002: only actions a standard user can take, no script vocabulary
    assert "Ctrl+Z" in plate.blendsolid_error and "feature" not in plate.blendsolid_error
    submitted = runtime.client().submitted
    for _ in range(20):
        runtime.tick()
    assert runtime.client().submitted == submitted
    back = primitive("cylinder", {"radius": 3, "height": 20}, "Pin", location=(0.005, 0.0, -0.005))
    back.blendsolid_script[part.PART_ID_KEY] = pid  # as undoing the deletion would bring it back
    bpy.context.view_layer.update()
    wait_for(lambda: plate.blendsolid_error == "" and up_to_date(plate))
    assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01


def test_parts_using_each_other_are_an_error_without_a_loop(clean):
    plate, pin = plate_and_pin()
    use(pin, plate, "ADD")
    runtime.tick()
    assert "loop" in plate.blendsolid_error and "loop" in pin.blendsolid_error
    assert "Ctrl+Z" in plate.blendsolid_error and "feature" not in plate.blendsolid_error
    submitted = runtime.client().submitted
    for _ in range(20):
        runtime.tick()
    assert runtime.client().submitted == submitted


def test_scaled_cutter_is_an_error(clean):
    plate, pin = plate_and_pin()
    pin.scale = (2.0, 2.0, 2.0)
    bpy.context.view_layer.update()
    runtime.tick()
    assert "scaled" in plate.blendsolid_error
    pin.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    wait_for(lambda: plate.blendsolid_error == "" and up_to_date(plate))


def test_scaled_target_is_an_error(clean):
    """A scaled TARGET must be reported as such, not misattributed to the (unscaled) cutter (the composed
    matrix relative_matrix() checks is skewed by the target's own scale too)."""
    plate, pin = plate_and_pin()
    plate.scale = (2.0, 2.0, 2.0)
    bpy.context.view_layer.update()
    runtime.tick()
    assert "This part 'Plate' is scaled" in plate.blendsolid_error
    plate.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    wait_for(lambda: plate.blendsolid_error == "" and up_to_date(plate))


def test_untrusted_cutter_is_an_error_until_trusted(clean):
    fp = bpy.context.preferences.filepaths
    saved = fp.use_scripts_auto_execute
    fp.use_scripts_auto_execute = False
    try:
        pin = primitive("cylinder", {"radius": 3, "height": 20}, "Pin", location=(0.005, 0.0, -0.005))
        path = os.path.join(tempfile.mkdtemp(), "cutter.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)  # the pin is now an untrusted part of a loaded file
        pin = bpy.data.objects["Pin"]
        plate = primitive("box", {"length": 40, "width": 30, "height": 10}, "Plate")  # trusted: new
        bpy.context.view_layer.update()
        use(plate, pin)
        runtime.tick()
        assert "not trusted" in plate.blendsolid_error
        bpy.ops.blendsolid.trust_scripts()
        wait_for(lambda: plate.blendsolid_error == "" and up_to_date(plate))
        assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01
    finally:
        fp.use_scripts_auto_execute = saved
        trust.reset_for_file(bpy.context.preferences, bpy.data.filepath)


def test_parts_without_references_keep_their_milestone_1_tag(clean):
    obj = part.new_part(bpy.context)
    assert part.current_tag(obj) == part.source_hash(f"{part.source_of(obj)}\0unit-factor={part.unit_factor()!r}")


def test_resolve_sends_the_cutter_in_the_target_frame(clean):
    plate = primitive("box", {"length": 40, "width": 30, "height": 10}, "Plate", location=(1.0, 0.0, 0.0))
    pin = primitive("cylinder", {"radius": 3, "height": 20}, "Pin", location=(1.005, 0.0, -0.005))
    bpy.context.view_layer.update()
    use(plate, pin)
    resolved = deps.resolve(plate, part.source_of(plate), part.unit_factor(), deps.part_index())
    (d,) = resolved.deps
    assert d["id"] == part.part_id(pin) and d["source"] == part.source_of(pin) and d["deps"] == []
    assert d["name"] == "Pin"  # for the worker's messages (ADR 0002: users know parts by name, not by id)
    assert d["matrices"] == [pytest.approx([1, 0, 0, 5, 0, 1, 0, 0, 0, 0, 1, -5], abs=1e-4)]  # millimetres


# -- review focus -------------------------------------------------------------------------------------------------

def test_every_linked_duplicate_of_a_cutter_cuts(clean):
    plate, pin = plate_and_pin(pin_x=-0.01)
    twin = pin.copy()  # Alt+D: same mesh and script, so the same part, shown twice
    bpy.context.collection.objects.link(twin)
    twin.location.x = 0.01
    bpy.context.view_layer.update()
    wait_for(lambda: up_to_date(plate))
    assert abs(mm3(plate) - (PLATE - 2 * HOLE)) / PLATE < 0.01
    twin.location.x = 0.1  # moving either instance recomputes the target
    bpy.context.view_layer.update()
    wait_for(lambda: up_to_date(plate))
    assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01


def test_cutters_in_a_millimetre_scene(clean):
    units = bpy.context.scene.unit_settings
    saved = units.scale_length
    units.scale_length = 0.001  # 1 Blender unit = 1 mm
    try:
        plate = primitive("box", {"length": 40, "width": 30, "height": 10}, "Plate")
        pin = primitive("cylinder", {"radius": 3, "height": 20}, "Pin", location=(5.0, 0.0, -5.0))
        bpy.context.view_layer.update()
        use(plate, pin)
        wait_for(lambda: up_to_date(plate) and up_to_date(pin))
        assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01
    finally:
        units.scale_length = saved


def test_reopening_a_file_with_cutters_does_not_recompute(clean):
    fp = bpy.context.preferences.filepaths
    saved = fp.use_scripts_auto_execute
    fp.use_scripts_auto_execute = True
    try:
        plate_and_pin()
        path = os.path.join(tempfile.mkdtemp(), "cutters.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        submitted = runtime.client().submitted
        for _ in range(10):
            runtime.tick()
        plate = bpy.data.objects["Plate"]
        assert up_to_date(plate) and runtime.client().submitted == submitted
        assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01
    finally:
        fp.use_scripts_auto_execute = saved
        trust.reset_for_file(bpy.context.preferences, bpy.data.filepath)


def test_a_cutter_cut_by_another_cutter(clean):
    plate, pin = plate_and_pin()
    core = primitive("cylinder", {"radius": 1, "height": 40}, "Core", location=(0.005, 0.0, -0.01))
    bpy.context.view_layer.update()
    use(pin, core)  # the pin becomes a tube: the plate keeps a radius 1 mm core inside its hole
    wait_for(lambda: up_to_date(pin) and up_to_date(plate))
    assert abs(mm3(plate) - (PLATE - HOLE + math.pi * 1 * 10)) / PLATE < 0.01
    core.location.x = 0.1  # moving the innermost cutter recomputes both
    bpy.context.view_layer.update()
    wait_for(lambda: up_to_date(pin) and up_to_date(plate))
    assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01


def test_shift_d_of_a_cutter_keeps_the_original_cutting(clean):
    """Blender names a duplicate with the lowest free suffix (duplicating 'Cylinder.003' gives 'Cylinder.001'),
    so the copy can sort before its original by name: the original (the older object) must keep the script
    and the id the target's ref() names, and the copy must get its own."""
    plate, pin = plate_and_pin()
    pin.name = "Cylinder.003"
    pid = part.part_id(pin)
    dup = pin.copy()  # Shift+D: object and mesh copied, the Text shared until tick copies it
    dup.data = pin.data.copy()
    bpy.context.collection.objects.link(dup)
    dup.name = "Cylinder.001"
    dup.location.x = 0.1  # out of the plate: if the copy took the id, the plate would lose its hole
    bpy.context.view_layer.update()
    runtime.tick()
    assert deps.part_index()[pid][0] == pin
    assert part.part_id(dup) not in (None, pid)
    wait_for(lambda: up_to_date(plate) and up_to_date(dup))
    assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01
