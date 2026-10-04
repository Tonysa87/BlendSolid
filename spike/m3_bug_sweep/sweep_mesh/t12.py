import sys, collections
import check
import numpy as np
import runner, tessellate
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.BRep import BRep_Tool
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_REVERSED
from OCP.GeomLProp import GeomLProp_SLProps
src = open(sys.argv[1]).read(); tol=float(sys.argv[2])
r = runner.run_script(src, tol, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
faces = tessellate.face_map(shape)
v = r.verts.astype(float); loops = r.loops; sizes = r.poly_sizes
starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
stats = collections.Counter(); ex = []
for p,(s,n) in enumerate(zip(starts,sizes)):
    P = v[loops[s:s+n]]
    nn = np.zeros(3)
    for k in range(1,n-1): nn += np.cross(P[k]-P[0], P[k+1]-P[0])
    if np.linalg.norm(nn) < 1e-12: continue
    nn /= np.linalg.norm(nn)
    cn = r.corner_normals[s:s+n].astype(float)
    d = cn @ nn
    if (d < 0).any():
        f = int(r.poly_face[p]); face = faces[f]
        surf = BRep_Tool.Surface_s(face)
        c = P.mean(0)
        pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*c), surf); u, w = pr.LowerDistanceParameters()
        pp = GeomLProp_SLProps(surf, u, w, 1, 1e-9); en = np.array([pp.Normal().X(), pp.Normal().Y(), pp.Normal().Z()])
        if face.Orientation() == TopAbs_REVERSED: en = -en
        kind = "poly flipped (fold)" if en @ nn < 0 else "corner normals wrong"
        stats[(f, check.SURF.get(BRepAdaptor_Surface(face).GetType()), kind, n)] += 1
        if len(ex) < 3: ex.append((p, f, P.round(4).tolist(), d.round(3).tolist(), float(en@nn)))
print(stats)
for e in ex: print(e)
