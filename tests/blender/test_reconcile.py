"""Reconcile loop: Edit Mode, Link Object Data direction, identity grouping/library parts, tick cost."""
import os
import statistics
import tempfile
import time

import bpy
import pytest

from blendsolid import part, runtime, trust
from conftest import mm3, up_to_date, wait_for


def new_part(name="Part"):
    obj = part.new_part(bpy.context, name=name)
    wait_for(lambda: up_to_date(obj))
    return obj


def enter_edit_mode(obj):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    assert bpy.ops.object.mode_set(mode="EDIT") == {"FINISHED"}
    assert obj.data.is_editmode


# -- Edit Mode (finding 2) -----------------------------------------------------------------------------------

def test_edit_mode_defers_rebuild_without_error(clean):
    obj = new_part()
    polys = len(obj.data.polygons)
    enter_edit_mode(obj)
    try:
        obj.blendsolid_params["box_1_length"].value = 44.0
        submitted = runtime.client().submitted
        for _ in range(20):
            runtime.tick()
        assert runtime.client().submitted == submitted
        assert obj.blendsolid_error == "" and runtime.part_status(obj) == "edit_mode"
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    assert len(obj.data.polygons) == polys
    wait_for(lambda: up_to_date(obj))
    assert obj.blendsolid_error == "" and runtime.part_status(obj) is None


def test_result_arriving_in_edit_mode_is_discarded(clean):
    obj = new_part()
    obj.blendsolid_params["box_1_length"].value = 46.0
    runtime.tick()  # submitted before entering Edit Mode
    assert obj.name in runtime._inflight
    enter_edit_mode(obj)
    try:
        wait_for(lambda: obj.name not in runtime._inflight)  # the result came back and was dropped
        for _ in range(5):
            runtime.tick()
        assert obj.blendsolid_error == "" and not up_to_date(obj)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    wait_for(lambda: up_to_date(obj))
    assert obj.blendsolid_error == ""


def test_edit_mode_on_mesh_sibling_defers_rebuild(clean):
    a = new_part()
    b = a.copy()  # Alt+D: same mesh, same script
    bpy.context.collection.objects.link(b)
    primary, sibling = sorted([a, b], key=lambda o: o.name)
    enter_edit_mode(sibling)
    try:
        primary.blendsolid_params["box_1_width"].value = 33.0
        submitted = runtime.client().submitted
        for _ in range(10):
            runtime.tick()
        assert runtime.client().submitted == submitted and primary.blendsolid_error == ""
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    wait_for(lambda: up_to_date(primary))


# -- Link Object Data direction (finding 3) --------------------------------------------------------------------

@pytest.mark.parametrize("target_name", ["A_target", "Z_target"])
def test_link_object_data_keeps_the_meshs_script(clean, target_name):
    """Ctrl+L with `source` active gives `target` source's mesh: the part must keep the script that mesh was
    computed from (source's), whichever object sorts first by name."""
    source = new_part("M_source")
    target = new_part(target_name)
    part.set_param(target, "box_1_length", 55.0)
    wait_for(lambda: up_to_date(target))
    target.data = source.data
    runtime.tick()
    assert target.blendsolid_script == source.blendsolid_script
    assert "length = 40.0\n" in part.source_of(target)
    wait_for(lambda: up_to_date(source))
    submitted = runtime.client().submitted
    for _ in range(10):
        runtime.tick()
    assert runtime.client().submitted == submitted


def test_link_object_data_falls_back_to_name_order(clean):
    a = new_part("A")
    b = new_part("B")
    part.set_param(a, "box_1_length", 51.0)
    part.set_param(b, "box_1_length", 52.0)  # neither script matches any applied mesh any more
    b.data = a.data
    runtime.tick()
    assert b.blendsolid_script == a.blendsolid_script and "length = 51.0\n" in part.source_of(a)


# -- identity grouping, library parts (finding 4) ---------------------------------------------------------------

