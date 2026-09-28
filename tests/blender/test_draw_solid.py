"""Tool 2 without the mouse: the drawing geometry and the operator's execute() (what the modal ends with and
what Blender's redo re-runs). The interactive part is in the manual GUI test."""
import math

import bpy
import pytest
from mathutils import Euler, Matrix, Vector

from blendsolid import drawing, ops_draw, part, script_model
from conftest import mm3, up_to_date, wait_for

F = 0.001  # unit factor of the default (metre) scene: 1 mm = 0.001 Blender units


def box_part(location=(0, 0, 0), rotation=(0, 0, 0)):
    bpy.context.scene.cursor.location, bpy.context.scene.cursor.rotation_euler = location, rotation
    bpy.ops.blendsolid.add_box(length=40, width=30, height=20)  # x -20..20, y -15..15, z 0..20 mm
    bpy.context.scene.cursor.location, bpy.context.scene.cursor.rotation_euler = (0, 0, 0), (0, 0, 0)
    obj = bpy.context.view_layer.objects.active
    bpy.context.view_layer.update()
    return obj


# -- geometry ---------------------------------------------------------------------------------------------------

def test_plane_on_the_top_face_follows_the_part_axes():
    obj_matrix = Matrix.Translation((1, 2, 3)) @ Euler((0, 0, math.radians(30))).to_matrix().to_4x4()
    normal = Vector((0.0, 1e-6, 1.0)).normalized()  # float32 noise from the tessellation
    plane = drawing.plane_on_face((1, 2, 3.02), normal, obj_matrix)
    assert plane.col[2].xyz == Vector((0, 0, 1))                       # snapped to the part's Z exactly
    assert (plane.col[0].xyz - obj_matrix.col[0].xyz).length < 1e-9      # the part's X
    assert (plane.translation - Vector((1, 2, 3.02))).length < 1e-9
    _, rotation = drawing.placement(plane, obj_matrix, F)
    assert rotation == pytest.approx((0, 0, 0), abs=1e-9)             # "a top face gives a rotation of zero"


def test_plane_on_a_side_face_uses_the_part_y_axis():
    plane = drawing.plane_on_face((0.02, 0, 0.01), (1, 0, 0), Matrix.Identity(4))
    assert plane.col[2].xyz == Vector((1, 0, 0)) and plane.col[0].xyz == Vector((0, 1, 0))


def test_plane_at_cursor():
    cursor = Matrix.Translation((0, 0, 1)) @ Euler((math.radians(90), 0, 0)).to_matrix().to_4x4()
    plane = drawing.plane_at_cursor(cursor)
    assert (plane.col[2].xyz - Vector((0, -1, 0))).length < 1e-6 and plane.translation == Vector((0, 0, 1))


def test_mouse_ray_to_plane_coordinates_and_height():
    plane = drawing.plane_at_cursor(Matrix.Identity(4))
    assert drawing.plane_coords(plane, (0.3, -0.2, 5), (0, 0, -1)) == pytest.approx((0.3, -0.2))
    assert drawing.plane_coords(plane, (0, 0, 5), (1, 0, 0)) is None     # parallel to the plane
    center = Vector((0.1, 0, 0))
    assert drawing.height_along_normal(plane, center, (5, 0, 0.25), (-1, 0, 0)) == pytest.approx(0.25)
    assert drawing.height_along_normal(plane, center, (5, 0, -0.1), (-1, 0, 0)) == pytest.approx(-0.1)


def test_drawn_box_and_cylinder_with_snapping():
    plane = drawing.plane_at_cursor(Matrix.Identity(4))
    box = drawing.drawn_solid("BOX", plane, (0.0, 0.0), (0.0402, -0.0198), 0.0101, F, step_mm=1.0)
    assert (box.length, box.width, box.height) == pytest.approx((40.0, 20.0, 10.0))
    assert (box.frame.translation - Vector((0.020, -0.010, 0))).length < 1e-9
    cyl = drawing.drawn_solid("CYLINDER", plane, (0.01, 0.0), (0.013, 0.004), -0.005, F)
    assert (cyl.radius, cyl.height) == pytest.approx((5.0, -5.0))
    assert (cyl.frame.translation - Vector((0.01, 0, 0))).length < 1e-9


