import math
import os
import tempfile

import bpy

from blendsolid import part, runtime
from conftest import wait_for


def expected_volume(length=40.0, width=30.0, height=20.0, r=6.0, bh=25.0, f=5.0):
    return length * width * height + math.pi * r * r * (bh - height) - (1 - math.pi / 4) * f * f * height


def up_to_date(obj):
    return part.applied_hash(obj) == part.source_hash(part.source_of(obj))


def new_part():
    obj = part.new_part(bpy.context)
    wait_for(lambda: up_to_date(obj))
    return obj


def test_new_part_builds_mesh_with_face_ids(clean):
    obj = new_part()
    assert abs(part.mesh_volume(obj.data) - expected_volume()) / expected_volume() < 0.01
    ids = {v.value for v in obj.data.attributes[part.FACE_ATTR].data}
    assert ids == set(range(len(ids))) and len(ids) >= 9
    assert [p.name for p in obj.blendsolid_params] == [
        "length", "width", "height", "boss_radius", "boss_height", "fillet_radius"]
    assert obj.blendsolid_error == ""


def test_param_edit_rewrites_script_and_recomputes(clean):
    obj = new_part()
    obj.blendsolid_params["height"].value = 22.0
    assert "height = 22.0\n" in part.source_of(obj)
    wait_for(lambda: up_to_date(obj))
    assert abs(part.mesh_volume(obj.data) - expected_volume(height=22.0)) / expected_volume(height=22.0) < 0.01


def test_error_keeps_previous_mesh(clean):
    obj = new_part()
    n_polys = len(obj.data.polygons)
    good_hash = part.applied_hash(obj)
    obj.blendsolid_script.from_string(part.source_of(obj).replace("result = part.part", "result = part.prt"))
    wait_for(lambda: obj.blendsolid_error != "")
    assert "AttributeError" in obj.blendsolid_error and obj.blendsolid_error_line > 0
    assert len(obj.data.polygons) == n_polys and part.applied_hash(obj) == good_hash
    obj.blendsolid_script.from_string(part.source_of(obj).replace("part.prt", "part.part"))
    wait_for(lambda: obj.blendsolid_error == "" and up_to_date(obj))


def test_stale_result_is_discarded(clean, monkeypatch):
    obj = new_part()
    applied_tags = []
    orig_apply = part.apply_result

    def recording_apply(obj_, event):
        applied_tags.append(event["tag"])
        orig_apply(obj_, event)

    monkeypatch.setattr(part, "apply_result", recording_apply)
    obj.blendsolid_params["length"].value = 50.0
    tag50 = part.source_hash(part.source_of(obj))
    runtime.tick()                                   # submits length=50
    obj.blendsolid_params["length"].value = 60.0     # before the first result arrives
    wait_for(lambda: up_to_date(obj))
    assert "length = 60.0\n" in part.source_of(obj)
    assert abs(part.mesh_volume(obj.data) - expected_volume(length=60.0)) / expected_volume(length=60.0) < 0.01
    # the length=50 result must never have been applied to the mesh (discarded as stale in runtime._handle)
    assert tag50 not in applied_tags


def test_reconcile_after_simulated_undo(clean):
    obj = new_part()
    source_a = part.source_of(obj)
    obj.blendsolid_params["width"].value = 35.0
    wait_for(lambda: up_to_date(obj))
    # an undo step can restore the script while the mesh is one step behind: the tick must repair it
    obj.blendsolid_script.from_string(source_a)
    assert not up_to_date(obj)
    wait_for(lambda: up_to_date(obj))
    assert abs(part.mesh_volume(obj.data) - expected_volume()) / expected_volume() < 0.01


def test_crash_does_not_loop(clean):
    obj = new_part()
    obj.blendsolid_script.from_string("import os\nos._exit(7)\n")
    wait_for(lambda: "crashed" in obj.blendsolid_error or "exited" in obj.blendsolid_error)
    submitted = runtime.client().submitted
    for _ in range(20):
        runtime.tick()
    assert runtime.client().submitted == submitted
    obj.blendsolid_script.from_string(part.default_source())
    wait_for(lambda: obj.blendsolid_error == "" and up_to_date(obj))


def test_duplicate_gets_own_script(clean):
    obj = new_part()
    dup = obj.copy()
    dup.data = obj.data.copy()
    bpy.context.collection.objects.link(dup)
    runtime.tick()
    assert dup.blendsolid_script != obj.blendsolid_script
    dup.blendsolid_params["length"].value = 70.0
    wait_for(lambda: up_to_date(dup))
    assert "length = 40.0\n" in part.source_of(obj)


