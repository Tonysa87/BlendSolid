"""Tool 4: Fillet. Round (or chamfer) clicked CAD edges of a part: one feature naming them with the references the
worker wrote for them (ADR 0009), e.g.

    fillet(edge_between(face("box_1", "+Z"), face("box_1", "-Y")), radius=fillet_2_radius)  # feature: fillet_2

The operator's properties describe the finished feature (the part, the references, the radius and whether it is
a chamfer); execute() only reads them: the tool's modal ends by calling it, Blender's redo re-runs it with the
values of the Adjust Last Operation panel, and tests call it directly. OCCT spreads a fillet along the edges
tangent to the selected ones (it can't be turned off; research §3.1).
"""
import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from mathutils import Matrix

from . import focus, part, primitives, script_model


def feature_spec(references, radius, chamfer=False, length2=None, angle=None, side=None):
    return primitives.blend_spec(references, radius, chamfer, length2, angle, side)


CHAMFER_MODES = [  # Fusion 360 and Onshape's chamfer types (research: docs/research/2026-09-29-chamfer-options.md)
    ("EQUAL", "Equal Distance", "The same length along both faces"),
    ("TWO", "Two Distances", "One length along the first face, another along the second"),
    ("ANGLE", "Distance and Angle", "A length along the first face and the chamfer's angle to that face"),
]


class BLENDSOLID_OT_fillet(bpy.types.Operator):
    """Round (or chamfer) edges of a part, named by references its script can resolve"""
    bl_idname = "blendsolid.fillet"
    bl_label = "Fillet"
    bl_options = {"REGISTER", "UNDO"}

    target: StringProperty(name="Part", description="The part whose edges are rounded")
    references: StringProperty(name="Edges", description="The references of the edges, one per line "
                                                         "(edge_between(...), edges_of(face(...)))")
    radius: FloatProperty(name="Radius", default=2.0, min=0.001, precision=3, step=10,
                          description="Fillet radius, or chamfer length, in millimetres")
    chamfer: BoolProperty(name="Chamfer", default=False, description="A flat chamfer instead of a round fillet")
    chamfer_mode: EnumProperty(name="Type", items=CHAMFER_MODES, default="EQUAL",
                               description="How the chamfer's size is given")
    length2: FloatProperty(name="Length 2", default=2.0, min=0.001, precision=3, step=10,
                           description="The chamfer's length along the second face, in millimetres")
    angle: FloatProperty(name="Angle", default=45.0, min=0.1, max=89.9, precision=2, step=100,
                         description="The chamfer's angle to the first face, in degrees")
    flip: BoolProperty(name="Flip", default=False,
                       description="Measure the first length on the other face")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "chamfer")
        if self.chamfer:
            layout.prop(self, "chamfer_mode")
        layout.prop(self, "radius", text=("Length" if self.chamfer_mode == "EQUAL" else "Length 1") if self.chamfer
                    else "Radius")
        if self.chamfer and self.chamfer_mode == "TWO":
            layout.prop(self, "length2")
        elif self.chamfer and self.chamfer_mode == "ANGLE":
            layout.prop(self, "angle")
        if self.chamfer and self.chamfer_mode != "EQUAL":
            layout.prop(self, "flip")

    def _chamfer_side(self, obj, refs):
        """(length, length2, angle, side face text) of an asymmetric chamfer, or an error message. The first
        length is measured on a face every selected edge lies on; Flip takes the other one (a single edge's two
        faces), or, for edges sharing one face only, swaps the two distances."""
        length, length2, angle = self.radius, None, None
        if self.chamfer_mode == "TWO":
            length2 = self.length2
        else:
            angle = self.angle
        sides = primitives.common_faces(refs)
        if not sides:
            return ("Two Distances and Distance and Angle measure the first length on a face all the edges lie on, "
                    "and these edges share none: chamfer them one face at a time")
        if not self.flip:
            return length, length2, angle, sides[0]
        if len(sides) > 1:
            return length, length2, angle, sides[1]
        if length2 is not None:
            return length2, length, None, sides[0]
        return ("Flip measures the length on the other face, and these edges have different other faces: select "
                "one edge, or use Two Distances")

    def execute(self, context):
        from . import ui  # lazy, as in ops_draw
        obj = part.local_part(self.target)
        if obj is None:
            self.report({"ERROR"}, f"There is no BlendSolid part named '{self.target}' to fillet")
            return {"CANCELLED"}
        if part.is_scaled(obj):
            self.report({"ERROR"}, part.scaled_message(obj))
            return {"CANCELLED"}
        blocked = part.blocking_error(obj)
        if blocked:
            self.report({"ERROR"}, blocked)
            return {"CANCELLED"}
        refs = [r.strip() for r in self.references.splitlines() if r.strip()]
        if not refs:
            self.report({"ERROR"}, "Select one or more edges (or a face, for all its edges) to fillet")
            return {"CANCELLED"}
        length, length2, angle, side = self.radius, None, None, None
        if self.chamfer and self.chamfer_mode != "EQUAL":
            chosen = self._chamfer_side(obj, refs)
            if isinstance(chosen, str):
                self.report({"ERROR"}, chosen)
                return {"CANCELLED"}
            length, length2, angle, side = chosen
        try:
            source, name = script_model.append_feature(part.source_of(obj),
                                                       feature_spec(refs, length, self.chamfer, length2, angle, side))
        except script_model.NotCanonical as e:
            self.report({"ERROR"}, part.not_canonical_message(obj, e, detail=ui.scripts_visible(context)))
            return {"CANCELLED"}
        obj.blendsolid_script.from_string(source)
        focus.set_focus(obj, name)  # a fillet has no arrows: the view is left clean (ADR 0011)
        return {"FINISHED"}


