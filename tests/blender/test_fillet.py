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


def test_edges_between_tangent_faces_are_not_sharp(clean):
    # the Fillet tool refuses a click on them (nothing to round: research on fillet edge cases, T10)
    import numpy as np
    from blendsolid import picking
    obj = part.new_part(bpy.context)  # the fillet_1 band meets the box's sides tangentially
    wait_for(lambda: up_to_date(obj))
    me = obj.data
    ids = np.empty(len(me.edges), np.int32)
    me.attributes[part.EDGE_ATTR].data.foreach_get("value", ids)
    sharp = np.empty(len(me.edges), bool)
    me.attributes["sharp_edge"].data.foreach_get("value", sharp)
    smooth = {int(i) for i in ids[(ids >= 0) & ~sharp]}
    hard = {int(i) for i in ids[(ids >= 0) & sharp]}
    assert len(smooth) == 2 and hard  # the two vertical edges of the fillet band
    assert not any(picking.edge_is_sharp(obj, e) for e in smooth) and all(picking.edge_is_sharp(obj, e) for e in hard)


def test_reference_warnings_reach_the_part(clean):
    source = ("with BuildPart() as part:\n    Box(40, 30, 20)  # feature: box_1\n"
              "    with Locations((0, 0, 10)):  # feature: groove_1\n"
              "        Box(10, 40, 10, mode=Mode.SUBTRACT)\n"
              '    fillet(edges_of(face("box_1", "+Z")), radius=1)  # feature: fillet_1\nresult = part.part\n')
    obj = part.new_part(bpy.context, source)
    wait_for(lambda: up_to_date(obj))
    assert not obj.blendsolid_error
    assert [(line, text.split(" now ")[0]) for line, text in part.warnings(obj)] == [(5, "face box_1 +Z")]
    obj.blendsolid_script.from_string(source.replace('face("box_1", "+Z")', 'face("box_1", "-Z")'))
    wait_for(lambda: up_to_date(obj))
    assert part.warnings(obj) == []


@pytest.fixture
def plain_box(clean):
    obj = part.new_part(bpy.context, "with BuildPart() as part:\n"
                                     "    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n"
                                     "result = part.part\n")
    wait_for(lambda: up_to_date(obj))
    return obj


def has_vertex(obj, y_mm, z_mm, x_mm=20):
    """A mesh vertex at (x, y, z) mm (by default at the box's end x = 20 mm)."""
    return any((v.co - Vector((x_mm * F, y_mm * F, z_mm * F))).length < 1e-4 * F for v in obj.data.vertices)


@pytest.mark.parametrize("mode, flip, removed, on_top, on_front", [
    ("TWO", False, 0.5 * 2 * 4 * 40, 2, 4),        # 2 mm along the top (+Z, the first face), 4 mm down the front
    ("TWO", True, 0.5 * 2 * 4 * 40, 4, 2),         # Flip: the first length on the other face
    ("ANGLE", False, 0.5 * 2 * 2 * math.tan(math.radians(30)) * 40, 2, 2 * math.tan(math.radians(30))),
    ("ANGLE", True, 0.5 * 2 * 2 * math.tan(math.radians(30)) * 40, 2 * math.tan(math.radians(30)), 2),
])
def test_asymmetric_chamfers(plain_box, mode, flip, removed, on_top, on_front):
    # Fusion 360 / Onshape's chamfer types: two distances, or a distance and the angle to the first face; the
    # first face is the edge's first face in its reference, Flip takes the other one.
    v0 = mm3(plain_box)
    assert bpy.ops.blendsolid.fillet(target=plain_box.name, references=TOP_FRONT, radius=2.0, chamfer=True,
                                     chamfer_mode=mode, length2=4.0, angle=30.0, flip=flip) == {"FINISHED"}
    source = part.source_of(plain_box)
    side = 'face("box_1", "-Y")' if flip else 'face("box_1", "+Z")'
    assert f"reference={side})" in source
    wait_for(lambda: up_to_date(plain_box))
    assert plain_box.blendsolid_error == ""
    assert v0 - mm3(plain_box) == pytest.approx(removed, rel=1e-6)
    assert has_vertex(plain_box, -15 + on_top, 20) and has_vertex(plain_box, -15, 20 - on_front)


def test_asymmetric_chamfer_of_a_face_flips_by_swapping(plain_box):
    # every edge of the top face: the top is the only face they all lie on, so Flip swaps the two distances
    assert bpy.ops.blendsolid.fillet(target=plain_box.name, references='edges_of(face("box_1", "+Z"))', radius=1.0,
                                     chamfer=True, chamfer_mode="TWO", length2=3.0, flip=True) == {"FINISHED"}
    assert "chamfer_1_length = 3" in part.source_of(plain_box)
    wait_for(lambda: up_to_date(plain_box))
    assert plain_box.blendsolid_error == ""
    assert has_vertex(plain_box, -15 + 3, 20, 20 - 3) and has_vertex(plain_box, -15, 20 - 1)  # the corners
    with pytest.raises(RuntimeError):  # a distance and an angle can't be flipped that way
        bpy.ops.blendsolid.fillet(target=plain_box.name, references='edges_of(face("box_1", "-Z"))', radius=1.0,
                                  chamfer=True, chamfer_mode="ANGLE", flip=True)