def test_snap_steps_ladder():
    assert drawing.STEPS[0] == 0.1 and 1.0 in drawing.STEPS and drawing.STEPS[-1] == 10000.0
    assert drawing.next_step(1.0, +1) == 2.0 and drawing.next_step(1.0, -1) == 0.5
    assert drawing.next_step(drawing.STEPS[-1], +1) == drawing.STEPS[-1]    # clamped at both ends
    assert drawing.next_step(drawing.STEPS[0], -1) == drawing.STEPS[0]


def test_grid_on_a_face_starts_at_the_part_origin():
    # The grid of a face is the part's own: its origin projected onto the face, whatever point was hit.
    obj_matrix = Matrix.Translation((1, 2, 3)) @ Euler((0, 0, math.radians(30))).to_matrix().to_4x4()
    hit = obj_matrix @ Vector((0.0123, -0.0071, 0.02))
    plane = drawing.plane_on_face(hit, obj_matrix.to_3x3() @ Vector((0, 0, 1)), obj_matrix)
    assert (plane.translation - obj_matrix @ Vector((0, 0, 0.02))).length < 1e-9


def test_plane_on_a_curved_face_follows_the_surface_without_jumps():
    # Maintainer's GUI check: on a cone's side the grid turned about the snap cross as the mouse moved, because
    # the plane X was the part's X projected on the tangent plane, switching to its Y past |n.x| = 0.9. On a
    # curved face X is the horizontal tangent (part Z x normal), Y goes up the surface: continuous all around.
    obj_matrix = Matrix.Translation((1, 2, 3)) @ Euler((0, 0, math.radians(30))).to_matrix().to_4x4()
    rot = obj_matrix.to_3x3()
    previous = None
    for deg in range(0, 361, 2):
        a = math.radians(deg)
        n = rot @ Vector((math.cos(a), math.sin(a), 0.45)).normalized()  # a cone's side
        hit = obj_matrix @ Vector((0.01 * math.cos(a), 0.01 * math.sin(a), 0.005))
        plane = drawing.plane_on_curved_face(hit, n, obj_matrix)
        x, y = plane.col[0].xyz, plane.col[1].xyz
        assert (plane.col[2].xyz - n).length < 1e-6
        assert abs(x.dot(rot.col[2])) < 1e-6                   # horizontal in the part's frame
        assert y.dot(rot.col[2]) > 0                           # up the surface
        if previous is not None:
            assert x.angle(previous) < math.radians(3)         # no jumps between neighbouring points
        previous = x
    # On a flat-ish spot facing the part's Z (a pole) there is no horizontal tangent: the flat-face rule.
    top = drawing.plane_on_curved_face(obj_matrix.translation, rot.col[2], obj_matrix)
    assert (top.col[0].xyz - rot.col[0]).length < 1e-6


def test_snapping_puts_box_corners_and_cylinder_centre_on_grid_nodes():
    plane = drawing.plane_at_cursor(Matrix.Identity(4))
    box = drawing.drawn_solid("BOX", plane, (0.0123, 0.0071), (0.0348, 0.0269), 0.0, F, step_mm=10.0)
    assert (box.length, box.width) == pytest.approx((20.0, 20.0))       # corners (10, 10) and (30, 30) mm
    assert (box.frame.translation - Vector((0.020, 0.020, 0))).length < 1e-9
    cyl = drawing.drawn_solid("CYLINDER", plane, (0.0123, -0.0071), (0.0283, -0.0071), 0.0, F, step_mm=10.0)
    assert cyl.radius == pytest.approx(20.0)                              # 16 mm rounded to the 10 mm step
    assert (cyl.frame.translation - Vector((0.010, -0.010, 0))).length < 1e-9
    assert drawing.grid_node(plane, (0.0123, -0.0071), F, 10.0) == pytest.approx((0.010, -0.010))


