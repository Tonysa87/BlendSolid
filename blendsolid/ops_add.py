"""Tool 1: parametric primitives as new parts (Shift+A > BlendSolid, the pie's Add, the BlendSolid sidebar tab).

One operator per primitive, with REGISTER and UNDO: its properties are the primitive's dimensions in
millimetres (plain floats, not DISTANCE: scripts are in millimetres whatever the scene's units, ADR 0003), so
Adjust Last Operation shows them and Blender's redo re-runs execute() with the new values.

Invoked from the viewport (the pie, Shift+A), the part is placed and sized interactively (ADR 0015): it appears
where the pie was opened (on the face or the 3D cursor's plane under it; from Shift+A, at the 3D cursor), at a
round size about a fifth of the view, and the mouse scales it like Blender's S (round steps; Ctrl: the grid;
digits type the size). Click or Enter confirms, Esc or right-click cancels. While scaling only the object's scale
changes (no recompute); the confirmed size is written into the script.
"""

import bpy
from bpy.props import BoolProperty, FloatProperty, FloatVectorProperty
from mathutils import Matrix, Vector

from . import part, primitives, script_model

ICONS = {"box": "MESH_CUBE", "cylinder": "MESH_CYLINDER", "sphere": "MESH_UVSPHERE", "cone": "MESH_CONE",
         "torus": "MESH_TORUS", "wedge": "OBJECT_DATAMODE"}


def add_primitive_part(context, kind, values, matrix=None):
    """A new part whose script is primitive `kind` with `values` (suffix -> mm), placed at `matrix` (object
    transform, not script; None: the 3D cursor's matrix), selected and active. Returns the object."""
    prim = primitives.PRIMITIVES[kind]
    source, _ = script_model.new_script(primitives.feature_spec(kind, values))
    for obj in context.selected_objects:
        obj.select_set(False)
    obj = part.new_part(context, source, name=prim.label)
    obj.matrix_world = context.scene.cursor.matrix if matrix is None else matrix
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj


def _draw_millimetres(op, prim):
    layout = op.layout
    layout.use_property_split = True
    layout.label(text="Dimensions (millimetres)")
    for suffix, _, _ in prim.params:
        layout.prop(op, suffix)


def _make_operator(prim):
    annotations = {
        suffix: FloatProperty(name=label, default=default, min=0.0 if suffix == "top_length" else 0.001,
                              soft_min=0.0 if suffix == "top_length" else 0.1, precision=3, step=100,
                              description=f"{label} in millimetres")
        for suffix, label, default in prim.params}

    annotations["matrix"] = FloatVectorProperty(size=16, options={"HIDDEN", "SKIP_SAVE"})
    annotations["placed"] = BoolProperty(options={"HIDDEN", "SKIP_SAVE"})  # use `matrix`, not the 3D cursor
    # chosen in the pie: start where the pie was opened (Shift+A and the sidebar start at the 3D cursor)
    annotations["from_pie"] = BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        matrix = Matrix([self.matrix[i * 4:i * 4 + 4] for i in range(4)]) if self.placed else None
        add_primitive_part(context, prim.kind, {s: getattr(self, s) for s, _, _ in prim.params}, matrix)
        return {"FINISHED"}

    def invoke(self, context, event):
        return _Placement.invoke(self, context, event, prim)

    def modal(self, context, event):
        return self._placement.modal(self, context, event)

    def draw(self, context):
        _draw_millimetres(self, prim)

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":  # e.g. from Edit Mode: another mesh would stay in Edit Mode meanwhile
            cls.poll_message_set("Switch to Object Mode to add a BlendSolid part")
            return False
        return True

    return type(f"BLENDSOLID_OT_add_{prim.kind}", (bpy.types.Operator,), {
        "bl_idname": f"blendsolid.add_{prim.kind}",
        "bl_label": prim.label,
        "bl_description": f"Add a parametric {prim.label.lower()} as a new BlendSolid part at the 3D cursor",
        "bl_options": {"REGISTER", "UNDO"},
        "__annotations__": annotations,
        "execute": execute,
        "invoke": invoke,
        "modal": modal,
        "draw": draw,
        "poll": poll,
    })