def test_asymmetric_chamfer_needs_a_common_face(plain_box):
    other = 'edge_between(face("box_1", "-Z"), face("box_1", "+Y"))'
    with pytest.raises(RuntimeError):
        bpy.ops.blendsolid.fillet(target=plain_box.name, references=f"{TOP_FRONT}\n{other}", radius=1.0,
                                  chamfer=True, chamfer_mode="TWO")
    assert "chamfer(" not in part.source_of(plain_box)


def test_a_failing_fillet_blocks_new_features_and_shows_in_the_viewport(clean):
    """test6.blend (maintainer, 2026-09-30): a fillet too large failed, and every feature added after it was never
    built (and was picked on the stale mesh). Now the part says which feature fails, and nothing can be added."""
    from blendsolid import ops_fillet, ui
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    obj = bpy.context.object
    wait_for(lambda: up_to_date(obj))
    bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target=obj.name, references='edges_of(face("box_1", "+Z"))',
                              radius=50.0)
    wait_for(lambda: obj.blendsolid_error != "")
    assert part.failing_feature(obj) == "fillet_1"
    limit = ops_fillet.too_large_limit(obj.blendsolid_error)
    assert limit is not None and 0 < limit < 20  # the box is 20 mm tall
    lines = ui.error_label(obj)
    assert lines[0] == f"{obj.name}: fillet_1 fails" and "too large" in " ".join(lines)
    blocked = part.blocking_error(obj)
    assert "fillet_1 fails" in blocked and "before adding features" in blocked
    source = part.source_of(obj)
    with pytest.raises(RuntimeError, match="fillet_1 fails"):
        bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target=obj.name,
                                  references='edge_between(face("box_1", "+X"), face("box_1", "+Y"))', radius=1.0)
    with pytest.raises(RuntimeError, match="fillet_1 fails"):
        bpy.ops.blendsolid.push_pull("EXEC_DEFAULT", True, target=obj.name, reference='face("box_1", "+X")',
                                     amount=5.0)
    assert part.source_of(obj) == source
    # changing the failing feature's own radius is allowed and clears it
    obj.blendsolid_script.from_string(source.replace("fillet_1_radius = 50.0", f"fillet_1_radius = {limit}"))
    wait_for(lambda: up_to_date(obj))
    assert obj.blendsolid_error == "" and part.blocking_error(obj) is None and ui.error_label(obj) == []


@pytest.mark.parametrize("why", ["scaled", "untrusted"])
def test_the_fillet_tool_leaves_parts_it_cannot_edit_alone(default_part, monkeypatch, why):
    # picking only checked "local part": the tool took a scaled or untrusted part, the release's operator call
    # raised (scaled), or wrote a fillet that never computes (untrusted, ADR 0004) — bug sweep, 2026-10-04
    from types import SimpleNamespace

    from blendsolid import ops_fillet, trust
    if why == "scaled":
        default_part.scale = (2.0, 1.0, 1.0)
        bpy.context.view_layer.update()
    else:
        monkeypatch.setattr(trust, "_file_trusted", False)
        monkeypatch.setattr(trust, "_trusted_texts", set())
    edge = 'edge_between(face("box_1", "+Z"), face("box_1", "-Y"))'
    source = part.source_of(default_part)
    if why == "untrusted":
        assert picking.pick(bpy.context, *down(30, 0.3), PIXEL) is None
        with pytest.raises(RuntimeError, match="not trusted"):
            bpy.ops.blendsolid.fillet(target=default_part.name, references=edge, radius=1.0)
        assert part.source_of(default_part) == source
    # an edge selected before the part became uneditable: the drag's release is refused, the drag ends cleanly
    monkeypatch.setitem(ops_fillet._selection, "part", default_part.name)
    monkeypatch.setitem(ops_fillet._selection, "refs", [edge])
    cls = ops_fillet.BLENDSOLID_OT_fillet_click
    op = SimpleNamespace(_source=source, _radius=1.0, _chamfer=False, _timer=None,
                         _handles=[], _restore=lambda: None)
    op._end = lambda context, result: cls._end(op, context, result)
    ops_fillet._dragging.add(id(op))
    event = SimpleNamespace(type="LEFTMOUSE", value="RELEASE", ctrl=False, shift=False)
    assert cls.modal(op, bpy.context, event) == {"CANCELLED"}
    assert not ops_fillet._dragging and part.source_of(default_part) == source


def test_a_new_chamfer_starts_equal(default_part):
    # the chamfer's Type, Length 2, Angle and Flip were kept from the last call (Blender reuses an operator's last
    # values): a drag after one Two Distances chamfer wrote another, unlike its preview (bug sweep, 2026-10-04)
    top = 'edge_between(face("box_1", "+Z"), face("box_1", "-Y"))'
    side = 'edge_between(face("box_1", "+X"), face("box_1", "-Y"))'
    assert bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target=default_part.name, references=top, radius=1.0,
                                     chamfer=True, chamfer_mode="TWO", length2=3.0) == {"FINISHED"}
    assert bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target=default_part.name, references=side, radius=1.5,
                                     chamfer=True) == {"FINISHED"}  # as the tool's release calls it
    last = [line for line in part.source_of(default_part).splitlines() if "chamfer(" in line][-1]
    assert "length2" not in last and "angle" not in last, last
