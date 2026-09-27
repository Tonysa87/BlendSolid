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


# -- the fillet operator ------------------------------------------------------------------------------------------

TOP_FRONT = 'edge_between(face("box_1", "+Z"), face("box_1", "-Y"))'
ROUND = 1 - math.pi / 4  # cross-section area removed by a fillet of radius 1 on a right-angled edge
CHAIN = 35 + 2.5 * math.pi + 25  # mm: the top-front edge's tangent chain on the default part


def fillet(obj, *refs, radius=2.0, chamfer=False):
    return bpy.ops.blendsolid.fillet(target=obj.name, references="\n".join(refs), radius=radius, chamfer=chamfer)


def test_fillet_one_edge_and_it_follows_upstream_changes(default_part):
    v0 = mm3(default_part)
    assert fillet(default_part, TOP_FRONT) == {"FINISHED"}
    feats = script_model.features(part.source_of(default_part))
    assert feats[-1].name == "fillet_2"  # the template already has fillet_1
    assert TOP_FRONT in part.source_of(default_part) and "radius=fillet_2_radius" in part.source_of(default_part)
    wait_for(lambda: up_to_date(default_part))
    removed = v0 - mm3(default_part)
    # The edge runs from the template's fillet (x = 5) to x = 40 and is tangent, through that fillet's top arc,
    # to the -X top edge: OCCT rounds the whole chain (35 + 2.5π + 25 mm).
    assert removed == pytest.approx(ROUND * 4 * CHAIN, rel=0.03)
    part.set_param(default_part, "box_1_length", 60.0)  # upstream change: the same edge, now 55 mm long
    wait_for(lambda: up_to_date(default_part))
    assert default_part.blendsolid_error == ""
    assert (v0 + 20 * 30 * 20 - mm3(default_part)) == pytest.approx(ROUND * 4 * (CHAIN + 20), rel=0.03)


def test_chamfer_and_a_face_selection(default_part):
    v0 = mm3(default_part)
    assert fillet(default_part, TOP_FRONT, radius=2.0, chamfer=True) == {"FINISHED"}
    assert "chamfer(" in part.source_of(default_part) and "length=chamfer_1_length" in part.source_of(default_part)
    wait_for(lambda: up_to_date(default_part))
    assert v0 - mm3(default_part) == pytest.approx(2 * CHAIN, rel=0.03)  # a 2 mm chamfer: 2 mm² per mm of edge
    assert fillet(default_part, 'edges_of(face("boss_1", "+Z"))', radius=1.0) == {"FINISHED"}
    wait_for(lambda: up_to_date(default_part))
    assert default_part.blendsolid_error == ""


def test_two_edges_in_one_feature(default_part):
    other = 'edge_between(face("box_1", "+X"), face("box_1", "+Z"))'
    assert fillet(default_part, TOP_FRONT, other) == {"FINISHED"}
    assert f"fillet({TOP_FRONT} + {other}, radius=fillet_2_radius)" in part.source_of(default_part)
    wait_for(lambda: up_to_date(default_part))
    assert default_part.blendsolid_error == ""


def test_a_radius_too_large_is_an_error_on_its_line(default_part):
    fillet(default_part, TOP_FRONT, radius=50.0)
    wait_for(lambda: default_part.blendsolid_error != "")
    line = next(n for n, text in enumerate(part.source_of(default_part).splitlines(), 1) if "fillet_2" in text
                and "fillet(" in text)
    assert default_part.blendsolid_error_line == line


def test_refused_without_references_or_on_a_non_canonical_part(default_part):
    with pytest.raises(RuntimeError):
        fillet(default_part)  # nothing selected
    other = part.new_part(bpy.context, "result = Box(10, 10, 10)\n")
    with pytest.raises(RuntimeError):
        fillet(other, TOP_FRONT)


def test_edge_frames_give_the_faces_on_either_side(default_part):
    frames = picking.edge_frames(default_part, TOP_FRONT)
    assert frames
    for a, b, n1, n2, c1, c2 in frames:
        normals = {tuple(round(v, 5) for v in n) for n in (n1, n2)}
        assert normals == {(0.0, 0.0, 1.0), (0.0, -1.0, 0.0)}  # the top and the front face
        assert abs(a.y) < 1e-9 and abs(a.z - 20 * F) < 1e-9
    assert len(picking.edge_frames(default_part, 'edges_of(face("box_1", "+Z"))')) > len(frames)
