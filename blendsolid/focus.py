"""The focused feature of a part: the one whose parameter arrows are shown (ADR 0011).

A part shows the arrows of one feature at a time, like SolidWorks' Instant3D: clicking a face of the active part
focuses the feature that made the face (the face's reference names it, ADR 0009), a tool that adds a feature
focuses it, and the sidebar lists the features to pick one. With no focus, or one that no longer exists, the
first feature (the base solid) is focused.
"""
import re

import bpy
from bpy.props import StringProperty
from bpy_extras import view3d_utils

from . import part, script_model

_FEATURE_OF_REF = re.compile(r'face\("([^"]+)"')
_keymap_items = []


def feature_of_reference(reference):
    """The feature a face reference names (`face("cut_1", "wall")` -> "cut_1"), or None."""
    found = _FEATURE_OF_REF.match(reference or "")
    return found.group(1) if found else None


def features_of(obj):
    """The part's features in script order ([] if its script isn't canonical)."""
    try:
        return script_model.features(part.source_of(obj))
    except (script_model.NotCanonical, SyntaxError):
        return []


def focused(obj, features=None):
    """The name of obj's focused feature among `features` (default: its script's), or None if it has none."""
    features = features_of(obj) if features is None else features
    names = [f.name for f in features]
    if obj.blendsolid_focus in names:
        return obj.blendsolid_focus
    return names[0] if names else None


def set_focus(obj, name):
    """Focus feature `name` on obj and on every object of the same part (they share the arrows' script)."""
    for o in (obj, *part.mesh_siblings(obj)):
        if o.blendsolid_focus != name:
            o.blendsolid_focus = name


def focus_at(context, obj, polygon_index):
    """Focus the feature that made the face under evaluated polygon `polygon_index` of obj; its name, or None."""
    depsgraph = context.evaluated_depsgraph_get()
    fid = part.face_id(obj.evaluated_get(depsgraph).data, polygon_index)
    name = feature_of_reference(part.face_reference(obj, fid))
    if name is None or name not in [f.name for f in features_of(obj)]:
        return None
    set_focus(obj, name)
    return name


def _redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


class BLENDSOLID_OT_focus_click(bpy.types.Operator):
    """Show the arrows of the feature that made the clicked face of the active part"""
    bl_idname = "blendsolid.focus_click"
    bl_label = "Focus Feature Under Mouse"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        # On the press, before or after whatever select tool is active (Tweak consumes its click, Select Box
        # selects on release): the event always passes through, this only moves the focus of the part under the
        # mouse, which Blender's own selection then makes active.
        region, rv3d = context.region, context.region_data
        if rv3d is not None:
            from . import ops_draw
            mouse = (event.mouse_region_x, event.mouse_region_y)
            origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
            direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
            found = ops_draw._first_hit(context, context.evaluated_depsgraph_get(), origin, direction)
            if found is not None and part.is_local_part(found[3]) and focus_at(context, found[3], found[2]):
                _redraw(context)
        return {"PASS_THROUGH"}


class BLENDSOLID_OT_focus_feature(bpy.types.Operator):
    """Show this feature's arrows"""
    bl_idname = "blendsolid.focus_feature"
    bl_label = "Focus Feature"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    part_name: StringProperty()
    feature: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get((self.part_name, None))
        if not part.is_local_part(obj) or self.feature not in [f.name for f in features_of(obj)]:
            self.report({"ERROR"}, f"'{self.part_name}' has no feature '{self.feature}'")
            return {"CANCELLED"}
        set_focus(obj, self.feature)
        _redraw(context)  # the arrows follow at once, not when the mouse next enters the viewport
        return {"FINISHED"}


def draw_features(layout, obj):
    """The part's features (sidebar): the focused one highlighted, a click focuses another."""
    features = features_of(obj)
    if len(features) < 2:
        return
    current = focused(obj, features)
    layout.label(text="Arrows of:")
    flow = layout.grid_flow(row_major=True, columns=3, even_columns=True, align=True)
    for f in features:
        op = flow.operator(BLENDSOLID_OT_focus_feature.bl_idname, text=f.name, depress=f.name == current)
        op.part_name, op.feature = obj.name, f.name


CLASSES = [BLENDSOLID_OT_focus_click, BLENDSOLID_OT_focus_feature]


def register():
    bpy.types.Object.blendsolid_focus = StringProperty(
        name="Focused Feature", description="The feature whose parameter arrows the part shows")
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is not None:  # None in some background sessions
        km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        _keymap_items.append((km, km.keymap_items.new(BLENDSOLID_OT_focus_click.bl_idname, "LEFTMOUSE", "PRESS")))


def unregister():
    for km, kmi in _keymap_items:
        km.keymap_items.remove(kmi)
    _keymap_items.clear()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Object.blendsolid_focus
