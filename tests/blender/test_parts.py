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


def test_stale_result_is_discarded(clean):
    obj = new_part()
    obj.blendsolid_params["length"].value = 50.0
    runtime.tick()                                   # submits length=50
    obj.blendsolid_params["length"].value = 60.0     # before the first result arrives
    wait_for(lambda: up_to_date(obj))
    assert "length = 60.0\n" in part.source_of(obj)
    assert abs(part.mesh_volume(obj.data) - expected_volume(length=60.0)) / expected_volume(length=60.0) < 0.01


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
