"""BlendSolid — exact BRep/NURBS CAD modeling in Blender with a parametric history written as code.

bpy is imported only inside register()/unregister(), so the bpy-free modules can be unit tested.
"""


def register():
    from . import (focus, gizmos, ops_add, ops_boolean, ops_draw, ops_extrude, ops_fillet, ops_pushpull,
                   ops_sketch, pies, runtime, ui)
    ui.register()
    focus.register()
    ops_add.register()
    ops_boolean.register()
    ops_draw.register()
    ops_fillet.register()
    ops_pushpull.register()
    ops_sketch.register()
    ops_extrude.register()
    gizmos.register()
    pies.register()
    runtime.register()


def unregister():
    from . import (focus, gizmos, ops_add, ops_boolean, ops_draw, ops_extrude, ops_fillet, ops_pushpull,
                   ops_sketch, pies, runtime, ui)
    runtime.unregister()
    pies.unregister()
    gizmos.unregister()
    ops_extrude.unregister()
    ops_sketch.unregister()
    ops_pushpull.unregister()
    ops_fillet.unregister()
    ops_draw.unregister()
    ops_boolean.unregister()
    ops_add.unregister()
    focus.unregister()
    ui.unregister()
