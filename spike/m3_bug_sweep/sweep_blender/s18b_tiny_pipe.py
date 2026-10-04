import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
TOP = 'on_face(face("box_1", "+Z"))'

def main():
    P4 = [[-15, -5, False], [5, -5, False], [5, 5, False], [-15, 5, False]]
    for w, d, pts in ((0.1, 0.1, P4), (0.01, 0.01, P4), (0.001, 0.001, [[-15, -5, False], [5, -5, False]]), (0.001, 0.001, P4)):
        clean()
        bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True); settle("Box")
        bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="PATH", target="Box", plane=TOP, points=json.dumps(pts))
        settle("Box")
        t = time.monotonic()
        bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", entity="path_1", width=w, depth=d, profile="circle")
        try:
            o = settle("Box", 240)
            print(w, len(pts), f"{time.monotonic() - t:.1f}s", state("Box"))
        except AssertionError:
            print(w, len(pts), "TIMEOUT 240 s", runtime._inflight, runtime._client.state)
            FINDINGS.append(f"groove {w}x{d} on {len(pts)}-pt path: no result in 240 s")

run(main)
