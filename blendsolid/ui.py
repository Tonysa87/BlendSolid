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


CLASSES = [BS_Param]


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
