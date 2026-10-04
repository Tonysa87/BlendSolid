import sys, math
import check
import numpy as np
import runner, tessellate, meshing
from OCP.BRepAdaptor import BRepAdaptor_Surface
src = open(sys.argv[1]).read(); fid = int(sys.argv[2]); tol=float(sys.argv[3]) if len(sys.argv)>3 else 1.0
r = runner.run_script(src, tol, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
faces = tessellate.face_map(shape); edges = tessellate.edge_map(shape)
kinds=[]
for f in faces:
    rev = tessellate._revolution(f)
    kinds.append("self" if tessellate._self_contained(rev) else "revolution" if rev is not None else "plane" if BRepAdaptor_Surface(f).GetType()==0 else "curved")
lay = meshing.plan(faces, edges, kinds, [1]*len(faces), tol, 0.15)
fi = lay.faces[fid]
for loop in fi.loops:
    m = len(loop)
    for k in range(m):
        a = meshing._tangent3d(fi, lay.edges, loop[k-1], True); b = meshing._tangent3d(fi, lay.edges, loop[k], False)
        e = lay.edges[loop[k].edge]
        print(f"use {k}: edge {loop[k].edge} len {e.length:.4f} count {e.count} own {e.own} deg {e.degenerate}  turn before {math.degrees(math.acos(max(-1,min(1,float(a@b))))) if np.linalg.norm(a)>.5 and np.linalg.norm(b)>.5 else 'n/a'}")
print("kind", fi.kind, "step", fi.step, "box", fi.box, "scale", fi.scale)
