"""Tool 4: Fillet. Round (or chamfer) clicked CAD edges of a part: one feature naming them with the references the
worker wrote for them (ADR 0009), e.g.

    fillet(edge_between(face("box_1", "+Z"), face("box_1", "-Y")), radius=fillet_2_radius)  # feature: fillet_2

The operator's properties describe the finished feature (the part, the references, the radius and whether it is
a chamfer); execute() only reads them: the tool's modal ends by calling it, Blender's redo re-runs it with the
values of the Adjust Last Operation panel, and tests call it directly. OCCT spreads a fillet along the edges
tangent to the selected ones (it can't be turned off; research §3.1).
"""
import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty

from . import part, script_model


def _local_part(name):
    obj = bpy.data.objects.get((name, None)) if name else None
    return obj if part.is_local_part(obj) else None


def feature_spec(references, radius, chamfer=False):
    """The FeatureSpec of a fillet (or chamfer) of `references` (reference texts: edge_between(...),
    edges_of(face(...))): one call on their sum (build123d ShapeLists add up)."""
    joined = " + ".join(references)
    if chamfer:
        return script_model.FeatureSpec("chamfer", (("length", float(radius)),),
                                        f"chamfer({joined}, length={{name}}_length)")
    return script_model.FeatureSpec("fillet", (("radius", float(radius)),), f"fillet({joined}, radius={{name}}_radius)")


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

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "chamfer")
        layout.prop(self, "radius", text="Length" if self.chamfer else "Radius")

    def execute(self, context):
        from . import ui  # lazy, as in ops_draw
        obj = _local_part(self.target)
        if obj is None:
            self.report({"ERROR"}, f"There is no BlendSolid part named '{self.target}' to fillet")
            return {"CANCELLED"}
        if part.is_scaled(obj):
            self.report({"ERROR"}, part.scaled_message(obj))
            return {"CANCELLED"}
        refs = [r.strip() for r in self.references.splitlines() if r.strip()]
        if not refs:
            self.report({"ERROR"}, "Select one or more edges (or a face, for all its edges) to fillet")
            return {"CANCELLED"}
        try:
            source, _ = script_model.append_feature(part.source_of(obj),
                                                    feature_spec(refs, self.radius, self.chamfer))
        except script_model.NotCanonical as e:
            self.report({"ERROR"}, part.not_canonical_message(obj, e, detail=ui.scripts_visible(context)))
            return {"CANCELLED"}
        obj.blendsolid_script.from_string(source)
        return {"FINISHED"}


# -- the Fillet tool ------------------------------------------------------------------------------------------------

DRAG_PX = 5  # a press that moves farther than this (before the interface scale) is a radius drag, not a click
HOVER_COLOUR = (0.45, 0.8, 1.0, 0.9)
SELECTED_COLOUR = (1.0, 0.55, 0.1, 1.0)
_selection = {"part": None, "refs": []}  # reference texts: they survive recomputes (the ids don't)
_dragging = set()  # the tool's modals in progress (the hover overlay hides meanwhile)


def selection(context=None):
    """(part, [reference texts]) the Fillet tool has selected, or (None, []) if its part is gone."""
    obj = _local_part(_selection["part"])
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
    from bpy_extras import view3d_utils
    from . import ops_draw, picking
    region, rv3d = context.region, context.region_data
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    hit = ops_draw._first_hit(context, context.evaluated_depsgraph_get(), origin, direction)
    if hit is None:
        return None, None
    pixel = ops_draw._pixel_size(region, rv3d, hit[0])
    return (picking.pick(context, origin, direction, pixel) if pixel else None), pixel


class BLENDSOLID_OT_fillet_click(bpy.types.Operator):
    """Fillet tool: click an edge (Shift: add or remove it), a face for all its edges, or empty space to clear;
    press and drag to set the radius of the selected edges"""
    bl_idname = "blendsolid.fillet_click"
    bl_label = "Fillet Edges"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.region_data is None:
            return {"CANCELLED"}
        self._press = (event.mouse_region_x, event.mouse_region_y)
        self._pick, self._pixel = _mouse_pick(context, self._press)
        self._extend = event.shift
        self._source = self._target = None
        self._radius, self._chamfer = 0.0, False
        self._factor = part.unit_factor(context.scene)
        _dragging.add(id(self))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        from . import ops_draw
        if event.type in ops_draw.NAV_EVENTS:
            return {"PASS_THROUGH"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._restore()
            return self._end(context, {"CANCELLED"})
        if event.type == "C" and event.value == "PRESS" and self._source is not None:
            self._chamfer = not self._chamfer
            self._preview(context, event)
        elif event.type in {"MOUSEMOVE", "LEFT_CTRL", "RIGHT_CTRL"}:
            ui = (context.preferences.system.ui_scale or 1.0)
            moved = ((event.mouse_region_x - self._press[0]) ** 2 + (event.mouse_region_y - self._press[1]) ** 2) ** 0.5
            if self._source is None and moved > DRAG_PX * ui:
                self._start_drag()
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

    def _start_drag(self):
        """Start a radius drag: from a pick outside the selection, that pick is the selection (Plasticity: drag
        an edge to fillet it); from empty space, the selection as it is."""
        if self._pick is not None and (self._pick.obj.name != _selection["part"]
                                       or self._pick.reference not in _selection["refs"]):
            select(self._pick, extend=self._extend)
        obj, refs = selection()
        if obj is None or not refs or self._pixel is None:
            return False
        self._target, self._source = obj, part.source_of(obj)
        return True

    def _preview(self, context, event):
        """Rewrite the part's script with the fillet at the current radius (no undo step: the release replaces
        it with the operator's own edit); the worker recomputes it like any script change."""
        from . import ops_draw
        dx, dy = event.mouse_region_x - self._press[0], event.mouse_region_y - self._press[1]
        radius = (dx * dx + dy * dy) ** 0.5 * self._pixel / self._factor
        if event.ctrl:
            step = ops_draw.step_mm(context.scene)
            radius = max(ops_draw.drawing.snap(radius, step), step)
        self._radius = max(radius, 0.001)
        _, refs = selection()
        try:
            source, _ = script_model.append_feature(self._source, feature_spec(refs, self._radius, self._chamfer))
        except script_model.NotCanonical:
            return
        self._target.blendsolid_script.from_string(source)

    def _restore(self):
        if self._source is not None and self._target is not None:
            self._target.blendsolid_script.from_string(self._source)

    def _header(self, context):
        if self._source is None:
            return
        what = "chamfer" if self._chamfer else "radius"
        context.area.header_text_set(f"Fillet: {what} {self._radius:.3f} mm | C: fillet/chamfer | Ctrl: snap "
                                     f"{self._step(context):g} mm | release: confirm | Esc/right-click: cancel")

    @staticmethod
    def _step(context):
        from . import ops_draw
        return ops_draw.step_mm(context.scene)

    def _end(self, context, result):
        _dragging.discard(id(self))
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()
        return result


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
                      "C while dragging: chamfer; Ctrl: snap the radius")
    bl_icon = "ops.mesh.bevel"
    bl_widget = "BLENDSOLID_GGT_fillet_hover"
    bl_keymap = (
        ("blendsolid.fillet_click", {"type": "LEFTMOUSE", "value": "PRESS", "any": True}, None),
        ("blendsolid.fillet_clear", {"type": "ESC", "value": "PRESS"}, None),
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
