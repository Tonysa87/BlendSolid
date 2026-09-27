"""Tool 2, interactive side, headless: the Draw Solid modal driven by synthetic events whose mouse rays are
given directly (no window in background mode), ray casts against real part meshes, and the tool's
registration. What only a person can check (the preview drawing, the header, snapping feel) is in the manual
GUI test."""
import math
from types import SimpleNamespace

import bpy
import pytest
from mathutils import Vector

from blendsolid import ops_draw, part, script_model, trust
from conftest import mm3, up_to_date, wait_for

OP = ops_draw.BLENDSOLID_OT_draw_solid


class FakeArea:
    type = "VIEW_3D"

    def __init__(self):
        self.headers = []

    def header_text_set(self, text):
        self.headers.append(text)

    def tag_redraw(self):
        pass


class Driver:
    """Runs the operator's own invoke/modal/_update/... on a plain object with the operator's properties."""
    invoke, modal, _update, _mode, _header, _finish = OP.invoke, OP.modal, OP._update, OP._mode, OP._header, \
        OP._finish

    def __init__(self, shape):
        bpy.context.scene.blendsolid_draw_shape = shape  # the tool reads the shape from the scene
        self.shape, self.reports, self.executed = shape, [], None
        self.context = SimpleNamespace(area=FakeArea(), region=None, region_data=object(), scene=bpy.context.scene,
                                       window_manager=SimpleNamespace(modal_handler_add=lambda op: None),
                                       evaluated_depsgraph_get=bpy.context.evaluated_depsgraph_get)

    def report(self, kind, message):
        self.reports.append(message)

    def execute(self, context):
        self.executed = {k: getattr(self, k) for k in ("shape", "mode", "target", "location", "rotation", "height")}
        self.executed.update({k: getattr(self, k) for k in ("length", "width", "radius") if hasattr(self, k)})
        return bpy.ops.blendsolid.draw_solid(**self.executed)

    def wheel(self, kind, at, ctrl=True):
        return SimpleNamespace(type=kind, value="PRESS", ctrl=ctrl, shift=False,
                               ray=(Vector(at) + Vector((0, 0, 1.0)), Vector((0, 0, -1.0))))

    def event(self, kind, value, at, ctrl=False, shift=False):
        """A mouse event whose ray looks straight down at world point `at` (Blender units)."""
        ray = (Vector(at) + Vector((0, 0, 1.0)), Vector((0, 0, -1.0)))
        return SimpleNamespace(type=kind, value=value, ctrl=ctrl, shift=shift, ray=ray)

    def side_event(self, kind, value, at, ctrl=False, shift=False):
        """A ray along -Y through `at`: moving it up and down sets the height."""
        return SimpleNamespace(type=kind, value=value, ctrl=ctrl, shift=shift,
                               ray=(Vector(at) + Vector((0, 1.0, 0)), Vector((0, -1.0, 0))))

    def x_face_event(self, kind, value, at):
        """A ray along -X through `at`: picks/drags on a part's +X face."""
        return SimpleNamespace(type=kind, value=value, ctrl=False, shift=False,
                               ray=(Vector(at) + Vector((1.0, 0, 0)), Vector((-1.0, 0, 0))))

    def run(self, events):
        result = self.invoke(self.context, events[0])
        for e in events[1:]:
            if result != {"RUNNING_MODAL"}:
                break
            result = self.modal(self.context, e)
        return result


@pytest.fixture
def rays(monkeypatch):
    monkeypatch.setattr(ops_draw, "_mouse_ray", lambda context, event: event.ray)


def box_part():
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.ops.blendsolid.add_box(length=40, width=30, height=20)
    obj = bpy.context.view_layer.objects.active
    wait_for(lambda: up_to_date(obj))  # ray casts need its mesh
    bpy.context.view_layer.update()
    return obj


