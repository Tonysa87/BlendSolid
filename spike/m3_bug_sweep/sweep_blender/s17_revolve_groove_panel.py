import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
from mathutils import Matrix
TOP = 'on_face(face("box_1", "+Z"))'
I = [v for r in Matrix.Identity(4) for v in r]

def main():
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="RECTANGLE", start=(15, 0), end=(19, 10), matrix=I)
    n = bpy.context.object.name
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="PATH", target=n, sketch="sketch_1", points=json.dumps([[0, -20, False], [0, 20, False]]))
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="PATH", target=n, sketch="sketch_1", points=json.dumps([[17, -20, False], [17, 20, False]]))
    settle(n)
    bpy.ops.blendsolid.revolve("EXEC_DEFAULT", True, target=n, sketch="sketch_1", seed=(16, 5), axis="path_1", angle=360)
    runtime.tick()
    for kw in (dict(angle=-360), dict(angle=90), dict(angle=-90, operation="SUBTRACT"), dict(angle=360, axis="path_2"),
               dict(angle=360, axis="nope"), dict(angle=0.5), dict(angle=360, operation="INTERSECT"), dict(angle=360, seed=(100, 100))):
        bpy.ops.ed.undo()
        args = dict(target=n, sketch="sketch_1", seed=(16, 5), axis="path_1"); args.update(kw)
        try:
            r = bpy.ops.blendsolid.revolve("EXEC_DEFAULT", True, **args)
        except RuntimeError as e:
            r = str(e).splitlines()[0]
        o = settle(n)
        print("revolve", kw, r, f"vol={mm3(o):.1f} err={o.blendsolid_error!r}")
    clean()
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True); settle("Box")
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="PATH", target="Box", plane=TOP, points=json.dumps([[-15, -5, False], [5, -5, False], [5, 5, False], [-15, 5, False]]))
    settle("Box")
    bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", entity="path_1", width=2, depth=1)
    runtime.tick()
    for kw in (dict(width=12), dict(depth=25), dict(width=10, depth=25, profile="v"), dict(profile="circle", width=40),
               dict(corners="round", width=4), dict(operation="ADD", profile="round", depth=30), dict(profile="circle", operation="ADD"),
               dict(entity="path_9"), dict(sketch="sketch_9"), dict(width=0.001, depth=0.001)):
        bpy.ops.ed.undo()
        args = dict(target="Box", sketch="sketch_1", entity="path_1", width=2, depth=1); args.update(kw)
        try:
            r = bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, **args)
        except RuntimeError as e:
            r = str(e).splitlines()[0]
        try:
            o = settle("Box", 60)
        except AssertionError:
            o = bpy.data.objects["Box"]
            print("TIMEOUT", state("Box"), (part.applied_hash(o) or "")[:8], part.current_tag(o)[:8], (part.error_tag(o) or "")[:8], runtime._inflight, runtime._failed, runtime._client.state)
            FINDINGS.append(f"timeout {kw}")
        print("groove", kw, r, f"vol={mm3(o):.1f} err={o.blendsolid_error!r}")

run(main)
