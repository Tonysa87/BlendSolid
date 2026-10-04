import sys
import check
import numpy as np
import runner, tessellate, meshing, brepman
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
src = open(sys.argv[1]).read(); tol=float(sys.argv[2])
r = runner.run_script(src, 1.0, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
print("brep >2-face edges, free edges:", brepman.brep_edge_faces(shape))
faces = tessellate.face_map(shape); edges = tessellate.edge_map(shape)
revs = [tessellate._revolution(f) for f in faces]
kinds=[]
for f, rev in zip(faces, revs):
    kinds.append("self" if tessellate._self_contained(rev) else "revolution" if rev is not None else "plane" if BRepAdaptor_Surface(f).GetType()==0 else "curved")
import math
rings = [4 * math.ceil(tessellate._TAU / tessellate._step(tol, 0.15, rev.max_circle_radius()) / 4) if rev is not None and "circle" in rev.ends else 1 for rev in revs]
lay = meshing.plan(faces, edges, kinds, rings, tol, 0.15)
for fid, fi in enumerate(lay.faces):
    if kinds[fid] in ("revolution", "self"): continue
    s = fi.surf
    periods = (s.UPeriod() if s.IsUPeriodic() else None, s.VPeriod() if s.IsVPeriodic() else None)
    kind0 = fi.kind
    out = meshing.mesh_face(fi, lay.edges, periods)
    if out is None:
        p = GProp_GProps(); BRepGProp.SurfaceProperties_s(faces[fid], p)
        print("FAIL face", fid, check.SURF.get(s.GetType()), "kind", kind0, "->", fi.kind, "area", p.Mass(), "loops", [len(l) for l in fi.loops], "nodes", sum(lay.edges[u.edge].count for l in fi.loops for u in l), "step", fi.step, "box", fi.box)
        # diagnose: trimmed without grid / Delaunay recover
        for grid in ((True, False) if fi.kind != "plane" else (False,)):
            print("   trimmed grid=%s ->" % grid, meshing.trimmed(fi, lay.edges, periods, grid=grid) is not None)

# deep diagnosis of first failing face
import scipy.spatial
orig_recover = meshing._recover
def rec(q, tris, cons, budget=200000):
    out = orig_recover(q, tris, cons, budget)
    big = orig_recover(q, tris, cons, 10**8) if out is None else out
    print("   _recover:", "ok" if out is not None else "FAILED", "| with huge budget:", "ok" if big is not None else "FAILED", "points", len(q), "constraints", len(cons))
    # check boundary self-intersections in q-space
    segs = np.asarray(cons)
    P = q[segs]
    n = 0; touch = 0
    for i in range(len(P)):
        for j in range(i+2, len(P)):
            if (j+1) % len(P) == i: continue
            a,b = P[i]; c,d = P[j]
            def o(p,q_,r): return (q_[0]-p[0])*(r[1]-p[1])-(q_[1]-p[1])*(r[0]-p[0])
            if o(a,b,c)*o(a,b,d) < 0 and o(c,d,a)*o(c,d,b) < 0: n += 1
    print("   boundary self-crossings in (u,v):", n, "duplicate points:", len(q[:len(np.unique(segs))]) - len(np.unique(np.round(q[:len(np.unique(segs))], 12), axis=0)))
    return out
meshing._recover = rec
for fid, fi in enumerate(lay.faces):
    if kinds[fid] in ("revolution", "self"): continue
    s = fi.surf
    periods = (s.UPeriod() if s.IsUPeriodic() else None, s.VPeriod() if s.IsVPeriodic() else None)
    if fi.kind == "tfi":
        if meshing.tfi(fi, lay.edges, periods) is not None: continue
        print("face", fid, "tfi folded")
        fi.step = meshing._fitted(fi, meshing._capped(fi.step))
    out = meshing.trimmed(fi, lay.edges, periods, grid=fi.kind != "plane")
    if out is None:
        print("face", fid, "trimmed failed; step", fi.step, "scale", fi.scale)
        break
