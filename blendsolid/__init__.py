"""BlendSolid — exact BRep/NURBS CAD modeling in Blender with a parametric history written as code.

bpy is imported only inside register()/unregister(), so the bpy-free modules can be unit tested.
"""


def register():
    from . import ops_add, runtime, ui
    ui.register()
    ops_add.register()
    runtime.register()


def unregister():
    from . import ops_add, runtime, ui
    runtime.unregister()
    ops_add.unregister()
    ui.unregister()
