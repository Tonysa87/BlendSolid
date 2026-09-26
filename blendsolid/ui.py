"""Properties, operators and panel of BlendSolid."""
import bpy
from bpy.props import BoolProperty, CollectionProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import params, part, trust


def _on_param_value(self, context):
    _write_param(self, self.value)


def _on_param_value_int(self, context):
    _write_param(self, self.value_int)


def _write_param(item, value):
    obj = item.id_data
    if part.is_syncing() or obj.blendsolid_script is None or part.is_linked(obj):
        return
    try:
        part.set_param(obj, item.name, value)
    except (SyntaxError, params.ParamError) as e:
        # a broken script (SyntaxError) or a non-finite value (ParamError, e.g. from a driver/animation):
        # never let this escape into Blender's RNA update. Tag with the current (unwritten) source hash,
        # so tick() clears it once the script actually changes (including by reverting to a previously-
        # good source) rather than leaving it stuck forever. Written to every object sharing this mesh
        # (this object plus its siblings, if any), so tick()'s primary-to-sibling mirroring agrees with it
        # instead of overwriting it on the next tick.
        tag = part.current_tag(obj)
        for target in (obj, *part.mesh_siblings(obj)):
            part.set_error(target, str(e), tag=tag)


class BS_Param(bpy.types.PropertyGroup):
    value: FloatProperty(name="Value", update=_on_param_value, precision=3)
    value_int: IntProperty(name="Value", update=_on_param_value_int)  # mirror shown when is_int
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


class BLENDSOLID_OT_trust_scripts(bpy.types.Operator):
    """Run the BlendSolid scripts of this file until another file is loaded. Scripts are Python code: only
    trust files from sources you trust"""
    bl_idname = "blendsolid.trust_scripts"
    bl_label = "Trust Scripts in This File"

    @classmethod
    def poll(cls, context):
        return not trust.file_trusted()

    def execute(self, context):
        trust.trust_file()  # session only, never saved (ADR 0004)
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
        obj = context.object
        if obj is None or obj.blendsolid_script is None or part.is_linked(obj):
            return False
        if not trust.is_trusted(obj):
            cls.poll_message_set("Scripts in this file are not trusted: press Trust Scripts in This File first "
                                 "(BlendSolid never runs them before that)")
            return False
        return True

    def execute(self, context):
        from . import runtime
        # objects sharing a mesh are one part (part.part_groups()); tick() only ever submits/tracks the
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
        from . import ops_add
        ops_add.draw_add_buttons(layout)
        if obj is None or obj.blendsolid_script is None:
            return
        from . import runtime
        status = runtime.part_status(obj)
        if part.is_scaled(obj):
            box = layout.box()
            box.label(text="This part is scaled", icon="ERROR")
            box.label(text="Keep scale 1 and change its size parameters:", icon="BLANK1")
            box.label(text="gizmos and cutters don't work on scaled parts.", icon="BLANK1")
        col = layout.column(align=True)
        col.enabled = status != "linked"  # a library part is read-only
        for item in obj.blendsolid_params:
            col.prop(item, "value_int" if item.is_int else "value", text=item.name.replace("_", " ").capitalize())
        advanced = scripts_visible(context)
        if status == "linked":
            layout.label(text="Linked from a library: edit it in its own file", icon="LINKED")
        elif status == "edit_mode":
            layout.label(text="Leave Edit Mode to rebuild", icon="EDITMODE_HLT")
        elif status == "starting":
            layout.label(text="Starting geometry engine…", icon="SORTTIME")
        elif status == "computing":
            layout.label(text="Computing…", icon="SORTTIME")
        elif status == "untrusted":
            box = layout.box()
            box.label(text="Scripts in this file are not trusted", icon="LOCKED")
            box.label(text="Auto Run Python Scripts is off or excludes this file:", icon="BLANK1")
            box.label(text="the part keeps its saved mesh and won't rebuild.", icon="BLANK1")
            box.operator("blendsolid.trust_scripts", icon="CHECKMARK")
        if obj.blendsolid_error:
            box = layout.box()
            box.label(text="The part could not be rebuilt", icon="ERROR")
            line = f" (line {obj.blendsolid_error_line})" if advanced and obj.blendsolid_error_line else ""
            for i, text in enumerate(obj.blendsolid_error.splitlines()[:6]):
                box.label(text=(text + line) if i == 0 else text, icon="BLANK1")
        from . import ops_boolean
        layout.label(text="Booleans (selected parts on this one):")
        ops_boolean.draw_boolean_buttons(layout)
        row = layout.row(align=True)
        if advanced:
            row.operator("blendsolid.edit_script", icon="TEXT")
        row.operator("blendsolid.recompute", icon="FILE_REFRESH")


CLASSES = [BS_Param, BLENDSOLID_AP_preferences, BLENDSOLID_OT_new_part, BLENDSOLID_OT_trust_scripts,
           BLENDSOLID_OT_edit_script,
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
