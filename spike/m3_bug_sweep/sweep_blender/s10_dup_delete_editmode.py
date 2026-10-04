import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
TOP = 'on_face(face("box_1", "+Z"))'
from blendsolid import ops_sketch

def sel(*names):
    for ob in bpy.context.view_layer.objects: ob.select_set(False)
    for n in names: bpy.data.objects[n].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects[names[0]]

def main():
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    settle("Box")
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="RECTANGLE", target="Box", plane=TOP, start=(-5, -5), end=(5, 5))
    settle("Box")
    # Alt+D
    sel("Box")
    bpy.ops.object.duplicate_move_linked("EXEC_DEFAULT", True, TRANSFORM_OT_translate={"value": (0.1, 0, 0)})
    sib = bpy.context.object.name
    print("alt+d:", sib, bpy.data.objects[sib].data == bpy.data.objects["Box"].data)
    runtime.tick()
    # extrude on the sibling
    bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target=sib, sketch="sketch_1", seed=(0, 0), amount=5)
    settle("Box")
    print(state("Box")); print(state(sib))
    check(abs(mm3(bpy.data.objects[sib]) - 24500) < 1e-2, "extrude through the Alt+D sibling")
    # Shift+D of Box, then sketch on the copy -> only the copy changes
    sel("Box")
    bpy.ops.object.duplicate_move("EXEC_DEFAULT", True, TRANSFORM_OT_translate={"value": (0, 0.1, 0)})
    cp = bpy.context.object.name
    runtime.tick()
    print("shift+d:", cp, part.part_id(bpy.data.objects[cp]) != part.part_id(bpy.data.objects["Box"]))
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="CIRCLE", target=cp, sketch="sketch_1", start=(10, 10), end=(12, 10))
    settle(cp); settle("Box")
    print(state(cp)); print(state("Box"))
    check("circle" not in part.source_of(bpy.data.objects["Box"]), "Shift+D copy's sketch doesn't change the original")
    # delete Box (primary) -> sibling becomes primary
    sel("Box")
    bpy.ops.object.delete("EXEC_DEFAULT", True)
    runtime.tick()
    print("after delete:", [o.name for o in bpy.data.objects])
    bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target=sib, sketch="sketch_1", seed=(0, 0), amount=-2, operation="SUBTRACT")
    s = settle(sib)
    print(state(sib))
    bpy.ops.ed.undo(); runtime.tick()
    bpy.ops.ed.undo(); runtime.tick()   # undo delete
    print("after undo delete:", [o.name for o in bpy.data.objects])
    b = settle("Box"); settle(sib)
    print(state("Box")); print(state(sib))
    check(abs(mm3(b) - 24500) < 1e-2 and up_to_date(b), "undo delete: Box back with its extrude")
    print("sketches after undo:", [(s["name"], s["used"]) for s in ops_sketch.sketches_of(b)])
    # Edit Mode: operator while in edit mode
    sel("Box")
    bpy.ops.object.mode_set(mode="EDIT")
    print("editmode", bpy.data.objects["Box"].data.is_editmode, bpy.context.mode)
    try:
        r = bpy.ops.blendsolid.extrude("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", seed=(0, 0), amount=3)
    except RuntimeError as e:
        r = str(e)
    print("extrude in edit mode:", r)
    for i in range(30): runtime.tick(); time.sleep(0.03)
    print("in edit mode:", state("Box"), runtime.part_status(bpy.data.objects["Box"]))
    bpy.ops.object.mode_set(mode="OBJECT")
    b = settle("Box")
    print("after edit mode:", state("Box"))
    check(up_to_date(b), "rebuilt after leaving edit mode")
    # undo in edit mode chain
    bpy.ops.ed.undo(); runtime.tick()
    b = settle("Box")
    print("undo after edit:", state("Box"))

run(main)
