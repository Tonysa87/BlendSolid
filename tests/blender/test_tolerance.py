"""Display tolerance: a scene setting (millimetres, default 1) that decides how finely parts are tessellated."""
import bpy
import pytest

from blendsolid import part
from conftest import up_to_date, wait_for

SPHERE = "radius = 1000.0\nresult = Sphere(radius)\n"  # one metre: the tolerance, not the angle, decides


@pytest.fixture
def tolerance():
    scene = bpy.context.scene
    saved = scene.blendsolid_tolerance
    yield scene
    scene.blendsolid_tolerance = saved


def test_default_is_one_millimetre(clean, tolerance):
    assert bpy.types.Scene.bl_rna.properties["blendsolid_tolerance"].default == 1.0


def test_changing_the_tolerance_recomputes_with_more_or_fewer_triangles(clean, tolerance):
    tolerance.blendsolid_tolerance = 1.0
    obj = part.new_part(bpy.context, SPHERE)
    wait_for(lambda: up_to_date(obj))
    coarse = len(obj.data.polygons)
    tag = part.applied_hash(obj)
    tolerance.blendsolid_tolerance = 0.25
    assert part.current_tag(obj) != tag  # the tolerance is part of the mesh tag
    wait_for(lambda: up_to_date(obj))
    fine = len(obj.data.polygons)
    assert fine > 2 * coarse
    assert coarse < 20000  # a one-metre sphere stays light at the default tolerance