def test_euler_zyx_matches_mathutils_in_float64():
    for angles in [(0.1, 0.2, 0.3), (-1.2, 0.7, 2.9), (math.pi, 0, 0), (0, math.pi / 2, math.pi / 2), (0.3, -1.1, -2.0)]:
        m = Euler(angles, "ZYX").to_matrix()
        cols = [tuple(m.col[i]) for i in range(3)]
        back = Euler(drawing.euler_zyx(*cols), "ZYX").to_matrix()  # the same rotation (angles may differ)
        assert all((back.col[i] - m.col[i]).length < 1e-6 for i in range(3))
    # exact axes give exact angles (mathutils' float32 would give 180.000005 degrees)
    assert drawing.euler_zyx((1, 0, 0), (0, -1, 0), (0, 0, -1)) == (math.pi, 0.0, 0.0)


def test_plane_on_a_part_face_is_exact():
    top = drawing.plane_on_part_face((0.0, 0.0, 1.0), 130.0)
    assert top.origin == (0.0, 0.0, 130.0) and top.x == (1.0, 0.0, 0.0) and top.z == (0.0, 0.0, 1.0)
    side = drawing.plane_on_part_face((1.0, 0.0, 0.0), 20.0)
    location, rotation = drawing.placement_local(side.moved(5.0, -7.5))
    assert location == (20.0, 5.0, -7.5)
    assert all(math.degrees(a) % 90.0 == 0.0 for a in rotation)


def test_placement_round_trip():
    frame = Matrix.Translation((0.01, 0.02, 0.03)) @ Euler((0.1, 0.2, 0.3), "ZYX").to_matrix().to_4x4()
    location, rotation = drawing.placement(frame, None, F)
    assert location == pytest.approx((10, 20, 30))
    back = drawing.frame_matrix(location, rotation, F)
    assert all(abs(back[i][j] - frame[i][j]) < 1e-6 for i in range(4) for j in range(4))


def test_preview_lines_outline_the_solid():
    plane = drawing.plane_at_cursor(Matrix.Identity(4))
    box = drawing.drawn_solid("BOX", plane, (0, 0), (0.04, 0.02), 0.01, F)
    lines = drawing.preview_lines(box, F)
    assert len(lines) == 12  # base, top, 4 verticals
    zs = sorted({round(p.z, 9) for line in lines for p in line})
    assert zs == [0.0, 0.01]


# -- the operator ---------------------------------------------------------------------------------------------------

def test_new_part_on_the_grid(clean):
    assert bpy.ops.blendsolid.draw_solid(shape="BOX", mode="NEW", location=(10, 20, 0), rotation=(0, 0, 0),
                                         length=40, width=30, height=20) == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    assert obj.name == "Box" and (obj.matrix_world.translation - Vector((0.01, 0.02, 0))).length < 1e-7
    wait_for(lambda: up_to_date(obj))
    assert abs(mm3(obj) - 24000) < 50


def test_cut_into_the_top_face(clean):
    box = box_part()
    assert bpy.ops.blendsolid.draw_solid(shape="CYLINDER", mode="CUT", target=box.name, location=(5, 5, 20),
                                         rotation=(0, 0, 0), radius=3, height=5) == {"FINISHED"}
    feats = script_model.features(part.source_of(box))
    assert [(f.name, f.kind, f.mode) for f in feats] == [("box_1", "box", "ADD"), ("cut_1", "cylinder", "SUBTRACT")]
    assert feats[1].location == (5.0, 5.0, 20.0) and feats[1].align == ("CENTER", "CENTER", "MAX")
    wait_for(lambda: up_to_date(box))
    expected = 40 * 30 * 20 - math.pi * 9 * 5
    assert abs(mm3(box) - expected) / expected < 0.01


