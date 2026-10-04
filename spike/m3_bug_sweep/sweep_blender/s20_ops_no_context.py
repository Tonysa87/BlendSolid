import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *

def sweep(label):
    for name in sorted(dir(bpy.ops.blendsolid)):
        if name.startswith("add_") or name in ("call_pie", "pie_or_menu"):
            continue
        op = getattr(bpy.ops.blendsolid, name)
        try:
            if not op.poll():
                print(f"[{label}] {name}: poll False"); continue
            r = op("EXEC_DEFAULT")
            print(f"[{label}] {name}: {r}")
        except RuntimeError as e:
            msg = str(e)
            tb = "Traceback" in msg
            print(f"[{label}] {name}: {'TRACEBACK ' if tb else ''}{msg.splitlines()[0][:150]}")
            if tb:
                FINDINGS.append(f"{label} {name}: {msg[-300:]}")
        except Exception as e:
            print(f"[{label}] {name}: {type(e).__name__} {e}")

def main():
    bpy.ops.ed.undo_push()
    sweep("empty scene")
    bpy.ops.mesh.primitive_cube_add()
    sweep("plain cube active")
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    settle("Box")
    bpy.context.view_layer.objects.active = None
    sweep("part exists, none active")

run(main)