def test_linked_library_part_is_never_written_or_submitted(clean):
    lib_obj = new_part()  # "Part", mesh "Part", text ".Part.py" — same names as the local part below
    part.set_param(lib_obj, "box_1_length", 60.0)  # stale in the library: would be submitted if it were local
    lib_source = part.source_of(lib_obj)
    lib_path = os.path.join(tempfile.mkdtemp(), "lib.blend")
    bpy.data.libraries.write(lib_path, {lib_obj, lib_obj.data, lib_obj.blendsolid_script})
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.texts):
        bpy.data.batch_remove(list(coll))
    runtime.reset_state()

    local = new_part()
    assert local.name == "Part" and local.data.name == "Part"
    with bpy.data.libraries.load(lib_path, link=True) as (src, dst):
        dst.objects = ["Part"]
    linked = dst.objects[0]
    bpy.context.collection.objects.link(linked)
    assert linked.library is not None and linked.name == "Part" and linked.data.name == "Part"
    trust.trust_file()  # so trust can't be what keeps the linked part from running
    try:
        submitted = runtime.client().submitted
        for _ in range(20):
            runtime.tick()
        assert runtime.client().submitted == submitted
        assert part.source_of(linked) == lib_source and linked.blendsolid_error == ""
        assert linked.blendsolid_script != local.blendsolid_script
        assert runtime.part_status(linked) == "linked"
        local.blendsolid_params["box_1_length"].value = 42.0  # the local part still reconciles normally
        wait_for(lambda: up_to_date(local))
        assert part.source_of(linked) == lib_source
    finally:
        trust.reset_for_file(bpy.context.preferences, bpy.data.filepath)


# -- tick cost (finding 5) ----------------------------------------------------------------------------------------

def test_tick_is_fast_with_many_parts(clean):
    coll = bpy.context.collection
    for i in range(300):
        text = bpy.data.texts.new(f".P{i}.py")
        text.from_string(f"size = {i + 1}.0\nresult = Box(size, size, size)\n")
        trust.mark_trusted(text)
        obj = bpy.data.objects.new(f"P{i}", bpy.data.meshes.new(f"P{i}"))
        coll.objects.link(obj)
        obj.blendsolid_script = text
        obj.data[part.HASH_KEY] = part.current_tag(obj)  # already up to date: nothing to submit
    plain = bpy.data.meshes.new("plain")
    for i in range(2000):
        coll.objects.link(bpy.data.objects.new(f"O{i}", plain))
    runtime.tick()  # first tick mirrors every part's parameters once
    submitted = runtime.client().submitted
    times = []
    for _ in range(30):
        t0 = time.perf_counter()
        runtime.tick()
        times.append(time.perf_counter() - t0)
    median = statistics.median(times)
    print(f"\ntick with 300 parts + 2000 objects: median {median * 1000:.2f} ms, "
          f"min {min(times) * 1000:.2f} ms, max {max(times) * 1000:.2f} ms")
    assert runtime.client().submitted == submitted
    assert median < 0.010


# -- the parameter mirror after undo (found by tools/gui_check.py, step 15) ----------------------------------

def test_undo_to_a_step_pushed_before_the_mirror_synced_resyncs_it(clean):
    """An operator that edits a script pushes its undo step before the next tick mirrors the new parameters,
    so that step holds a stale mirror. Undoing back to it restores the stale mirror with the script it belongs
    to: the tick must mirror it again even though that script's tag is the one it last synced."""
    bpy.ops.ed.undo_push(message="start")
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True, length=40, width=30, height=20)
    box = bpy.context.view_layer.objects.active
    runtime.tick()
    bpy.ops.blendsolid.draw_solid("EXEC_DEFAULT", True, shape="BOX", mode="UNION", target=box.name,
                                  location=(0, 0, 20), rotation=(0, 0, 0), length=10, width=10, height=5)
    runtime.tick()  # mirrors box_2's parameters, after the step above was pushed
    assert "box_2_height" in box.blendsolid_params
    bpy.ops.blendsolid.add_cylinder("EXEC_DEFAULT", True)  # another step, the box unchanged
    bpy.ops.ed.undo()
    box = bpy.data.objects["Box"]
    runtime.tick()
    assert [p.name for p in box.blendsolid_params] == [
        "box_1_length", "box_1_width", "box_1_height", "box_2_length", "box_2_width", "box_2_height"]


def test_busy_ticks_poll_faster_and_kick_submits_at_once(clean):
    # Milestone 2 (Fillet drag latency): while a result is awaited the timer polls every TICK_BUSY; a tool that
    # edits a script calls kick() to submit it now instead of at the next tick.
    from blendsolid import part, runtime
    obj = part.new_part(bpy.context)
    wait_for(lambda: part.applied_hash(obj) == part.current_tag(obj))
    assert runtime.tick() == runtime.TICK_INTERVAL  # nothing in flight
    obj.blendsolid_script.from_string(part.source_of(obj).replace("box_1_height = 20.0", "box_1_height = 21.0"))
    runtime.kick()
    assert runtime._inflight.get(obj.name) == part.current_tag(obj)
    assert runtime.tick() == runtime.TICK_BUSY < runtime.TICK_INTERVAL
    wait_for(lambda: part.applied_hash(obj) == part.current_tag(obj))