# -- the Fillet tool ------------------------------------------------------------------------------------------------

DRAG_PX = 5  # a press that moves farther than this (before the interface scale) is a radius drag, not a click
HOVER_COLOUR = (0.45, 0.8, 1.0, 0.9)
SELECTED_COLOUR = (1.0, 0.55, 0.1, 1.0)
_selection = {"part": None, "refs": []}  # reference texts: they survive recomputes (the ids don't)
_dragging = set()  # the tool's modals in progress (the hover overlay hides meanwhile)


def selection(context=None):
    """(part, [reference texts]) the Fillet tool has selected, or (None, []) if its part is gone."""
    obj = part.local_part(_selection["part"])
    return (obj, list(_selection["refs"])) if obj is not None else (None, [])


def select(pick, extend=False):
    """Apply a click: a new selection of `pick` (None clears), or with `extend` toggle it in the selection (a
    pick on another part starts over)."""
    if pick is None:
        if not extend:
            _selection.update(part=None, refs=[])
        return
    if not extend or _selection["part"] != pick.obj.name:
        _selection.update(part=pick.obj.name, refs=[pick.reference])
    elif pick.reference in _selection["refs"]:
        _selection["refs"].remove(pick.reference)
    else:
        _selection["refs"].append(pick.reference)


def _mouse_pick(context, coord):
    from . import ops_draw, picking
    region, rv3d = context.region, context.region_data
    origin, direction = ops_draw.mouse_ray(context, coord)
    hit = ops_draw._first_hit(context, context.evaluated_depsgraph_get(), origin, direction)
    if hit is None:
        return None, None
    pixel = ops_draw._pixel_size(region, rv3d, hit[0])
    return (picking.pick(context, origin, direction, pixel) if pixel else None), pixel


ARROW_PX = 40  # the drag handle's length on screen (before the interface scale) when no radius is set yet
ARROW_COLOUR = (1.0, 0.85, 0.3, 1.0)