def test_reload_does_not_recompute(clean):
    obj = new_part()
    path = os.path.join(tempfile.mkdtemp(), "part.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    submitted = runtime.client().submitted
    for _ in range(10):
        runtime.tick()
    obj = bpy.data.objects["Part"]
    assert up_to_date(obj) and runtime.client().submitted == submitted


def test_shared_mesh_is_one_part(clean):
    """Ctrl+L (Link Object Data) makes two objects share one mesh: controller ruling says they are ONE
    part, so tick() must unify their scripts and submit only once, never ping-ponging between them."""
    a = new_part()
    b = part.new_part(bpy.context, name="Part2")
    part.set_param(b, "length", 55.0)  # diverge b's script from a's before linking data
    b.data = a.data                    # simulated Ctrl+L Link Object Data
    runtime.tick()
    assert b.blendsolid_script == a.blendsolid_script
    wait_for(lambda: up_to_date(a) and up_to_date(b))
    submitted = runtime.client().submitted
    for _ in range(20):
        runtime.tick()
    assert runtime.client().submitted == submitted


def test_param_edit_on_broken_script_does_not_raise(clean):
    obj = new_part()
    obj.blendsolid_script.from_string("this is not valid python(\n")
    obj.blendsolid_params["height"].value = 21.0  # must not raise into the RNA update
    assert obj.blendsolid_error != ""


def test_param_edit_with_no_script_does_not_raise(clean):
    obj = new_part()
    obj.blendsolid_script = None
    obj.blendsolid_params["length"].value = 41.0  # must not raise: nothing to write to


def test_param_error_from_ui_survives_ticks(clean):
    # Blender's FloatProperty clamps float("inf") to FLT_MAX (a finite value) before the update callback
    # ever sees it, so the non-finite value can't be produced through the real property: call the update
    # callback directly with a duck-typed item, as the brief's fallback for this case allows.
    from blendsolid import ui

    obj = new_part()

    class FakeItem:
        id_data = obj
        name = "length"
        value = float("inf")

    ui._on_param_value(FakeItem(), bpy.context)
    assert obj.blendsolid_error != ""
    assert "length = 40.0\n" in part.source_of(obj)  # set_param rejected it before writing the script
    for _ in range(5):
        runtime.tick()
    assert obj.blendsolid_error != ""  # a runtime tick must not wipe a UI-raised error


def test_object_error_does_not_stop_other_objects_reconciling(clean, monkeypatch):
    a = new_part()
    b = part.new_part(bpy.context, name="Part2")
    wait_for(lambda: up_to_date(b))
    a.blendsolid_params["length"].value = 41.0
    b.blendsolid_params["length"].value = 42.0

    orig_sync = part.sync_params

    def boom(obj, source=None):
        if obj.name == "Part":
            raise RuntimeError("boom")
        return orig_sync(obj, source)

    monkeypatch.setattr(part, "sync_params", boom)
    runtime.tick()
    assert "boom" in a.blendsolid_error
    monkeypatch.undo()
    wait_for(lambda: up_to_date(b))


def test_mesh_sibling_mirrors_params_and_error(clean):
    a = new_part()
    b = a.copy()  # Alt+D-style: shares a's mesh (and, from the copy, a's script too)
    bpy.context.collection.objects.link(b)
    assert b.data == a.data

    a.blendsolid_params["height"].value = 23.0
    wait_for(lambda: up_to_date(a))
    assert abs(b.blendsolid_params["height"].value - 23.0) < 1e-6

    a.blendsolid_script.from_string(part.source_of(a).replace("result = part.part", "result = part.prt"))
    wait_for(lambda: a.blendsolid_error != "")
    assert b.blendsolid_error == a.blendsolid_error and b.blendsolid_error_line == a.blendsolid_error_line

    a.blendsolid_script.from_string(part.source_of(a).replace("part.prt", "part.part"))
    wait_for(lambda: a.blendsolid_error == "" and up_to_date(a))
    assert b.blendsolid_error == ""


def test_error_tag_clears_when_script_tag_changes_away(clean):
    obj = new_part()
    part.set_error(obj, "simulated runtime error", tag="some-other-tag")
    assert obj.blendsolid_error != "" and part.error_tag(obj) == "some-other-tag"
    runtime.tick()  # current tag == applied hash, which differs from the error's tag -> must clear
    assert obj.blendsolid_error == "" and part.error_tag(obj) is None


def test_ui_error_without_tag_survives_ticks_while_script_unchanged(clean):
    obj = new_part()
    part.set_error(obj, "simulated UI error")  # no tag, like ui._on_param_value's ParamError path
    for _ in range(5):
        runtime.tick()
    assert obj.blendsolid_error == "simulated UI error"


def test_handle_exception_marks_failed_to_avoid_resubmit_loop(clean, monkeypatch):
    # A tight loop of tick() calls with no delay may not give the worker time to reply again even without
    # the fix (the resubmit-loop bug is real but timing-dependent to observe from the outside), so assert
    # the actual mechanism directly: _failed must be recorded for the tag that just failed to handle.
    obj = new_part()
    obj.blendsolid_params["length"].value = 45.0
    tag = part.source_hash(part.source_of(obj))

    def boom(obj_, event):
        raise RuntimeError("boom")

    monkeypatch.setattr(part, "apply_result", boom)
    wait_for(lambda: "boom" in obj.blendsolid_error)
    assert runtime._failed.get(obj.name) == tag
    submitted = runtime.client().submitted
    runtime.tick()  # deterministic regardless of worker timing: _failed alone must block this resubmission
    assert runtime.client().submitted == submitted


def test_worker_start_error_marks_remaining_objects_failed_without_retrying(clean, monkeypatch):
    from blendsolid.client import WorkerClient, WorkerStartError

    a = new_part()
    b = part.new_part(bpy.context, name="Part2")
    wait_for(lambda: up_to_date(b))
    a.blendsolid_params["length"].value = 41.0
    b.blendsolid_params["length"].value = 42.0

    calls = []

    def boom(self, key, source, tag, *args, **kwargs):
        calls.append(key)
        raise WorkerStartError("simulated: worker cannot start")

    monkeypatch.setattr(WorkerClient, "submit", boom)
    runtime.tick()
    assert len(calls) == 1  # only the first object actually called submit()
    assert "geometry worker" in a.blendsolid_error
    assert "geometry worker" in b.blendsolid_error
