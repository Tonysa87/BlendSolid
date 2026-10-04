import sys
import check
import numpy as np
import runner, tessellate
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRep import BRep_Tool
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.gp import gp_Pnt
src = open(sys.argv[1]).read(); tol=float(sys.argv[2])
r = runner.run_script(src, tol, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
faces = tessellate.face_map(shape)
v = r.verts.astype(float); loops=r.loops; sizes=r.poly_sizes
starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
worst = {}
for p,(s,n) in enumerate(zip(starts,sizes)):
    f = int(r.poly_face[p]); st = BRepAdaptor_Surface(faces[f]).GetType()
    if st == 0: continue
    P = v[loops[s:s+n]]; surf = BRep_Tool.Surface_s(faces[f])
    for k in range(1, n-1):
        for w in ((1/3,1/3,1/3),(0.5,0.5,0),(0,0.5,0.5),(0.5,0,0.5)):
            c = w[0]*P[0]+w[1]*P[k]+w[2]*P[k+1]
            pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*c), surf)
            if pr.NbPoints():
                d = pr.LowerDistance()
                if d > worst.get(f, (0,))[0]: worst[f] = (d, p, P.round(2).tolist())
for f,(d,p,P) in sorted(worst.items(), key=lambda x:-x[1][0])[:3]:
    print("face", f, check.SURF.get(BRepAdaptor_Surface(faces[f]).GetType()), "max dev", round(d,3), "= %.1f x tol"%(d/tol), "poly", p, P)
print("polys", len(sizes))
