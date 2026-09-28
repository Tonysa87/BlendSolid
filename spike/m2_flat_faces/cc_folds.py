"""One Catmull-Clark step on a part's display mesh (pure numpy, Blender's rules for a closed mesh) and the child
polygons whose normal flips against their parent's: $PY spike/m2_flat_faces/cc_folds.py [names...]"""
import sys, math; sys.path[:0] = ["blendsolid/worker", ".dev/worker_libs", ".dev/pytest", "tests/unit", "."]
import numpy as np, build123d as bd, tessellate
from test_tessellate import COLLARED


def default_part():
    p = bd.Box(40, 30, 20, align=bd.Align.MIN) + bd.Pos(20, 15, 0) * bd.Cylinder(6, 25, align=(bd.Align.CENTER,
                                                                                               bd.Align.CENTER, bd.Align.MIN))
    return bd.fillet(p.edges().filter_by(bd.Axis.Z).sort_by_distance((0, 0, 0))[0], 5)


def folds(shape):
    m = tessellate.display_mesh(shape.wrapped, 1.0, 0.3)
    v = m.verts.astype(np.float64)
    st = np.concatenate([[0], np.cumsum(m.poly_sizes)[:-1]])
    polys = [m.loops[s:s + n].tolist() for s, n in zip(st, m.poly_sizes)]
    fp = np.array([v[p].mean(0) for p in polys])
    edge_faces, vert_faces, vert_edges = {}, {}, {}
    for i, p in enumerate(polys):
        for k in range(len(p)):
            a, b = p[k], p[(k + 1) % len(p)]
            e = (min(a, b), max(a, b))
            edge_faces.setdefault(e, []).append(i)
            vert_faces.setdefault(a, []).append(i)
    for e in edge_faces:
        for x in e:
            vert_edges.setdefault(x, []).append(e)
    ep = {e: (v[e[0]] + v[e[1]] + fp[f].sum(0)) / (2 + len(f)) for e, f in edge_faces.items()}
    vp = {}
    for x, fs in vert_faces.items():
        n = len(fs)
        Q = fp[fs].mean(0)
        R = np.mean([(v[a] + v[b]) / 2 for a, b in vert_edges[x]], axis=0)
        vp[x] = (Q + 2 * R + (n - 3) * v[x]) / n
    bad = []
    for i, p in enumerate(polys):
        nrm = np.cross(v[p[1]] - v[p[0]], v[p[2]] - v[p[0]])
        pn = sum(np.cross(v[p[k]] - fp[i], v[p[(k + 1) % len(p)]] - fp[i]) for k in range(len(p)))
        for k in range(len(p)):
            a, b, c = p[k - 1], p[k], p[(k + 1) % len(p)]
            q = [vp[b], ep[(min(b, c), max(b, c))], fp[i], ep[(min(a, b), max(a, b))]]
            cn = np.cross(q[1] - q[0], q[3] - q[0]) + np.cross(q[3] - q[2], q[1] - q[2])
            if np.dot(cn, pn) <= 0:
                bad.append((i, len(p), np.round(v[b], 2).tolist()))
    angles = []
    for p in polys:
        P = v[p]
        a, b = np.roll(P, 1, 0) - P, np.roll(P, -1, 0) - P
        cos = (a * b).sum(1) / np.linalg.norm(a, axis=1) / np.linalg.norm(b, axis=1)
        angles.append(np.degrees(np.arccos(np.clip(cos, -1, 1))).min())
    return bad, min(angles), len(polys)


SHAPES = {"default_part": default_part, **{k: v[0] for k, v in COLLARED.items()}}
for name in sys.argv[1:] or SHAPES:
    bad, amin, n = folds(SHAPES[name]())
    print(f"{name:18s} polys {n:4d}  min angle {amin:6.2f}  folded children {len(bad)}", bad[:3])
