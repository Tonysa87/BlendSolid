"""BlendSolid — exact BRep/NURBS CAD modeling in Blender with a parametric history written as code.

bpy is imported only inside register()/unregister(), so the bpy-free modules can be unit tested.
"""


def register():
    from . import runtime, ui
    ui.register()
    runtime.register()


def unregister():
    from . import runtime, ui
    runtime.unregister()
    ui.unregister()
