import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
import fakeview as fv
from fakeview import ev
from blendsolid import ops_fillet, drawing
fv.install()
drawing.height_along_normal = lambda plane, start, o, d: (fv._amount_mm * part.unit_factor())
fv._amount_mm = 0.0
F = ops_fillet.BLENDSOLID_OT_fillet_click

def pump(op, ctx, secs=4.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        runtime.tick()
        F.modal(op, ctx, ev("TIMER", "NOTHING"))
        time.sleep(0.05)

def drag(radii, chamfer_toggle_at=None, release=True):
    clean()
    ops_fillet.select(None)
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    settle("Box")
    ctx = fv.context()
    op = fv.fake_op(F)
    fv._amount_mm = 0.0
    r = F.invoke(op, ctx, ev("LEFTMOUSE", "PRESS", 197, 3))
    print("invoke", r, op._pick and (op._pick.kind, op._pick.reference))
    for i, rad in enumerate(radii):
        fv._amount_mm = rad
        F.modal(op, ctx, ev("MOUSEMOVE", "NOTHING", 200, 100 + i))
        if chamfer_toggle_at == i:
            F.modal(op, ctx, ev("C"))
        pump(op, ctx)
        o = bpy.data.objects["Box"]
        print(f"  wanted {rad}: radius={op._radius:.4f} limit={op._limit} err={o.blendsolid_error[:70]!r} up={up_to_date(o)}")
    if release:
        try:
            res = F.modal(op, ctx, ev("LEFTMOUSE", "RELEASE", 200, 120))
        except Exception as e:
            res = f"EXC {e}"
        o = settle("Box")
        print("release", res, state("Box"))
        return o, op
    return None, op

def main():
    o, op = drag([5.0, 25.0, 40.0, 60.0])
    check(o.blendsolid_error == "", "a drag far past the limit leaves a fillet that builds")
    check(not ops_fillet._dragging, "fillet drag cleaned up")
    o, op = drag([5.0, 40.0, 40.0], chamfer_toggle_at=1)
    check(o.blendsolid_error == "", "chamfer drag past the limit builds")
    # ESC mid-drag restores the script
    o, op = drag([5.0, 50.0], release=False)
    ctx = fv.context()
    F.modal(op, ctx, ev("ESC"))
    o = settle("Box")
    print("esc:", state("Box"))
    check("fillet" not in part.source_of(o) and o.blendsolid_error == "", "esc restores the script and no error remains")

run(main)
