"""Tool 4: Fillet. Round (or chamfer) clicked CAD edges of a part: one feature naming them with the references the
worker wrote for them (ADR 0009), e.g.

    fillet(edge_between(face("box_1", "+Z"), face("box_1", "-Y")), radius=fillet_2_radius)  # feature: fillet_2

The operator's properties describe the finished feature (the part, the references, the radius and whether it is
a chamfer); execute() only reads them: the tool's modal ends by calling it, Blender's redo re-runs it with the
values of the Adjust Last Operation panel, and tests call it directly. OCCT spreads a fillet along the edges
tangent to the selected ones (it can't be turned off; research §3.1).
"""
import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty

from . import part, script_model


def _local_part(name):
    obj = bpy.data.objects.get((name, None)) if name else None
    return obj if part.is_local_part(obj) else None


def feature_spec(references, radius, chamfer=False):
    """The FeatureSpec of a fillet (or chamfer) of `references` (reference texts: edge_between(...),
    edges_of(face(...))): one call on their sum (build123d ShapeLists add up)."""
    joined = " + ".join(references)
    if chamfer:
        return script_model.FeatureSpec("chamfer", (("length", float(radius)),),
                                        f"chamfer({joined}, length={{name}}_length)")
    return script_model.FeatureSpec("fillet", (("radius", float(radius)),), f"fillet({joined}, radius={{name}}_radius)")


class BLENDSOLID_OT_fillet(bpy.types.Operator):
    """Round (or chamfer) edges of a part, named by references its script can resolve"""
    bl_idname = "blendsolid.fillet"
    bl_label = "Fillet"
    bl_options = {"REGISTER", "UNDO"}

    target: StringProperty(name="Part", description="The part whose edges are rounded")
    references: StringProperty(name="Edges", description="The references of the edges, one per line "
                                                         "(edge_between(...), edges_of(face(...)))")
    radius: FloatProperty(name="Radius", default=2.0, min=0.001, precision=3, step=10,
                          description="Fillet radius, or chamfer length, in millimetres")
    chamfer: BoolProperty(name="Chamfer", default=False, description="A flat chamfer instead of a round fillet")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "chamfer")
        layout.prop(self, "radius", text="Length" if self.chamfer else "Radius")

    def execute(self, context):
        from . import ui  # lazy, as in ops_draw
        obj = _local_part(self.target)
        if obj is None:
            self.report({"ERROR"}, f"There is no BlendSolid part named '{self.target}' to fillet")
            return {"CANCELLED"}
        if part.is_scaled(obj):
            self.report({"ERROR"}, part.scaled_message(obj))
            return {"CANCELLED"}
        refs = [r.strip() for r in self.references.splitlines() if r.strip()]
        if not refs:
            self.report({"ERROR"}, "Select one or more edges (or a face, for all its edges) to fillet")
            return {"CANCELLED"}
        try:
            source, _ = script_model.append_feature(part.source_of(obj),
                                                    feature_spec(refs, self.radius, self.chamfer))
        except script_model.NotCanonical as e:
            self.report({"ERROR"}, part.not_canonical_message(obj, e, detail=ui.scripts_visible(context)))
            return {"CANCELLED"}
        obj.blendsolid_script.from_string(source)
        return {"FINISHED"}


CLASSES = [BLENDSOLID_OT_fillet]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
