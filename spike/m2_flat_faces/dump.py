"""Dump the biggest flat face's polygons of some metrics.py parts to metrics.py.json (for plot.py).
$PY spike/m2_flat_faces/dump.py spike/m2_flat_faces/metrics.py bosses washer ..."""
import sys, json, math; sys.path[:0]=["blendsolid/worker",".dev/worker_libs"]
exec(open(sys.argv[1]).read().split("def angles")[0].split("PARTS={")[0])
src=open(sys.argv[1]).read(); ns={}
import numpy as np, build123d as bd, tessellate
exec("PARTS={"+src.split("PARTS={")[1].split("\ndef angles")[0], globals())
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
out={}
for name in sys.argv[2:]:
    w=PARTS[name]().wrapped; m=tessellate.display_mesh(w,1.0,0.3)
    starts=np.concatenate([[0],np.cumsum(m.poly_sizes)[:-1]]); v=m.verts.astype(float)
    faces=tessellate.face_map(w); best=None
    for fid,f in enumerate(faces):
        if BRepAdaptor_Surface(f).GetType()!=GeomAbs_Plane: continue
        idx=np.where(m.poly_face==fid)[0]
        if best is None or len(idx)>len(best): best=idx
    polys=[v[m.loops[starts[i]:starts[i]+m.poly_sizes[i]]].tolist() for i in best]
    out[name]=polys
json.dump(out,open(sys.argv[1]+".json","w"))
