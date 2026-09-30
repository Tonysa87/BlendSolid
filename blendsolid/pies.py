"""The command pie (ADR 0013): a two-level native pie with the families of commands, opened by E (tap: the pie stays
open, click an item; hold: release on the item) or by dragging with the right mouse button in Object Mode (a
right-click without a drag still opens Blender's Object context menu). Level 0 holds the families, each opening its
own level-1 pie; items that don't exist yet stay greyed out in place, so positions never move.

Research: docs/research/2026-09-30-pie-menus-and-command-access.md, docs/research/2026-09-30-pie-key.md.
"""
import time

import bpy
from bpy.props import StringProperty

from . import ops_add, ops_boolean, ops_draw, primitives

PIE = "VIEW3D_MT_blendsolid_pie"
CONTEXT_MENU = "VIEW3D_MT_object_context_menu"
_keymap_items = []
_origin = None  # where the pie was last opened: (area pointer, (x, y) region pixels, time.monotonic())
ORIGIN_SECONDS = 30.0  # a command chosen this soon after opening the pie still starts where it was opened


def remember_origin(context, event):
    global _origin
    _origin = (context.area.as_pointer(), (event.mouse_region_x, event.mouse_region_y), time.monotonic())


def take_origin(context):
    """Region pixels where the pie was opened in this area, if recently (then forgotten), else None."""
    global _origin
    found, _origin = _origin, None
    if found is None or context.area is None or found[0] != context.area.as_pointer() \
            or time.monotonic() - found[2] > ORIGIN_SECONDS:
        return None
    return found[1]

# Level 0, in Blender's pie order (W, E, S, N, NW, NE, SW, SE): (label, icon, level-1 menu or None if not built)
FAMILIES = [
    ("Add", "ADD", "VIEW3D_MT_blendsolid_pie_add"),
    ("Sketch", "GREASEPENCIL", "VIEW3D_MT_blendsolid_pie_sketch"),
    ("Edit", "MOD_BEVEL", "VIEW3D_MT_blendsolid_pie_edit"),
    ("Draw Solid", "MESH_CUBE", "VIEW3D_MT_blendsolid_pie_draw"),
    ("Booleans", "MOD_BOOLEAN", "VIEW3D_MT_blendsolid_pie_boolean"),
    ("Solid from Sketch", "MOD_SOLIDIFY", "VIEW3D_MT_blendsolid_pie_solid"),
    ("Pattern", "MOD_ARRAY", None),  # milestone 3b
    ("Part & File", "FILE", "VIEW3D_MT_blendsolid_pie_part"),
]


def _tool(layout, tool, text, icon, setting="", value=""):
    op = layout.operator(BLENDSOLID_OT_use_tool.bl_idname, text=text, icon=icon)
    op.tool, op.setting, op.value = tool, setting, value


def _later(layout, text, icon):
    """A command of a later milestone: shown greyed out, so the pie's positions never move."""
    row = layout.row()
    row.enabled = False
    row.operator(BLENDSOLID_OT_use_tool.bl_idname, text=text, icon=icon)


class BLENDSOLID_OT_use_tool(bpy.types.Operator):
    """Activate a BlendSolid tool, optionally with one of its settings (e.g. the Sketch tool's shape)"""
    bl_idname = "blendsolid.use_tool"
    bl_label = "Use BlendSolid Tool"
    bl_options = {"INTERNAL"}

    tool: StringProperty()
    setting: StringProperty()  # a Scene property the tool reads, e.g. blendsolid_sketch_shape
    value: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        if not self.tool:
            return {"CANCELLED"}
        if self.setting:
            setattr(context.scene, self.setting, self.value)
        bpy.ops.wm.tool_set_by_id(name=self.tool)
        return {"FINISHED"}


class BLENDSOLID_OT_call_pie(bpy.types.Operator):
    """Open the BlendSolid pie at the mouse (tap: it stays open; hold: release on an item)"""
    bl_idname = "blendsolid.call_pie"
    bl_label = "BlendSolid Pie"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        remember_origin(context, event)
        bpy.ops.wm.call_menu_pie("INVOKE_DEFAULT", name=PIE)
        return {"FINISHED"}


class BLENDSOLID_OT_pie_or_menu(bpy.types.Operator):
    """Right mouse in Object Mode: a click opens the Object context menu, a drag opens the BlendSolid pie"""
    bl_idname = "blendsolid.pie_or_menu"
    bl_label = "BlendSolid Pie or Context Menu"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        self._key = event.type
        self._start = (event.mouse_x, event.mouse_y)
        remember_origin(context, event)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == self._key and event.value == "RELEASE":
            bpy.ops.wm.call_menu("INVOKE_DEFAULT", name=CONTEXT_MENU)
            return {"FINISHED"}
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            dx, dy = event.mouse_x - self._start[0], event.mouse_y - self._start[1]
            if dx * dx + dy * dy >= drag_threshold(context) ** 2:
                bpy.ops.wm.call_menu_pie("INVOKE_DEFAULT", name=PIE)
                return {"FINISHED"}
        if event.type == "ESC":
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}


def drag_threshold(context):
    """Blender's own mouse drag threshold (Preferences > Input), in pixels at the interface scale."""
    inputs = context.preferences.inputs
    px = getattr(inputs, "drag_threshold_mouse", 3) or 3
    return px * (context.preferences.system.ui_scale or 1.0)


