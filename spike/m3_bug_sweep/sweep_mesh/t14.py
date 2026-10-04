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
fi = lay.faces[fid]; s = fi.surf
periods = (s.UPeriod() if s.IsUPeriodic() else None, s.VPeriod() if s.IsVPeriodic() else None)
kind = fi.kind
uv, xyz, t = meshing.mesh_face(fi, lay.edges, periods)
q = uv * np.array(fi.scale) / np.array(fi.step) if kind != "plane" else uv
a = meshing._area2d(uv, t)
loop_area = 0
for loop in fi.loops:
    luv, _, _ = meshing.loop_nodes(loop, lay.edges, periods)
    x, y = luv[:,0], luv[:,1]
    loop_area += 0.5*np.sum(x*np.roll(y,-1)-np.roll(x,-1)*y)
print("kind", kind, "tris", len(t), "sum uv area", a.sum()/2, "|loop area|", abs(loop_area), "neg", (a<0).sum())
# 3D folds inside the face
N = np.cross(xyz[t[:,1]]-xyz[t[:,0]], xyz[t[:,2]]-xyz[t[:,0]]); L = np.linalg.norm(N,axis=1); N = N/np.maximum(L,1e-300)[:,None]
em = {}
for i,(x,y,z) in enumerate(t):
    for e in ((x,y),(y,z),(z,x)): em.setdefault((min(e),max(e)),[]).append(i)
bad = [(e,ts) for e,ts in em.items() if len(ts)==2 and N[ts[0]]@N[ts[1]] < -0.5]
print("3D folds", len(bad), "edges with >2 tris", sum(len(ts)>2 for ts in em.values()))
for e, ts in bad[:5]:
    print(" ", e, "uv", uv[list(e)].round(5).tolist(), "tris", [t[i].tolist() for i in ts], [uv[t[i]].round(4).tolist() for i in ts])
print("---- face_need per use")
for loop in fi.loops:
    for use in loop:
        e = lay.edges[use.edge]
        tmid = (use.first + use.last)/2
        p2, d2 = meshing._p2d(use.pcurve, tmid)
        print(" edge", use.edge, "count", e.count, "need", meshing.face_need(fi, use, e), "p2", np.round(p2,4), "d2", np.round(d2,4), "first/last", use.first, use.last)
# which other faces use edge 62 / 45?
for f2, fj in enumerate(lay.faces):
    for loop in fj.loops:
        for use in loop:
            if use.edge in (62, 45) and f2 != fid: print(" edge", use.edge, "also in face", f2, fj.kind)
