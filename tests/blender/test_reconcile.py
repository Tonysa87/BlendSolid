"""Reconcile loop: Edit Mode, Link Object Data direction, identity grouping/library parts, tick cost."""
import os
import statistics
import tempfile
import time

import bpy
import pytest

from blendsolid import part, runtime, trust
from conftest import up_to_date, wait_for


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