class _Placement:
    """The interactive part of an add operator: a preview part scaled by the mouse, then confirmed or removed."""
    START_FRACTION = 0.2  # a new part starts about this fraction of the view's height
    MIN_PX = 40  # the mouse's starting distance from the anchor counts as at least this (pixels, scale 1)

    @staticmethod
    def invoke(op, context, event, prim):
        from . import ops_draw, pies, runtime
        if context.area is None or context.area.type != "VIEW_3D" or context.region_data is None:
            return op.execute(context)
        runtime.warm_up()
        region, rv3d = context.region, context.region_data
        factor = part.unit_factor(context.scene)
        matrix = context.scene.cursor.matrix.normalized()
        origin = pies.take_origin(context) if op.from_pie else None
        if origin is not None:  # where the pie was opened: the face under it, else the 3D cursor's plane
            ray = ops_draw.mouse_ray(context, origin)
            plane, _, _ = ops_draw.pick(context, *ray, near=ops_draw._near_rays(context, origin))
            hit = _ray_plane(plane, *ray)
            if hit is not None:
                matrix = plane.copy()
                matrix.translation = hit
        anchor = matrix.translation.copy()
        pixel = ops_draw._pixel_size(region, rv3d, anchor)
        if pixel is None:
            return op.execute(context)
        size = primitives.nice_size(region.height * _Placement.START_FRACTION * pixel / factor)
        self = _Placement()
        self.prim, self.matrix, self.anchor, self.factor = prim, matrix, anchor, factor
        self.size = self.written = size
        self.typed = ""
        here = _region_point(context, anchor)
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        self.anchor_px = here
        self.start_px = max((mouse - here).length if here is not None else 0.0,
                            _Placement.MIN_PX * ops_draw.ui_scale(context))
        self.obj = add_primitive_part(context, prim.kind, primitives.sized_values(prim.kind, size), matrix)
        self.handle = bpy.types.SpaceView3D.draw_handler_add(_draw_label, (self,), "WINDOW", "POST_PIXEL")
        op._placement = self
        context.window_manager.modal_handler_add(op)
        self.status(context)
        return {"RUNNING_MODAL"}

    def modal(self, op, context, event):
        from . import ops_draw
        if event.type in ops_draw.NAV_EVENTS:
            return {"PASS_THROUGH"}
        if event.value == "PRESS" and event.type in {"ESC", "RIGHTMOUSE"}:
            self.end(context)
            _remove_part(self.obj)
            return {"CANCELLED"}
        if event.value == "PRESS" and event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER", "SPACE"}:
            if self.typed and self._typed_value() is None:
                return {"RUNNING_MODAL"}  # the label says why: Backspace, or type on
            self.end(context)
            values = primitives.sized_values(self.prim.kind, self.size)
            for suffix, value in values.items():
                setattr(op, suffix, value)
            op.matrix = [v for row in self.matrix for v in row]
            op.placed = True
            if self.size != self.written:
                source, _ = script_model.new_script(primitives.feature_spec(self.prim.kind, values))
                self.obj.blendsolid_script.from_string(source)
                part.sync_params(self.obj, source)
                # the worker's mesh at this size comes later: until then the mesh shown takes the scale, or the
                # part pops back to the starting size for a moment
                self.obj.data.transform(Matrix.Scale(self.size / self.written, 4))
            self.obj.scale = (1.0, 1.0, 1.0)
            return {"FINISHED"}
        if event.value == "PRESS" and self._type(event):
            pass
        elif event.type in {"MOUSEMOVE", "LEFT_CTRL", "RIGHT_CTRL"} and not self.typed:
            self.size = self._mouse_size(context, event)
        else:
            return {"RUNNING_MODAL"}
        k = self.size / self.written
        self.obj.scale = (k, k, k)
        self.status(context)
        return {"RUNNING_MODAL"}

    def _type(self, event):
        """Digits, '.' and Backspace type the size (Blender's numeric input, reduced); True if handled. A size
        too small for the part's parameters isn't taken (nor confirmed): the label says so."""
        if event.type in TYPED_KEYS:
            key = TYPED_KEYS[event.type]
            if not (key == "." and "." in self.typed):  # a second point would be ignored by float(): refuse it
                self.typed += key
        elif event.type == "BACK_SPACE" and self.typed:
            self.typed = self.typed[:-1]
        else:
            return False
        value = self._typed_value()
        if value is not None:
            self.size = value
        return True

    def _typed_value(self):
        """The typed size, rounded as scripts write numbers, or None while it isn't a usable one."""
        try:
            value = round(float(self.typed), 6)
        except ValueError:
            return None
        return value if value >= primitives.min_size(self.prim.kind) else None

    def _mouse_size(self, context, event):
        from . import ops_draw
        if self.anchor_px is None:
            return self.size
        d = (Vector((event.mouse_region_x, event.mouse_region_y)) - self.anchor_px).length
        size = self.written * max(d, 1.0) / self.start_px
        if event.ctrl:
            step = ops_draw.step_mm(context.scene)
            size = max(step, round(size / step) * step)
        else:
            size = primitives.nice_size(size, primitives.DRAG_STEPS)
        return max(round(size, 6), primitives.min_size(self.prim.kind))

    def label(self):
        dims = " × ".join(f"{e:g}" for e in self.prim.extents(primitives.sized_values(self.prim.kind, self.size)))
        if self.typed and self._typed_value() is None:
            return (f"{self.prim.label} {dims} mm  (typed {self.typed}: at least "
                    f"{primitives.min_size(self.prim.kind):g} mm)")
        return f"{self.prim.label} {dims} mm" + (f"  (typed {self.typed})" if self.typed else "")

    def status(self, context):
        context.area.header_text_set(
            f"Add {self.prim.label}: move the mouse to scale | Ctrl: grid | type a size | click/Enter: confirm | "
            f"Esc/right-click: cancel")
        context.area.tag_redraw()

    def end(self, context):
        if self.handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle, "WINDOW")
            self.handle = None
        context.area.header_text_set(None)
        context.area.tag_redraw()


