import time

import bpy
import pytest

import blendsolid


@pytest.fixture(scope="session")
def addon():
    blendsolid.register()
    yield blendsolid
    blendsolid.unregister()


@pytest.fixture
def clean(addon):
    """Empty scene and fresh runtime state for each test."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for text in list(bpy.data.texts):
        bpy.data.texts.remove(text)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
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
