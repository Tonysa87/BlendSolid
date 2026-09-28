"""Fuzz: random box/cylinder cuts on a 1000 mm box + fillets; valid solids only; counts BRepMesh fallbacks, open
meshes, timeouts. $PY spike/m2_flat_faces/fuzz_valid.py <seed> <count> <out dir for failing .brep>"""
import sys, random, time, signal, io, contextlib; sys.path[:0]=["blendsolid/worker",".dev/worker_libs"]
import numpy as np, build123d as bd, tessellate
from OCP.BRepCheck import BRepCheck_Analyzer
seed=int(sys.argv[1]); n=int(sys.argv[2]); rnd=random.Random(seed)
def alarm(*a): raise TimeoutError
signal.signal(signal.SIGALRM, alarm)
stats=dict(valid=0, invalid=0, err=0, fallback=0, open=0, slow=0); worst=0
for k in range(n):
    try:
        box=bd.Box(1000,1000,1000)
        r=rnd.uniform(50,500); x=rnd.choice([-500,500])+rnd.uniform(-200,200); y=rnd.choice([-500,500])+rnd.uniform(-200,200)
        if rnd.random()<0.5: cut=bd.Pos(x,y,0)*bd.Cylinder(r,rnd.uniform(400,1200))
        else: cut=bd.Pos(x,y,rnd.uniform(-300,300))*bd.Box(rnd.uniform(100,600),rnd.uniform(100,600),rnd.uniform(100,600))
        part=box-cut if rnd.random()<0.7 else box+cut
        es=part.edges(); pick=rnd.sample(list(es), min(len(es), rnd.randint(1,4)))
        part=bd.fillet(pick, rnd.uniform(5,200)) if hasattr(bd,'fillet') else part
    except Exception: stats['err']+=1; continue
    w=part.wrapped
    if not BRepCheck_Analyzer(w).IsValid(): stats['invalid']+=1; continue
    stats['valid']+=1
    buf=io.StringIO(); t0=time.perf_counter(); signal.alarm(10)
    try:
        with contextlib.redirect_stderr(buf): m=tessellate.display_mesh(w,1.0,0.3)
    except TimeoutError: stats['slow']+=1; print("TIMEOUT", seed, k); continue
    except Exception as e: print("ERR",seed,k,e); continue
    finally: signal.alarm(0)
    dt=time.perf_counter()-t0; worst=max(worst,dt)
    starts=np.concatenate([[0],np.cumsum(m.poly_sizes)[:-1]]); nxt=np.arange(len(m.loops))+1; nxt[starts+m.poly_sizes-1]=starts
    pr=np.sort(np.stack([m.loops,m.loops[nxt]],1),1); _,c=np.unique(pr,axis=0,return_counts=True)
    if not (c==2).all(): stats['open']+=1
    if "fallback" in buf.getvalue():
        stats['fallback']+=1; print("FALLBACK",seed,k); bd.export_brep(part, f"{sys.argv[3]}/fb_{seed}_{k}.brep")
print(seed, stats, "worst %.2fs"%worst)
