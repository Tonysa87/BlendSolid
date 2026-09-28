"""Plot dump.py's JSON to a PNG (system python3 with matplotlib): python3 plot.py metrics.py.json out.png"""
import json,sys,numpy as np,matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
d=json.load(open(sys.argv[1])); fig,axs=plt.subplots(2,3,figsize=(18,12))
for ax,(name,polys) in zip(axs.ravel(),d.items()):
    P=[np.array(p) for p in polys]; allp=np.concatenate(P); c=allp.mean(0)
    n=np.cross(P[0][1]-P[0][0],P[0][2]-P[0][0]); n/=np.linalg.norm(n)
    e1=np.cross(n,[0,0,1]) if abs(n[2])<0.9 else np.array([1.,0,0]); e1/=np.linalg.norm(e1); e2=np.cross(n,e1)
    for p in P:
        q=np.array([[(x-c)@e1,(x-c)@e2] for x in p]); q=np.vstack([q,q[:1]]); ax.plot(q[:,0],q[:,1],lw=0.6,color="#d07000")
    ax.set_aspect("equal"); ax.set_title(f"{name}: {len(P)} polys")
plt.tight_layout(); plt.savefig(sys.argv[2],dpi=80)
