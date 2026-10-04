"""Tool 5: Push/Pull. Drag a clicked flat face of a part along its normal: out adds a block (the face extruded),
in cuts one. One feature naming the face by its reference (ADR 0009), e.g.

    extrude(face("box_1", "+X"), amount=push_1_amount, mode=Mode.ADD)  # feature: push_1

The operator's properties describe the finished feature; execute() only reads them (the tool's modal ends by
calling it, Blender's redo re-runs it, tests call it). Curved faces are refused (offsetting them is v2).
"""
import bpy
from bpy.props import FloatProperty, StringProperty

from . import focus, part, primitives, script_model


def feature_spec(reference, amount):
    return primitives.push_spec(reference, amount)


def face_id_of(obj, reference):
    refs = obj.data.get(part.FACE_REFS_KEY) or []
    return list(refs).index(reference) if reference in refs else None


class BLENDSOLID_OT_push_pull(bpy.types.Operator):
    """Pull a flat face of a part out (adding a block) or push it in (cutting one)"""
    bl_idname = "blendsolid.push_pull"
    bl_label = "Push/Pull"
    bl_options = {"REGISTER", "UNDO"}

    target: StringProperty(name="Part", description="The part whose face is pushed or pulled")
    reference: StringProperty(name="Face", description="The face's reference, e.g. face(\"box_1\", \"+X\")")
    amount: FloatProperty(name="Distance", default=10.0, precision=3, step=100,
                          description="Millimetres along the face's normal: positive pulls out (adds), negative "
                                      "pushes in (cuts)")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "amount")

    def execute(self, context):
        from . import ui
        obj = part.local_part(self.target)
        if obj is None:
            self.report({"ERROR"}, f"There is no BlendSolid part named '{self.target}'")
            return {"CANCELLED"}
        if part.is_scaled(obj):
            self.report({"ERROR"}, part.scaled_message(obj))
            return {"CANCELLED"}
        blocked = part.blocking_error(obj)
        if blocked:
            self.report({"ERROR"}, blocked)
            return {"CANCELLED"}
        fid = face_id_of(obj, self.reference)
        if fid is not None and part.face_plane(obj, fid) is None:
            self.report({"ERROR"}, "Push/Pull works on flat faces only")
            return {"CANCELLED"}
        if not self.reference.strip() or abs(self.amount) < 1e-6:
            self.report({"ERROR"}, "Nothing to push or pull (no face, or a zero distance)")
            return {"CANCELLED"}
        try:
            source, name = script_model.append_feature(part.source_of(obj), feature_spec(self.reference, self.amount))
        except script_model.NotCanonical as e:
            self.report({"ERROR"}, part.not_canonical_message(obj, e, detail=ui.scripts_visible(context)))
            return {"CANCELLED"}
        obj.blendsolid_script.from_string(source)
        focus.set_focus(obj, name)  # ADR 0011
        return {"FINISHED"}


# -- the Push/Pull tool ---------------------------------------------------------------------------------------------

HOVER_COLOUR = (0.45, 0.8, 1.0, 0.9)
_dragging = set()


def _flat_pick(context, coord):
    """The flat CAD face under region coordinate `coord` (a picking.Pick of kind FACE), or None."""
    from . import ops_fillet
    found, _ = ops_fillet._mouse_pick(context, coord)
    if found is None:
        return None
    if found.kind == "EDGE":  # near an edge: the face it was hit on is still what Push/Pull wants
        from . import picking
        fid = _hit_face(context, coord)
        if fid is None:
            return None
        found = picking.Pick(found.obj, "FACE", fid, f"edges_of({part.face_reference(found.obj, fid)})",
                             picking.face_segments(found.obj, fid))
    if part.face_plane(found.obj, found.id) is None:
        return None
    return found


def _hit_face(context, coord):
    from . import ops_draw
    origin, direction = ops_draw.mouse_ray(context, coord)
    depsgraph = context.evaluated_depsgraph_get()
    hit = ops_draw._first_hit(context, depsgraph, origin, direction)
    return None if hit is None else part.face_id(hit[3].evaluated_get(depsgraph).data, hit[2])


