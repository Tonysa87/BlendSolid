"""Properties, operators and panel of BlendSolid."""
import bpy
from bpy.props import BoolProperty, CollectionProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import params, part


def _on_param_value(self, context):
    if part.is_syncing():
        return
    try:
        part.set_param(self.id_data, self.name, self.value)
    except params.ParamError as e:
        # e.g. a non-finite value from a driver/animation: never let this escape into Blender's UI.
        part.set_error(self.id_data, str(e))


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
