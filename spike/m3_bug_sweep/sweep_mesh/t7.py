import sys
import check
import numpy as np
import runner, tessellate
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.TopAbs import TopAbs_REVERSED
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
src = open(sys.argv[1]).read(); tol = float(sys.argv[2])
r = runner.run_script(src, tol, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
print("valid", BRepCheck_Analyzer(shape).IsValid(), "vol", r.volume, "faces", r.faces)
loops = r.loops.astype(np.int64); sizes = r.poly_sizes
starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
nxt = np.arange(len(loops)) + 1; nxt[starts + sizes - 1] = starts
pol = np.repeat(np.arange(len(sizes)), sizes)
d = {}
for i,(a,b) in enumerate(zip(loops, loops[nxt])):
    d.setdefault((a,b), []).append(pol[i])
und = {}
for (a,b), ps in d.items():
    und.setdefault((min(a,b),max(a,b)), []).extend(ps)
bad = [(k,v) for k,v in d.items() if len(v)>1]
faces = tessellate.face_map(shape)
print("dup directed", len(bad))
fs = set()
for (a,b), ps in bad[:20]:
    print((a,b), [(int(p), int(r.poly_face[p])) for p in ps], r.verts[a].round(4), r.verts[b].round(4))
    fs.update(int(r.poly_face[p]) for p in ps)
openx = [(k,v) for k,v in und.items() if len(v)==1]
print("open", len(openx), sorted({int(r.poly_face[v[0]]) for k,v in openx}))
nm = [(k,v) for k,v in und.items() if len(v)>2]
print("nonmanifold", len(nm), sorted({int(r.poly_face[p]) for k,v in nm for p in v}))
for f in sorted(fs):
    p = GProp_GProps(); BRepGProp.SurfaceProperties_s(faces[f], p)
    s = BRepAdaptor_Surface(faces[f])
    print("face", f, check.SURF.get(s.GetType()), "orient", faces[f].Orientation(), "area", p.Mass(), "npolys", int((r.poly_face==f).sum()))
