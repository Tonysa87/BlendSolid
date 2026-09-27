"""Tool 2: Draw Solid. Draw a box or a cylinder on a part's face or on the 3D cursor's plane; on a part, the
direction of the height picks the boolean (out of the face: union, into it: cut); elsewhere it makes a new part.

The operator's properties describe the finished solid (shape, mode, the part it is drawn on, placement and
dimensions in millimetres), and execute() only reads them: the interactive modal sets them and ends by calling
execute(), Blender's redo re-runs execute() with the values edited in the Adjust Last Operation panel, and
tests call it directly. The result is one feature with a fixed placement (a Location in the part's frame).
"""
import dataclasses
import json
import math
import struct

import bpy
from bpy.props import EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector

from . import drawing, ops_add, part, primitives, script_model, trust

SHAPES = [("BOX", "Box", "Draw a box", "MESH_CUBE", 0),
          ("CYLINDER", "Cylinder", "Draw a cylinder", "MESH_CYLINDER", 1)]
MODES = [("NEW", "New Part", "Make a new part", "ADD", 0),
         ("UNION", "Union", "Add the solid to the part it is drawn on", "SELECT_EXTEND", 1),
         ("CUT", "Cut", "Cut the solid out of the part it is drawn on", "SELECT_SUBTRACT", 2)]
KIND = {"BOX": "box", "CYLINDER": "cylinder"}
COLORS = {"UNION": (0.35, 0.9, 0.45, 1.0), "CUT": (1.0, 0.35, 0.3, 1.0), "NEW": (0.35, 0.65, 1.0, 1.0)}
MIN_MM = 0.001  # matches the size properties' `min`: a drag under this is treated as no drag at all
WHEEL = {"WHEELUPMOUSE": 1, "WHEELDOWNMOUSE": -1}  # Ctrl+Wheel: next / previous snap step
STEP_ITEMS = [(f"{v:g}", f"{v:g} mm", f"Snap to {v:g} mm (Shift+Ctrl: {v / 10:g} mm)") for v in drawing.STEPS]
NAV_EVENTS = {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE", "TRACKPADPAN",
             "TRACKPADZOOM", "NDOF_MOTION"}  # viewport navigation: never swallowed by the modal


def step_mm(scene):
    return float(scene.blendsolid_snap_step)


def change_step(scene, direction):
    scene.blendsolid_snap_step = f"{drawing.next_step(step_mm(scene), direction):g}"
    return step_mm(scene)


def _f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


def _local_part(name):
    obj = bpy.data.objects.get((name, None)) if name else None
    return obj if part.is_local_part(obj) else None


