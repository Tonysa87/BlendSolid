"""Arrow gizmos on the dimensions of the active part's focused feature (tool 1; ADR 0011: one feature at a
time, only while the part is active, selected and visible).

Each arrow writes its parameter through the panel's own path (the parameter's mirror property, whose update
rewrites the script: ui._write_param), so the reconcile loop, error handling and undo stay exactly as for a
panel edit. Blender pushes one undo step per drag (Gizmo.use_undo); while dragging, every new value replaces
the queued recompute of the part (the worker client coalesces per part), so the latest value wins.

Arrows start at the face they move (primitives.arrows()), never at the object origin, so Blender's transform
gizmo stays visible. They follow the object transform on every redraw.
"""
import math

import bpy
from mathutils import Euler, Matrix, Vector

from . import focus, params, part, primitives, script_model

MIN_VALUE = 0.01  # mm: a primitive dimension can't reach 0 by dragging (top_length may, see _minimum)
_layout_cache = {}  # object name -> (source, [(Feature, Arrow)]): scripts are parsed once per change


def feature_matrix(feature, factor):
    """Feature frame -> part frame, in Blender units (the script's millimetres times the unit factor)."""
    loc = Vector(feature.location) * factor
    rot = Euler([math.radians(a) for a in feature.rotation], "ZYX")  # = build123d's intrinsic XYZ
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def arrow_layout(obj):
    """[(Feature, Arrow)] of obj's focused feature ([] if the script isn't canonical, or the feature has no
    arrows: a fillet, a boolean)."""
    source = part.source_of(obj)
    key = (source, obj.blendsolid_focus)
    cached = _layout_cache.get(obj.name)
    if cached is not None and cached[0] == key:
        return cached[1]
    try:
        feats = script_model.features(source)
        values = {p.name: p.value for p in params.parse_params(source)}
    except (script_model.NotCanonical, params.ParamError, SyntaxError):
        feats, values = [], {}
    name = focus.focused(obj, feats)
    arrows = [(f, a) for f in feats if f.name == name for a in primitives.arrows(f, values)]
    _layout_cache[obj.name] = (key, arrows)
    return arrows


def arrow_matrices(obj, factor=None):
    """[(parameter name, matrix_basis, scale)] for obj's arrows: matrix_basis is in world space with the
    arrow along its local +Z; the arrow's offset (Blender units) is value_mm * scale * factor."""
    factor = part.unit_factor() if factor is None else factor
    out = []
    for feature, arrow in arrow_layout(obj):
        align_z = Vector((0.0, 0.0, 1.0)).rotation_difference(Vector(arrow.direction)).to_matrix().to_4x4()
        basis = (obj.matrix_world @ feature_matrix(feature, factor)
                 @ Matrix.Translation(Vector(arrow.origin) * factor) @ align_z)
        out.append((arrow.param, basis, arrow.scale))
    return out


def _item(obj_name, param):
    obj = bpy.data.objects.get((obj_name, None))
    if obj is None or obj.blendsolid_script is None:
        return None
    return obj.blendsolid_params.get(param)


def _minimum(param):
    return 0.0 if param.endswith("_top_length") else MIN_VALUE


def arrow_get(obj_name, param, scale):
    item = _item(obj_name, param)
    return 0.0 if item is None else item.value * scale * part.unit_factor()


def arrow_set(obj_name, param, scale, offset):
    item = _item(obj_name, param)
    if item is None or scale == 0:
        return
    item.value = max(_minimum(param), offset / (scale * part.unit_factor()))  # -> ui._write_param


def _drawing_tool_active(context):
    """While the Draw Solid tool is active a click must start a drawing, even over a selected part's arrows."""
    workspace = getattr(context, "workspace", None)
    tool = workspace.tools.from_space_view3d_mode("OBJECT", create=False) if workspace is not None else None
    return tool is not None and tool.idname == "blendsolid.draw_solid_tool"


class BLENDSOLID_GGT_parameters(bpy.types.GizmoGroup):
    bl_idname = "BLENDSOLID_GGT_parameters"
    bl_label = "BlendSolid Parameters"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT"}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (context.mode == "OBJECT" and obj is not None and part.is_local_part(obj)
                and obj.select_get() and obj.visible_get()  # as Geometry Nodes gizmos: active and selected
                and not part.is_scaled(obj) and not _drawing_tool_active(context))

    def setup(self, context):
        self.key = None

    def _rebuild(self, context, obj, layout):
        self.gizmos.clear()
        for param, _, scale in layout:
            gz = self.gizmos.new("GIZMO_GT_arrow_3d")
            # never transform={"CONSTRAIN"} without a range= callback: Blender calls it and crashes (tested)
            gz.target_set_handler("offset",
                                  get=lambda n=obj.name, p=param, s=scale: arrow_get(n, p, s),
                                  set=lambda v, n=obj.name, p=param, s=scale: arrow_set(n, p, s, v))
            gz.use_undo = True
            gz.draw_style = "BOX"
            gz.length = 0.6
            gz.color = 0.25, 0.6, 1.0
            gz.alpha = 0.6
            gz.color_highlight = 0.6, 0.85, 1.0
            gz.alpha_highlight = 1.0
        self.key = (obj.name, tuple(p for p, _, _ in layout))

    def draw_prepare(self, context):
        obj = context.object
        layout = arrow_matrices(obj)
        if self.key != (obj.name, tuple(p for p, _, _ in layout)):
            self._rebuild(context, obj, layout)
        for gz, (_, basis, _) in zip(self.gizmos, layout):
            gz.matrix_basis = basis


def register():
    bpy.utils.register_class(BLENDSOLID_GGT_parameters)


def unregister():
    bpy.utils.unregister_class(BLENDSOLID_GGT_parameters)
    _layout_cache.clear()
