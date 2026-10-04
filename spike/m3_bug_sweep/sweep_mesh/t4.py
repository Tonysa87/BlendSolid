import sys
import check
import numpy as np
import runner, tessellate
from OCP.BRepAdaptor import BRepAdaptor_Surface
SRC = '''with BuildPart() as part:
    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-15.0, -5.0), (5.0, -5.0), (5.0, 5.0))
    groove(sketch_1.path_1, width=2.0, depth=2.0, profile="round", corners="mitre", mode=Mode.SUBTRACT)  # feature: groove_1
result = part.part
'''
r = runner.run_script(SRC, 1.0, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
fid = int(sys.argv[1]) if len(sys.argv) > 1 else 12
starts = np.concatenate([[0], np.cumsum(r.poly_sizes)[:-1]])
sel = np.nonzero(r.poly_face == fid)[0]
print("polys", len(sel), "sizes", np.bincount(r.poly_sizes[sel]))
for p in sel[:8]:
    print([tuple(np.round(x,3)) for x in r.verts[r.loops[starts[p]:starts[p]+r.poly_sizes[p]]]])
# plan info
faces = tessellate.face_map(shape); edges = tessellate.edge_map(shape)
import meshing
kinds=[]
for f in faces:
    rev = tessellate._revolution(f)
    kinds.append("self" if tessellate._self_contained(rev) else "revolution" if rev is not None else "plane" if BRepAdaptor_Surface(f).GetType()==0 else "curved")
lay = meshing.plan(faces, edges, kinds, [1]*len(faces), 1.0, 0.15)
fi = lay.faces[fid]
print("kind", fi.kind, "step", fi.step, "sides", fi.sides)
for loop in fi.loops:
    for u in loop:
        e = lay.edges[u.edge]
        print("  edge", u.edge, "len", round(e.length,3), "count", e.count, "own", e.own)