class BLENDSOLID_OT_draw_solid(bpy.types.Operator):
    """Draw a box or cylinder on a part's face (union or cut, by the direction of its height) or on the 3D
    cursor's plane (a new part)"""
    bl_idname = "blendsolid.draw_solid"
    bl_label = "Draw Solid"
    bl_options = {"REGISTER", "UNDO"}

    shape: EnumProperty(name="Shape", items=SHAPES, default="BOX")
    mode: EnumProperty(name="Mode", items=MODES, default="NEW")
    target: StringProperty(name="Part", description="The part the solid is drawn on; its placement is in that "
                                                    "part's frame (empty: in the world)")
    location: FloatVectorProperty(name="Location", size=3, precision=3,
                                  description="Centre of the solid's base, millimetres")
    rotation: FloatVectorProperty(name="Rotation", size=3, subtype="EULER",
                                  description="Orientation of the base (build123d Location angles)")
    length: FloatProperty(name="Length", default=10.0, min=0.001, precision=3, step=100)
    width: FloatProperty(name="Width", default=10.0, min=0.001, precision=3, step=100)
    radius: FloatProperty(name="Radius", default=5.0, min=0.001, precision=3, step=100)
    height: FloatProperty(name="Height", default=10.0, min=0.001, precision=3, step=100)
    # Float properties are float32: the exact (float64) placement of a drawing, used while location and
    # rotation still hold its float32 rounding (edited by hand in the redo panel, they win).
    exact: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "shape")
        layout.prop(self, "mode")
        layout.prop(self, "target")
        layout.label(text="Millimetres, in the part's frame (the world's when no part)")
        for name in (("length", "width") if self.shape == "BOX" else ("radius",)) + ("height",):
            layout.prop(self, name)
        layout.prop(self, "location")
        layout.prop(self, "rotation")

    def _values(self):
        if self.shape == "BOX":
            return {"length": self.length, "width": self.width, "height": self.height}
        return {"radius": self.radius, "height": self.height}

    def execute(self, context):
        from . import ui  # lazy: ui.py itself imports ops_add/runtime lazily to avoid import cycles
        factor = part.unit_factor(context.scene)
        reference = _local_part(self.target)
        if self.target and reference is None:
            self.report({"ERROR"}, f"There is no BlendSolid part named '{self.target}' to draw on")
            return {"CANCELLED"}
        if self.mode != "NEW" and reference is None:
            self.report({"ERROR"}, "Union and Cut need the part the solid is drawn on")
            return {"CANCELLED"}
        if reference is not None and part.is_scaled(reference):
            self.report({"ERROR"}, part.scaled_message(reference))
            return {"CANCELLED"}
        kind = KIND[self.shape]
        location, rotation = self._placement()
        frame = drawing.frame_matrix(location, rotation, factor)
        if self.mode == "NEW":
            matrix = (reference.matrix_world if reference is not None else Matrix.Identity(4)) @ frame
            ops_add.add_primitive_part(context, kind, self._values(), matrix=matrix)
            return {"FINISHED"}
        spec = primitives.feature_spec(
            kind, self._values(), mode="ADD" if self.mode == "UNION" else "SUBTRACT",
            align=primitives.BASE if self.mode == "UNION" else primitives.TOP,
            location=location, rotation=tuple(math.degrees(a) for a in rotation))
        try:
            source, _ = script_model.append_feature(part.source_of(reference), spec)
        except script_model.NotCanonical as e:
            self.report({"ERROR"}, part.not_canonical_message(reference, e, detail=ui.scripts_visible(context)))
            return {"CANCELLED"}
        reference.blendsolid_script.from_string(source)
        return {"FINISHED"}

    def _placement(self):
        """(location mm, rotation radians): the exact ones while the float32 properties still match them."""
        location, rotation = tuple(self.location), tuple(self.rotation)
        if self.exact:
            try:
                e = json.loads(self.exact)
                if (all(_f32(a) == b for a, b in zip(e["location"], location))
                        and all(_f32(a) == b for a, b in zip(e["rotation"], rotation))):
                    return tuple(e["location"]), tuple(e["rotation"])
            except (ValueError, KeyError, TypeError):
                pass
        return location, rotation

    # -- interactive drawing (the Draw Solid tool's left click) ---------------------------------------------------

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.region_data is None:
            return {"CANCELLED"}
        self.shape = context.scene.blendsolid_draw_shape
        origin, direction = _mouse_ray(context, event)
        near = _near_rays(context, (event.mouse_region_x, event.mouse_region_y)) if context.region else ()
        self._plane, self._target, self._local = pick(context, origin, direction, near=near)
        p = drawing.plane_coords(self._plane, origin, direction)
        if p is None:
            return {"CANCELLED"}
        self._p0 = self._p1 = p
        self._stage, self._drawn, self._base = "BASE", None, None
        self._factor = part.unit_factor(context.scene)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(_draw_preview, (self,), "WINDOW", "POST_VIEW")
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in WHEEL and event.ctrl and event.value == "PRESS":
            change_step(context.scene, WHEEL[event.type])
            self._update(context, event)
            self._header(context)
            context.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type in NAV_EVENTS:
            return {"PASS_THROUGH"}  # let the viewport orbit/zoom/pan while the modal keeps running
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish(context)
            return {"CANCELLED"}
        if event.type in {"MOUSEMOVE", "LEFT_CTRL", "RIGHT_CTRL", "LEFT_SHIFT", "RIGHT_SHIFT"}:
            self._update(context, event)
        elif event.type == "LEFTMOUSE" and event.value == "RELEASE" and self._stage == "BASE":
            self._update(context, event)
            d = self._drawn
            if d is None or (d.radius < MIN_MM if d.shape == "CYLINDER" else min(d.length, d.width) < MIN_MM):
                self._finish(context)
                return {"CANCELLED"}  # a click without a drag (or a sub-millimetre one): nothing drawn
            self._stage, self._base = "HEIGHT", d  # the base is final (snapped as it was on release)
        elif event.type == "LEFTMOUSE" and event.value == "PRESS" and self._stage == "HEIGHT":
            self._update(context, event)
            self._finish(context)
            if abs(self._drawn.height) < MIN_MM:
                self.report({"WARNING"}, "The solid has no height: nothing drawn")
                return {"CANCELLED"}
            for key, value in drawn_properties(self._drawn, self._target, self._factor).items():
                setattr(self, key, value)
            return self.execute(context)
        self._header(context)
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def _update(self, context, event):
        origin, direction = _mouse_ray(context, event)
        step = step_mm(context.scene)
        step = (step / 10 if event.shift else step) if event.ctrl else 0.0  # millimetres
        if self._stage == "BASE":
            p = drawing.plane_coords(self._plane, origin, direction)
            if p is not None:
                self._p1 = p
            self._drawn = drawing.drawn_solid(self.shape, self._plane, self._p0, self._p1, 0.0, self._factor, step,
                                              local=self._local)
        else:
            h = drawing.height_along_normal(self._plane, self._base.frame.translation, origin, direction)
            self._drawn = dataclasses.replace(self._base, height=drawing.snap(h / self._factor, step))

    def _mode(self):
        if self._target is None:
            return "NEW"
        return "CUT" if self._drawn is not None and self._drawn.height < 0 else "UNION"

    def _header(self, context):
        d = self._drawn
        step = step_mm(context.scene)
        snapping = f"Ctrl: snap {step:g} mm (Shift+Ctrl: {step / 10:g} mm) | Ctrl+Wheel: step"
        if self._stage == "BASE":
            size = "" if d is None else (f"{d.length:.3f} x {d.width:.3f} mm" if d.shape == "BOX"
                                         else f"radius {d.radius:.3f} mm")
            text = f"Draw Solid: drag the base {size}, release for the height | {snapping} | Esc/right-click: cancel"
        else:
            what = {"NEW": "new part", "UNION": f"union with {self._target.name if self._target else ''}",
                    "CUT": f"cut from {self._target.name if self._target else ''}"}[self._mode()]
            text = (f"Draw Solid: height {abs(d.height) if d else 0.0:.3f} mm, {what} | click: confirm | "
                    f"{snapping} | Esc/right-click: cancel")
        context.area.header_text_set(text)

    def _finish(self, context):
        if getattr(self, "_handle", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            self._handle = None
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()


def _mouse_ray(context, event):
    coord = (event.mouse_region_x, event.mouse_region_y)
    return (view3d_utils.region_2d_to_origin_3d(context.region, context.region_data, coord),
            view3d_utils.region_2d_to_vector_3d(context.region, context.region_data, coord))


PICK_RADIUS_PX = 3  # a drag started this close to a part's face (e.g. on its edge) starts on that face


def _near_rays(context, coord, radius=PICK_RADIUS_PX):
    """Rays through 8 points `radius` pixels around region coordinate `coord` (for pick(near=...))."""
    region, rv3d = context.region, context.region_data
    rays = []
    for k in range(8):
        a = k * math.pi / 4
        c = (coord[0] + radius * math.cos(a), coord[1] + radius * math.sin(a))
        rays.append((view3d_utils.region_2d_to_origin_3d(region, rv3d, c),
                     view3d_utils.region_2d_to_vector_3d(region, rv3d, c)))
    return rays


def _first_hit(context, depsgraph, origin, direction):
    """(location, normal, polygon index, object) of the first object a ray hits, looking through wire-display
    objects such as cutters, or None."""
    start, direction = Vector(origin), Vector(direction).normalized()
    for _ in range(16):
        hit, location, normal, index, obj, _ = context.scene.ray_cast(depsgraph, start, direction)
        if not hit:
            return None
        obj = obj.original
        if obj.display_type in {"WIRE", "BOUNDS"}:
            start = location + direction * max(1e-6, location.length * 1e-6)
            continue
        return location, normal, index, obj
    return None


def pick_plane(context, origin, direction):
    """(drawing plane, target part or None) under the mouse ray: see pick()."""
    return pick(context, origin, direction)[:2]


def pick(context, origin, direction, near=()):
    """(drawing plane, target part or None, the plane in the target's own coordinates or None) under the mouse
    ray: the face of the first object hit (looking through wire-display objects such as cutters), else the
    plane through the 3D cursor. When the ray misses, the `near` rays (a few pixels around the mouse) are
    tried and the face most facing the view wins, so a drag started on a face's edge or corner starts on the
    face looked at. The
    target is the object hit if it is a BlendSolid part the tools can edit (local, unscaled, trusted,
    canonical script); any other object is drawn on as a new part, on its face's plane. On a target's flat
    face the plane comes from the face's exact plane (the worker's, not the float32 mesh), so what is drawn
    there sits exactly on the face."""
    depsgraph = context.evaluated_depsgraph_get()
    found = _first_hit(context, depsgraph, origin, direction)
    if found is None:
        # On an edge or a corner several faces are near: the one facing the view most is the one looked at.
        view = Vector(direction).normalized()
        hits = [h for h in (_first_hit(context, depsgraph, o, d) for o, d in near) if h is not None]
        found = max(hits, key=lambda h: abs(Vector(h[1]).normalized().dot(view)), default=None)
    if found is None:
        return drawing.plane_at_cursor(context.scene.cursor.matrix), None, None
    location, normal, index, obj = found
    is_part = (part.is_local_part(obj) and not part.is_scaled(obj) and trust.is_trusted(obj)
               and script_model.is_canonical(part.source_of(obj)))
    exact = part.face_plane(obj, index) if is_part and not obj.modifiers else None
    if exact is not None:
        local = drawing.plane_on_part_face(exact[0], exact[1])
        return obj.matrix_world @ local.matrix(part.unit_factor(context.scene)), obj, local
    return drawing.plane_on_face(location, normal, obj.matrix_world), (obj if is_part else None), None


def _draw_preview(op):
    try:
        drawn, factor = op._drawn, op._factor
        mode = op._mode()
    except (ReferenceError, AttributeError):
        return  # the operator is gone
    if drawn is None:
        return
    import gpu  # not available in background mode: imported only when actually drawing
    from gpu_extras.batch import batch_for_shader
    coords = [tuple(p) for line in drawing.preview_lines(drawn, factor) for p in line]
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    batch = batch_for_shader(shader, "LINES", {"pos": coords})
    region = bpy.context.region
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", 2.0)
    shader.uniform_float("color", COLORS[mode])
    gpu.state.blend_set("ALPHA")
    batch.draw(shader)
    gpu.state.blend_set("NONE")


class BLENDSOLID_OT_snap_step(bpy.types.Operator):
    """Next or previous snap step of the Draw Solid tool (Ctrl+Wheel)"""
    bl_idname = "blendsolid.snap_step"
    bl_label = "Snap Step"
    bl_options = {"INTERNAL"}

    direction: IntProperty(name="Direction", default=1, min=-1, max=1)

    def execute(self, context):
        change_step(context.scene, self.direction)  # shown by the tool header and the sidebar: no report
        if context.area is not None:
            context.area.tag_redraw()
        return {"FINISHED"}


def _hover(context, origin, direction, near=()):
    """(world point, plane, target) of the grid node where a Ctrl drag starting under the mouse would begin."""
    plane, target, _ = pick(context, origin, direction, near=near)
    p = drawing.plane_coords(plane, origin, direction)
    if p is None:
        return None
    u, v = drawing.grid_node(plane, p, part.unit_factor(context.scene), step_mm(context.scene))
    return plane.translation + plane.col[0].xyz * u + plane.col[1].xyz * v, plane, target


def hover_node(context, origin, direction):
    found = _hover(context, origin, direction)
    return None if found is None else found[0]


def marker_color(target):
    """White: the drawing would start on the 3D cursor's plane (a new part); orange: on a part's face (a union
    or a cut, by the direction of the height)."""
    return (1.0, 1.0, 1.0, 0.9) if target is None else (1.0, 0.55, 0.1, 1.0)


class BLENDSOLID_GT_snap_marker(bpy.types.Gizmo):
    """A cross on the grid node a Ctrl drag would start from, drawn while the Draw Solid tool is active.
    Blender doesn't tell a gizmo whether Ctrl is held, so it is always shown."""
    bl_idname = "BLENDSOLID_GT_snap_marker"

    def setup(self):
        self.mouse = None

    def test_select(self, context, location):
        self.mouse = tuple(location)
        context.area.tag_redraw()
        return -1  # never "selected": the click goes to the tool's keymap

    def draw(self, context):
        if self.mouse is None or context.region_data is None:
            return
        region, rv3d = context.region, context.region_data
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, self.mouse)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, self.mouse)
        found = _hover(context, origin, direction, near=_near_rays(context, self.mouse))
        if found is None:
            return
        point, plane, target = found
        here = view3d_utils.location_3d_to_region_2d(region, rv3d, point)
        if here is None:
            return
        arm = (view3d_utils.region_2d_to_location_3d(region, rv3d, (here.x + 8, here.y), point) - point).length
        x, y = plane.col[0].xyz * arm, plane.col[1].xyz * arm
        import gpu  # not available in background mode
        from gpu_extras.batch import batch_for_shader
        shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        batch = batch_for_shader(shader, "LINES", {"pos": [point - x, point + x, point - y, point + y]})
        shader.uniform_float("viewportSize", (region.width, region.height))
        shader.uniform_float("lineWidth", 2.0)
        shader.uniform_float("color", marker_color(target))
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        batch.draw(shader)
        gpu.state.blend_set("NONE")


