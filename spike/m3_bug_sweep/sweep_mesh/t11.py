import sys, math
import check
import numpy as np
import runner, tessellate, meshing
from OCP.BRepAdaptor import BRepAdaptor_Surface
src = open(sys.argv[1]).read(); tol=float(sys.argv[2]); fid=int(sys.argv[3])
r = runner.run_script(src, tol, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
faces = tessellate.face_map(shape); edges = tessellate.edge_map(shape)
revs = [tessellate._revolution(f) for f in faces]
kinds=["self" if tessellate._self_contained(rev) else "revolution" if rev is not None else "plane" if BRepAdaptor_Surface(f).GetType()==0 else "curved" for f, rev in zip(faces, revs)]
rings = [4 * math.ceil(tessellate._TAU / tessellate._step(tol, 0.15, rev.max_circle_radius()) / 4) if rev is not None and "circle" in rev.ends else 1 for rev in revs]
lay = meshing.plan(faces, edges, kinds, rings, tol, 0.15)
fi = lay.faces[fid]; s = fi.surf
periods = (s.UPeriod() if s.IsUPeriodic() else None, s.VPeriod() if s.IsVPeriodic() else None)
print("face", fid, check.SURF.get(s.GetType()), "kind", fi.kind, "periods", periods, "box", fi.box, "U", s.FirstUParameter(), s.LastUParameter(), "V", s.FirstVParameter(), s.LastVParameter())
for li, loop in enumerate(fi.loops):
    uv, xyz, starts = meshing.loop_nodes(loop, lay.edges, periods)
    print(" loop", li, "nodes", len(uv))
    for k, use in enumerate(loop):
        e = lay.edges[use.edge]
        a = starts[k]; b = starts[k+1] if k+1 < len(starts) else len(uv)
        print(f"  use {k} edge {use.edge} rev {use.reversed} len {e.length:.5f} count {e.count} deg {e.degenerate} seam {meshing._is_seam(use, fi)} uv {uv[a].round(5)} -> {uv[b % len(uv)].round(5)}")
    _, idx, cnt = np.unique(np.round(uv, 9), axis=0, return_index=True, return_counts=True)
    for i in idx[cnt > 1]:
        same = np.nonzero(np.all(np.abs(uv - uv[i]) < 1e-9, axis=1))[0]
        print("  DUP uv", uv[i], "at nodes", same, "xyz", xyz[same].round(5).tolist())
