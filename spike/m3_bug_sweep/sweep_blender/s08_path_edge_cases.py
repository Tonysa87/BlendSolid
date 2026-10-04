import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
TOP = 'on_face(face("box_1", "+Z"))'
from blendsolid import ops_sketch

CASES = [
    ("2pts closed", [[0, 0, False], [10, 0, False]], True),
    ("2pts + arc back to start", [[0, 0, False], [10, 0, False], [0, 0, True]], False),
    ("arc straight ahead (collinear)", [[0, 0, False], [10, 0, False], [15, 0, True]], False),
    ("arc straight back (reversal)", [[0, 0, False], [10, 0, False], [5, 0, True]], False),
    ("self crossing", [[-10, -10, False], [10, 10, False], [10, -10, False], [-10, 10, False]], False),
    ("closed triangle", [[-10, -10, False], [10, -10, False], [0, 10, False]], True),
    ("closed by arc", [[-10, -5, False], [10, -5, False], [10, 5, True], [-10, 5, False], [-10, -5, True]], False),
    ("tiny segment", [[0, 0, False], [0.0005, 0, False], [10, 0, False]], False),
    ("off face entirely", [[100, 100, False], [120, 100, False]], False),
    ("first arc flag ignored", [[0, 0, True], [10, 0, True]], False),
]

def main():
    for label, pts, closed in CASES:
        clean()
        bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
        settle("Box")
        try:
            r = bpy.ops.blendsolid.sketch_entity("EXEC_DEFAULT", True, shape="PATH", target="Box", plane=TOP, points=json.dumps(pts), closed=closed)
        except RuntimeError as e:
            r = f"refused: {e}"
        o = settle("Box")
        sk = ops_sketch.sketches_of(o)
        regs = [round(rg["area"], 3) for s in sk for rg in s["regions"]]
        print(f"[{label}] op={r} err={o.blendsolid_error!r} up={up_to_date(o)} regions={regs}")
        if o.blendsolid_error:
            # then a groove on it
            continue
        try:
            bpy.ops.blendsolid.groove("EXEC_DEFAULT", True, target="Box", sketch="sketch_1", entity="path_1", width=1.0, depth=1.0)
        except RuntimeError as e:
            print("  groove refused", e)
        o = settle("Box")
        print(f"   groove: err={o.blendsolid_error!r} vol={mm3(o):.3f}")

run(main)
