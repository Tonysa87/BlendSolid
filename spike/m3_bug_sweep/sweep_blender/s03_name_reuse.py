import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
from blendsolid import ops_add

def main():
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)   # 40x30x20
    settle("Box")
    print(state("Box"))
    # delete it (as X > Delete does), then add another Box of another size
    obj = bpy.data.objects["Box"]
    bpy.data.objects.remove(obj)
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True, length=10, width=10, height=10)
    new = bpy.data.objects["Box"]
    runtime.tick()
    print("after one tick:", state("Box"))
    check(len(new.data.polygons) == 0 or abs(mm3(new) - 1000) < 1, f"new Box doesn't show the deleted Box's mesh while computing (vol {mm3(new):.1f})")
    settle("Box")
    print(state("Box"))
    # now a failing part with a reused name
    obj = bpy.data.objects["Box"]
    bpy.data.objects.remove(obj)
    bad = part.new_part(bpy.context, part.default_source().replace("result = part.part", "result = part.part\n1/0"), name="Box")
    print(bad.name)
    settle("Box")
    bad = bpy.data.objects["Box"]
    print("failing new part:", state("Box"))
    check(len(bad.data.polygons) == 0, f"a brand-new failing part shows no mesh (has {len(bad.data.polygons)} polys, vol {mm3(bad):.1f})")
    # Placement cancel then a new Add of a different primitive named the same? use cylinder-> different name, skip

run(main)
