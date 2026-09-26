"""Properties, operators and panel of BlendSolid."""
import bpy
from bpy.props import BoolProperty, CollectionProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import params, part


def _on_param_value(self, context):
    obj = self.id_data
    if part.is_syncing() or obj.blendsolid_script is None:
        return
    try:
        part.set_param(obj, self.name, self.value)
    except (SyntaxError, params.ParamError) as e:
        # a broken script (SyntaxError) or a non-finite value (ParamError, e.g. from a driver/animation):
        # never let this escape into Blender's RNA update. Tag with the current (unwritten) source hash,
        # so tick() clears it once the script actually changes (including by reverting to a previously-
        # good source) rather than leaving it stuck forever. Written to every object sharing this mesh
        # (this object plus its siblings, if any), so tick()'s primary-to-sibling mirroring agrees with it
        # instead of overwriting it on the next tick.
        tag = part.source_hash(part.source_of(obj))
        for target in (obj, *part.mesh_siblings(obj)):
            part.set_error(target, str(e), tag=tag)


class BS_Param(bpy.types.PropertyGroup):
    value: FloatProperty(name="Value", update=_on_param_value, precision=3)
    is_int: BoolProperty(default=False)


class BLENDSOLID_OT_new_part(bpy.types.Operator):
    """Add a new BlendSolid part defined by a build123d script"""
    bl_idname = "blendsolid.new_part"
    bl_label = "New Part"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for obj in context.selected_objects:
            obj.select_set(False)
        obj = part.new_part(context)
        obj.location = context.scene.cursor.location
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


FORCE_SHOW_SCRIPTS = False  # tests: the add-on isn't registered as an extension there, so it has no preferences


class BLENDSOLID_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    show_scripts: BoolProperty(
        name="Show history scripts",
        description="Advanced: show and edit the build123d script behind each part",
        default=False)

    def draw(self, context):
        self.layout.prop(self, "show_scripts")


def scripts_visible(context):
    if FORCE_SHOW_SCRIPTS:
        return True
    addon = context.preferences.addons.get(__package__)
    return bool(addon and addon.preferences and addon.preferences.show_scripts)


class BLENDSOLID_OT_edit_script(bpy.types.Operator):
    """Show the part's script in a Text Editor"""
    bl_idname = "blendsolid.edit_script"
    bl_label = "Edit Script"

    @classmethod
    def poll(cls, context):
        return (scripts_visible(context) and context.object is not None
                and context.object.blendsolid_script is not None)

    def execute(self, context):
        editors = [a for a in context.screen.areas if a.type == "TEXT_EDITOR"]
        if not editors:
            self.report({"WARNING"}, "Open a Text Editor area to edit the script")
            return {"CANCELLED"}
        editors[0].spaces.active.text = context.object.blendsolid_script
        return {"FINISHED"}


class BLENDSOLID_OT_recompute(bpy.types.Operator):
    """Recompute the part even if its script didn't change"""
    bl_idname = "blendsolid.recompute"
    bl_label = "Recompute"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.blendsolid_script is not None

    def execute(self, context):
        from . import runtime
        # objects sharing a mesh are one part (part.primary_objects()); tick() only ever submits/tracks the
        # primary by its own object name, so force() must act on the primary even when a non-primary
        # sibling happens to be the active object, or the Recompute click would silently do nothing.
        runtime.force(part.primary(context.object))
        return {"FINISHED"}


class BLENDSOLID_PT_part(bpy.types.Panel):
    bl_label = "BlendSolid"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlendSolid"

    def draw(self, context):
        layout = self.layout
        obj = context.object
        layout.operator("blendsolid.new_part", icon="ADD")
        if obj is None or obj.blendsolid_script is None:
            return
        col = layout.column(align=True)
        for item in obj.blendsolid_params:
            col.prop(item, "value", text=item.name.replace("_", " ").capitalize())
        advanced = scripts_visible(context)
        if obj.blendsolid_error:
            box = layout.box()
            box.label(text="The part could not be rebuilt", icon="ERROR")
            line = f" (line {obj.blendsolid_error_line})" if advanced and obj.blendsolid_error_line else ""
            for i, text in enumerate(obj.blendsolid_error.splitlines()[:6]):
                box.label(text=(text + line) if i == 0 else text, icon="BLANK1")
        row = layout.row(align=True)
        if advanced:
            row.operator("blendsolid.edit_script", icon="TEXT")
        row.operator("blendsolid.recompute", icon="FILE_REFRESH")


CLASSES = [BS_Param, BLENDSOLID_AP_preferences, BLENDSOLID_OT_new_part, BLENDSOLID_OT_edit_script,
           BLENDSOLID_OT_recompute, BLENDSOLID_PT_part]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.blendsolid_script = PointerProperty(name="Script", type=bpy.types.Text)
    bpy.types.Object.blendsolid_params = CollectionProperty(type=BS_Param)
    bpy.types.Object.blendsolid_error = StringProperty()
    bpy.types.Object.blendsolid_error_line = IntProperty()


def unregister():
    for name in ("blendsolid_error_line", "blendsolid_error", "blendsolid_params", "blendsolid_script"):
        delattr(bpy.types.Object, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
