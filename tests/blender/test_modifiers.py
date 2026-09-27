"""Parts under Blender modifiers (milestone 2, ADR 0008): the welded display mesh is an ordinary closed mesh, so
modifiers work on it, and the tools still find the CAD face a click lands on.

What the modifiers do to the part's attributes (measured on the default part, Blender 5.2.2):
- every modifier below keeps `brep_face_id` on every polygon; faces a modifier makes (Bevel's bevel faces,
  Solidify's inner shell and rims, Subdivision's children, Array's copies) take the id of the face they come from;
- Bevel with Limit Method Weight rounds exactly the sharp CAD edges (`bevel_weight_edge` = 1); with Clamp Overlap
  (its default) the result equals the unclamped one, because flat faces have no short chords (one polygon per face,
  convex polygons around holes);
- Edge Split with "Sharp Edges" splits exactly the sharp CAD edges.
"""
import math

import bmesh
import bpy
import numpy as np
import pytest
from mathutils import Vector

from blendsolid import ops_draw, part
from conftest import up_to_date, wait_for

F = 0.001  # unit factor of the default (metre) scene


@pytest.fixture
def default_part(clean):
    obj = part.new_part(bpy.context)  # box 40 x 30 x 20 mm, boss r6 h25 at (20, 15), fillet r5 on the edge at x=y=0
    wait_for(lambda: up_to_date(obj))
    return obj


def evaluated(obj):
    bpy.context.view_layer.update()
    return obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data


def stats(obj):
    """(non-manifold edges, volume mm³) of obj's evaluated mesh."""
    bm = bmesh.new()
    bm.from_mesh(evaluated(obj))
    out = sum(1 for e in bm.edges if not e.is_manifold), bm.calc_volume() / F ** 3
    bm.free()
    return out


def face_ids(mesh):
    ids = np.empty(len(mesh.polygons), np.int32)
    mesh.attributes[part.FACE_ATTR].data.foreach_get("value", ids)
    return ids


def top_face_id(obj):
    planes = np.asarray(obj.data[part.PLANES_KEY]).reshape(-1, 4)
    return int(np.nonzero(np.all(np.abs(planes - (0, 0, 1, 20)) < 1e-9, axis=1))[0][0])


def pick_down(x_mm, y_mm):
    """ops_draw.pick() with a ray straight down through (x, y) mm."""
    return ops_draw.pick(bpy.context, Vector((x_mm * F, y_mm * F, 1.0)), Vector((0, 0, -1)))


def hit_polygon(obj, x_mm, y_mm):
    hit, _, _, index, found, _ = bpy.context.scene.ray_cast(bpy.context.evaluated_depsgraph_get(),
                                                           Vector((x_mm * F, y_mm * F, 1.0)), Vector((0, 0, -1)))
    assert hit and found.original == obj
    return index


def add(obj, kind, **settings):
    mod = obj.modifiers.new(kind, kind)
    for key, value in settings.items():
        setattr(mod, key, value)
    return mod


def sharp_length_mm(obj):
    me = obj.data
    sharp = np.empty(len(me.edges), bool)
    me.attributes["sharp_edge"].data.foreach_get("value", sharp)
    return sum((me.vertices[e.vertices[0]].co - me.vertices[e.vertices[1]].co).length / F
               for e in me.edges if sharp[e.index])


def test_the_part_itself_is_closed(default_part):
    holes, volume = stats(default_part)
    assert holes == 0 and volume == pytest.approx(part.mesh_volume(default_part.data) / F ** 3, rel=1e-9)


@pytest.mark.parametrize("clamp", [True, False])
def test_bevel_by_weight_rounds_the_cad_edges(default_part, clamp):
    _, before = stats(default_part)
    add(default_part, "BEVEL", limit_method="WEIGHT", width=1 * F, segments=3, use_clamp_overlap=clamp)
    holes, after = stats(default_part)
    removed = before - after
    estimate = sharp_length_mm(default_part) * (1 - math.pi / 4)  # a 1 mm round along every sharp edge
    assert holes == 0
    assert 0.8 * estimate < removed < 1.1 * estimate  # not clamped to nothing by short chords
    assert set(face_ids(evaluated(default_part)).tolist()) == set(range(9))


@pytest.mark.parametrize("kind, settings", [
    ("WEIGHTED_NORMAL", {}),
    ("TRIANGULATE", {}),
])
def test_modifiers_that_keep_the_shape(default_part, kind, settings):
    _, before = stats(default_part)
    add(default_part, kind, **settings)
    holes, after = stats(default_part)
    assert holes == 0 and after == pytest.approx(before, rel=1e-6)
    assert part.face_id(evaluated(default_part), hit_polygon(default_part, 5, 25)) == top_face_id(default_part)