class BLENDSOLID_GGT_draw_hover(bpy.types.GizmoGroup):
    bl_idname = "BLENDSOLID_GGT_draw_hover"
    bl_label = "Draw Solid Snap Marker"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    def setup(self, context):  # called when the Draw Solid tool becomes active
        from . import runtime
        runtime.warm_up()
        self.gizmos.new(BLENDSOLID_GT_snap_marker.bl_idname)


def drawn_properties(drawn, target, factor):
    """The draw_solid operator properties for a drag (drawing.Drawn) on part `target` (or None): on a part,
    a positive height (out of the face) is a union and a negative one a cut; elsewhere it is a new part."""
    frame, height = drawn.frame, drawn.height
    if target is not None:
        mode = "UNION" if height > 0 else "CUT"
    else:
        mode = "NEW"
        if height < 0:  # drawn downwards: the new part's frame looks the other way
            frame = frame @ Matrix.Rotation(math.pi, 4, "X")
    if target is not None and drawn.local is not None:  # exact: already in the part's frame
        location, rotation = drawing.placement_local(drawn.local)
    else:
        location, rotation = drawing.placement(frame, target.matrix_world if target is not None else None, factor)
    props = {"shape": drawn.shape, "mode": mode, "target": target.name if target is not None else "",
             "location": location, "rotation": rotation, "height": abs(height),
             "exact": json.dumps({"location": list(location), "rotation": list(rotation)})}
    if drawn.shape == "BOX":
        props.update(length=drawn.length, width=drawn.width)
    else:
        props.update(radius=drawn.radius)
    return props


