import json, sys
import numpy as np
from check import run_case, analyse
import runner, tessellate
SRC = '''with BuildPart() as part:
    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-15.0, -5.0), (5.0, -5.0), (5.0, 5.0))
    groove(sketch_1.path_1, width=2.0, depth=2.0, profile="v", corners="round", mode=Mode.SUBTRACT)  # feature: groove_1
result = part.part
'''
r = runner.run_script(SRC, 1.0, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
a = analyse(r, shape, 1.0)
print({k: a[k] for k in ["polys","zero_area_polys","curved_min_angle","curved_lt1","sliver_faces","dev_over_tol"]})
from OCP.BRepAdaptor import BRepAdaptor_Surface
faces = tessellate.face_map(shape)
for fid in [int(k.split(":")[0]) for k in a["sliver_faces"]]:
    s = BRepAdaptor_Surface(faces[fid])
    c = s.Cone()
    print("face", fid, "semi-angle deg", np.degrees(c.SemiAngle()), "ref radius", c.RefRadius(), "apex", c.Apex().X(), c.Apex().Y(), c.Apex().Z(), "u", s.FirstUParameter(), s.LastUParameter(), "v", s.FirstVParameter(), s.LastVParameter())
    sel = np.nonzero(r.poly_face == fid)[0]
    starts = np.concatenate([[0], np.cumsum(r.poly_sizes)[:-1]])
    print(" polys", len(sel), "sizes", np.bincount(r.poly_sizes[sel]))
    for p in sel[:6]:
        print("  ", r.verts[r.loops[starts[p]:starts[p]+r.poly_sizes[p]]].round(4).tolist())