class VIEW3D_MT_blendsolid_pie(bpy.types.Menu):
    bl_idname = PIE
    bl_label = "BlendSolid"

    def draw(self, context):
        from . import runtime
        runtime.warm_up()
        pie = self.layout.menu_pie()
        for label, icon, menu in FAMILIES:
            if menu is None:
                _later(pie, label, icon)
            else:
                pie.operator("wm.call_menu_pie", text=label, icon=icon).name = menu


class VIEW3D_MT_blendsolid_pie_add(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_blendsolid_pie_add"
    bl_label = "Add"

    def draw(self, context):
        pie = self.layout.menu_pie()
        for kind, prim in primitives.PRIMITIVES.items():
            pie.operator(f"blendsolid.add_{kind}", text=prim.label, icon=ops_add.ICONS[kind])
        pie.operator("blendsolid.new_part", icon="FILE_NEW")


class VIEW3D_MT_blendsolid_pie_sketch(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_blendsolid_pie_sketch"
    bl_label = "Sketch"

    def draw(self, context):
        pie = self.layout.menu_pie()
        _tool(pie, "blendsolid.sketch_tool", "Path", "IPO_LINEAR", "blendsolid_sketch_shape", "PATH")
        _tool(pie, "blendsolid.sketch_tool", "Rectangle", "MESH_PLANE", "blendsolid_sketch_shape", "RECTANGLE")
        _tool(pie, "blendsolid.sketch_tool", "Circle", "MESH_CIRCLE", "blendsolid_sketch_shape", "CIRCLE")


class VIEW3D_MT_blendsolid_pie_edit(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_blendsolid_pie_edit"
    bl_label = "Edit"

    def draw(self, context):
        pie = self.layout.menu_pie()
        _tool(pie, "blendsolid.fillet_tool", "Fillet / Chamfer", "MOD_BEVEL")
        _tool(pie, "blendsolid.push_pull_tool", "Push/Pull", "MOD_SOLIDIFY")


class VIEW3D_MT_blendsolid_pie_draw(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_blendsolid_pie_draw"
    bl_label = "Draw Solid"

    def draw(self, context):
        pie = self.layout.menu_pie()
        for value, label, _, icon, _ in ops_draw.SHAPES:
            _tool(pie, "blendsolid.draw_solid_tool", label, icon, "blendsolid_draw_shape", value)


class VIEW3D_MT_blendsolid_pie_boolean(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_blendsolid_pie_boolean"
    bl_label = "Booleans"

    def draw(self, context):
        pie = self.layout.menu_pie()
        for value, label, _, icon, _ in ops_boolean.OPERATIONS:
            pie.operator(ops_boolean.BLENDSOLID_OT_boolean.bl_idname, text=label, icon=icon).operation = value
        pie.operator("blendsolid.show_cutters", icon="HIDE_OFF")


class VIEW3D_MT_blendsolid_pie_solid(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_blendsolid_pie_solid"
    bl_label = "Solid from Sketch"

    def draw(self, context):
        pie = self.layout.menu_pie()
        _tool(pie, "blendsolid.extrude_tool", "Extrude", "MOD_SOLIDIFY")
        _tool(pie, "blendsolid.revolve_tool", "Revolve", "MOD_SCREW")
        _tool(pie, "blendsolid.groove_tool", "Groove / Rib", "MOD_CURVE")


class VIEW3D_MT_blendsolid_pie_part(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_blendsolid_pie_part"
    bl_label = "Part & File"

    def draw(self, context):
        pie = self.layout.menu_pie()
        pie.operator("blendsolid.new_part", icon="FILE_NEW")
        pie.operator("blendsolid.edit_script", icon="TEXT")
        pie.operator("blendsolid.recompute", icon="FILE_REFRESH")
        _later(pie, "Import STEP", "IMPORT")
        _later(pie, "Export STEP", "EXPORT")


LEVEL_1 = [VIEW3D_MT_blendsolid_pie_add, VIEW3D_MT_blendsolid_pie_sketch, VIEW3D_MT_blendsolid_pie_edit,
           VIEW3D_MT_blendsolid_pie_draw, VIEW3D_MT_blendsolid_pie_boolean, VIEW3D_MT_blendsolid_pie_solid,
           VIEW3D_MT_blendsolid_pie_part]
CLASSES = [BLENDSOLID_OT_use_tool, BLENDSOLID_OT_call_pie, BLENDSOLID_OT_pie_or_menu, VIEW3D_MT_blendsolid_pie, *LEVEL_1]


def right_click_select(context):
    """Is the active keymap set to select with the right mouse button (then right-drag stays Blender's)?"""
    try:
        return context.window_manager.keyconfigs.active.preferences.select_mouse == "RIGHT"
    except AttributeError:
        return False


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:  # None in some background sessions
        return
    km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
    _keymap_items.append((km, km.keymap_items.new(BLENDSOLID_OT_call_pie.bl_idname, "E", "PRESS")))
    if not right_click_select(bpy.context):
        _keymap_items.append((km, km.keymap_items.new(BLENDSOLID_OT_pie_or_menu.bl_idname, "RIGHTMOUSE", "PRESS")))


def unregister():
    for km, kmi in _keymap_items:
        km.keymap_items.remove(kmi)
    _keymap_items.clear()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
