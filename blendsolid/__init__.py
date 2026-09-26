"""BlendSolid — exact BRep/NURBS CAD modeling in Blender with a parametric history written as code.

bpy is imported only inside register()/unregister(), so the bpy-free modules can be unit tested.
"""


def register():
    from . import gizmos, ops_add, ops_boolean, ops_draw, runtime, ui
    ui.register()
    ops_add.register()
    ops_boolean.register()
    ops_draw.register()
    gizmos.register()
    runtime.register()


def unregister():
    from . import gizmos, ops_add, ops_boolean, ops_draw, runtime, ui
    runtime.unregister()
    gizmos.unregister()
    ops_draw.unregister()
    ops_boolean.unregister()
    ops_add.unregister()
    ui.unregister()
