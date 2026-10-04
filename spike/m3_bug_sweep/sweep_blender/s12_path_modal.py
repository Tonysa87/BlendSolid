import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
import fakeview as fv
from fakeview import ev
from blendsolid import ops_sketch
fv.install()
C = ops_sketch.BLENDSOLID_OT_sketch_entity

def new_op():
    return fv.fake_op(C, shape="PATH", target="", sketch="", plane="", start=(0, 0), end=(0, 0), points="", closed=False,
                      matrix=[0.0] * 16, exact="")

def drive(events, setup_box=True):
    clean()
    ops_sketch._sticky = None
    if setup_box:
        bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
        settle("Box")
    ctx = fv.context()
    op = new_op()
    first = events[0]
    r = C.invoke(op, ctx, first)
    res = [r]
    for e in events[1:]:
        try:
            r = C.modal(op, ctx, e)
        except Exception as ex:
            import traceback; traceback.print_exc()
            r = f"EXC {type(ex).__name__}: {ex}"
        res.append(r)
        if r in ({"FINISHED"}, {"CANCELLED"}) or isinstance(r, str):
            break
    return op, res, ctx

def click(x, y):
    return [ev("LEFTMOUSE", "PRESS", 10*x, 10*y), ev("LEFTMOUSE", "RELEASE", 10*x, 10*y)]

def report(label, op, res):
    handles = getattr(op, "_handles", None)
    print(f"[{label}] results={[r if isinstance(r,str) else sorted(r) for r in res][-3:]} points={op.points!r} closed={op.closed} handles_left={handles} dragging={len(ops_sketch._dragging)} header_last={fv.headers[-1] if fv.headers else None!r}")
    if ops_sketch._dragging:
        FINDINGS.append(f"{label}: _dragging not emptied")
        ops_sketch._dragging.clear()
    if fv.headers and fv.headers[-1] is not None:
        FINDINGS.append(f"{label}: header text left: {fv.headers[-1]!r}")
    for n in [o.name for o in bpy.data.objects]:
        try:
            o = settle(n, 30)
            print("   ", state(n))
        except AssertionError:
            print("   timeout", n)

def main():
    # 1: A, B, click A (close with two points)
    op, res, _ = drive([ev("LEFTMOUSE", "PRESS", -100, 0), ev("LEFTMOUSE", "RELEASE", -100, 0)] + click(10, 0) + click(-10, 0))
    report("close with 2 points", op, res)
    # 2: A, B, arc mode, click straight ahead
    op, res, _ = drive(click(-10, 0)[0:1] + click(-10, 0)[1:] + click(0, 0) + [ev("A")] + click(10, 0) + [ev("RET")])
    report("arc straight ahead", op, res)
    # 3: backspace past empty
    op, res, _ = drive(click(-10, 0)[0:1] + click(-10, 0)[1:] + click(0, 0) + [ev("BACK_SPACE"), ev("BACK_SPACE"), ev("BACK_SPACE")])
    report("backspace past empty", op, res)
    # 4: ctrl+z twice then enter with 1 point
    op, res, _ = drive(click(-10, 0)[0:1] + click(-10, 0)[1:] + click(0, 0) + click(5, 5) + [ev("Z", ctrl=True), ev("RET")])
    report("ctrl+z then enter", op, res)
    # 5: ESC mid path
    op, res, _ = drive(click(-10, 0)[0:1] + click(-10, 0)[1:] + click(0, 0) + [ev("ESC")])
    report("esc", op, res)
    # 6: backspace while the first press is still down (before release)
    op, res, _ = drive([ev("LEFTMOUSE", "PRESS", -10, 0), ev("BACK_SPACE")])
    report("backspace before first release", op, res)
    # 7: right-click with one point
    op, res, _ = drive(click(-10, 0)[0:1] + click(-10, 0)[1:] + [ev("RIGHTMOUSE")])
    report("rightclick 1 point", op, res)
    # 8: arc by drag closing on the first point, 3 points
    op, res, _ = drive(click(-10, -5)[0:1] + click(-10, -5)[1:] + click(10, -5) + click(10, 5) +
                       [ev("LEFTMOUSE", "PRESS", 0, 0), ev("MOUSEMOVE", "NOTHING", -100, -50), ev("LEFTMOUSE", "RELEASE", -100, -50)])
    report("close by dragged arc", op, res)
    # 9: on the cursor plane (no part): path then Enter -> new part
    op, res, _ = drive(click(100, 100)[0:1] + click(100, 100)[1:] + click(120, 100) + [ev("RET")], setup_box=False)
    report("cursor plane path", op, res)
    # 10: double click to end
    op, res, _ = drive(click(-10, 0)[0:1] + click(-10, 0)[1:] + click(0, 0) + [ev("LEFTMOUSE", "DOUBLE_CLICK", 0, 0), ev("LEFTMOUSE", "RELEASE", 0, 0)])
    report("double click end", op, res)
    # 11: A on the first segment then click (arc not allowed yet), then A pressed twice
    op, res, _ = drive(click(-10, 0)[0:1] + click(-10, 0)[1:] + [ev("A")] + click(0, 0) + [ev("A"), ev("A")] + click(0, 10) + [ev("RET")])
    report("A on first segment", op, res)
    # 12: rectangle drag with zero size
    clean(); bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True); settle("Box")
    ctx = fv.context(); op = new_op(); op.shape = "RECTANGLE"
    bpy.context.scene.blendsolid_sketch_shape = "RECTANGLE"
    r = C.invoke(op, ctx, ev("LEFTMOUSE", "PRESS", 0, 0))
    r2 = C.modal(op, ctx, ev("LEFTMOUSE", "RELEASE", 0, 0))
    print("zero rect", r, r2, ops_sketch._dragging, fv.headers[-1])
    bpy.context.scene.blendsolid_sketch_shape = "PATH"

run(main)