def test_draw_a_hole_into_the_top_face(clean, rays):
    box = box_part()
    d = Driver("CYLINDER")
    top = (0.005, 0.0, 0.02)
    result = d.run([
        d.event("LEFTMOUSE", "PRESS", top),                      # the circle's centre, on the top face
        d.event("MOUSEMOVE", "NOTHING", (0.008, 0.0, 0.02)),
        d.event("LEFTMOUSE", "RELEASE", (0.008, 0.0, 0.02)),       # radius 3 mm
        d.side_event("MOUSEMOVE", "NOTHING", (0.005, 0.0, 0.015)),  # 5 mm into the part: a cut
        d.side_event("LEFTMOUSE", "PRESS", (0.005, 0.0, 0.015)),
    ])
    assert result == {"FINISHED"}
    assert d.executed["mode"] == "CUT" and d.executed["target"] == box.name
    assert d.executed["radius"] == pytest.approx(3.0, abs=1e-3) and d.executed["height"] == pytest.approx(5, abs=1e-3)
    assert tuple(d.executed["location"]) == pytest.approx((5, 0, 20), abs=1e-3)
    assert [f.name for f in script_model.features(part.source_of(box))] == ["box_1", "cut_1"]
    wait_for(lambda: up_to_date(box))
    assert abs(mm3(box) - (24000 - math.pi * 9 * 5)) < 30
    assert d.context.area.headers[-1] is None  # the header text was restored


def test_pull_up_is_a_union_and_ctrl_snaps(clean, rays):
    box = box_part()
    d = Driver("BOX")
    d.run([
        d.event("LEFTMOUSE", "PRESS", (-0.0101, -0.0049, 0.02)),
        d.event("MOUSEMOVE", "NOTHING", (0.0098, 0.0052, 0.02), ctrl=True),
        d.event("LEFTMOUSE", "RELEASE", (0.0098, 0.0052, 0.02), ctrl=True),
        d.side_event("MOUSEMOVE", "NOTHING", (0.0, 0.0, 0.0302)),
        d.side_event("LEFTMOUSE", "PRESS", (0.0, 0.0, 0.0302)),
    ])
    assert d.executed["mode"] == "UNION"
    assert (d.executed["length"], d.executed["width"]) == (20.0, 10.0)  # snapped to whole millimetres


@pytest.fixture
def step():
    scene = bpy.context.scene
    saved = scene.blendsolid_snap_step
    yield scene
    scene.blendsolid_snap_step = saved


def test_ctrl_snaps_the_first_corner_to_the_grid_at_the_chosen_step(clean, rays, step):
    step.blendsolid_snap_step = "10"
    bpy.context.scene.cursor.location = (0, 0, 0)
    d = Driver("BOX")
    d.run([
        d.event("LEFTMOUSE", "PRESS", (0.0123, 0.0071, 0.0), ctrl=True),   # nearest node: (10, 10) mm
        d.event("MOUSEMOVE", "NOTHING", (0.0482, 0.0331, 0.0), ctrl=True),  # nearest node: (50, 30) mm
        d.event("LEFTMOUSE", "RELEASE", (0.0482, 0.0331, 0.0), ctrl=True),
        d.side_event("MOUSEMOVE", "NOTHING", (0.03, 0.0, 0.0123), ctrl=True),
        d.side_event("LEFTMOUSE", "PRESS", (0.03, 0.0, 0.0123), ctrl=True),
    ])
    assert (d.executed["length"], d.executed["width"], d.executed["height"]) == pytest.approx((40, 20, 10))
    assert tuple(d.executed["location"]) == pytest.approx((30, 20, 0))


def test_ctrl_wheel_changes_the_step_while_drawing(clean, rays, step):
    step.blendsolid_snap_step = "1"
    bpy.context.scene.cursor.location = (0, 0, 0)
    d = Driver("BOX")
    result = d.run([
        d.event("LEFTMOUSE", "PRESS", (0.0, 0.0, 0.0)),
        d.wheel("WHEELUPMOUSE", (0.01, 0.01, 0.0)),
        d.wheel("WHEELUPMOUSE", (0.01, 0.01, 0.0)),
    ])
    assert result == {"RUNNING_MODAL"} and step.blendsolid_snap_step == "5"
    assert "5 mm" in d.context.area.headers[-1]
    d.modal(d.context, d.wheel("WHEELDOWNMOUSE", (0.01, 0.01, 0.0)))
    assert step.blendsolid_snap_step == "2"
    # the wheel alone still zooms the view
    assert d.modal(d.context, d.wheel("WHEELUPMOUSE", (0.01, 0.01, 0.0), ctrl=False)) == {"PASS_THROUGH"}


