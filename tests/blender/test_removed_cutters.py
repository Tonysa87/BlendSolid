"""Deleting a live cutter doesn't destroy it (maintainer's request in the milestone 1.5 manual GUI test,
modelled on Fusion 360's timeline and HardOps' hidden cutters): the target keeps its cut, the cutter can be
restored where it was, and a single boolean can be removed from a part's history."""
import os
import tempfile
from types import SimpleNamespace

import bpy

from blendsolid import deps, part, runtime, trust, ui
from conftest import mm3, up_to_date, wait_for
from test_deps import HOLE, PLATE, plate_and_pin


def test_deleting_a_cutter_keeps_the_cut_across_save_and_reload(clean):
    fp = bpy.context.preferences.filepaths
    saved = fp.use_scripts_auto_execute
    fp.use_scripts_auto_execute = True
    try:
        plate, pin = plate_and_pin()
        text, pid = pin.blendsolid_script, part.part_id(pin)
        bpy.data.objects.remove(pin)
        for _ in range(5):
            runtime.tick()
        assert plate.blendsolid_error == "" and up_to_date(plate)       # no error, nothing to recompute
        assert text.use_fake_user                                        # its script is kept in the file
        assert [c.part_id for c in deps.booleans(plate)] == [pid] and deps.booleans(plate)[0].deleted
        path = os.path.join(tempfile.mkdtemp(), "removed-cutter.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        plate = bpy.data.objects["Plate"]
        runtime.tick()
        assert plate.blendsolid_error == "" and up_to_date(plate)
        assert abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01
    finally:
        fp.use_scripts_auto_execute = saved
        trust.reset_for_file(bpy.context.preferences, bpy.data.filepath)


def test_restore_brings_the_cutter_back_where_it_was(clean):
    plate, pin = plate_and_pin()
    pid, where = part.part_id(pin), plate.matrix_world.inverted() @ pin.matrix_world
    bpy.data.objects.remove(pin)
    runtime.tick()
    assert bpy.ops.blendsolid.restore_cutter(target=plate.name, part_id=pid) == {"FINISHED"}
    (back,) = deps.part_index()[pid]
    bpy.context.view_layer.update()
    assert (plate.matrix_world.inverted() @ back.matrix_world - where).to_translation().length < 1e-7
    assert back.display_type == "WIRE" and back.hide_render and back.name == "Pin"
    assert not deps.booleans(plate)[0].deleted
    wait_for(lambda: up_to_date(back) and up_to_date(plate))
    assert plate.blendsolid_error == "" and abs(mm3(plate) - (PLATE - HOLE)) / PLATE < 0.01


def test_remove_a_cut_whose_cutter_was_deleted(clean):
    plate, pin = plate_and_pin()
    text = pin.blendsolid_script
    bpy.data.objects.remove(pin)
    runtime.tick()
    (b,) = deps.booleans(plate)
    assert bpy.ops.blendsolid.remove_boolean(target=plate.name, feature=b.feature) == {"FINISHED"}
    assert "ref(" not in part.source_of(plate) and deps.booleans(plate) == []
    wait_for(lambda: up_to_date(plate))
    assert abs(mm3(plate) - PLATE) / PLATE < 0.01
    runtime.tick()
    assert not text.use_fake_user  # no part uses it any more: it goes with the next save


def test_remove_a_cut_whose_cutter_is_live_shows_the_cutter_again(clean):
    plate, pin = plate_and_pin()
    pin.display_type, pin.hide_render = "WIRE", True  # as the boolean operator leaves it
    (b,) = deps.booleans(plate)
    bpy.ops.blendsolid.remove_boolean(target=plate.name, feature=b.feature)
    assert pin.display_type == "TEXTURED" and not pin.hide_render
    wait_for(lambda: up_to_date(plate))
    assert abs(mm3(plate) - PLATE) / PLATE < 0.01


def test_select_cutter(clean):
    plate, pin = plate_and_pin()
    pin.hide_set(True)
    assert bpy.ops.blendsolid.select_cutter(part_id=part.part_id(pin)) == {"FINISHED"}
    assert pin.select_get() and not pin.hide_get() and bpy.context.view_layer.objects.active == pin
    assert not plate.select_get()


def test_a_cutter_whose_script_is_lost_is_still_an_error(clean):
    plate, pin = plate_and_pin()
    text = pin.blendsolid_script
    bpy.data.objects.remove(pin)
    bpy.data.texts.remove(text)
    runtime.tick()
    assert "no longer exists" in plate.blendsolid_error and "Remove" in plate.blendsolid_error
    assert deps.booleans(plate)[0].missing


def test_panel_lists_the_booleans_with_their_actions(clean):
    plate, pin = plate_and_pin()
    shown = []

    class Layout:
        def __getattr__(self, name):
            def record(*args, **kwargs):
                shown.append((name, args, kwargs))
                return self
            return record

    def ops():
        shown.clear()
        context = SimpleNamespace(object=plate, scene=bpy.context.scene, preferences=bpy.context.preferences)
        ui.BLENDSOLID_PT_part.draw(SimpleNamespace(layout=Layout()), context)
        return [a[0] for n, a, k in shown if n == "operator"]

    assert {"blendsolid.select_cutter", "blendsolid.remove_boolean"} <= set(ops())
    bpy.data.objects.remove(pin)
    runtime.tick()
    assert {"blendsolid.restore_cutter", "blendsolid.remove_boolean"} <= set(ops())
