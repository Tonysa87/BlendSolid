import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
import fakeview as fv
from fakeview import ev
from blendsolid import ops_sketch
fv.install()
C = ops_sketch.BLENDSOLID_OT_sketch_entity

def main():
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    settle("Box")
    ctx = fv.context()
    op = fv.fake_op(C, shape="PATH", target="", sketch="", plane="", start=(0, 0), end=(0, 0), points="", closed=False, matrix=[0.0]*16, exact="")
    print(C.invoke(op, ctx, ev("LEFTMOUSE", "PRESS", -10, 0)), op._target.obj, op._target.plane_code)
    for e in [ev("LEFTMOUSE", "RELEASE", -10, 0), ev("LEFTMOUSE", "PRESS", 0, 0), ev("LEFTMOUSE", "RELEASE", 0, 0), ev("A"), ev("LEFTMOUSE", "PRESS", 10, 0), ev("LEFTMOUSE", "RELEASE", 10, 0)]:
        r = C.modal(op, ctx, e)
        print(e.type, e.value, r, op._path, op._snapped)

run(main)
