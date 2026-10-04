import sys
import check
import numpy as np
import runner, tessellate
from OCP.BRepAdaptor import BRepAdaptor_Surface
src = open(sys.argv[1]).read(); tol=float(sys.argv[2])
r = runner.run_script(src, tol, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
faces = tessellate.face_map(shape)
v = r.verts.astype(float); loops=r.loops; sizes=r.poly_sizes
starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
diag = np.linalg.norm(v.max(0)-v.min(0))
for p,(s,n) in enumerate(zip(starts,sizes)):
    P = v[loops[s:s+n]]; nn = np.zeros(3)
    for k in range(1,n-1): nn += np.cross(P[k]-P[0], P[k+1]-P[0])
    a = np.linalg.norm(nn)/2
    if a < 1e-12*diag**2:
        f = int(r.poly_face[p])
        print("poly", p, "face", f, check.SURF.get(BRepAdaptor_Surface(faces[f]).GetType()), "n", n, "area", a, "ids", loops[s:s+n].tolist(), P.round(6).tolist())
