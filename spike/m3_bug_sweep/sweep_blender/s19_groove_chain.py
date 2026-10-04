import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
TOP = 'on_face(face("box_1", "+Z"))'

def diag(label):
    o = bpy.data.objects["Box"]
    print(label, state("Box"), "applied", (part.applied_hash(o) or "")[:8], "cur", part.current_tag(o)[:8],
          "errtag", (part.error_tag(o) or "")[:8], "inflight", {k: v[:8] for k, v in runtime._inflight.items()},
          "failed", {k: v[:8] for k, v in runtime._failed.items()}, "client", runtime._client.state)

def main():
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True); settle("Box")
    bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="PATH", target="Box", plane=TOP, points=json.dumps([[-15, -5, False], [5, -5, False], [5, 5, False], [-15, 5, False]]))
    settle("Box")
    bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", entity="path_1", width=2, depth=1)
    runtime.tick()
    for kw in (dict(entity="path_9"), dict(sketch="sketch_9"), dict(width=0.001, depth=0.001), dict(width=3)):
        bpy.ops.ed.undo()
        diag(" after undo")
        args = dict(target="Box", sketch="sketch_1", entity="path_1", width=2, depth=1); args.update(kw)
        r = bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, **args)
        diag(" after op")
        try:
            settle("Box", 20)
            diag(f"settled {kw}")
        except AssertionError:
            diag(f"TIMEOUT {kw}")
            FINDINGS.append(f"no settle after {kw}")
            for i in range(5):
                runtime.tick(); time.sleep(0.2)
            diag("  later")

run(main)