def test_edge_split_splits_exactly_the_sharp_edges(default_part):
    sharp = np.empty(len(default_part.data.edges), bool)
    default_part.data.attributes["sharp_edge"].data.foreach_get("value", sharp)
    add(default_part, "EDGE_SPLIT", use_edge_angle=False, use_edge_sharp=True)
    holes, _ = stats(default_part)
    assert holes == 2 * sharp.sum()  # each split edge becomes two open edges


def test_solidify_array_subdivision(default_part):
    _, before = stats(default_part)
    solidify = add(default_part, "SOLIDIFY", thickness=2 * F)
    holes, shell = stats(default_part)
    assert holes == 0 and 0 < shell < before
    default_part.modifiers.remove(solidify)
    array = add(default_part, "ARRAY", count=2)
    holes, doubled = stats(default_part)
    assert holes == 0 and doubled == pytest.approx(2 * before, rel=1e-6)
    default_part.modifiers.remove(array)
    add(default_part, "SUBSURF", levels=1)
    holes, smoothed = stats(default_part)
    assert holes == 0 and 0.5 * before < smoothed < before
    assert part.face_id(evaluated(default_part), hit_polygon(default_part, 5, 25)) == top_face_id(default_part)


# -- picking: Draw Solid's plane on a part with modifiers ------------------------------------------------------

@pytest.mark.parametrize("kind, settings", [
    ("BEVEL", {"limit_method": "WEIGHT", "width": 1 * F}),
    ("SOLIDIFY", {"thickness": 2 * F}),  # grows inwards: the outer top face stays where it was
    ("WEIGHTED_NORMAL", {}),
])
def test_a_face_the_modifier_leaves_in_place_keeps_its_exact_plane(default_part, kind, settings):
    add(default_part, kind, **settings)
    bpy.context.view_layer.update()
    plane, target, local = pick_down(5, 25)
    assert target == default_part and local is not None
    assert local.z == (0.0, 0.0, 1.0) and local.origin[2] == 20.0


def test_a_face_the_modifier_moved_gets_a_plane_through_the_hit(default_part):
    # An Array copy stacked on top: its top face comes from the part's top face (same id) but lies 37.5 mm
    # higher. The exact plane (z = 20 mm) would put a drawing inside the copy: the plane goes through the hit.
    add(default_part, "ARRAY", count=2, relative_offset_displace=(0.0, 0.0, 1.5))
    bpy.context.view_layer.update()
    plane, target, local = pick_down(5, 25)
    assert target == default_part and local is None
    assert plane.translation.z / F == pytest.approx(20 + 1.5 * 25, abs=1e-3)
    assert (plane.col[2].xyz - Vector((0, 0, 1))).length < 1e-6


def test_linked_duplicates_pick_on_their_own_modifiers(default_part):
    twin = default_part.copy()  # shares the mesh (Alt+D)
    bpy.context.collection.objects.link(twin)
    twin.location = (0.1, 0.0, 0.0)
    add(twin, "ARRAY", count=2, relative_offset_displace=(0.0, 0.0, 1.5))
    bpy.context.view_layer.update()
    assert pick_down(5, 25)[2] is not None           # the original: no modifier, exact plane
    plane, _, local = pick_down(105, 25)              # the twin, 100 mm to the right: its Array copy on top
    assert local is None and plane.translation.z / F == pytest.approx(57.5, abs=1e-3)


def test_far_from_the_origin_the_exact_plane_is_kept(default_part):
    # Review finding: float32 hits drift by ~4e-3 mm at 50 m; an absolute 1e-3 mm check rejected most of them and
    # fell back to the float32 plane (skins and slivers in booleans).
    for modifier in (None, "WEIGHTED_NORMAL"):
        if modifier:
            add(default_part, modifier)
        default_part.location = (50.0, 30.0, 20.0)
        default_part.rotation_euler = (0.4, 0.3, 0.2)  # the top face tilted: every coordinate of a hit is large
        bpy.context.view_layer.update()
        normal = (default_part.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
        misses = 0
        for k in range(40):
            local = Vector((2.0 + k * 0.4, 25.0 + (k % 7) * 0.5, 20.0)) * F
            world = default_part.matrix_world @ local
            _, _, got = ops_draw.pick(bpy.context, world + normal * 0.5, -normal)
            misses += got is None
        assert misses == 0, modifier
