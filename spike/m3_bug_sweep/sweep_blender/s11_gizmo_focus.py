import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
TOP = 'on_face(face("box_1", "+Z"))'
from blendsolid import gizmos, focus, ui
from mathutils import Matrix

def main():
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    settle("Box")
    E = bpy.ops.blendsolid
    E.sketch_entity("EXEC_DEFAULT", True, shape="RECTANGLE", target="Box", plane=TOP, start=(-5, -5), end=(5, 5))
    E.sketch_entity("EXEC_DEFAULT", True, shape="PATH", target="Box", sketch="sketch_1", points=json.dumps([[-20, 10, False], [20, 10, False]]))
    settle("Box")
    E.extrude("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", seed=(0, 0), amount=5, taper=5.0)
    E.groove("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", entity="path_1", width=2, depth=1)
    E.extrude("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", seed=(0, 0), amount=-1, extent="NEXT", operation="SUBTRACT")
    o = settle("Box")
    print(state("Box"))
    for f in focus.features_of(o):
        focus.set_focus(o, f.name)
        try:
            lay = gizmos.arrow_layout(o)
            mats = gizmos.arrow_matrices(o)
            print(f.name, [(a.param, a.direction, a.origin, a.scale) for _, a in lay])
            for p, basis, scale in mats:
                g = gizmos.arrow_get("Box", p, scale)
                gizmos.arrow_set("Box", p, scale, g * 1.1)
            runtime.tick()
        except Exception as e:
            import traceback; traceback.print_exc()
            FINDINGS.append(f"gizmo on {f.name}: {type(e).__name__}: {e}")
    o = settle("Box")
    print(state("Box"))
    print([l for l in part.source_of(o).splitlines() if "=" in l and not l.startswith(" ")])
    # sketch-only part with focus on sketch
    E.sketch_entity("EXEC_DEFAULT", True, shape="CIRCLE", start=(0, 0), end=(5, 0), matrix=[v for r in Matrix.Identity(4) for v in r])
    s = bpy.context.object
    settle(s.name)
    print(s.name, s.blendsolid_focus, gizmos.arrow_layout(s))
    for p, basis, scale in gizmos.arrow_matrices(s):
        print(" arrow", p, scale)
    print("error label", ui.error_label(s))

run(main)
