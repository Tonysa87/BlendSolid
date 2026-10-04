import sys, math
import check
import numpy as np
import runner, tessellate, meshing
from OCP.BRepAdaptor import BRepAdaptor_Surface
src = open(sys.argv[1]).read(); tol=float(sys.argv[2]); fid=int(sys.argv[3])
r = runner.run_script(src, tol, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
faces = tessellate.face_map(shape); edges = tessellate.edge_map(shape)
revs = [tessellate._revolution(f) for f in faces]
kinds=["self" if tessellate._self_contained(rev) else "revolution" if rev is not None else "plane" if BRepAdaptor_Surface(f).GetType()==0 else "curved" for f, rev in zip(faces, revs)]
rings = [4 * math.ceil(tessellate._TAU / tessellate._step(tol, 0.15, rev.max_circle_radius()) / 4) if rev is not None and "circle" in rev.ends else 1 for rev in revs]
lay = meshing.plan(faces, edges, kinds, rings, tol, 0.15)
fi = lay.faces[fid]
uv, xyz, starts = meshing.loop_nodes(fi.loops[0], lay.edges)
n = len(uv)
segs = [(uv[k], uv[(k+1)%n]) for k in range(n)]
def o(p,q,r): return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
cr = []
for i in range(n):
    for j in range(i+2, n):
        if (j+1)%n == i: continue
        a,b = segs[i]; c,d = segs[j]
        if o(a,b,c)*o(a,b,d) < 0 and o(c,d,a)*o(c,d,b) < 0: cr.append((i,j))
print("uv self-crossings:", len(cr), cr[:10])
# which uses
use_of = np.searchsorted(starts, np.arange(n), side="right") - 1
for i, j in cr[:10]:
    print("  seg", i, "use", use_of[i], "edge", fi.loops[0][use_of[i]].edge, "x seg", j, "use", use_of[j], "edge", fi.loops[0][use_of[j]].edge)
# 3D: is the polyline of a use far from its pcurve image? compare xyz vs surface(uv)
s = fi.surf
d = [np.linalg.norm(np.array(check.__dict__.get('x', 0)) ) for _ in []]
err = []
for k in range(n):
    p = s.Value(float(uv[k,0]), float(uv[k,1]))
    err.append(np.linalg.norm(np.array([p.X(),p.Y(),p.Z()]) - xyz[k]))
err = np.array(err); print("max |S(uv)-xyz| =", err.max(), "at node", err.argmax(), "use", use_of[err.argmax()])
