"""ADR 0004: parts loaded from a file run their script only if Blender's Auto Run Python Scripts allows the
file, or after the user presses Trust Scripts in This File. Parts created in this session are trusted."""
import os
import tempfile

import bpy
import pytest

from blendsolid import part, runtime
from conftest import up_to_date, wait_for


@pytest.fixture
def auto_run():
    fp = bpy.context.preferences.filepaths
    saved = fp.use_scripts_auto_execute
    yield fp
    fp.use_scripts_auto_execute = saved
    paths = bpy.context.preferences.autoexec_paths
    while len(paths):
        paths.remove(paths[0])


def save_stale_part_and_reload():
    """A file whose part's script differs from the script its mesh was computed from."""
    obj = part.new_part(bpy.context)
    wait_for(lambda: up_to_date(obj))
    part.set_param(obj, "box_1_length", 45.0)  # never ticked: the saved mesh is stale
    path = os.path.join(tempfile.mkdtemp(), "stale.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    return bpy.data.objects["Part"], path


def test_loaded_part_is_not_run_without_auto_run(clean, auto_run):
    auto_run.use_scripts_auto_execute = False
    obj, _ = save_stale_part_and_reload()
    polys = len(obj.data.polygons)
    submitted = runtime.client().submitted
    for _ in range(50):
        runtime.tick()
    assert runtime.client().submitted == submitted
    assert not up_to_date(obj) and len(obj.data.polygons) == polys  # cached mesh kept
    assert runtime.part_status(obj) == "untrusted"
    obj.blendsolid_params["box_1_width"].value = 31.0  # a param edit must not run it either
    for _ in range(20):
        runtime.tick()
    assert runtime.client().submitted == submitted


def test_trust_operator_runs_loaded_part(clean, auto_run):
    auto_run.use_scripts_auto_execute = False
    obj, _ = save_stale_part_and_reload()
    runtime.tick()
    assert runtime.part_status(obj) == "untrusted"
    assert bpy.ops.blendsolid.trust_scripts() == {"FINISHED"}
    wait_for(lambda: up_to_date(obj))
    assert "length = 45.0\n" in part.source_of(obj)
    assert runtime.part_status(obj) is None


def test_new_part_in_untrusted_file_computes(clean, auto_run):
    auto_run.use_scripts_auto_execute = False
    loaded, _ = save_stale_part_and_reload()
    fresh = part.new_part(bpy.context, name="Fresh")
    wait_for(lambda: up_to_date(fresh))
    assert not up_to_date(loaded)
    dup = fresh.copy()  # Shift+D of a trusted part: its script copy stays trusted
    dup.data = fresh.data.copy()
    bpy.context.collection.objects.link(dup)
    runtime.tick()
    dup.blendsolid_params["box_1_length"].value = 52.0
    wait_for(lambda: up_to_date(dup))


def test_loaded_part_runs_with_auto_run(clean, auto_run):
    auto_run.use_scripts_auto_execute = True
    obj, _ = save_stale_part_and_reload()
    wait_for(lambda: up_to_date(obj))


def test_excluded_path_is_not_run_even_with_auto_run(clean, auto_run):
    auto_run.use_scripts_auto_execute = True
    obj, path = save_stale_part_and_reload()
    excluded = bpy.context.preferences.autoexec_paths.new()
    excluded.path = os.path.dirname(path)
    bpy.ops.wm.open_mainfile(filepath=path)  # reload with the exclusion in place
    obj = bpy.data.objects["Part"]
    submitted = runtime.client().submitted
    for _ in range(30):
        runtime.tick()
    assert runtime.client().submitted == submitted and runtime.part_status(obj) == "untrusted"


def test_trust_is_not_saved(clean, auto_run):
    auto_run.use_scripts_auto_execute = False
    obj, path = save_stale_part_and_reload()
    bpy.ops.blendsolid.trust_scripts()
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    assert runtime.part_status(bpy.data.objects["Part"]) == "untrusted"


def test_recompute_is_disabled_on_untrusted_parts(clean, auto_run):
    auto_run.use_scripts_auto_execute = False
    obj, _ = save_stale_part_and_reload()
    bpy.context.view_layer.objects.active = obj
    assert not bpy.ops.blendsolid.recompute.poll()
    bpy.ops.blendsolid.trust_scripts()
    assert bpy.ops.blendsolid.recompute.poll()


@pytest.mark.parametrize("flag, expected", [("", "True"), ("-Y", "False")])
def test_disable_autoexec_flag_is_honoured(flag, expected):
    """Blender's -Y blocks auto-run even when the preference is on; BlendSolid must not run scripts then."""
    from conftest import run_probe

    probe = ("import bpy; from blendsolid import trust; "
             "bpy.context.preferences.filepaths.use_scripts_auto_execute = True; "
             "trust.reset_for_file(bpy.context.preferences, ''); print('PROBE', trust.file_trusted())")
    out = run_probe([flag] if flag else [], probe)
    assert f"PROBE {expected}" in out, out