def test_undo_and_redo_panel_keep_showing_the_part(clean):
    # An operator's undo step is pushed before the worker's result arrives: undoing to "add a box" restored an
    # empty mesh, and the Adjust Last Operation panel (undo, then the operator again) showed it while the new
    # result computed (the maintainer saw the part vanish/shrink, 2026-09-29). The results are kept: one tick
    # puts the script's own mesh back, or the last one shown while the new script computes.
    def dims(name):
        bpy.context.view_layer.update()
        return tuple(round(x * 1000, 3) for x in bpy.data.objects[name].dimensions)

    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    name = bpy.context.view_layer.objects.active.name
    wait_for(lambda: up_to_date(bpy.data.objects[name]))
    ref = 'edge_between(face("box_1", "+Z"), face("box_1", "-Y"))'
    bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target=name, references=ref, radius=2.0, chamfer=True)
    wait_for(lambda: up_to_date(bpy.data.objects[name]))
    bpy.ops.ed.undo()  # the step holds an empty mesh: the undo handler puts the kept result back before a redraw
    assert up_to_date(bpy.data.objects[name]) and dims(name) == (40.0, 30.0, 20.0)  # no recompute needed
    bpy.ops.ed.redo()
    bpy.ops.ed.undo()  # the panel's undo, then the operator with the new values
    bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target=name, references=ref, radius=2.0, chamfer=True,
                              chamfer_mode="TWO", length2=5.0)
    assert dims(name) == (40.0, 30.0, 20.0)  # the box while the chamfer computes, before any tick
    wait_for(lambda: up_to_date(bpy.data.objects[name]))
    assert len(bpy.data.objects[name].data.vertices) == 10


def test_undo_to_a_failing_script_keeps_that_steps_mesh(clean):
    # a failing script is never recomputed into a mesh: undoing to it must leave the step's own mesh (its last good
    # result), not the kept mesh of the step undone from (bug sweep, 2026-10-04: the r 5 fillet stayed shown on the
    # r 50 script that fails)
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    name = bpy.context.view_layer.objects.active.name
    wait_for(lambda: up_to_date(bpy.data.objects[name]))
    ref = 'edge_between(face("box_1", "+X"), face("box_1", "+Z"))'
    bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target=name, references=ref, radius=50.0)
    wait_for(lambda: bpy.data.objects[name].blendsolid_error != "")
    obj = bpy.data.objects[name]
    obj.blendsolid_params["fillet_1_radius"].value = 5.0
    bpy.ops.ed.undo_push(message="radius 5")
    wait_for(lambda: up_to_date(bpy.data.objects[name]))
    assert mm3(bpy.data.objects[name]) < 24000 - 1
    runtime.tick()
    bpy.ops.ed.undo()
    obj = bpy.data.objects[name]
    wait_for(lambda: bpy.data.objects[name].blendsolid_error != "")
    assert mm3(bpy.data.objects[name]) == pytest.approx(24000, rel=1e-6)


def test_a_new_part_never_shows_a_deleted_namesakes_mesh(clean):
    # runtime keeps meshes by object name: a new part named like a deleted one got its mesh back (bug sweep,
    # 2026-10-04), and kept it for good when its own script failed
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    old = bpy.context.view_layer.objects.active
    name = old.name
    wait_for(lambda: up_to_date(old))
    bpy.data.objects.remove(old)
    new = part.new_part(bpy.context, "result = Box(10, 10, 10) / 0\n", name=name)
    assert new.name == name
    bpy.ops.ed.undo_push()
    runtime._on_undo()  # what an undo/redo step runs
    runtime.tick()
    assert len(new.data.polygons) == 0
    wait_for(lambda: new.blendsolid_error != "")
    assert len(new.data.polygons) == 0


def test_a_new_part_gets_its_own_error_after_a_failing_namesake(clean):
    # the deleted part's "failed" record (by name, same script hash) kept the new one from ever being computed:
    # no error shown, no parameters (bug sweep, 2026-10-04)
    source = "size = 10.0\nwith BuildPart() as part:\n    Box(size, size, size / 0)  # feature: box_1\nresult = part.part\n"
    old = part.new_part(bpy.context, source, name="Fails")
    wait_for(lambda: old.blendsolid_error != "")
    bpy.data.objects.remove(old)
    new = part.new_part(bpy.context, source, name="Fails")
    assert new.name == "Fails"
    wait_for(lambda: new.blendsolid_error != "", timeout=10.0)
    assert "ZeroDivisionError" in new.blendsolid_error
