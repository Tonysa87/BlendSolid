import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
from mathutils import Matrix, Vector
from blendsolid import ops_sketch, ops_extrude

def dims(o):
    return tuple(round(d, 6) for d in o.dimensions)

def main():
    sc = bpy.context.scene
    sc.unit_settings.scale_length = 0.001
    f = part.unit_factor()
    print("factor", f)
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    o = settle("Box")
    bpy.context.view_layer.update()
    print("box dims", dims(o), mm3(o))
    check(dims(o) == (40.0, 30.0, 20.0), "box 40x30x20 BU at scale 0.001")
    # sketch on cursor plane: matrix in world (BU)
    M = Matrix.Translation((100.0, 0, 0))
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="RECTANGLE", start=(0, 0), end=(20, 10), matrix=[v for r in M for v in r])
    s = bpy.context.object
    name = s.name
    settle(name)
    (d,) = ops_sketch.sketches_of(s)
    print("sketch region area", d["regions"][0]["area"])
    # ray pick of the region at uv (5,5): world = (100+5*f, 5*f)
    found = ops_extrude.pick_region(bpy.context, Vector((100 + 5 * f, 5 * f, 50.0)), Vector((0, 0, -1)))
    print("pick", found and (found[0].name, found[2]))
    check(found is not None and abs(found[2][0] - 5) < 1e-4, "pick region uv in mm under scale 0.001")
    bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target=name, sketch="sketch_1", seed=(5, 5), amount=5.0)
    s = settle(name)
    bpy.context.view_layer.update()
    print(state(name), dims(s))
    check(abs(mm3(s) - 1000) < 1e-3 and dims(s) == (20.0, 10.0, 5.0), "extrude 20x10x5 in mm, BU dims at 0.001")
    # change scale back: everything recomputes
    sc.unit_settings.scale_length = 1.0
    o = settle("Box"); s = settle(name)
    bpy.context.view_layer.update()
    print("after scale 1:", dims(o), dims(s))
    check(dims(o) == (0.04, 0.03, 0.02), "box back to 0.04 m")
    # undo: back to before extrude -> scale stays 1 (scene prop not undone?)
    bpy.ops.ed.undo()
    runtime.tick()
    print("after undo scale_length", bpy.context.scene.unit_settings.scale_length)
    o = settle("Box"); s = settle(name)
    bpy.context.view_layer.update()
    print("after undo:", dims(o), dims(s), state(name))
    f = part.unit_factor()
    check(abs(dims(o)[0] - 40 * f) < 1e-6, "box dims follow the current scale after undo")

run(main)
