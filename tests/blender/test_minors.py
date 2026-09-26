"""Review follow-ups: script fake users, panel status, missing worker libraries, integer parameters."""
import os
import tempfile

import bpy

from blendsolid import part, paths, runtime
from conftest import wait_for


def up_to_date(obj):
    return part.applied_hash(obj) == part.current_tag(obj)


def stop_worker():
    if runtime._client is not None:
        runtime._client.stop()


# -- finding 8: no fake user on part scripts ---------------------------------------------------------------------

def test_deleted_part_leaves_no_script_behind(clean):
    obj = part.new_part(bpy.context)
    wait_for(lambda: up_to_date(obj))
    assert not obj.blendsolid_script.use_fake_user
    dup = obj.copy()  # Shift+D: its script copy must not get a fake user either
    dup.data = obj.data.copy()
    bpy.context.collection.objects.link(dup)
    runtime.tick()
    assert dup.blendsolid_script != obj.blendsolid_script and not dup.blendsolid_script.use_fake_user
    name, dup_name = obj.blendsolid_script.name, dup.blendsolid_script.name
    bpy.data.objects.remove(obj)
    assert bpy.data.texts[name].users == 0
    path = os.path.join(tempfile.mkdtemp(), "deleted.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    assert name not in bpy.data.texts and dup_name in bpy.data.texts


# -- finding 9: panel status while starting / computing ------------------------------------------------------------

def test_status_while_starting_then_computing(clean):
    stop_worker()
    obj = part.new_part(bpy.context, "size = 10.0\nimport time\ntime.sleep(1.0)\nresult = Box(size, size, size)\n")
    runtime.tick()
    assert runtime.part_status(obj) == "starting"
    wait_for(lambda: runtime.part_status(obj) == "computing")
    sibling = obj.copy()  # Alt+D: shows its primary's state
    bpy.context.collection.objects.link(sibling)
    assert runtime.part_status(sibling) == "computing"
    wait_for(lambda: up_to_date(obj))
    assert runtime.part_status(obj) is None


# -- finding 11: missing worker libraries -------------------------------------------------------------------------

def test_missing_worker_libraries_is_a_part_error(clean, monkeypatch, capsys):
    stop_worker()
    monkeypatch.setattr(runtime, "_client", None)

    def missing():
        raise FileNotFoundError("BlendSolid worker libraries not found")

    monkeypatch.setattr(paths, "worker_libs", missing)
    a = part.new_part(bpy.context)
    b = part.new_part(bpy.context, name="Part2")
    for _ in range(5):
        runtime._timer()  # through the timer wrapper, which used to print the exception every time
    for obj in (a, b):
        assert obj.blendsolid_error.startswith("Cannot start the geometry worker")
        assert "worker libraries not found" in obj.blendsolid_error
    assert "BlendSolid:" not in capsys.readouterr().out


# -- finding 13: integer parameters --------------------------------------------------------------------------------

def test_integer_parameter_is_an_int_property(clean):
    obj = part.new_part(bpy.context, "count = 3\nsize = 5.0\nresult = Box(size * count, size, size)\n")
    wait_for(lambda: up_to_date(obj))
    count, size = obj.blendsolid_params["count"], obj.blendsolid_params["size"]
    assert count.is_int and not size.is_int
    assert count.bl_rna.properties["value_int"].type == "INT" and count.value_int == 3
    count.value_int = 5
    assert "count = 5\n" in part.source_of(obj)
    wait_for(lambda: up_to_date(obj))
    assert count.value_int == 5 and abs(count.value - 5.0) < 1e-9
    size.value = 6.0  # floats still go through `value`
    assert "size = 6.0\n" in part.source_of(obj) and "count = 5\n" in part.source_of(obj)
