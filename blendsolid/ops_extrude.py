"""Tools 7, 8 and 9: Groove along a sketch curve, and Extrude and Revolve the closed areas (regions) of a part's
sketches (milestone 3a).

Extrude: press on a region and drag along the sketch's normal. Out along the normal adds; against it cuts when the
part already has a solid (else it adds, downwards). One feature, e.g.

    extrude(regions(sketch_1, (5.0, 0.0)), amount=extrude_1_amount)  # feature: extrude_1

Adjust Last Operation then offers the boolean, up to next/last, symmetric and the taper angle. Revolve: click a
region, then the sketch line to turn it about (360°; the angle is in Adjust Last Operation).
"""
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, StringProperty
from mathutils import Vector

from . import drawing, focus, ops_sketch, part, script_model, sketching

OPERATIONS = [("ADD", "Join", "Add the solid to the part", "SELECT_EXTEND", 0),
              ("SUBTRACT", "Cut", "Cut the solid out of the part", "SELECT_SUBTRACT", 1),
              ("INTERSECT", "Intersect", "Keep only what the part and the solid share", "SELECT_INTERSECT", 2)]
EXTENTS = [("DISTANCE", "Distance", "Extrude by a distance", 0),
           ("NEXT", "Up to Next", "Up to the next face of the part: a join fills the gap in front of the area, a "
                                  "cut goes through the first wall", 1),
           ("LAST", "Up to Last", "Through the whole part: a join up to its farthest face, a cut through all", 2)]
HOVER_COLOUR = (0.45, 0.8, 1.0, 0.35)
PREVIEW_COLOUR = {True: (0.35, 0.9, 0.45, 1.0), False: (1.0, 0.35, 0.3, 1.0)}


def _check_part(op, name):
    obj = part.local_part(name)
    if obj is None:
        op.report({"ERROR"}, f"There is no BlendSolid part named '{name}'")
        return None
    if part.is_scaled(obj):
        op.report({"ERROR"}, part.scaled_message(obj))
        return None
    blocked = part.blocking_error(obj)
    if blocked:
        op.report({"ERROR"}, blocked)
        return None
    return obj


def _append(op, context, obj, spec):
    from . import ui
    try:
        source, name = script_model.append_feature(part.source_of(obj), spec)
    except script_model.NotCanonical as e:
        op.report({"ERROR"}, part.not_canonical_message(obj, e, detail=ui.scripts_visible(context)))
        return {"CANCELLED"}
    obj.blendsolid_script.from_string(source)
    focus.set_focus(obj, name)
    return {"FINISHED"}


def has_solid(obj):
    return obj.data is not None and len(obj.data.polygons) > 0


def auto_operation(solid, amount):
    """Out along the sketch's normal joins; against it cuts, if there is anything to cut (`solid`: the part had a
    solid when the drag started; its mesh during the drag is the drag's own preview)."""
    return "SUBTRACT" if amount < 0 and solid else "ADD"


