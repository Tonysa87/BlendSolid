"""Milestone 2 phase C: picking CAD edges and faces, the fillet operator."""
import math

import bpy
import pytest
from mathutils import Vector

from blendsolid import part, picking, script_model
from conftest import mm3, up_to_date, wait_for

F = 0.001  # unit factor of the default (metre) scene
PIXEL = 0.1 * F  # a pixel's size at the hit: 0.1 mm (EDGE_PX pixels = 1 mm)


@pytest.fixture
def default_part(clean):
    obj = part.new_part(bpy.context)  # box 40 x 30 x 20 mm (x, y from 0), boss r6 h25 at (20, 15), fillet r5 at x=y=0
    wait_for(lambda: up_to_date(obj))
    return obj


def down(x_mm, y_mm):
    return Vector((x_mm * F, y_mm * F, 1.0)), Vector((0, 0, -1))


def test_near_an_edge_the_edge_is_picked(default_part):
    found = picking.pick(bpy.context, *down(30, 0.3), PIXEL)
    assert found.obj == default_part and found.kind == "EDGE"
    assert found.reference == 'edge_between(face("box_1", "+Z"), face("box_1", "-Y"))'
    assert found.segments and all(abs(a.y) < 1e-6 and abs(a.z - 20 * F) < 1e-6 for a, _ in found.segments)


def test_inside_a_face_the_face_is_picked(default_part):
    found = picking.pick(bpy.context, *down(30, 8), PIXEL)
    assert found.kind == "FACE" and found.reference == 'edges_of(face("box_1", "+Z"))'
    assert len(found.segments) > 4  # the face's outline, the boss's circle included


def test_picking_goes_through_a_bevel_modifier(default_part):
    mod = default_part.modifiers.new("Bevel", "BEVEL")
    mod.limit_method, mod.width = "WEIGHT", 1 * F
    bpy.context.view_layer.update()
    found = picking.pick(bpy.context, *down(30, 1.5), PIXEL * 3)
    assert found.kind == "EDGE" and found.reference == 'edge_between(face("box_1", "+Z"), face("box_1", "-Y"))'


def test_nothing_or_no_references(clean):
    assert picking.pick(bpy.context, *down(500, 500), PIXEL) is None
    other = part.new_part(bpy.context, "result = Box(10, 10, 10)\n")  # no features: nothing to write
    wait_for(lambda: up_to_date(other))
    assert picking.pick(bpy.context, *down(0, 0), PIXEL) is None