class DrawSolidTool(bpy.types.WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = "blendsolid.draw_solid_tool"
    bl_label = "Draw Solid"
    bl_description = ("Drag a base on a part's face or on the 3D cursor's plane, then move for the height: out of "
                      "the face adds to the part, into it cuts, elsewhere makes a new part")
    bl_icon = "ops.mesh.primitive_cube_add_gizmo"
    bl_widget = "BLENDSOLID_GGT_draw_hover"
    # any modifier: Ctrl (snapping) or Shift+Ctrl held before the press still start a drag (the modal reads them)
    bl_keymap = (
        ("blendsolid.draw_solid", {"type": "LEFTMOUSE", "value": "PRESS", "any": True}, None),
        ("blendsolid.snap_step", {"type": "WHEELUPMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", 1)]}),
        ("blendsolid.snap_step", {"type": "WHEELDOWNMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", -1)]}),
    )

    def draw_settings(context, layout, tool):
        draw_settings_into(layout, context.scene)


def draw_settings_into(layout, scene):
    """The Draw Solid settings (shape, snap step): the tool header and the BlendSolid sidebar show the same."""
    layout.prop(scene, "blendsolid_draw_shape", expand=True)
    layout.prop(scene, "blendsolid_snap_step", text="Snap")


CLASSES = [BLENDSOLID_OT_draw_solid, BLENDSOLID_OT_snap_step, BLENDSOLID_GT_snap_marker, BLENDSOLID_GGT_draw_hover]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.blendsolid_draw_shape = EnumProperty(name="Shape", items=SHAPES, default="BOX",
                                                         description="Shape the Draw Solid tool draws")
    bpy.types.Scene.blendsolid_snap_step = EnumProperty(
        name="Snap Step", items=STEP_ITEMS, default="1",
        description="Grid step of the Draw Solid tool while Ctrl is held (Ctrl+Wheel changes it)")
    bpy.utils.register_tool(DrawSolidTool, after={"builtin.primitive_cube_add"}, separator=True)


def unregister():
    bpy.utils.unregister_tool(DrawSolidTool)
    del bpy.types.Scene.blendsolid_snap_step
    del bpy.types.Scene.blendsolid_draw_shape
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