class BLENDSOLID_OT_extrude(bpy.types.Operator):
    """Extrude a closed area of a sketch: join, cut or intersect, by a distance or up to the next/last face"""
    bl_idname = "blendsolid.extrude"
    bl_label = "Extrude"
    bl_options = {"REGISTER", "UNDO"}

    target: StringProperty(name="Part")
    sketch: StringProperty(name="Sketch")
    seed: FloatVectorProperty(name="Area", size=2, precision=3,
                              description="A point inside the area to extrude, millimetres in the sketch's plane")
    amount: FloatProperty(name="Distance", default=10.0, precision=3, step=100,
                          description="Millimetres along the sketch's normal (negative: the other way)")
    # SKIP_SAVE: every extrude starts plain (Blender would otherwise reuse the last call's values)
    operation: EnumProperty(name="Operation", items=OPERATIONS, default="ADD", options={"SKIP_SAVE"})
    extent: EnumProperty(name="Extent", items=EXTENTS, default="DISTANCE", options={"SKIP_SAVE"})
    symmetric: BoolProperty(name="Symmetric", description="The same distance on both sides of the sketch",
                            options={"SKIP_SAVE"})
    taper: FloatProperty(name="Taper", default=0.0, min=-45.0, max=45.0, precision=2, step=100,
                         options={"SKIP_SAVE"},
                         description="Angle of the sides in degrees: positive narrows away from the sketch")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "operation")
        layout.prop(self, "extent")
        if self.extent == "DISTANCE":
            layout.prop(self, "amount")
            layout.prop(self, "symmetric")
            layout.prop(self, "taper")
        else:
            layout.prop(self, "amount", text="Direction (sign)")

    def execute(self, context):
        obj = _check_part(self, self.target)
        if obj is None:
            return {"CANCELLED"}
        if self.extent == "DISTANCE" and abs(self.amount) < 1e-6:
            self.report({"ERROR"}, "The extrude has no distance")
            return {"CANCELLED"}
        spec = sketching.extrude_spec(self.sketch, tuple(self.seed), self.amount, self.operation, self.extent,
                                      self.symmetric, self.taper, _bounds(obj, self.sketch, self.seed))
        return _append(self, context, obj, spec)

    # -- the Extrude tool's drag ----------------------------------------------------------------------------

    def invoke(self, context, event):
        from . import ops_draw
        if context.area is None or context.area.type != "VIEW_3D" or context.region_data is None:
            return {"CANCELLED"}
        origin, direction = ops_draw._mouse_ray(context, event)
        found = pick_region(context, origin, direction)
        if found is None:
            return {"PASS_THROUGH"}
        obj, sketch, uv, index = found
        blocked = part.blocking_error(obj)
        if blocked:
            self.report({"ERROR"}, blocked)
            return {"CANCELLED"}
        self._factor = part.unit_factor(context.scene)
        self._obj, self._sketch, self._uv = obj, sketch, uv
        plane = ops_sketch.plane_matrix(obj, sketch, self._factor)
        self._start = plane @ Vector((uv[0] * self._factor, uv[1] * self._factor, 0.0))
        self._plane = drawing._frame(self._start, plane.col[0].xyz, plane.col[2].xyz)
        self._normal = plane.col[2].xyz.normalized()
        self._outline = [(ops_sketch.world_point(obj, sketch, p, self._factor),
                          ops_sketch.world_point(obj, sketch, q, self._factor))
                         for loop in sketch["regions"][index]["loops"] for p, q in zip(loop, loop[1:] + loop[:1])]
        self._source, self._amount, self._snap = part.source_of(obj), 0.0, 0.0
        self._solid = has_solid(obj)
        self._handles = [bpy.types.SpaceView3D.draw_handler_add(_draw_drag, (self,), "WINDOW", "POST_VIEW"),
                         bpy.types.SpaceView3D.draw_handler_add(_draw_drag_label, (self,), "WINDOW", "POST_PIXEL")]
        _dragging.add(id(self))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        from . import ops_draw
        if event.type in ops_draw.WHEEL and event.ctrl and event.value == "PRESS":
            ops_draw.change_step(context.scene, ops_draw.WHEEL[event.type])
            self._update(context, event)
            return {"RUNNING_MODAL"}
        if event.type in ops_draw.NAV_EVENTS:
            return {"PASS_THROUGH"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._obj.blendsolid_script.from_string(self._source)
            return self._end(context, {"CANCELLED"})
        if event.type in {"MOUSEMOVE", "LEFT_CTRL", "RIGHT_CTRL", "LEFT_SHIFT", "RIGHT_SHIFT"}:
            self._update(context, event)
        elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._obj.blendsolid_script.from_string(self._source)
            self._end(context, None)
            if abs(self._amount) < 1e-3:
                return {"CANCELLED"}
            self.target, self.sketch, self.seed = self._obj.name, self._sketch["name"], self._uv
            self.amount = self._amount
            self.operation = auto_operation(self._solid, self._amount)
            self.extent, self.symmetric, self.taper = "DISTANCE", False, 0.0
            return self.execute(context)
        what = {"ADD": "join", "SUBTRACT": "cut"}[auto_operation(self._solid, self._amount)]
        context.area.header_text_set(
            f"Extrude: {abs(self._amount):.3f} mm, {what} | Ctrl: snap {ops_draw.step_mm(context.scene):g} mm | "
            "release: confirm (taper, up to next/last: Adjust Last Operation) | Esc/right-click: cancel")
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def _update(self, context, event):
        from . import ops_draw, runtime
        origin, direction = ops_draw._mouse_ray(context, event)
        amount = drawing.height_along_normal(self._plane, self._start, origin, direction) / self._factor
        step = ops_draw.step_mm(context.scene)
        self._snap = (step / 10 if event.shift else step) if event.ctrl else 0.0
        if self._snap:
            amount = drawing.snap(amount, self._snap)
        self._amount = amount
        if abs(amount) < 1e-3:
            self._obj.blendsolid_script.from_string(self._source)
            return
        spec = sketching.extrude_spec(self._sketch["name"], self._uv, amount, auto_operation(self._solid, amount),
                                      bounds=sketching.region_bounds(self._sketch, self._uv))
        try:
            source, _ = script_model.append_feature(self._source, spec)
        except script_model.NotCanonical:
            return
        self._obj.blendsolid_script.from_string(source)  # the live preview: the worker recomputes it
        runtime.kick()

    def _end(self, context, result):
        for handle in getattr(self, "_handles", []):
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        self._handles = []
        _dragging.discard(id(self))
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()
        return result


_dragging = set()


def _bounds(obj, sketch, seed):
    """The bounding curves of the area at `seed` in `obj`'s sketch `sketch`, as the part last drew it (the panel's
    Area may have been edited: the area under the point now, not the one first clicked)."""
    return sketching.region_bounds(ops_sketch.find_sketch(obj, sketch), tuple(seed))


def pick_region(context, origin, direction):
    """(part, sketch, (u, v) mm, region index) of the sketch region under the mouse ray, in front of any solid,
    on an editable part; or None."""
    found = ops_sketch.pick_sketch(context, origin, direction, used=True, within_regions=True)
    if found is None:
        return None
    obj, sketch, uv, along = found
    if not ops_sketch.editable(obj) or along > ops_sketch._in_front(ops_sketch.solid_distance(context, origin,
                                                                                              direction)):
        return None
    uv = tuple(round(c, 6) + 0.0 for c in uv)
    index = sketching.region_at(sketch, uv)
    return None if index is None else (obj, sketch, uv, index)


def _draw_drag(op):
    from . import ops_draw
    try:
        amount, factor, normal, outline = op._amount, op._factor, op._normal, op._outline
    except (ReferenceError, AttributeError):
        return
    colour = PREVIEW_COLOUR[amount >= 0]
    offset = normal * (amount * factor)
    lines = [(a + offset, b + offset, colour, colour) for a, b in outline]
    lines += [(a, a + offset, colour, colour) for a, _ in outline[:: max(1, len(outline) // 8)]]
    ops_draw._draw_segments(bpy.context.region, lines, 2.5 * ops_draw.ui_scale(bpy.context))


def _draw_drag_label(op):
    from . import ops_draw
    try:
        amount, factor, normal, start, snap = op._amount, op._factor, op._normal, op._start, op._snap
    except (ReferenceError, AttributeError):
        return
    lines = [f"{'+' if amount >= 0 else '−'}{drawing.mm(abs(amount))} mm"] + ([f"snap {snap:g} mm"] if snap else [])
    ops_draw.draw_text_lines(bpy.context, start + normal * (amount * factor), lines)


class BLENDSOLID_GT_region_hover(bpy.types.Gizmo):
    """The Extrude and Revolve tools' overlay: the sketch region under the mouse, filled."""
    bl_idname = "BLENDSOLID_GT_region_hover"

    def setup(self):
        self.mouse = None

    def test_select(self, context, location):
        self.mouse = tuple(location)
        context.area.tag_redraw()
        return -1

    def draw(self, context):
        from . import ops_draw
        if self.mouse is None or context.region_data is None or _dragging:
            return
        if _revolving:
            _draw_axis_hover(context, self.mouse)
            return
        origin, direction = ops_draw.mouse_ray(context, self.mouse)
        found = pick_region(context, origin, direction)
        if found is None:
            return
        obj, sketch, _, index = found
        factor = part.unit_factor(context.scene)
        ops_sketch.draw_triangles(ops_sketch.region_triangles(obj, sketch, sketch["regions"][index], factor),
                                  HOVER_COLOUR)


class BLENDSOLID_GGT_region_hover(bpy.types.GizmoGroup):
    bl_idname = "BLENDSOLID_GGT_region_hover"
    bl_label = "Sketch Region Overlay"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    def setup(self, context):
        from . import runtime
        runtime.warm_up()
        self.gizmos.new(BLENDSOLID_GT_region_hover.bl_idname)


# -- revolve ------------------------------------------------------------------------------------------------------

class BLENDSOLID_OT_revolve(bpy.types.Operator):
    """Turn a closed area of a sketch about one of the sketch's lines"""
    bl_idname = "blendsolid.revolve"
    bl_label = "Revolve"
    bl_options = {"REGISTER", "UNDO"}

    target: StringProperty(name="Part")
    sketch: StringProperty(name="Sketch")
    seed: FloatVectorProperty(name="Area", size=2, precision=3)
    axis: StringProperty(name="Axis", description="The sketch line the area turns about")
    angle: FloatProperty(name="Angle", default=360.0, min=-360.0, max=360.0, precision=2, step=100,
                         description="Degrees")
    operation: EnumProperty(name="Operation", items=OPERATIONS, default="ADD", options={"SKIP_SAVE"})

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "operation")
        layout.prop(self, "angle")

    def execute(self, context):
        obj = _check_part(self, self.target)
        if obj is None:
            return {"CANCELLED"}
        if abs(self.angle) < 1e-6:
            self.report({"ERROR"}, "The revolve has no angle")
            return {"CANCELLED"}
        spec = sketching.revolve_spec(self.sketch, tuple(self.seed), self.axis, self.angle, self.operation,
                                      _bounds(obj, self.sketch, self.seed))
        return _append(self, context, obj, spec)

    def invoke(self, context, event):
        from . import ops_draw
        if context.area is None or context.area.type != "VIEW_3D" or context.region_data is None:
            return {"CANCELLED"}
        origin, direction = ops_draw._mouse_ray(context, event)
        found = pick_region(context, origin, direction)
        if found is None:
            return {"PASS_THROUGH"}
        obj, sketch, uv, _ = found
        blocked = part.blocking_error(obj)
        if blocked:  # now, not after the axis click
            self.report({"ERROR"}, blocked)
            return {"CANCELLED"}
        if not sketching.line_entities(sketch):
            self.report({"WARNING"}, "Draw a line in the sketch first: the area turns about it")
            return {"CANCELLED"}
        self._obj, self._sketch, self._uv = obj, sketch, uv
        _revolving.clear()
        _revolving.append((obj, sketch))
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set("Revolve: click the sketch line to turn the area about | Esc: cancel")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        from . import ops_draw
        if event.type in ops_draw.NAV_EVENTS or event.type == "MOUSEMOVE":
            return {"PASS_THROUGH"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            return self._end(context, {"CANCELLED"})
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            axis = axis_under(context, (event.mouse_region_x, event.mouse_region_y), self._obj, self._sketch)
            if axis is None:
                return {"RUNNING_MODAL"}
            self._end(context, None)
            self.target, self.sketch, self.seed, self.axis = self._obj.name, self._sketch["name"], self._uv, axis
            self.angle, self.operation = 360.0, "ADD"
            return self.execute(context)
        return {"RUNNING_MODAL"}

    def _end(self, context, result):
        _revolving.clear()
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()
        return result


_revolving = []  # (part, sketch) while the Revolve tool waits for the axis


def axis_under(context, coord, obj, sketch):
    """The line entity of `sketch` under region coordinate `coord` (within a few pixels), or None."""
    from . import ops_draw
    factor = part.unit_factor(context.scene)
    plane = ops_sketch.plane_matrix(obj, sketch, factor)
    origin, direction = ops_draw.mouse_ray(context, coord)
    found = ops_sketch.ray_uv(plane, origin, direction, factor)
    if found is None:
        return None
    uv = found[0]
    pixel = ops_draw._pixel_size(context.region, context.region_data,
                                 plane @ Vector((uv[0] * factor, uv[1] * factor, 0.0)))
    if pixel is None:
        return None
    radius = 8 * ops_draw.ui_scale(context) * pixel / factor
    return sketching.entity_at(sketch, uv, radius, names=sketching.line_entities(sketch))


def _draw_axis_hover(context, mouse):
    from . import ops_draw
    try:
        obj, sketch = _revolving[0]
        name = axis_under(context, mouse, obj, sketch)
    except (ReferenceError, IndexError):
        return
    factor = part.unit_factor(context.scene)
    colour = (0.45, 0.8, 1.0, 1.0)
    lines = []
    for n in sketching.line_entities(sketch):
        a, b = sketch["curves"][n][0]
        c = colour if n == name else (0.45, 0.8, 1.0, 0.4)
        lines.append((ops_sketch.world_point(obj, sketch, a, factor), ops_sketch.world_point(obj, sketch, b, factor),
                      c, c))
    ops_draw._draw_segments(context.region, lines, 4.0 * ops_draw.ui_scale(context))


# -- grooves and ribs along sketch paths --------------------------------------------------------------------------

PROFILES = [("rect", "Rectangle", "A flat-bottomed groove (or a square rib)", 0),
            ("round", "Round", "A U groove: its bottom a half circle as wide as the groove", 1),
            ("v", "V", "A V groove: its apex at the depth", 2),
            ("circle", "Circle", "A round pipe of the width's diameter, centred on the path", 3)]
CORNERS = [("mitre", "Sharp", "Sharp corners follow the path's own", 0),
           ("round", "Round", "The outside of sharp corners rounded", 1)]
GROOVE_OPERATIONS = [("SUBTRACT", "Groove", "Cut the profile into the part", "SELECT_SUBTRACT", 0),
                     ("ADD", "Rib", "Add the profile to the part", "SELECT_EXTEND", 1)]


class BLENDSOLID_OT_groove(bpy.types.Operator):
    """Sweep a profile along a sketch curve: a groove cut into the part, or a rib added to it"""
    bl_idname = "blendsolid.groove"
    bl_label = "Groove"
    bl_options = {"REGISTER", "UNDO"}

    target: StringProperty(name="Part")
    sketch: StringProperty(name="Sketch")
    entity: StringProperty(name="Path", description="The sketch curve the profile follows")
    operation: EnumProperty(name="Operation", items=GROOVE_OPERATIONS, default="SUBTRACT", options={"SKIP_SAVE"})
    profile: EnumProperty(name="Profile", items=PROFILES, default="rect")
    width: FloatProperty(name="Width", default=2.0, min=0.001, precision=3, step=10, description="Millimetres")
    depth: FloatProperty(name="Depth", default=1.0, min=0.001, precision=3, step=10,
                         description="Millimetres into the part (a groove) or out of it (a rib)")
    corners: EnumProperty(name="Corners", items=CORNERS, default="mitre")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "operation")
        layout.prop(self, "profile")
        layout.prop(self, "width")
        if self.profile != "circle":
            layout.prop(self, "depth", text="Height" if self.operation == "ADD" else "Depth")
        layout.prop(self, "corners")

    def execute(self, context):
        obj = _check_part(self, self.target)
        if obj is None:
            return {"CANCELLED"}
        spec = sketching.groove_spec(self.sketch, self.entity, self.width, self.depth, self.profile, self.corners,
                                     self.operation)
        return _append(self, context, obj, spec)

    def invoke(self, context, event):
        from . import ops_draw
        if context.area is None or context.area.type != "VIEW_3D" or context.region_data is None:
            return {"CANCELLED"}
        found = pick_curve(context, (event.mouse_region_x, event.mouse_region_y))
        if found is None:
            return {"PASS_THROUGH"}
        obj, sketch, name, uv = found
        blocked = part.blocking_error(obj)
        if blocked:
            self.report({"ERROR"}, blocked)
            return {"CANCELLED"}
        scene = context.scene
        self.profile, self.width, self.corners = (scene.blendsolid_groove_profile, scene.blendsolid_groove_width,
                                                  scene.blendsolid_groove_corners)
        self._factor = part.unit_factor(scene)
        self._obj, self._sketch, self._name = obj, sketch, name
        plane = ops_sketch.plane_matrix(obj, sketch, self._factor)
        self._start = plane @ Vector((uv[0] * self._factor, uv[1] * self._factor, 0.0))
        self._plane = drawing._frame(self._start, plane.col[0].xyz, plane.col[2].xyz)
        self._normal = plane.col[2].xyz.normalized()
        self._outline = [(ops_sketch.world_point(obj, sketch, p, self._factor),
                          ops_sketch.world_point(obj, sketch, q, self._factor))
                         for curve in sketch["curves"][name] for p, q in zip(curve, curve[1:])]
        self._source, self._amount, self._snap = part.source_of(obj), 0.0, 0.0
        self._solid = has_solid(obj)
        self._handles = [bpy.types.SpaceView3D.draw_handler_add(_draw_drag, (self,), "WINDOW", "POST_VIEW"),
                         bpy.types.SpaceView3D.draw_handler_add(_draw_drag_label, (self,), "WINDOW", "POST_PIXEL")]
        _dragging.add(id(self))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _operation(self, amount):
        return auto_operation(self._solid, amount)

    def modal(self, context, event):
        from . import ops_draw
        if event.type in ops_draw.WHEEL and event.ctrl and event.value == "PRESS":
            ops_draw.change_step(context.scene, ops_draw.WHEEL[event.type])
            self._update(context, event)
            return {"RUNNING_MODAL"}
        if event.type in ops_draw.NAV_EVENTS:
            return {"PASS_THROUGH"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._obj.blendsolid_script.from_string(self._source)
            return self._end(context, {"CANCELLED"})
        if event.type in {"MOUSEMOVE", "LEFT_CTRL", "RIGHT_CTRL", "LEFT_SHIFT", "RIGHT_SHIFT"}:
            self._update(context, event)
        elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._obj.blendsolid_script.from_string(self._source)
            self._end(context, None)
            if abs(self._amount) < 1e-3 and self.profile != "circle":
                return {"CANCELLED"}
            self.target, self.sketch, self.entity = self._obj.name, self._sketch["name"], self._name
            self.operation = self._operation(self._amount)
            self.depth = max(abs(self._amount), 0.001)
            return self.execute(context)
        what = "groove" if self._operation(self._amount) == "SUBTRACT" else "rib"
        context.area.header_text_set(
            f"Groove: {what} {abs(self._amount):.3f} mm, {self.profile} {self.width:g} mm wide | into the part: "
            f"groove, out: rib | Ctrl: snap | release: confirm (profile, width, corners: Adjust Last Operation) | "
            "Esc/right-click: cancel")
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def _update(self, context, event):
        from . import ops_draw, runtime
        origin, direction = ops_draw._mouse_ray(context, event)
        amount = drawing.height_along_normal(self._plane, self._start, origin, direction) / self._factor
        step = ops_draw.step_mm(context.scene)
        self._snap = (step / 10 if event.shift else step) if event.ctrl else 0.0
        if self._snap:
            amount = drawing.snap(amount, self._snap)
        self._amount = amount
        if abs(amount) < 1e-3:
            self._obj.blendsolid_script.from_string(self._source)
            return
        spec = sketching.groove_spec(self._sketch["name"], self._name, self.width, abs(amount), self.profile,
                                     self.corners, self._operation(amount))
        try:
            source, _ = script_model.append_feature(self._source, spec)
        except script_model.NotCanonical:
            return
        self._obj.blendsolid_script.from_string(source)
        runtime.kick()

    def _end(self, context, result):
        for handle in getattr(self, "_handles", []):
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        self._handles = []
        _dragging.discard(id(self))
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()
        return result


CURVE_PICK_PX = 8


def pick_curve(context, coord):
    """(part, sketch, entity name, (u, v) mm) of the sketch curve under region coordinate `coord` (within a few
    pixels), in front of any solid, on an editable part; or None."""
    from . import ops_draw
    origin, direction = ops_draw.mouse_ray(context, coord)
    factor = part.unit_factor(context.scene)
    solid = ops_sketch.solid_distance(context, origin, direction)
    best = None
    for obj in ops_sketch.sketch_parts(context):
        if not ops_sketch.editable(obj):
            continue
        for sketch in ops_sketch.sketches_of(obj):
            plane = ops_sketch.plane_matrix(obj, sketch, factor)
            found = ops_sketch.ray_uv(plane, origin, direction, factor)
            if found is None or found[1] > ops_sketch._in_front(solid):
                continue
            uv, along = found
            pixel = ops_draw._pixel_size(context.region, context.region_data,
                                         plane @ Vector((uv[0] * factor, uv[1] * factor, 0.0)))
            if pixel is None:
                continue
            name = sketching.entity_at(sketch, uv, CURVE_PICK_PX * ops_draw.ui_scale(context) * pixel / factor)
            if name is not None and (best is None or along < best[4]):
                best = (obj, sketch, name, tuple(round(c, 6) + 0.0 for c in uv), along)
    return None if best is None else best[:4]


class BLENDSOLID_GT_curve_hover(bpy.types.Gizmo):
    """The Groove tool's overlay: the sketch curve under the mouse, highlighted."""
    bl_idname = "BLENDSOLID_GT_curve_hover"

    def setup(self):
        self.mouse = None

    def test_select(self, context, location):
        self.mouse = tuple(location)
        context.area.tag_redraw()
        return -1

    def draw(self, context):
        from . import ops_draw
        if self.mouse is None or context.region_data is None or _dragging:
            return
        found = pick_curve(context, self.mouse)
        if found is None:
            return
        obj, sketch, name, _ = found
        factor = part.unit_factor(context.scene)
        colour = (0.45, 0.8, 1.0, 1.0)
        lines = [(ops_sketch.world_point(obj, sketch, p, factor), ops_sketch.world_point(obj, sketch, q, factor),
                  colour, colour) for curve in sketch["curves"][name] for p, q in zip(curve, curve[1:])]
        ops_draw._draw_segments(context.region, lines, 4.0 * ops_draw.ui_scale(context))


class BLENDSOLID_GGT_curve_hover(bpy.types.GizmoGroup):
    bl_idname = "BLENDSOLID_GGT_curve_hover"
    bl_label = "Sketch Curve Overlay"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    def setup(self, context):
        from . import runtime
        runtime.warm_up()
        self.gizmos.new(BLENDSOLID_GT_curve_hover.bl_idname)


class GrooveTool(bpy.types.WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = "blendsolid.groove_tool"
    bl_label = "Groove"
    bl_description = ("Press on a sketch curve and drag: into the part cuts a groove along it, out adds a rib; "
                      "profile, width and corners in the tool settings and in Adjust Last Operation")
    bl_icon = "ops.curve.draw"
    bl_widget = "BLENDSOLID_GGT_curve_hover"
    bl_keymap = (
        ("blendsolid.groove", {"type": "LEFTMOUSE", "value": "PRESS", "any": True}, None),
        ("blendsolid.snap_step", {"type": "WHEELUPMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", 1)]}),
        ("blendsolid.snap_step", {"type": "WHEELDOWNMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", -1)]}),
    )

    def draw_settings(context, layout, tool):
        scene = context.scene
        layout.prop(scene, "blendsolid_groove_profile", text="")
        layout.prop(scene, "blendsolid_groove_width", text="Width")
        layout.prop(scene, "blendsolid_groove_corners", text="")
        layout.prop(scene, "blendsolid_snap_step", text="Snap")


class ExtrudeTool(bpy.types.WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = "blendsolid.extrude_tool"
    bl_label = "Extrude Sketch"
    bl_description = ("Drag a closed area of a sketch along its normal: out joins, in cuts; taper and up to "
                      "next/last in Adjust Last Operation; Ctrl: snap")
    bl_icon = "ops.mesh.extrude_manifold"
    bl_widget = "BLENDSOLID_GGT_region_hover"
    bl_keymap = (
        ("blendsolid.extrude", {"type": "LEFTMOUSE", "value": "PRESS", "any": True}, None),
        ("blendsolid.snap_step", {"type": "WHEELUPMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", 1)]}),
        ("blendsolid.snap_step", {"type": "WHEELDOWNMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", -1)]}),
    )

    def draw_settings(context, layout, tool):
        layout.prop(context.scene, "blendsolid_snap_step", text="Snap")


