import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
TOP = 'on_face(face("box_1", "+Z"))'
from blendsolid import ops_sketch, ops_extrude, trust, picking, ops_fillet
from mathutils import Vector
F = "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender/s09.blend"

def main():
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    settle("Box")
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="PATH", target="Box", plane=TOP,
        points=json.dumps([[-15, -5, False], [5, -5, False], [5, 5, True], [-15, 5, False]]))
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="RECTANGLE", target="Box", sketch="sketch_1", start=(8, -4), end=(16, 4))
    settle("Box")
    bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", entity="path_1", width=2, depth=1.5)
    settle("Box")
    v0 = mm3(bpy.data.objects["Box"])
    print(state("Box"))
    bpy.ops.wm.save_as_mainfile(filepath=F)
    bpy.ops.wm.open_mainfile(filepath=F)
    bpy.ops.ed.undo_push()
    o = bpy.data.objects["Box"]
    print("trusted?", trust.is_trusted(o), "status", runtime.part_status(o))
    for i in range(20): runtime.tick(); time.sleep(0.02)
    print("after ticks", state("Box"))
    check(abs(mm3(o) - v0) < 1e-6, "reloaded mesh volume is the saved one")
    sk = ops_sketch.sketches_of(o)
    print("sketches after reload", [(s["name"], s["used"], len(s["regions"])) for s in sk])
    # tools on an untrusted part
    f = part.unit_factor()
    region = ops_extrude.pick_region(bpy.context, Vector((12 * f, 0, 1.0)), Vector((0, 0, -1)))
    print("extrude pick_region on untrusted:", region and region[0].name)
    curve = None
    pk = picking.pick(bpy.context, Vector((19.9 * f, 0, 1.0)), Vector((0, 0, -1)), 0.0005 * f)
    print("fillet/push-pull picking on untrusted:", pk and (pk.kind, pk.reference))
    check(pk is None, "fillet/push-pull picking refuses an untrusted part (as Draw Solid and Extrude do)")
    src = part.source_of(o)
    refs = list(o.data[part.EDGE_REFS_KEY])
    try:
        r = bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target="Box", references=refs[0], radius=1.0)
    except RuntimeError as e:
        r = str(e)
    print("fillet on untrusted:", r)
    check(part.source_of(bpy.data.objects["Box"]) == src, "fillet operator refuses an untrusted part")
    for i in range(20): runtime.tick(); time.sleep(0.02)
    o = bpy.data.objects["Box"]
    print("after fillet on untrusted:", state("Box"), runtime.part_status(o))
    bpy.ops.ed.undo()
    o = bpy.data.objects["Box"]
    print("after undo:", state("Box"))
    # trust then extrude the rectangle region
    bpy.ops.blendsolid.trust_scripts()
    o = settle("Box")
    print("trusted:", state("Box"))
    check(abs(mm3(o) - v0) < 1e-3, "trusted recompute keeps the volume")
    bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", seed=(12, 0), amount=-3, operation="SUBTRACT")
    o = settle("Box")
    print("extruded:", state("Box"))
    check(abs(mm3(o) - (v0 - 8 * 8 * 3)) < 1, f"cut 8x8x3 ({v0 - mm3(o)})")
    bpy.ops.ed.undo(); runtime.tick()
    o = settle("Box")
    print("undo extrude:", state("Box"))
    check(abs(mm3(o) - v0) < 1e-3, "undo extrude")
    # save again, reload, check undo after load works
    bpy.ops.wm.save_as_mainfile(filepath=F)
    bpy.ops.wm.open_mainfile(filepath=F)
    print("2nd reload:", state("Box"), trust.file_trusted())

run(main)