def test_union_on_the_top_face(clean):
    box = box_part()
    bpy.ops.blendsolid.draw_solid(shape="BOX", mode="UNION", target=box.name, location=(0, 0, 20),
                                  rotation=(0, 0, 0), length=10, width=10, height=5)
    assert script_model.features(part.source_of(box))[1].name == "box_2"
    wait_for(lambda: up_to_date(box))
    assert abs(mm3(box) - (24000 + 500)) < 20


@pytest.mark.parametrize("up, mode, expected", [(True, "UNION", 24000 + math.pi * 16 * 6),
                                                 (False, "CUT", 24000 - math.pi * 16 * 6)])
def test_drag_on_a_rotated_part_face(clean, up, mode, expected):
    """The whole pipeline minus the mouse: hit on the top face of a moved and rotated part, drag a circle,
    pull up or push down, then the operator with the resulting properties."""
    box = box_part(location=(0.5, 0.2, 0.0), rotation=(0, 0, math.radians(30)))
    top_center = box.matrix_world @ Vector((0.005, 0.0, 0.020))
    plane = drawing.plane_on_face(top_center, box.matrix_world.to_3x3() @ Vector((0, 0, 1)), box.matrix_world)
    u, v = drawing.plane_coords(plane, top_center + plane.col[2].xyz, -plane.col[2].xyz)  # the grid is the part's
    drawn = drawing.drawn_solid("CYLINDER", plane, (u, v), (u + 0.004, v), 0.006 if up else -0.006, F)
    props = ops_draw.drawn_properties(drawn, box, F)
    assert props["mode"] == mode and props["target"] == box.name
    assert props["location"] == pytest.approx((5, 0, 20), abs=1e-4)
    assert props["rotation"] == pytest.approx((0, 0, 0), abs=1e-6)
    assert bpy.ops.blendsolid.draw_solid(**props) == {"FINISHED"}
    wait_for(lambda: up_to_date(box))
    assert abs(mm3(box) - expected) / expected < 0.01


def test_drag_down_on_the_grid_makes_a_part_below(clean):
    plane = drawing.plane_at_cursor(Matrix.Identity(4))
    drawn = drawing.drawn_solid("BOX", plane, (0.0, 0.0), (0.01, 0.01), -0.01, F)
    props = ops_draw.drawn_properties(drawn, None, F)
    assert props["mode"] == "NEW" and props["height"] == pytest.approx(10)
    bpy.ops.blendsolid.draw_solid(**props)
    obj = bpy.context.view_layer.objects.active
    wait_for(lambda: up_to_date(obj))
    zs = [(obj.matrix_world @ v.co).z for v in obj.data.vertices]
    assert min(zs) == pytest.approx(-0.01, abs=1e-6) and max(zs) == pytest.approx(0.0, abs=1e-6)


def test_redo_can_switch_cut_to_union(clean):
    box = box_part()
    before = part.source_of(box)
    bpy.ops.ed.undo_push(message="before")
    kwargs = dict(shape="CYLINDER", target=box.name, location=(0, 0, 20), rotation=(0, 0, 0), radius=3, height=5)
    bpy.ops.blendsolid.draw_solid("EXEC_DEFAULT", True, mode="CUT", **kwargs)
    bpy.ops.ed.undo()
    box = bpy.data.objects["Box"]
    assert part.source_of(box) == before
    bpy.ops.blendsolid.draw_solid("EXEC_DEFAULT", True, mode="UNION", **kwargs)
    box = bpy.data.objects["Box"]
    assert [f.name for f in script_model.features(part.source_of(box))] == ["box_1", "cylinder_1"]


def test_errors_are_reported_not_raised_into_the_scene(clean):
    with pytest.raises(RuntimeError, match="need the part"):
        bpy.ops.blendsolid.draw_solid(mode="CUT")
    with pytest.raises(RuntimeError, match="no BlendSolid part named"):
        bpy.ops.blendsolid.draw_solid(mode="UNION", target="Nothing")
    box = box_part()
    box.blendsolid_script.from_string("size = 10.0\nresult = Box(size, size, size)\n")
    with pytest.raises(RuntimeError, match="the tools can't add features"):
        bpy.ops.blendsolid.draw_solid(mode="UNION", target=box.name)