class RevolveTool(bpy.types.WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = "blendsolid.revolve_tool"
    bl_label = "Revolve Sketch"
    bl_description = "Click a closed area of a sketch, then a line of the same sketch to turn it about"
    bl_icon = "ops.mesh.spin"
    bl_widget = "BLENDSOLID_GGT_region_hover"
    bl_keymap = (
        ("blendsolid.revolve", {"type": "LEFTMOUSE", "value": "PRESS", "any": True}, None),
    )


CLASSES = [BLENDSOLID_OT_extrude, BLENDSOLID_OT_revolve, BLENDSOLID_OT_groove, BLENDSOLID_GT_region_hover,
           BLENDSOLID_GGT_region_hover, BLENDSOLID_GT_curve_hover, BLENDSOLID_GGT_curve_hover]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.blendsolid_groove_profile = EnumProperty(name="Profile", items=PROFILES, default="rect",
                                                             description="The Groove tool's profile")
    bpy.types.Scene.blendsolid_groove_width = FloatProperty(name="Width", default=2.0, min=0.001, precision=3,
                                                            step=10, description="The Groove tool's width, mm")
    bpy.types.Scene.blendsolid_groove_corners = EnumProperty(name="Corners", items=CORNERS, default="mitre",
                                                             description="The Groove tool's sharp corners")
    bpy.utils.register_tool(GrooveTool, after={"blendsolid.sketch_tool"})
    bpy.utils.register_tool(ExtrudeTool, after={"blendsolid.groove_tool"})
    bpy.utils.register_tool(RevolveTool, after={"blendsolid.extrude_tool"})


def unregister():
    bpy.utils.unregister_tool(RevolveTool)
    bpy.utils.unregister_tool(ExtrudeTool)
    bpy.utils.unregister_tool(GrooveTool)
    for name in ("blendsolid_groove_profile", "blendsolid_groove_width", "blendsolid_groove_corners"):
        delattr(bpy.types.Scene, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
