"""BlendSolid — minimal spike build (objective 8): checks that the packaged OCP wheels work."""
import bpy


class BLENDSOLID_OT_test_solid(bpy.types.Operator):
    """Creates the spike test solid (box + cylinder + fillet) with OCCT"""
    bl_idname = "blendsolid.test_solid"
    bl_label = "BlendSolid: Test Solid"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        import OCP
        from . import bl_bridge, occ_model
        shape, (v, t, f), _ = occ_model.build_and_tessellate()
        info = occ_model.check(shape)
        obj = bl_bridge.ensure_object("BS_Solid")
        bl_bridge.fill_mesh(obj.data, v, t, f)
        msg = f"OCP from {OCP.__file__}: valid={info['valid']} volume={info['volume']:.3f} faces={info['faces']}"
        print("[8]", msg)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


def register():
    bpy.utils.register_class(BLENDSOLID_OT_test_solid)


def unregister():
    bpy.utils.unregister_class(BLENDSOLID_OT_test_solid)