def test_millimetre_scene(clean):
    units = bpy.context.scene.unit_settings
    saved = units.scale_length
    units.scale_length = 0.001  # 1 Blender unit = 1 mm: the placement numbers stay millimetres
    try:
        bpy.ops.blendsolid.draw_solid(shape="BOX", mode="NEW", location=(10, 20, 0), rotation=(0, 0, 0),
                                      length=40, width=30, height=20)
        box = bpy.context.view_layer.objects.active
        assert (box.matrix_world.translation - Vector((10, 20, 0))).length < 1e-5
        bpy.context.view_layer.update()
        bpy.ops.blendsolid.draw_solid(shape="CYLINDER", mode="CUT", target=box.name, location=(5, 5, 20),
                                      rotation=(0, 0, 0), radius=3, height=5)
        wait_for(lambda: up_to_date(box))
        expected = 40 * 30 * 20 - math.pi * 9 * 5
        assert abs(mm3(box) - expected) / expected < 0.01
        plane = drawing.plane_on_face(box.matrix_world @ Vector((5, 5, 20)), (0, 0, 1), box.matrix_world)
        assert drawing.plane_coords(plane, (15, 25, 30), (0, 0, -1)) == pytest.approx((5, 5))  # the part's grid
        drawn = drawing.drawn_solid("BOX", plane, (5, 5), (9, 7), 3, part.unit_factor())
        assert (drawn.length, drawn.width, drawn.height) == pytest.approx((4, 2, 3))  # 1 unit = 1 mm
        props = ops_draw.drawn_properties(drawn, box, part.unit_factor())
        assert props["mode"] == "UNION" and props["target"] == box.name
        assert props["location"] == pytest.approx((7, 6, 20), abs=1e-4)  # millimetres, in the part's frame
    finally:
        units.scale_length = saved


def test_exact_placement_is_used_until_edited_by_hand(clean):
    import json
    box = box_part()
    exact = json.dumps({"location": [0.0, 0.0, 33.333333], "rotation": [math.pi, 0.0, 0.0]})
    common = dict(shape="BOX", mode="CUT", target=box.name, length=10, width=10, height=5, exact=exact)
    bpy.ops.blendsolid.draw_solid(location=(0.0, 0.0, 33.333333), rotation=(math.pi, 0.0, 0.0), **common)
    line = [ln for ln in part.source_of(box).splitlines() if "cut_1" in ln and "Location" in ln][0]
    assert "(0.0, 0.0, 33.333333), (180.0, 0.0, 0.0)" in line   # float32 would give 33.333332 and 180.000005
    bpy.ops.blendsolid.draw_solid(location=(1.0, 0.0, 33.333333), rotation=(math.pi, 0.0, 0.0), **common)
    line = [ln for ln in part.source_of(box).splitlines() if "cut_2" in ln and "Location" in ln][0]
    assert "(1.0, 0.0, 33.333332" in line                          # edited by hand: the typed values win


# -- snap feedback: axis colours, local grid, height ticks, labels (maintainer's request, manual GUI test) ------

AXES = ((1.0, 0.2, 0.3), (0.5, 0.8, 0.1), (0.2, 0.5, 1.0))  # like Blender's theme axis_x / axis_y / axis_z


def test_axis_color_mixes_the_axis_colours_by_direction():
    assert drawing.axis_color(Vector((1, 0, 0)), AXES)[:3] == pytest.approx(AXES[0])
    assert drawing.axis_color(Vector((0, 0, -2)), AXES)[:3] == pytest.approx(AXES[2])  # sign and length ignored
    d = Vector((1, 0, 1)).normalized()                                                     # 45 degrees in XZ
    assert drawing.axis_color(d, AXES)[:3] == pytest.approx([(a + b) / 2 for a, b in zip(AXES[0], AXES[2])])


