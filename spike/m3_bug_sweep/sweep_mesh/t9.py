import sys
import check
import numpy as np
import runner, tessellate
from OCP.TopAbs import TopAbs_WIRE, TopAbs_EDGE, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.BRep import BRep_Tool
from OCP.TopoDS import TopoDS
src = open(sys.argv[1]).read(); tol=float(sys.argv[2]); fl = [int(x) for x in sys.argv[3].split(",")]
r = runner.run_script(src, tol, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
faces = tessellate.face_map(shape); edges = tessellate.edge_map(shape)
starts = np.concatenate([[0], np.cumsum(r.poly_sizes)[:-1]])
for f in fl:
    print("face", f, faces[f].Orientation())
    w = TopExp_Explorer(faces[f], TopAbs_WIRE)
    while w.More():
        es = []
        ee = TopExp_Explorer(w.Current(), TopAbs_EDGE)
        while ee.More():
            e = TopoDS.Edge(ee.Current())
            idx = [i for i, x in enumerate(edges) if x.IsSame(e)][0]
            v = TopExp_Explorer(e, TopAbs_VERTEX); pts=[]
            while v.More():
                p = BRep_Tool.Pnt_s(TopoDS.Vertex(v.Current())); pts.append((round(p.X(),3), round(p.Z(),3))); v.Next()
            es.append((idx, pts))
            ee.Next()
        print("  wire", es)
        w.Next()
    for p in np.nonzero(r.poly_face == f)[0]:
        print("  poly", p, [(int(i), tuple(np.round(r.verts[i][[0,2]],3))) for i in r.loops[starts[p]:starts[p]+r.poly_sizes[p]]])
