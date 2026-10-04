import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *

def main():
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    o = settle("Box")
    ref = 'edge_between(face("box_1", "+X"), face("box_1", "+Z"))'
    bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target="Box", references=ref, radius=50.0)
    o = settle("Box")
    print("fillet 50:", state("Box"))
    # fix it from the panel: radius 5
    o.blendsolid_params["fillet_1_radius"].value = 5.0
    bpy.ops.ed.undo_push(message="radius 5")
    o = settle("Box")
    print("radius 5:", state("Box"))
    v5 = mm3(o)
    runtime.tick()
    bpy.ops.ed.undo()
    o = settle("Box")
    print("undo to fillet 50:", state("Box"))
    check(abs(mm3(o) - 24000) < 0.01, f"after undo to the failing fillet 50, the part shows its last good result (plain box 24000), not the radius-5 mesh of the step undone ({mm3(o):.2f}; r5 = {v5:.2f})")
    bpy.ops.ed.redo()
    o = settle("Box")
    print("redo:", state("Box"))

run(main)
