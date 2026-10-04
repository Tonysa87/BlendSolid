import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *

TOP = 'on_face(face("box_1", "+Z"))'

def attempt(label, fn):
    o = bpy.data.objects["Box"]
    before = part.source_of(o)
    try:
        r = fn()
    except RuntimeError as e:
        r = f"RuntimeError: {str(e).splitlines()[0]}"
    after = part.source_of(bpy.data.objects["Box"])
    print(f"{label}: {r}")
    check(after == before, f"{label}: refused on failing part (script unchanged)")

def main():
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    settle("Box")
    sk = bpy.ops.blendsolid.sketch_entity
    sk("EXEC_DEFAULT", True, shape="RECTANGLE", start=(-5, -5), end=(5, 5), target="Box", plane=TOP)
    sk("EXEC_DEFAULT", True, shape="PATH", target="Box", sketch="sketch_1", points=json.dumps([[-20, -10, False], [20, -10, False]]))
    settle("Box")
    refs = list(bpy.data.objects["Box"].data[part.EDGE_REFS_KEY])
    # make it fail: fillet radius 50 on an edge
    bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target="Box", references=refs[0], radius=50.0)
    o = settle("Box")
    print(state("Box"))
    print("blocking:", part.blocking_error(o))
    check(bool(o.blendsolid_error), "fillet 50 fails")
    attempt("sketch rect new sketch", lambda: sk("EXEC_DEFAULT", True, shape="RECTANGLE", start=(-5, -5), end=(5, 5), target="Box", plane='on_face(face("box_1", "-Z"))'))
    attempt("sketch add to sketch_1", lambda: sk("EXEC_DEFAULT", True, shape="CIRCLE", start=(0, 0), end=(2, 0), target="Box", sketch="sketch_1"))
    attempt("extrude", lambda: bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", seed=(0, 0), amount=5))
    attempt("groove", lambda: bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", entity="path_1"))
    attempt("revolve", lambda: bpy.ops.blendsolid.revolve("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", seed=(0, 0), axis="path_1"))
    attempt("fillet", lambda: bpy.ops.blendsolid.fillet("EXEC_DEFAULT", True, target="Box", references=refs[1], radius=1))
    attempt("push_pull", lambda: bpy.ops.blendsolid.push_pull("EXEC_DEFAULT", True, target="Box", reference='face("box_1", "+X")', amount=3))
    attempt("draw union", lambda: bpy.ops.blendsolid.draw_solid("EXEC_DEFAULT", True, target="Box", mode="UNION", shape="BOX") if hasattr(bpy.ops.blendsolid, "draw_solid") else "no op")
    # boolean: select another part and the box
    bpy.ops.blendsolid.add_cylinder("EXEC_DEFAULT", True)
    settle("Cylinder")
    for ob in bpy.context.view_layer.objects: ob.select_set(False)
    bpy.data.objects["Cylinder"].select_set(True); bpy.data.objects["Box"].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["Box"]
    ops = [n for n in dir(bpy.ops.blendsolid) if "bool" in n]
    print("boolean ops", ops)
    attempt("boolean", lambda: bpy.ops.blendsolid.boolean("EXEC_DEFAULT", True, operation="DIFFERENCE"))
    # error label/blocking on a Alt+D sibling
    sib = bpy.data.objects["Box"].copy(); bpy.context.collection.objects.link(sib)
    runtime.tick()
    print("sibling", sib.name, "blocking:", part.blocking_error(sib))
    check(part.blocking_error(sib) is not None, "a linked duplicate of a failing part is blocked too")
    from blendsolid import ui
    print("label:", ui.error_label(bpy.data.objects["Box"]))
    print("label sib:", ui.error_label(sib))

run(main)
