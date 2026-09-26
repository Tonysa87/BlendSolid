"""ADR 0003: scripts are in millimetres; meshes are in Blender units, factor 0.001 / scene scale_length."""
import bpy
import pytest

from blendsolid import part, runtime
from conftest import wait_for

BOX = "length = 40.0\nwidth = 30.0\nheight = 20.0\nresult = Box(length, width, height)\n"


def up_to_date(obj):
    return part.applied_hash(obj) == part.current_tag(obj)


@pytest.fixture
def scale_length():
    units = bpy.context.scene.unit_settings
    saved = units.scale_length
    yield units
    units.scale_length = saved


def dims(obj):
    """Rounded to float32 precision (the mesh stores float32 coordinates)."""
    return tuple(float(f"{d:.5g}") for d in obj.dimensions)


def test_default_scene_is_metres(clean, scale_length):
    scale_length.scale_length = 1.0
    obj = part.new_part(bpy.context, BOX)
    wait_for(lambda: up_to_date(obj))
    assert dims(obj) == (0.04, 0.03, 0.02)  # 40 x 30 x 20 mm


def test_millimetre_scene(clean, scale_length):
    scale_length.scale_length = 0.001
    obj = part.new_part(bpy.context, BOX)
    wait_for(lambda: up_to_date(obj))
    assert dims(obj) == (40.0, 30.0, 20.0)


def test_changing_the_unit_scale_recomputes(clean, scale_length):
    scale_length.scale_length = 1.0
    obj = part.new_part(bpy.context, BOX)
    wait_for(lambda: up_to_date(obj))
    scale_length.scale_length = 0.01  # centimetres
    assert not up_to_date(obj)  # the factor is part of the cache tag
    wait_for(lambda: up_to_date(obj))
    assert dims(obj) == (4.0, 3.0, 2.0)
    submitted = runtime.client().submitted
    for _ in range(10):
        runtime.tick()
    assert runtime.client().submitted == submitted