def test_marker_arms_are_coloured_by_their_world_axis():
    front = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))  # a -Y face: X and Z in it
    lines = drawing.marker_lines(Vector((0, 0, 0)), front, 0.5, AXES)
    colours = sorted(tuple(round(c, 6) for c in colour[:3]) for _, _, colour in lines)
    assert len(lines) == 5  # +-u, +-v and the normal stub
    assert colours.count(AXES[0]) == 2 and colours.count(AXES[2]) == 2 and colours.count(AXES[1]) == 1
    stub = [(a, b) for a, b, colour in lines if tuple(round(c, 6) for c in colour[:3]) == AXES[1]][0]
    assert (stub[1] - stub[0]).normalized() == Vector((0, -1, 0))  # along the face normal, out of it


def test_grid_is_drawn_on_the_plane_through_the_snap_nodes_and_fades():
    plane = Matrix.Translation((0, 0, 0.02)) @ Euler((0, 0, math.radians(30))).to_matrix().to_4x4()
    step = 0.01
    segments = drawing.grid_segments(plane, (0.03, -0.02), step, half=4)
    ax, ay, n, o = plane.col[0].xyz, plane.col[1].xyz, plane.col[2].xyz, plane.translation
    for a, b, alpha_a, alpha_b, major in segments:
        for p in (a, b):
            assert abs((p - o).dot(n)) < 1e-6                                   # on the plane (float32)
        u0, v0, u1, v1 = (a - o).dot(ax), (a - o).dot(ay), (b - o).dot(ax), (b - o).dot(ay)
        on_u_line = abs(u0 - u1) < 1e-6
        k = (u0 if on_u_line else v0) / step
        assert abs(k - round(k)) < 1e-6                                         # through grid nodes
        assert major == (round(k) % 5 == 0)                                      # every 5th line is major
        assert 0.0 <= alpha_a <= 1.0 and 0.0 <= alpha_b <= 1.0
    # the brightest point is the node under the mouse; the grid fades out at `half` steps from it
    centre = o + ax * 0.03 + ay * -0.02
    assert max(max(s[2], s[3]) for s in segments) == pytest.approx(1.0)
    far = [alpha for a, b, alpha_a, alpha_b, _ in segments for p, alpha in ((a, alpha_a), (b, alpha_b))
           if (p - centre).length >= 4 * step - 1e-9]
    assert far and max(far) == pytest.approx(0.0)


def test_grid_step_on_screen():
    assert drawing.visible_grid_step(0.01, 0.001) == 0.01            # 10 px a cell: every line
    assert drawing.visible_grid_step(0.01, 0.004) == pytest.approx(0.05)  # 2.5 px: only the major lines
    assert drawing.visible_grid_step(0.01, 0.1) is None                # too dense even for the major lines


def test_height_ticks_along_the_normal_every_step():
    frame = Matrix.Translation((0.1, 0, 0))
    ticks = drawing.height_ticks(frame, -0.023, 0.01, tick=0.002, half=3)
    heights = sorted({round((a - frame.translation).dot(Vector((0, 0, 1))), 9) for a, _, _ in ticks})
    assert heights == pytest.approx([-0.05, -0.04, -0.03, -0.02, -0.01, 0.0, 0.01])  # around -0.02, the nearest
    for a, b, alpha in ticks:
        assert (b - a).length == pytest.approx(0.002, abs=1e-6) and abs((b - a).dot(Vector((0, 0, 1)))) < 1e-9


def test_labels_while_drawing():
    box = drawing.Drawn("BOX", Matrix.Identity(4), length=250.0, width=300.5, height=-50.0)
    assert drawing.labels(box, "BASE", 10.0) == ["250 × 300.5 mm", "snap 10 mm"]
    assert drawing.labels(box, "HEIGHT", 0.0) == ["H 50 mm"]
    cyl = drawing.Drawn("CYLINDER", Matrix.Identity(4), radius=12.3456)
    assert drawing.labels(cyl, "BASE", 0.0) == ["R 12.346 mm"]


