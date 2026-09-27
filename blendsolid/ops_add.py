"""Tool 1: parametric primitives as new parts (Shift+A > BlendSolid, and the BlendSolid sidebar tab).

One operator per primitive, with REGISTER and UNDO: its properties are the primitive's dimensions in
millimetres (plain floats, not DISTANCE: scripts are in millimetres whatever the scene's units, ADR 0003), so
Adjust Last Operation shows them and Blender's redo re-runs execute() with the new values.
"""
import bpy
from bpy.props import FloatProperty

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

    def execute(self, context):
        add_primitive_part(context, prim.kind, {s: getattr(self, s) for s, _, _ in prim.params})
        return {"FINISHED"}

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
        "draw": draw,
        "poll": poll,
    })


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