def anchor(obj, reference):
    """(midpoint, direction, frame) of the drag handle of `reference`'s middle segment (see drawing.fillet_handle),
    or None; `frame` is a matrix whose Z is the direction (for drawing.height_along_normal/height_ticks)."""
    from . import drawing, picking
    frames = picking.edge_frames(obj, reference)
    if not frames:
        return None
    a, b, n1, n2, _, _ = frames[len(frames) // 2]
    mid, w = drawing.fillet_handle(a, b, n1, n2)
    return mid, w, drawing._frame(mid, (b - a) if (b - a).length > 0 else w.orthogonal(), w)


def arrow_lines(mid, w, length, pixel, colour, region=None, rv3d=None, min_px=0):
    """The handle: a shaft from the edge along `w` and a head (world segments with colours). With the view, the
    shaft is lengthened to at least `min_px` pixels on screen: the handle often points almost at the viewer."""
    ratio = 1.0
    if region is not None:
        from bpy_extras import view3d_utils
        a = view3d_utils.location_3d_to_region_2d(region, rv3d, mid)
        b = view3d_utils.location_3d_to_region_2d(region, rv3d, mid + w * pixel)
        if a is not None and b is not None:
            ratio = max((b - a).length, 0.15)  # pixels on screen per pixel-size step along w
        length = max(length, min_px * pixel / ratio)
    tip = mid + w * length
    head = 14 * pixel / ratio
    back = tip - w * head
    side = w.orthogonal().normalized() * (7 * pixel / ratio ** 0.5)
    out = [(mid, tip, colour, colour)]
    for k in range(6):  # a small cone of strokes: visible from any side
        out.append((tip, back + Matrix.Rotation(k * math.pi / 3, 3, w) @ side, colour, colour))
    return out


def preview_lines(obj, refs, size_mm, chamfer, factor, colour):
    """The immediate preview of a fillet/chamfer of `refs` at `size_mm` (drawing.fillet_preview per segment)."""
    from . import drawing, picking
    out = []
    for ref in refs:
        for a, b, n1, n2, c1, c2 in picking.edge_frames(obj, ref):
            out += [(p, q, colour, colour) for p, q in drawing.fillet_preview(a, b, n1, n2, c1, c2, size_mm * factor,
                                                                              chamfer, arc_segments=8)]
    return out


def too_large_limit(error):
    """The largest working size (mm) in the worker's "... is too large for ...: the largest that works is X mm"
    message, or None for any other error."""
    import re
    found = re.search(r"too large for .*: the largest that works is ([0-9.]+) mm", error.splitlines()[0] if error
                      else "")
    return float(found.group(1)) if found and float(found.group(1)) > 0 else None


def header_error(obj):
    """The part's current error for the drag's header (" | can't: ..."), e.g. the worker's "fillet radius 16 mm
    is too large for these 4 edges: the largest that works is 14.996 mm"; "" when it builds."""
    error = obj.blendsolid_error.splitlines()[0] if obj is not None and obj.blendsolid_error else ""
    return f" | can't: {error}" if error else ""


class BLENDSOLID_OT_fillet_click(bpy.types.Operator):
    """Fillet tool: click an edge (Shift: add or remove it), a face for all its edges, or empty space to clear;
    press and drag along the arrow to set the radius of the selected edges"""
    bl_idname = "blendsolid.fillet_click"
    bl_label = "Fillet Edges"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.region_data is None:
            return {"CANCELLED"}
        self._press = (event.mouse_region_x, event.mouse_region_y)
        self._pick, self._pixel = _mouse_pick(context, self._press)
        from . import picking
        if self._pick is not None and self._pick.kind == "EDGE" and not picking.edge_is_sharp(self._pick.obj,
                                                                                               self._pick.id):
            # OCCT drops it silently among others, or fails alone (research: fillet edge cases, T10)
            self.report({"WARNING"}, "This edge is between tangent faces: there is nothing to round")
            return {"CANCELLED"}
        self._extend = event.shift
        self._source = self._target = self._anchor = None
        self._radius, self._chamfer, self._snap, self._start = 0.0, False, 0.0, 0.0
        self._limit = None  # the largest size the worker found working while dragging: the drag stops there
        self._factor = part.unit_factor(context.scene)
        self._handles = []
        _dragging.add(id(self))
        # the worker's result (or error) arrives between mouse events: the header follows it
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        from . import ops_draw
        if event.type in ops_draw.WHEEL and event.ctrl and event.value == "PRESS":
            ops_draw.change_step(context.scene, ops_draw.WHEEL[event.type])
            if self._source is not None:
                self._preview(context, event)
            self._header(context)
            context.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type in ops_draw.NAV_EVENTS:
            return {"PASS_THROUGH"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._restore()
            return self._end(context, {"CANCELLED"})
        if event.type == "TIMER":
            self._check_limit()
        elif event.type == "C" and event.value == "PRESS" and self._source is not None:
            self._chamfer = not self._chamfer
            self._limit = None  # a chamfer's limit is another one
            self._preview(context, event)
        elif event.type in {"MOUSEMOVE", "LEFT_CTRL", "RIGHT_CTRL", "LEFT_SHIFT", "RIGHT_SHIFT"}:
            ui = context.preferences.system.ui_scale or 1.0
            moved = ((event.mouse_region_x - self._press[0]) ** 2 + (event.mouse_region_y - self._press[1]) ** 2) ** 0.5
            if self._source is None and moved > DRAG_PX * ui:
                self._start_drag(context, event)
                if getattr(self, "_blocked", None):
                    self.report({"ERROR"}, self._blocked)
                    return self._end(context, {"CANCELLED"})
            if self._source is not None:
                self._preview(context, event)
        elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if self._source is None:  # a click: change the selection
                select(self._pick, self._extend)
                return self._end(context, {"FINISHED"})
            self._restore()
            obj, refs = selection()
            bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target=obj.name, references="\n".join(refs),
                                      radius=max(self._radius, 0.001), chamfer=self._chamfer)
            return self._end(context, {"FINISHED"})
        self._header(context)
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def _start_drag(self, context, event):
        """Start a radius drag: from a pick outside the selection, that pick is the selection (Plasticity: drag
        an edge to fillet it); from elsewhere, the selection as it is. The radius is measured along the handle
        of the edge pressed on (else the first selected one)."""
        if self._pick is not None and (self._pick.obj.name != _selection["part"]
                                       or self._pick.reference not in _selection["refs"]):
            select(self._pick, extend=self._extend)
        obj, refs = selection()
        if obj is None or not refs:
            return
        self._blocked = part.blocking_error(obj)
        if self._blocked:
            return
        ref = self._pick.reference if self._pick is not None and self._pick.reference in refs else refs[0]
        self._anchor = anchor(obj, ref)
        if self._anchor is None:
            return
        from . import drawing, ops_draw
        origin, direction = ops_draw.mouse_ray(context, self._press)
        self._start = drawing.height_along_normal(self._anchor[2], self._anchor[0], origin, direction)
        self._target, self._source = obj, part.source_of(obj)
        self._handles = [bpy.types.SpaceView3D.draw_handler_add(_draw_drag, (self,), "WINDOW", "POST_VIEW"),
                         bpy.types.SpaceView3D.draw_handler_add(_draw_drag_label, (self,), "WINDOW", "POST_PIXEL")]

    def _preview(self, context, event):
        """The radius along the handle; the immediate overlay redraws with it, and the part's script is rewritten
        with the fillet at that radius (no undo step: the release replaces it with the operator's own edit) and
        submitted at once: the worker's real result follows the overlay."""
        from . import drawing, ops_draw
        origin, direction = ops_draw.mouse_ray(context, (event.mouse_region_x, event.mouse_region_y))
        mid, _, frame = self._anchor
        radius = (drawing.height_along_normal(frame, mid, origin, direction) - self._start) / self._factor
        step = ops_draw.step_mm(context.scene)
        self._snap = (step / 10 if event.shift else step) if event.ctrl else 0.0
        if self._snap:
            radius = max(drawing.snap(radius, self._snap), self._snap)
        self._wanted = max(radius, 0.001)
        self._write(min(self._wanted, self._limit) if self._limit else self._wanted)

    def _check_limit(self):
        """When the worker answers that the size is too large for these edges, the drag stops at the largest
        size that works (it bisects it, worker/blends.py): a drag never leaves a fillet that can't be built."""
        obj = self._target
        if self._source is None or obj is None or not obj.blendsolid_error \
                or part.error_tag(obj) != part.current_tag(obj):
            return
        limit = too_large_limit(obj.blendsolid_error)
        if limit is None or (self._limit is not None and limit >= self._limit):
            return
        self._limit = limit
        if self._radius > limit:
            self._write(limit)

    def _write(self, radius):
        from . import runtime
        self._radius = radius
        _, refs = selection()
        try:
            source, _ = script_model.append_feature(self._source, feature_spec(refs, self._radius, self._chamfer))
        except script_model.NotCanonical:
            return
        self._target.blendsolid_script.from_string(source)
        runtime.kick()  # submit the preview now, not at the next tick

    def _restore(self):
        if self._source is not None and self._target is not None:
            self._target.blendsolid_script.from_string(self._source)

    def _header(self, context):
        if self._source is None:
            return
        from . import ops_draw
        step = ops_draw.step_mm(context.scene)
        what = "chamfer" if self._chamfer else "radius"
        error = header_error(self._target)
        if self._limit is not None and self._radius >= self._limit:
            error = f" (the largest that works: {self._limit:g} mm)"
        context.area.header_text_set(f"Fillet: {what} {self._radius:.3f} mm{error} | drag along the arrow"
                                     f" | C: fillet/chamfer | Ctrl: snap {step:g} mm (Shift+Ctrl: {step / 10:g})"
                                     " | Ctrl+Wheel: step | release: confirm | Esc/right-click: cancel")

    def _end(self, context, result):
        if getattr(self, "_timer", None) is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        for handle in self._handles:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        self._handles = []
        _dragging.discard(id(self))
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()
        return result


def _draw_drag(op):
    """While dragging: the fillet's immediate preview, the handle out to the radius, and snap ticks along it."""
    from . import drawing, ops_draw
    try:
        mid, w, frame = op._anchor
        radius, factor, snap, obj = op._radius, op._factor, op._snap, op._target
    except (ReferenceError, AttributeError, TypeError):
        return
    context = bpy.context
    region, rv3d = context.region, context.region_data
    pixel = ops_draw._pixel_size(region, rv3d, mid)
    if pixel is None:
        return
    ui = context.preferences.system.ui_scale or 1.0
    _, refs = selection()
    lines = preview_lines(obj, refs, radius, op._chamfer, factor, SELECTED_COLOUR)
    lines += arrow_lines(mid, w, radius * factor + 12 * ui * pixel, pixel * ui, ARROW_COLOUR, region, rv3d,
                         ARROW_PX * ui)
    if snap and snap * factor / pixel >= drawing.MIN_GRID_PX:
        ticks = drawing.height_ticks(frame, radius * factor, snap * factor, tick=14 * ui * pixel)
        lines += [(a, b, ARROW_COLOUR[:3] + (alpha,), ARROW_COLOUR[:3] + (alpha,)) for a, b, alpha in ticks]
    ops_draw._draw_segments(region, lines, 3.0 * ui)


def _draw_drag_label(op):
    try:
        mid, w, _ = op._anchor
        radius, factor, snap, chamfer = op._radius, op._factor, op._snap, op._chamfer
    except (ReferenceError, AttributeError, TypeError):
        return
    from . import drawing, ops_draw
    limit = getattr(op, "_limit", None)
    lines = [f"{'C' if chamfer else 'R'} {drawing.mm(radius)} mm" + (" (max)" if limit and radius >= limit else "")]
    lines += [f"snap {snap:g} mm"] if snap else []
    ops_draw.draw_text_lines(bpy.context, mid + w * radius * factor, lines)


class BLENDSOLID_OT_fillet_clear(bpy.types.Operator):
    """Clear the Fillet tool's selection"""
    bl_idname = "blendsolid.fillet_clear"
    bl_label = "Clear Fillet Selection"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        select(None)
        if context.area is not None:
            context.area.tag_redraw()
        return {"FINISHED"}


class BLENDSOLID_GT_fillet_hover(bpy.types.Gizmo):
    """The Fillet tool's overlay: the edge (or the face's edges) under the mouse and the selected edges."""
    bl_idname = "BLENDSOLID_GT_fillet_hover"

    def setup(self):
        self.mouse = None

    def test_select(self, context, location):
        self.mouse = tuple(location)
        context.area.tag_redraw()
        return -1  # never "selected": the click goes to the tool's keymap

    def draw(self, context):
        from . import ops_draw, picking
        if context.region_data is None:
            return
        ui = context.preferences.system.ui_scale or 1.0
        lines = []
        obj, refs = selection()
        for ref in refs:
            lines += [(a, b, SELECTED_COLOUR, SELECTED_COLOUR) for a, b in picking.segments_of(obj, ref)]
        if refs and not _dragging:  # where to drag: the first selected edge's handle
            handle = anchor(obj, refs[0])
            pixel = handle and ops_draw._pixel_size(context.region, context.region_data, handle[0])
            if pixel:
                lines += arrow_lines(handle[0], handle[1], ARROW_PX * ui * pixel, pixel * ui, ARROW_COLOUR,
                                     context.region, context.region_data, ARROW_PX * ui)
        if self.mouse is not None and not _dragging:
            found, _ = _mouse_pick(context, self.mouse)
            if found is not None:
                lines += [(a, b, HOVER_COLOUR, HOVER_COLOUR) for a, b in found.segments]
        ops_draw._draw_segments(context.region, lines, 3.0 * ui)


class BLENDSOLID_GGT_fillet_hover(bpy.types.GizmoGroup):
    bl_idname = "BLENDSOLID_GGT_fillet_hover"
    bl_label = "Fillet Overlay"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    def setup(self, context):
        from . import runtime
        runtime.warm_up()
        self.gizmos.new(BLENDSOLID_GT_fillet_hover.bl_idname)


class FilletTool(bpy.types.WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = "blendsolid.fillet_tool"
    bl_label = "Fillet"
    bl_description = ("Click edges of a part (Shift: add), or a face for all its edges, then drag to round them; "
                      "C while dragging: chamfer (two distances, distance and angle, Flip: Adjust Last Operation "
                      "panel); Ctrl: snap the radius")
    bl_icon = "ops.mesh.bevel"
    bl_widget = "BLENDSOLID_GGT_fillet_hover"
    bl_keymap = (
        ("blendsolid.fillet_click", {"type": "LEFTMOUSE", "value": "PRESS", "any": True}, None),
        ("blendsolid.fillet_clear", {"type": "ESC", "value": "PRESS"}, None),
        ("blendsolid.snap_step", {"type": "WHEELUPMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", 1)]}),
        ("blendsolid.snap_step", {"type": "WHEELDOWNMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", -1)]}),
    )

    def draw_settings(context, layout, tool):
        layout.prop(context.scene, "blendsolid_snap_step", text="Snap")


CLASSES = [BLENDSOLID_OT_fillet, BLENDSOLID_OT_fillet_click, BLENDSOLID_OT_fillet_clear, BLENDSOLID_GT_fillet_hover,
           BLENDSOLID_GGT_fillet_hover]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.utils.register_tool(FilletTool, after={"blendsolid.draw_solid_tool"})


def unregister():
    bpy.utils.unregister_tool(FilletTool)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    select(None)
