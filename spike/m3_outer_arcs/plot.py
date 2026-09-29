"""Plot flat faces' polygons: $PY spike/m3_outer_arcs/plot.py out.png test2:0 test2:1 file.step:solid:face ...
(dumps JSON and calls system python3 with matplotlib)."""
import sys, json, subprocess; sys.path[:0] = ["spike/m3_outer_arcs"]
import numpy as np, measure, tessellate
out, items = sys.argv[1], sys.argv[2:]
data = {}
for it in items:
    parts = it.split(":")
    if parts[0] == "test2":
        shape, fid = measure.test2()[0], int(parts[1])
    elif not parts[0].endswith(".step"):
        import notch_parts
        shape, fid = notch_parts.PARTS[parts[0]]().wrapped, int(parts[1])
    else:
        shape, fid = measure.step_solids(parts[0])[int(parts[1])], int(parts[2])
    m = tessellate.display_mesh(shape, 1.0, 0.3)
    v = m.verts.astype(float); st = np.concatenate([[0], np.cumsum(m.poly_sizes)[:-1]])
    data[it.split("/")[-1]] = [v[m.loops[st[i]:st[i] + m.poly_sizes[i]]].tolist() for i in np.where(m.poly_face == fid)[0]]
json.dump(data, open(out + ".json", "w"))
subprocess.run(["python3", "-c", r'''
import json,sys,numpy as np,matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
d=json.load(open(sys.argv[1])); n=len(d); fig,axs=plt.subplots(1,n,figsize=(9*n,8),squeeze=False)
for ax,(name,polys) in zip(axs[0],d.items()):
    P=[np.array(p) for p in polys]; allp=np.concatenate(P); c=allp.mean(0)
    nn=sum(np.cross(p[i]-p[0],p[i+1]-p[0]) for p in P for i in range(1,len(p)-1)); nn/=np.linalg.norm(nn)
    e1=np.cross(nn,[0,0,1]) if abs(nn[2])<0.9 else np.array([1.,0,0]); e1/=np.linalg.norm(e1); e2=np.cross(nn,e1)
    for p in P:
        q=np.array([[(x-c)@e1,(x-c)@e2] for x in p]); q=np.vstack([q,q[:1]]); ax.fill(q[:,0],q[:,1],alpha=0.15); ax.plot(q[:,0],q[:,1],lw=0.6,color="#d07000")
    ax.set_aspect("equal"); ax.set_title(f"{name}: {len(P)} polys")
plt.tight_layout(); plt.savefig(sys.argv[2],dpi=70)''', out + ".json", out], check=True)