def test_hovering_around_a_cone_turns_the_grid_smoothly(clean):
    bpy.ops.blendsolid.add_cone()  # bottom radius 10, top radius 5, height 20 mm
    obj = bpy.context.view_layer.objects.active
    wait_for(lambda: up_to_date(obj))
    bpy.context.view_layer.update()
    previous = None
    for tenth in range(0, 3601, 5):  # every half degree around the side, at mid height
        a = math.radians(tenth / 10)
        d = Vector((math.cos(a), math.sin(a), 0))
        plane, target, local = ops_draw.pick(bpy.context, Vector((0, 0, 0.01)) + d * 0.1, -d)
        assert target == obj and local is None
        n, x = plane.col[2].xyz, plane.col[0].xyz
        exact = Vector((20 * math.cos(a), 20 * math.sin(a), 5)).normalized()  # the cone's own normal
        # The vertex normals interpolated across a triangle: within 1.4 degrees of the surface's (measured at
        # mid height, the default 1 mm tolerance's triangles); a triangle's own normal was up to 6 degrees off.
        assert n.angle(exact) < math.radians(2.0)
        assert abs(x.z) < 1e-5
        if previous is not None:
            assert x.angle(previous[0]) < math.radians(1.5) and n.angle(previous[1]) < math.radians(1.5)
        previous = x, n
    # The flat top still gets its exact plane.
    plane, target, local = ops_draw.pick(bpy.context, Vector((0.002, 0.001, 1)), Vector((0, 0, -1)))
    assert local is not None and local.z == (0.0, 0.0, 1.0)


# -- the Fillet tool's immediate preview (milestone 2: the worker's result follows) ----------------------------------

def test_fillet_preview_of_a_right_angled_edge():
    # the top-front edge of a box: top face normal +Z, front face normal -Y; the faces' centres say which way
    # each face lies from the edge
    a, b = Vector((0, 0, 0)), Vector((10, 0, 0))
    n1, n2 = Vector((0, 0, 1)), Vector((0, -1, 0))
    c1, c2 = Vector((5, 5, 0)), Vector((5, 0, -5))
    mid, w = drawing.fillet_handle(a, b, n1, n2)
    assert mid == Vector((5, 0, 0)) and (w - Vector((0, -1, 1)).normalized()).length < 1e-6  # out of the solid
    lines = drawing.fillet_preview(a, b, n1, n2, c1, c2, 2.0, chamfer=False)
    ends = {tuple(round(v, 5) for v in p) for seg in lines[:2] for p in seg}
    assert ends == {(0, 2, 0), (10, 2, 0), (0, 0, -2), (10, 0, -2)}  # where the round meets each face
    arc = [p for seg in lines[2:] for p in seg]
    centre = Vector((5, 2, -2))
    assert all(abs((p - centre).length - 2.0) < 1e-6 for p in arc)  # the cross-section at the middle
    chamfer = drawing.fillet_preview(a, b, n1, n2, c1, c2, 2.0, chamfer=True)
    assert {tuple(round(v, 5) for v in p) for p in chamfer[-1]} == {(5, 2, 0), (5, 0, -2)}  # the flat cut


def test_fillet_preview_of_an_obtuse_edge():
    # faces at 135 degrees inside the material: the round meets them r / tan(67.5 degrees) from the edge
    a, b = Vector((0, 0, 0)), Vector((0, 10, 0))
    n1, n2 = Vector((0, 0, 1)), Vector((1, 0, 1)).normalized()
    c1, c2 = Vector((-5, 5, 0)), Vector((5, 5, -5))
    lines = drawing.fillet_preview(a, b, n1, n2, c1, c2, 1.0, chamfer=False)
    s = 1.0 / math.tan(math.radians(67.5))
    assert abs(lines[0][0].x + s) < 1e-6 and abs(lines[0][0].z) < 1e-6
