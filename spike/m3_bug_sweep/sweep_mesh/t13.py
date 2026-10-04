import sys
import check
import numpy as np
import runner
src = open(sys.argv[1]).read(); tol=float(sys.argv[2])
r = runner.run_script(src, tol, 0.3, tag="x")
v = r.verts.astype(float); loops = r.loops.astype(int); sizes = r.poly_sizes
starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
N = []
for s,n in zip(starts,sizes):
    P = v[loops[s:s+n]]; nn = np.zeros(3)
    for k in range(1,n-1): nn += np.cross(P[k]-P[0], P[k+1]-P[0])
    N.append(nn/ max(np.linalg.norm(nn),1e-300))
N = np.array(N)
edge = {}
for p,(s,n) in enumerate(zip(starts,sizes)):
    for k in range(n):
        a,b = loops[s+k], loops[s+(k+1)%n]
        edge.setdefault((min(a,b),max(a,b)), []).append(p)
folds = []
for e, ps in edge.items():
    if len(ps)==2 and r.poly_face[ps[0]]==r.poly_face[ps[1]]:
        d = N[ps[0]] @ N[ps[1]]
        if d < -0.5: folds.append((e, ps, int(r.poly_face[ps[0]]), round(float(d),3)))
print("same-face dihedral folds (>120deg):", len(folds))
for f in folds[:8]: print(f, v[list(f[0])].round(4).tolist())