def test_snap_step_operator_and_the_tool_keymap(clean, step):
    step.blendsolid_snap_step = "1"
    assert bpy.ops.blendsolid.snap_step(direction=1) == {"FINISHED"} and step.blendsolid_snap_step == "2"
    bpy.ops.blendsolid.snap_step(direction=-1)
    bpy.ops.blendsolid.snap_step(direction=-1)
    assert step.blendsolid_snap_step == "0.5"
    wheel = [k for k in ops_draw.DrawSolidTool.bl_keymap if k[0] == "blendsolid.snap_step"]
    assert {k[1]["type"] for k in wheel} == {"WHEELUPMOUSE", "WHEELDOWNMOUSE"} and all(k[1]["ctrl"] for k in wheel)


def test_hover_marker_is_the_grid_node_under_the_mouse(clean, step):
    step.blendsolid_snap_step = "10"
    bpy.context.scene.cursor.location = (0, 0, 0)
    point = ops_draw.hover_node(bpy.context, (0.0123, 0.0071, 1.0), (0, 0, -1.0))
    assert (point - Vector((0.010, 0.010, 0.0))).length < 1e-9


def test_through_a_wire_cutter_and_on_empty_space(clean, rays):
    box = box_part()
    bpy.context.scene.cursor.location = (0, 0, 0.05)
    bpy.ops.blendsolid.add_box(length=100, width=100, height=1)  # a flat plate above the box...
    plate = bpy.context.view_layer.objects.active
    plate.display_type = "WIRE"                                 # ...shown as a cutter: looked through
    bpy.context.scene.cursor.location = (0, 0, 0)
    wait_for(lambda: up_to_date(plate))
    bpy.context.view_layer.update()
    ctx = Driver("BOX").context
    ray = (Vector((0.0, 0.0, 1.0)), Vector((0.0, 0.0, -1.0)))
    plane, target = ops_draw.pick_plane(ctx, *ray)
    assert target == box and plane.translation.z == pytest.approx(0.02)
    plane, target = ops_draw.pick_plane(ctx, Vector((1.0, 1.0, 1.0)), Vector((0.0, 0.0, -1.0)))
    assert target is None and plane.translation == bpy.context.scene.cursor.location


def test_click_without_drag_and_escape_draw_nothing(clean, rays):
    box = box_part()
    before = part.source_of(box)
    d = Driver("BOX")
    assert d.run([d.event("LEFTMOUSE", "PRESS", (0, 0, 0.02)), d.event("LEFTMOUSE", "RELEASE", (0, 0, 0.02))]) \
        == {"CANCELLED"}
    d = Driver("BOX")
    assert d.run([d.event("LEFTMOUSE", "PRESS", (0, 0, 0.02)), d.event("MOUSEMOVE", "NOTHING", (0.01, 0.01, 0.02)),
                  d.event("ESC", "PRESS", (0.01, 0.01, 0.02))]) == {"CANCELLED"}
    assert part.source_of(box) == before and len(bpy.data.objects) == 1