class BLENDSOLID_OT_push_pull_drag(bpy.types.Operator):
    """Push/Pull tool: press on a flat face of a part and drag along its normal (out adds, in cuts); Ctrl snaps"""
    bl_idname = "blendsolid.push_pull_drag"
    bl_label = "Push/Pull Face"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        from mathutils import Vector, geometry
        from . import drawing
        if context.area is None or context.area.type != "VIEW_3D" or context.region_data is None:
            return {"CANCELLED"}
        found = _flat_pick(context, (event.mouse_region_x, event.mouse_region_y))
        if found is None:
            return {"PASS_THROUGH"}
        obj, fid = found.obj, found.id
        (nx, ny, nz), d = part.face_plane(obj, fid)
        self._factor = part.unit_factor(context.scene)
        from . import ops_draw
        origin, direction = ops_draw._mouse_ray(context, event)
        self._normal = (obj.matrix_world.to_3x3() @ Vector((nx, ny, nz))).normalized()
        # where the ray meets the face's exact plane: the drag measures along the normal from there
        hit = geometry.intersect_line_plane(origin, origin + direction,
                                            obj.matrix_world @ (Vector((nx, ny, nz)) * d * self._factor), self._normal)
        if hit is None:
            return {"CANCELLED"}
        x_axis = Vector((1, 0, 0)) if abs(self._normal.x) < 0.9 else Vector((0, 1, 0))
        self._plane, self._start = drawing._frame(hit, x_axis, self._normal), hit
        blocked = part.blocking_error(obj)
        if blocked:
            self.report({"ERROR"}, blocked)
            return {"CANCELLED"}
        self._target, self._reference = obj, part.face_reference(obj, fid)
        self._source, self._amount, self._snap = part.source_of(obj), 0.0, 0.0
        self._outline = found.segments
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
            context.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type in ops_draw.NAV_EVENTS:
            return {"PASS_THROUGH"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._target.blendsolid_script.from_string(self._source)
            return self._end(context, {"CANCELLED"})
        if event.type in {"MOUSEMOVE", "LEFT_CTRL", "RIGHT_CTRL", "LEFT_SHIFT", "RIGHT_SHIFT"}:
            self._update(context, event)
        elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._target.blendsolid_script.from_string(self._source)
            if abs(self._amount) < 1e-3:
                return self._end(context, {"CANCELLED"})  # a click without a drag
            try:
                bpy.ops.blendsolid.push_pull("EXEC_DEFAULT", True, target=self._target.name,
                                             reference=self._reference, amount=self._amount)
            except RuntimeError:  # refused: the operator reported why; the drag must still end cleanly
                return self._end(context, {"CANCELLED"})
            return self._end(context, {"FINISHED"})
        step = ops_draw.step_mm(context.scene)
        what = "pull out (add)" if self._amount >= 0 else "push in (cut)"
        context.area.header_text_set(f"Push/Pull: {abs(self._amount):.3f} mm, {what} | Ctrl: snap {step:g} mm "
                                     f"(Shift+Ctrl: {step / 10:g}) | Ctrl+Wheel: step | release: confirm | "
                                     "Esc/right-click: cancel")
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def _update(self, context, event):
        from . import drawing, ops_draw
        origin, direction = ops_draw._mouse_ray(context, event)
        amount = drawing.height_along_normal(self._plane, self._start, origin, direction) / self._factor
        step = ops_draw.step_mm(context.scene)
        self._snap = (step / 10 if event.shift else step) if event.ctrl else 0.0
        if self._snap:
            amount = drawing.snap(amount, self._snap)
        self._amount = amount
        if abs(amount) < 1e-3:
            self._target.blendsolid_script.from_string(self._source)
            return
        try:
            source, _ = script_model.append_feature(self._source, feature_spec(self._reference, amount))
        except script_model.NotCanonical:
            return
        self._target.blendsolid_script.from_string(source)  # the live preview: the worker recomputes it
        from . import runtime
        runtime.kick()  # submit it now, not at the next tick

    def _end(self, context, result):
        for handle in self._handles:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        self._handles = []
        _dragging.discard(id(self))
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()
        return result


PREVIEW_COLOUR = {True: (0.35, 0.9, 0.45, 1.0), False: (1.0, 0.35, 0.3, 1.0)}  # out (union) green, in (cut) red


def _draw_drag(op):
    """While dragging: the face's outline moved to the current distance (at once; the worker's result follows),
    lines from the face to it, and snap ticks along the normal."""
    from . import drawing, ops_draw
    try:
        amount, factor, snap, normal, start, outline = (op._amount, op._factor, op._snap, op._normal, op._start,
                                                        op._outline)
    except (ReferenceError, AttributeError):
        return
    context = bpy.context
    region = context.region
    pixel = ops_draw._pixel_size(region, context.region_data, start)
    if pixel is None:
        return
    ui = context.preferences.system.ui_scale or 1.0
    colour = PREVIEW_COLOUR[amount >= 0]
    offset = normal * (amount * factor)
    lines = [(a + offset, b + offset, colour, colour) for a, b in outline]
    lines += [(a, a + offset, colour, colour) for a, _ in outline[:: max(1, len(outline) // 8)]]
    if snap and snap * factor / pixel >= drawing.MIN_GRID_PX:
        ticks = drawing.height_ticks(op._plane, amount * factor, snap * factor, tick=14 * ui * pixel)
        lines += [(a, b, colour[:3] + (alpha,), colour[:3] + (alpha,)) for a, b, alpha in ticks]
    ops_draw._draw_segments(region, lines, 2.5 * ui)


def _draw_drag_label(op):
    try:
        amount, factor, snap, normal, start = op._amount, op._factor, op._snap, op._normal, op._start
    except (ReferenceError, AttributeError):
        return
    from . import drawing, ops_draw
    lines = [f"{'+' if amount >= 0 else '−'}{drawing.mm(abs(amount))} mm"] + ([f"snap {snap:g} mm"] if snap else [])
    ops_draw.draw_text_lines(bpy.context, start + normal * (amount * factor), lines)


class BLENDSOLID_GT_push_pull_hover(bpy.types.Gizmo):
    """The Push/Pull tool's overlay: the outline of the flat face under the mouse."""
    bl_idname = "BLENDSOLID_GT_push_pull_hover"

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
        found = _flat_pick(context, self.mouse)
        if found is not None:
            ui = context.preferences.system.ui_scale or 1.0
            ops_draw._draw_segments(context.region, [(a, b, HOVER_COLOUR, HOVER_COLOUR) for a, b in found.segments],
                                    3.0 * ui)


class BLENDSOLID_GGT_push_pull_hover(bpy.types.GizmoGroup):
    bl_idname = "BLENDSOLID_GGT_push_pull_hover"
    bl_label = "Push/Pull Overlay"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    def setup(self, context):
        from . import runtime
        runtime.warm_up()
        self.gizmos.new(BLENDSOLID_GT_push_pull_hover.bl_idname)


class PushPullTool(bpy.types.WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = "blendsolid.push_pull_tool"
    bl_label = "Push/Pull"
    bl_description = "Drag a flat face of a part along its normal: out adds a block, in cuts one; Ctrl: snap"
    bl_icon = "ops.mesh.extrude_region_move"
    bl_widget = "BLENDSOLID_GGT_push_pull_hover"
    bl_keymap = (
        ("blendsolid.push_pull_drag", {"type": "LEFTMOUSE", "value": "PRESS", "any": True}, None),
        ("blendsolid.snap_step", {"type": "WHEELUPMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", 1)]}),
        ("blendsolid.snap_step", {"type": "WHEELDOWNMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", -1)]}),
    )

    def draw_settings(context, layout, tool):
        layout.prop(context.scene, "blendsolid_snap_step", text="Snap")


CLASSES = [BLENDSOLID_OT_push_pull, BLENDSOLID_OT_push_pull_drag, BLENDSOLID_GT_push_pull_hover,
           BLENDSOLID_GGT_push_pull_hover]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.utils.register_tool(PushPullTool, after={"blendsolid.fillet_tool"})


def unregister():
    bpy.utils.unregister_tool(PushPullTool)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
