import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
import fakeview as fv
from fakeview import ev
from blendsolid import ops_extrude, drawing, ops_sketch
from mathutils import Matrix
fv.install()
# the drag amount (mm) is the event's mouse_region_y / 10
drawing.height_along_normal = lambda plane, start, o, d: (fv._amount_mm * part.unit_factor())
fv._amount_mm = 0.0
X = ops_extrude.BLENDSOLID_OT_extrude
G = ops_extrude.BLENDSOLID_OT_groove

def move(op, ctx, cls, mm, kind="MOUSEMOVE", value="NOTHING"):
    fv._amount_mm = mm
    return cls.modal(op, ctx, ev(kind, value, 0, 0))

def sketch_only_part():
    clean()
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="RECTANGLE", start=(0, 0), end=(20, 10),
                                     matrix=[v for r in Matrix.Identity(4) for v in r])
    o = bpy.context.object
    settle(o.name)
    return o.name

def main():
    name = sketch_only_part()
    ctx = fv.context()
    op = fv.fake_op(X, target="", sketch="", seed=(0, 0), amount=0.0, operation="ADD", extent="DISTANCE", symmetric=False, taper=0.0)
    r = X.invoke(op, ctx, ev("LEFTMOUSE", "PRESS", 50, 50))
    print("invoke", r, getattr(op, "_obj", None))
    for mm in (-1.0, -3.0, -5.0):
        print(" move", mm, move(op, ctx, X, mm), "op auto:", ops_extrude.auto_operation(bpy.data.objects[name], mm))
        for i in range(60):
            runtime.tick(); time.sleep(0.03)
        print("   ", state(name))
    fv._amount_mm = -5.0
    r = X.modal(op, ctx, ev("LEFTMOUSE", "RELEASE", 0, 0))
    print("release", r, "operation written:", op.operation)
    o = settle(name)
    print(state(name))
    print([l for l in part.source_of(o).splitlines() if "extrude(" in l])
    check(o.blendsolid_error == "" and abs(mm3(o) - 1000) < 1e-3, "dragging a sketch-only part's region down makes a 20x10x5 solid")

    # same for groove: a path-only part
    clean()
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="PATH", points=json.dumps([[0, 0, False], [20, 0, False]]),
                                     matrix=[v for r in Matrix.Identity(4) for v in r])
    name = bpy.context.object.name
    settle(name)
    ctx = fv.context()
    bpy.context.scene.blendsolid_groove_profile = "rect"
    op = fv.fake_op(G, target="", sketch="", entity="", operation="SUBTRACT", profile="rect", width=2.0, depth=1.0, corners="mitre")
    # pick_curve uses mouse_ray + entity_at with pixel; press on (10, 0) mm = region (100, 0)
    r = G.invoke(op, ctx, ev("LEFTMOUSE", "PRESS", 100, 0))
    print("groove invoke", r)
    if r == {"RUNNING_MODAL"}:
        for mm in (-1.0, -2.0):
            print(" move", mm, move(op, ctx, G, mm))
            for i in range(60):
                runtime.tick(); time.sleep(0.03)
            print("   ", state(name))
        fv._amount_mm = -2.0
        print("release", G.modal(op, ctx, ev("LEFTMOUSE", "RELEASE", 0, 0)), op.operation)
        o = settle(name)
        print(state(name))
        check(o.blendsolid_error == "", "groove dragged 'into' a path-only part makes a rib, no error")

run(main)
