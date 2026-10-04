import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *

TOP = 'on_face(face("box_1", "+Z"))'

def sk(**kw):
    return bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, **kw)

def consistent(name, label):
    o = settle(name)
    s = state(name)
    print(label, "->", s)
    ok = up_to_date(o) or o.blendsolid_error
    check(up_to_date(o), f"{label}: up to date")
    return o

def main():
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    consistent("Box", "add box")
    pts = [[-15.0, -5.0, False], [5.0, -5.0, False], [5.0, 5.0, True], [-15.0, 5.0, False]]
    sk(shape="PATH", target="Box", plane=TOP, points=json.dumps(pts))
    consistent("Box", "path")
    r = bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", entity="path_1", width=2.0, depth=1.5, operation="SUBTRACT")
    runtime.tick()   # recompute in flight
    v_groove = mm3(bpy.data.objects["Box"])
    bpy.ops.ed.undo()
    o = consistent("Box", "undo groove")
    check(abs(mm3(o) - 24000) < 1e-3, f"undo groove volume 24000 ({mm3(o)})")
    bpy.ops.ed.redo()
    o = consistent("Box", "redo groove")
    vg = mm3(o)
    check(abs(vg - (24000 - 3 * (40 + 5 * math.pi))) < 1, f"redo groove volume ({vg})")
    # Adjust last operation: undo then groove with other values, several times quickly without settling
    for prof, w in (("round", 3.0), ("v", 2.5), ("circle", 2.0), ("rect", 4.0)):
        bpy.ops.ed.undo()
        bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", entity="path_1", width=w, depth=1.5, profile=prof, operation="SUBTRACT")
        runtime.tick()
        print("redo-panel", prof, state("Box"))
    o = consistent("Box", "after panel reruns")
    check(abs(mm3(o) - (24000 - 6 * (40 + 5 * math.pi))) < 2, f"rect 4x1.5 groove volume ({mm3(o)})")
    src = part.source_of(o)
    check(src.count("groove(") == 1 or src.count("feature: groove") == 1, "only one groove feature")
    # undo back two steps, then redo twice
    bpy.ops.ed.undo(); runtime.tick(); bpy.ops.ed.undo(); runtime.tick()
    o = consistent("Box", "undo x2")
    check(abs(mm3(o) - 24000) < 1e-3 and "sketch" not in part.source_of(o), "undo x2: plain box")
    bpy.ops.ed.redo(); runtime.tick(); bpy.ops.ed.redo(); runtime.tick()
    o = consistent("Box", "redo x2")
    check(abs(mm3(o) - (24000 - 6 * (40 + 5 * math.pi))) < 2, f"redo x2 volume ({mm3(o)})")
    print(part.source_of(o))

run(main)
