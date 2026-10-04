import sys
import numpy as np
from check import analyse
import runner, tessellate, meshing
from OCP.BRepAdaptor import BRepAdaptor_Surface
prof, corn, mode = sys.argv[1], sys.argv[2], sys.argv[3]
tol = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
SRC = f'''with BuildPart() as part:
    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-15.0, -5.0), (5.0, -5.0), (5.0, 5.0))
    groove(sketch_1.path_1, width=2.0, depth=2.0, profile="{prof}", corners="{corn}", mode={mode})  # feature: groove_1
result = part.part
'''
r = runner.run_script(SRC, tol, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
a = analyse(r, shape, tol)
print({k: a[k] for k in ["polys","zero_area_polys","curved_min_angle","curved_lt1","curved_lt5","plane_lt1","sliver_faces","dev_over_tol","dvol_over_area_tol"]})
faces = tessellate.face_map(shape)
# plan kinds
import math
revs = [tessellate._revolution(f) for f in faces]
starts = np.concatenate([[0], np.cumsum(r.poly_sizes)[:-1]])
for fid in [int(k.split(":")[0]) for k in a["sliver_faces"]][:3]:
    s = BRepAdaptor_Surface(faces[fid])
    sel = np.nonzero(r.poly_face == fid)[0]
    print("face", fid, a["sliver_faces"], "type", s.GetType(), "u", round(s.FirstUParameter(),4), round(s.LastUParameter(),4), "v", round(s.FirstVParameter(),4), round(s.LastVParameter(),4), "polys", len(sel), "rev", revs[fid] is not None)
