import os
import subprocess
import time

import bpy
import pytest

import blendsolid
from blendsolid import part


@pytest.fixture(scope="session")
def addon():
    blendsolid.register()
    yield blendsolid
    blendsolid.unregister()


@pytest.fixture
def clean(addon):
    """Empty scene and fresh runtime state for each test."""
    for coll in (bpy.data.objects, bpy.data.texts, bpy.data.meshes, bpy.data.libraries):
        bpy.data.batch_remove(list(coll))  # one pass: some tests create thousands of objects
    from blendsolid import runtime
    if hasattr(runtime, "reset_state"):
        runtime.reset_state()
    yield


def wait_for(predicate, timeout=90.0):
    """Timers don't run in background mode: pump the add-on's reconcile tick by hand."""
    from blendsolid import runtime
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        runtime.tick()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not reached within %.0f s" % timeout)


def up_to_date(obj):
    return part.applied_hash(obj) == part.current_tag(obj)


def mm3(obj):
    return part.mesh_volume(obj.data) / part.unit_factor() ** 3


def select(active, *others):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in (active, *others):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active


def run_probe(extra_args, probe):
    """Spawn a headless Blender with the add-on enabled and run `probe` (a --python-expr snippet) in it.
    `extra_args` are inserted before --python-expr (e.g. flags like "-Y"). Returns combined stdout/stderr."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = [bpy.app.binary_path, "-b", "--factory-startup", *extra_args, "--python-use-system-env",
            "--addons", "blendsolid", "--python-expr", probe]
    out = subprocess.run(args, env=dict(os.environ, PYTHONPATH=root), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, timeout=120).stdout
    assert "Traceback" not in out, out
    return out
