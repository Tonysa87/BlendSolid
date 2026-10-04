import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *

def main():
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    box = settle("Box")
    refs = list(box.data[part.EDGE_REFS_KEY])
    print("edge refs", refs[:3])
    # a chamfer with Two Distances (as set in the Adjust Last Operation panel)
    r = bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target="Box", references=refs[0], radius=1.0, chamfer=True,
                                  chamfer_mode="TWO", length2=3.0)
    print(r, part.source_of(bpy.data.objects["Box"]))
    settle("Box")
    # now the tool's drag release call (as ops_fillet modal does): only target, references, radius, chamfer
    r = bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target="Box", references=refs[5], radius=1.5, chamfer=True)
    src = part.source_of(bpy.data.objects["Box"])
    print(src)
    last = [l for l in src.splitlines() if "chamfer" in l or "fillet" in l]
    print(last)
    check("3.0" not in src.split("feature: fillet_2")[0].split("\n")[-1] , "second chamfer not given length2 from the previous call")

run(main)