def _ray_plane(plane, origin, direction):
    from mathutils import geometry
    return geometry.intersect_line_plane(Vector(origin), Vector(origin) + Vector(direction), plane.translation,
                                         plane.col[2].xyz)


def _region_point(context, point):
    from bpy_extras import view3d_utils
    return view3d_utils.location_3d_to_region_2d(context.region, context.region_data, point)


def _draw_label(placement):
    from . import ops_draw
    try:
        top = placement.anchor + placement.matrix.col[2].xyz.normalized() * (
            max(placement.prim.extents(primitives.sized_values(placement.prim.kind, placement.size))[2], 0.0)
            * placement.factor)
        ops_draw.draw_text_lines(bpy.context, top, [placement.label()])
    except ReferenceError:
        pass


# event types that type a size: the row digits are ZERO..NINE, the keypad's NUMPAD_0..NUMPAD_9 (Blender's names)
TYPED_KEYS = {name: str(i) for i, name in enumerate(("ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN",
                                                     "EIGHT", "NINE"))}
TYPED_KEYS.update({f"NUMPAD_{i}": str(i) for i in range(10)})
TYPED_KEYS.update({"PERIOD": ".", "NUMPAD_PERIOD": ".", "COMMA": "."})

def _remove_part(obj):
    """Remove a part made a moment ago (the cancelled preview): its object, mesh and script."""
    text, mesh = obj.blendsolid_script, obj.data
    bpy.data.objects.remove(obj)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    if text is not None and text.users == 0:
        bpy.data.texts.remove(text)


OPERATORS = [_make_operator(p) for p in primitives.PRIMITIVES.values()]


class VIEW3D_MT_blendsolid_add(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_blendsolid_add"
    bl_label = "BlendSolid"

    def draw(self, context):
        from . import runtime
        runtime.warm_up()
        layout = self.layout
        for kind, prim in primitives.PRIMITIVES.items():
            layout.operator(f"blendsolid.add_{kind}", text=prim.label, icon=ICONS[kind])


def draw_add_buttons(layout):
    """The primitives as buttons (the BlendSolid sidebar panel's Create section)."""
    grid = layout.grid_flow(columns=3, align=True)
    for kind, prim in primitives.PRIMITIVES.items():
        grid.operator(f"blendsolid.add_{kind}", text=prim.label, icon=ICONS[kind])


def _add_menu_entry(self, context):
    self.layout.separator()
    self.layout.menu(VIEW3D_MT_blendsolid_add.bl_idname, icon="MOD_BOOLEAN")


CLASSES = [*OPERATORS, VIEW3D_MT_blendsolid_add]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_add.append(_add_menu_entry)


def unregister():
    bpy.types.VIEW3D_MT_add.remove(_add_menu_entry)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
