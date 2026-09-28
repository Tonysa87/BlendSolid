"""Blender Bevel's Clamp Overlap limit on a part's display mesh (bmesh_bevel.cc, bevel_limit_offset: for a
bevelled edge B = (b, c) in a polygon, an un-bevelled previous edge (a, b) limits the offset to the distance from
a to B's line; likewise the next edge): the tightest spots. $PY spike/m2_flat_faces/clamp_limit.py [names...]"""
import sys; sys.argv, names = sys.argv[:1], sys.argv[1:]
exec(open("spike/m2_flat_faces/cc_folds.py").read().split("SHAPES = {")[0])
SHAPES = {"default_part": default_part, **{k: v[0] for k, v in COLLARED.items()}}
for name in names or SHAPES:
    m = tessellate.display_mesh(SHAPES[name]().wrapped, 1.0, 0.3)
    v = m.verts.astype(np.float64)
    sharp = {(min(a, b), max(a, b)) for (a, b), s in zip(m.edges, m.edge_sharp) if s}
    st = np.concatenate([[0], np.cumsum(m.poly_sizes)[:-1]])
    out = []
    for s, n in zip(st, m.poly_sizes):
        p = m.loops[s:s + n].tolist()
        for k in range(n):
            b, c = p[k], p[(k + 1) % n]
            if (min(b, c), max(b, c)) not in sharp:
                continue
            u = (v[c] - v[b]) / np.linalg.norm(v[c] - v[b])
            for x, y in ((p[k - 1], b), (p[(k + 2) % n], c)):
                if (min(x, y), max(x, y)) in sharp:
                    continue
                w = v[x] - v[b]
                out.append((float(np.linalg.norm(w - (w @ u) * u)), np.round(v[b], 2).tolist(), np.round(v[x], 2).tolist()))
    out.sort()
    print(name, [o for o in out[:3]])
