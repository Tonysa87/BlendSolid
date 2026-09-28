"""Polygons of the default part's top face touching the fillet arc's ends (where Bevel flipped a polygon)."""
import sys; sys.path[:0]=["blendsolid/worker",".dev/worker_libs"]
import numpy as np, build123d as bd, tessellate
p=bd.fillet((bd.Box(40,30,20,align=bd.Align.MIN)+bd.Pos(20,15,0)*bd.Cylinder(6,25,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))).edges().filter_by(bd.Axis.Z).sort_by_distance((0,0,0))[0],5)
m=tessellate.display_mesh(p.wrapped,1.0,0.3); v=m.verts.astype(float)
st=np.concatenate([[0],np.cumsum(m.poly_sizes)[:-1]])
top=[i for i in range(len(st)) if abs(v[m.loops[st[i]:st[i]+m.poly_sizes[i]]][:,2]-20).max()<1e-6]
for i in top:
    L=v[m.loops[st[i]:st[i]+m.poly_sizes[i]]]
    if np.min(np.linalg.norm(L[:,:2]-[0,5],axis=1))<0.5 or np.min(np.linalg.norm(L[:,:2]-[5,0],axis=1))<0.5:
        print(i, m.poly_sizes[i], L[:,:2].round(2).tolist())
