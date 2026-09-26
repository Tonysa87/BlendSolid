"""Tool 2: Draw Solid. Draw a box or a cylinder on a part's face or on the 3D cursor's plane; on a part, the
direction of the height picks the boolean (out of the face: union, into it: cut); elsewhere it makes a new part.

The operator's properties describe the finished solid (shape, mode, the part it is drawn on, placement and
dimensions in millimetres), and execute() only reads them: the interactive modal sets them and ends by calling
execute(), Blender's redo re-runs execute() with the values edited in the Adjust Last Operation panel, and
tests call it directly. The result is one feature with a fixed placement (a Location in the part's frame).
"""
import math

import bpy
from bpy.props import EnumProperty, FloatProperty, FloatVectorProperty, StringProperty
from mathutils import Matrix

from . import drawing, ops_add, part, primitives, script_model

SHAPES = [("BOX", "Box", "Draw a box", "MESH_CUBE", 0),
          ("CYLINDER", "Cylinder", "Draw a cylinder", "MESH_CYLINDER", 1)]
MODES = [("NEW", "New Part", "Make a new part", "ADD", 0),
         ("UNION", "Union", "Add the solid to the part it is drawn on", "SELECT_EXTEND", 1),
         ("CUT", "Cut", "Cut the solid out of the part it is drawn on", "SELECT_SUBTRACT", 2)]
KIND = {"BOX": "box", "CYLINDER": "cylinder"}


def _local_part(name):
    obj = bpy.data.objects.get((name, None)) if name else None
    return obj if part.is_local_part(obj) else None


class BLENDSOLID_OT_draw_solid(bpy.types.Operator):
    """Draw a box or cylinder on a part's face (union or cut, by the direction of its height) or on the 3D
    cursor's plane (a new part)"""
    bl_idname = "blendsolid.draw_solid"
    bl_label = "Draw Solid"
    bl_options = {"REGISTER", "UNDO"}

    shape: EnumProperty(name="Shape", items=SHAPES, default="BOX")
    mode: EnumProperty(name="Mode", items=MODES, default="NEW")
    target: StringProperty(name="Part", description="The part the solid is drawn on; its placement is in that "
                                                    "part's frame (empty: in the world)")
    location: FloatVectorProperty(name="Location", size=3, precision=3,
                                  description="Centre of the solid's base, millimetres")
    rotation: FloatVectorProperty(name="Rotation", size=3, subtype="EULER",
                                  description="Orientation of the base (build123d Location angles)")
    length: FloatProperty(name="Length", default=10.0, min=0.001, precision=3, step=100)
    width: FloatProperty(name="Width", default=10.0, min=0.001, precision=3, step=100)
    radius: FloatProperty(name="Radius", default=5.0, min=0.001, precision=3, step=100)
    height: FloatProperty(name="Height", default=10.0, min=0.001, precision=3, step=100)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "shape")
        layout.prop(self, "mode")
        layout.prop(self, "target")
        layout.label(text="Millimetres, in the part's frame (the world's when no part)")
        for name in (("length", "width") if self.shape == "BOX" else ("radius",)) + ("height",):
            layout.prop(self, name)
        layout.prop(self, "location")
        layout.prop(self, "rotation")

    def _values(self):
        if self.shape == "BOX":
            return {"length": self.length, "width": self.width, "height": self.height}
        return {"radius": self.radius, "height": self.height}

    def execute(self, context):
        from . import ui  # lazy: ui.py itself imports ops_add/runtime lazily to avoid import cycles
        factor = part.unit_factor(context.scene)
        reference = _local_part(self.target)
        if self.target and reference is None:
            self.report({"ERROR"}, f"There is no BlendSolid part named '{self.target}' to draw on")
            return {"CANCELLED"}
        if self.mode != "NEW" and reference is None:
            self.report({"ERROR"}, "Union and Cut need the part the solid is drawn on")
            return {"CANCELLED"}
        if reference is not None and part.is_scaled(reference):
            self.report({"ERROR"}, part.scaled_message(reference))
            return {"CANCELLED"}
        kind = KIND[self.shape]
        frame = drawing.frame_matrix(self.location, self.rotation, factor)
        if self.mode == "NEW":
            matrix = (reference.matrix_world if reference is not None else Matrix.Identity(4)) @ frame
            ops_add.add_primitive_part(context, kind, self._values(), matrix=matrix)
            return {"FINISHED"}
        spec = primitives.feature_spec(
            kind, self._values(), mode="ADD" if self.mode == "UNION" else "SUBTRACT",
            align=primitives.BASE if self.mode == "UNION" else primitives.TOP,
            location=tuple(self.location), rotation=tuple(math.degrees(a) for a in self.rotation))
        try:
            source, _ = script_model.append_feature(part.source_of(reference), spec)
        except script_model.NotCanonical as e:
            self.report({"ERROR"}, part.not_canonical_message(reference, e, detail=ui.scripts_visible(context)))
            return {"CANCELLED"}
        reference.blendsolid_script.from_string(source)
        return {"FINISHED"}


def drawn_properties(drawn, target, factor):
    """The draw_solid operator properties for a drag (drawing.Drawn) on part `target` (or None): on a part,
    a positive height (out of the face) is a union and a negative one a cut; elsewhere it is a new part."""
    frame, height = drawn.frame, drawn.height
    if target is not None:
        mode = "UNION" if height > 0 else "CUT"
    else:
        mode = "NEW"
        if height < 0:  # drawn downwards: the new part's frame looks the other way
            frame = frame @ Matrix.Rotation(math.pi, 4, "X")
    location, rotation = drawing.placement(frame, target.matrix_world if target is not None else None, factor)
    props = {"shape": drawn.shape, "mode": mode, "target": target.name if target is not None else "",
             "location": location, "rotation": rotation, "height": abs(height)}
    if drawn.shape == "BOX":
        props.update(length=drawn.length, width=drawn.width)
    else:
        props.update(radius=drawn.radius)
    return props


CLASSES = [BLENDSOLID_OT_draw_solid]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
