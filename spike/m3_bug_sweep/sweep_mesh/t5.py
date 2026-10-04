import sys
import check
import numpy as np
import runner, tessellate, meshing
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
src = open(sys.argv[1]).read()
tol = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
r = runner.run_script(src, tol, 0.3, tag="x")
assert r.ok, r.error
shape = runner.SHAPES.get("x").wrapped
faces = tessellate.face_map(shape); edges = tessellate.edge_map(shape)
kinds=[]
for f in faces:
    rev = tessellate._revolution(f)
    kinds.append("self" if tessellate._self_contained(rev) else "revolution" if rev is not None else "plane" if BRepAdaptor_Surface(f).GetType()==0 else "curved")
lay = meshing.plan(faces, edges, kinds, [1]*len(faces), tol, 0.15)
cnt = np.bincount(r.poly_face, minlength=len(faces))
print("total polys", len(r.poly_sizes), "tess time", r.timing)
for fid in np.argsort(-cnt)[:int(sys.argv[3]) if len(sys.argv)>3 else 8]:
    p = GProp_GProps(); BRepGProp.SurfaceProperties_s(faces[fid], p)
    fi = lay.faces[fid]
    s = BRepAdaptor_Surface(faces[fid])
    print(f"face {fid} {check.SURF.get(s.GetType())} kind={kinds[fid]}/{fi.kind} polys={cnt[fid]} area={p.Mass():.4g} step={tuple(round(x,4) for x in fi.step)} loops={[len(l) for l in fi.loops]}")
