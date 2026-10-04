import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
TOP = 'on_face(face("box_1", "+Z"))'

VARIANTS = [
    dict(amount=5.0), dict(amount=-5.0, operation="SUBTRACT"), dict(amount=-1.0, operation="SUBTRACT", extent="NEXT"),
    dict(amount=-1.0, operation="SUBTRACT", extent="LAST"), dict(amount=1.0, operation="ADD", extent="NEXT"),
    dict(amount=1.0, operation="ADD", extent="LAST"), dict(amount=5.0, symmetric=True),
    dict(amount=5.0, taper=45.0), dict(amount=5.0, taper=-45.0), dict(amount=30.0, taper=30.0),
    dict(amount=-25.0, operation="SUBTRACT", taper=10.0), dict(amount=5.0, operation="INTERSECT"),
    dict(amount=-5.0, operation="INTERSECT"), dict(amount=5.0, symmetric=True, taper=10.0),
    dict(amount=-5.0, operation="ADD"), dict(amount=5.0, operation="SUBTRACT"),
]

def main():
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    settle("Box")
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="RECTANGLE", target="Box", plane=TOP, start=(-5, -5), end=(5, 5))
    settle("Box")
    bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", seed=(0, 0), amount=3.0)
    runtime.tick()
    for v in VARIANTS:
        bpy.ops.ed.undo()
        kw = dict(target="Box", sketch="sketch_1", seed=(0, 0)); kw.update(v)
        try:
            r = bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, **kw)
        except RuntimeError as e:
            r = str(e).splitlines()[0]
        o = settle("Box")
        print(v, r, "->", f"vol={mm3(o):.2f} err={o.blendsolid_error!r} up={up_to_date(o)}")
        if o.blendsolid_error and not o.blendsolid_error.startswith(("Sketch", "RuntimeError: Nothing")):
            FINDINGS.append(f"{v}: {o.blendsolid_error}")
    # the panel offers PATH for a rectangle
    bpy.ops.ed.undo(); bpy.ops.ed.undo()
    try:
        r = bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="PATH", target="Box", plane=TOP, start=(-5, -5), end=(5, 5))
    except RuntimeError as e:
        r = str(e)
    print("rect re-run as PATH from the panel:", r)

run(main)
