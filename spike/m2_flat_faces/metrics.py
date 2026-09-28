"""Metrics of flat faces meshed as several polygons (count, min/max corner angle, area vs BRep) on sample parts.
Run from the repo root: $PY spike/m2_flat_faces/metrics.py [part ...]  (PY = Blender's Python)."""
import sys, math, time; sys.path[:0]=["blendsolid/worker",".dev/worker_libs"]
import numpy as np, build123d as bd, tessellate
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
def cyl_y(r,x,z,h=30): return bd.Pos(x,-20,z)*bd.Rot(90,0,0)*bd.Cylinder(r,h)
PARTS={
 "bosses": lambda: bd.Box(100,40,100)+cyl_y(8,-25,38)+cyl_y(8,25,38),
 "holes": lambda: bd.Box(100,40,100)-cyl_y(8,-25,38,60)-cyl_y(8,25,38,60),
 "plate_small_hole": lambda: bd.Box(200,200,5)-bd.Cylinder(3,20),
 "washer": lambda: bd.Cylinder(20,5)-bd.Cylinder(8,20),
 "box_with_hole": lambda: bd.Box(40,30,20)-bd.Cylinder(6,30),
 "slot": lambda: bd.Box(60,30,10)-bd.extrude(bd.SlotOverall(30,8),20,both=True),
 "bolt_circle": lambda: bd.Cylinder(50,5)-[bd.Pos(35*math.cos(a),35*math.sin(a),0)*bd.Cylinder(4,20) for a in np.linspace(0,2*math.pi,7)[:-1]],
 "rect_pocket": lambda: bd.Box(60,60,10)-bd.Box(20,20,20),
 "default": lambda: bd.fillet((bd.Box(40,30,20,align=bd.Align.MIN)+bd.Pos(20,15,0)*bd.Cylinder(6,25,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN))).edges().filter_by(bd.Axis.Z).sort_by_distance((0,0,0))[0],5),
 "near_edge": lambda: bd.Box(60,60,10)-bd.Pos(22,0,0)*bd.Cylinder(7.5,20),
}
def angles(poly):
    k=len(poly); out=[]
    for i in range(k):
        a=poly[i-1]-poly[i]; b=poly[(i+1)%k]-poly[i]
        out.append(math.degrees(math.acos(np.clip(a@b/np.linalg.norm(a)/np.linalg.norm(b),-1,1))))
    return out
for name in (sys.argv[1:] or PARTS):
    part=PARTS[name](); w=part.wrapped
    t0=time.perf_counter(); m=tessellate.display_mesh(w,1.0,0.3); dt=time.perf_counter()-t0
    v=m.verts.astype(np.float64); starts=np.concatenate([[0],np.cumsum(m.poly_sizes)[:-1]])
    nxt=np.arange(len(m.loops))+1; nxt[starts+m.poly_sizes-1]=starts
    pr=np.sort(np.stack([m.loops,m.loops[nxt]],1),1); _,c=np.unique(pr,axis=0,return_counts=True)
    vol=0
    for s,n in zip(starts,m.poly_sizes):
        p=v[m.loops[s:s+n]]
        for i in range(1,n-1): vol+=p[0]@np.cross(p[i],p[i+1])/6
    faces=tessellate.face_map(w); line=[]
    for fid,f in enumerate(faces):
        if BRepAdaptor_Surface(f).GetType()!=GeomAbs_Plane: continue
        ps=[v[m.loops[s:s+n]] for s,n in zip(starts,m.poly_sizes) if m.poly_face[list(starts).index(s)]==fid] if False else None
        idx=np.where(m.poly_face==fid)[0]
        if len(idx)<2: continue
        ps=[v[m.loops[starts[i]:starts[i]+m.poly_sizes[i]]] for i in idx]
        g=GProp_GProps(); BRepGProp.SurfaceProperties_s(f,g)
        area=sum(np.linalg.norm(sum(np.cross(p[i],p[(i+1)%len(p)]) for i in range(len(p))))/2 for p in ps)
        mina=min(min(angles(p)) for p in ps); maxa=max(max(angles(p)) for p in ps)
        line.append(f"f{fid}: {len(idx)} polys min {mina:.2f} max {maxa:.2f} area err {abs(area-g.Mass())/g.Mass():.1e}")
    print(f"{name}: closed {(c==2).all()} vol {vol:.1f} brep {part.volume:.1f} time {dt:.2f}s"); [print("   ",l) for l in line]