def test_zero_size_base_and_zero_height_draw_nothing(clean, rays):
    """Controller ruling: a drag whose base has zero radius/length/width, or whose height ends up zero, must
    end like a click without a drag (no execute(), no script edit) rather than drawing a degenerate solid.
    The height case uses a sub-millimetre move with Ctrl held: the geometry pipeline doesn't return a
    bit-exact 0.0 for "no vertical movement" (float precision in the line/plane intersections), but Ctrl's
    round-to-the-millimetre snap does, which is the realistic way a user's near-zero move ends up at 0 mm."""
    box = box_part()
    before = part.source_of(box)
    away = 0.1  # off the box's footprint: falls through to the cursor's plane, not a real mesh raycast

    d = Driver("CYLINDER")  # press and release at the same point: radius 0
    result = d.run([
        d.event("LEFTMOUSE", "PRESS", (away, 0.0, 0.0)),
        d.event("MOUSEMOVE", "NOTHING", (away, 0.0, 0.0)),
        d.event("LEFTMOUSE", "RELEASE", (away, 0.0, 0.0)),
    ])
    assert result == {"CANCELLED"} and d.executed is None

    d = Driver("BOX")  # a valid base, but a sub-millimetre move snaps the height to exactly 0 mm
    result = d.run([
        d.event("LEFTMOUSE", "PRESS", (away - 0.005, -0.005, 0.0)),
        d.event("MOUSEMOVE", "NOTHING", (away + 0.005, 0.005, 0.0)),
        d.event("LEFTMOUSE", "RELEASE", (away + 0.005, 0.005, 0.0)),
        d.side_event("MOUSEMOVE", "NOTHING", (away, 0.0, 0.0002), ctrl=True),
        d.side_event("LEFTMOUSE", "PRESS", (away, 0.0, 0.0002), ctrl=True),
    ])
    assert result == {"CANCELLED"} and d.executed is None
    assert part.source_of(box) == before and len(bpy.data.objects) == 1

    d = Driver("BOX")  # an *unsnapped* height click right back at the base's own level: without Ctrl, the
    # line/plane intersections don't cancel to a bit-exact 0.0 (float precision) but the sub-micron result
    # must still be treated as "no height", not committed as a (clamped) 0.001 mm feature
    result = d.run([
        d.event("LEFTMOUSE", "PRESS", (-0.005, -0.005, 0.02)),
        d.event("MOUSEMOVE", "NOTHING", (0.005, 0.005, 0.02)),
        d.event("LEFTMOUSE", "RELEASE", (0.005, 0.005, 0.02)),
        d.side_event("MOUSEMOVE", "NOTHING", (0.0, 0.0, 0.02)),
        d.side_event("LEFTMOUSE", "PRESS", (0.0, 0.0, 0.02)),
    ])
    assert result == {"CANCELLED"} and d.executed is None

    d = Driver("CYLINDER")  # a tiny but genuinely non-zero radius (0.0004 mm), below the property minimum
    result = d.run([
        d.event("LEFTMOUSE", "PRESS", (0.0, 0.0, 0.0)),
        d.event("MOUSEMOVE", "NOTHING", (0.0000004, 0.0, 0.0)),
        d.event("LEFTMOUSE", "RELEASE", (0.0000004, 0.0, 0.0)),
    ])
    assert result == {"CANCELLED"} and d.executed is None

    d = Driver("BOX")  # dragged along one axis only: zero width
    result = d.run([
        d.event("LEFTMOUSE", "PRESS", (-0.005, 0.0, 0.02)),
        d.event("MOUSEMOVE", "NOTHING", (0.005, 0.0, 0.02)),
        d.event("LEFTMOUSE", "RELEASE", (0.005, 0.0, 0.02)),
    ])
    assert result == {"CANCELLED"} and d.executed is None

    assert part.source_of(box) == before and len(bpy.data.objects) == 1


def test_viewport_navigation_passes_through(clean, rays):
    """Controller ruling: while the modal runs, viewport navigation events (middle-mouse orbit, wheel zoom,
    trackpad pan/zoom, NDOF) must not be swallowed: they return PASS_THROUGH so the viewport still reacts,
    and they must not disturb the in-progress drag."""
    box_part()
    d = Driver("BOX")
    d.invoke(d.context, d.event("LEFTMOUSE", "PRESS", (-0.005, -0.005, 0.02)))
    d.modal(d.context, d.event("MOUSEMOVE", "NOTHING", (0.005, 0.005, 0.02)))
    before_drawn, before_stage = d._drawn, d._stage
    for nav_type in ("MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE",
                     "TRACKPADPAN", "TRACKPADZOOM", "NDOF_MOTION"):
        event = SimpleNamespace(type=nav_type, value="NOTHING", ctrl=False, shift=False, ray=None)
        assert d.modal(d.context, event) == {"PASS_THROUGH"}
    assert d._drawn == before_drawn and d._stage == before_stage


def test_cut_into_a_side_face_has_nonzero_rotation(clean, rays):
    """Controller ruling: drawing on a SIDE face (a non-zero rotation of the drawn frame) exercises the
    Euler 'ZYX' <-> build123d Location convention end to end, not just the top-face (zero-rotation) case."""
    box = box_part()
    d = Driver("CYLINDER")
    face = (0.02, 0.0, 0.01)   # centre of the +X face, mid-height
    rim = (0.02, 0.003, 0.01)  # 3 mm radius, along the face's local X (the part's Y)
    result = d.run([
        d.x_face_event("LEFTMOUSE", "PRESS", face),
        d.x_face_event("MOUSEMOVE", "NOTHING", rim),
        d.x_face_event("LEFTMOUSE", "RELEASE", rim),
        d.event("MOUSEMOVE", "NOTHING", (0.015, 0.0, 0.01)),   # 5 mm into the part along -X: a cut
        d.event("LEFTMOUSE", "PRESS", (0.015, 0.0, 0.01)),
    ])
    assert result == {"FINISHED"}
    assert d.executed["mode"] == "CUT" and d.executed["target"] == box.name
    assert d.executed["radius"] == pytest.approx(3.0, abs=1e-3)
    assert d.executed["height"] == pytest.approx(5.0, abs=1e-3)
    assert tuple(d.executed["location"]) == pytest.approx((20, 0, 10), abs=1e-3)
    assert d.executed["rotation"] != pytest.approx((0, 0, 0), abs=1e-3)  # a real (non-zero) rotation
    wait_for(lambda: up_to_date(box))
    assert abs(mm3(box) - (24000 - math.pi * 9 * 5)) < 30


def test_tool_is_registered(addon):
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    cls = ToolSelectPanelHelper._tool_class_from_space_type("VIEW_3D")
    ids = [t.idname for group in cls.tools_from_context(bpy.context, mode="OBJECT") if group
           for t in (group if isinstance(group, tuple) else (group,)) if t is not None and hasattr(t, "idname")]
    assert "blendsolid.draw_solid_tool" in ids


def test_tool_starts_a_drag_with_modifiers_held(addon):
    """Ctrl (snapping) or Shift+Ctrl held before the press must still start a drag: the modal reads the
    modifiers itself, so the tool's LMB item must accept any modifier."""
    km = bpy.context.window_manager.keyconfigs.addon.keymaps["3D View Tool: Object, Draw Solid"]
    (item,) = [i for i in km.keymap_items if i.idname == "blendsolid.draw_solid"]
    assert item.type == "LEFTMOUSE" and item.value == "PRESS" and item.any


@pytest.mark.parametrize("why", ["non-canonical", "untrusted"])
def test_a_part_the_tools_cannot_edit_is_drawn_on_as_a_new_part(clean, rays, monkeypatch, why):
    """A part whose script the tools can't edit (hand-edited / milestone 1 layout, or not trusted) is not a
    target: the solid is drawn on its face plane as a new part, instead of being refused only at the end."""
    box = box_part()
    if why == "non-canonical":
        box.blendsolid_script.from_string("size = 10.0\nresult = Box(size, size, size)\n")  # mesh kept: no tick
    else:
        monkeypatch.setattr(trust, "_file_trusted", False)
        monkeypatch.setattr(trust, "_trusted_texts", set())
    plane, target = ops_draw.pick_plane(Driver("BOX").context, Vector((0.0, 0.0, 1.0)), Vector((0.0, 0.0, -1.0)))
    assert target is None and plane.translation.z == pytest.approx(0.02)  # still on the top face
