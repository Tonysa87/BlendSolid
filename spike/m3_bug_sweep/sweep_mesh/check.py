"""Mesh quality checks on a runner.RunResult (+ the BRep shape)."""
import io
import math
import sys
import time
import contextlib

sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import numpy as np
import runner
import tessellate
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.gp import gp_Pnt
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

SURF = {0: "plane", 1: "cyl", 2: "cone", 3: "sphere", 4: "torus", 5: "bezier", 6: "bspline", 7: "revol",
        8: "extrus", 9: "offset", 10: "other"}


def poly_iter(r):
    start = 0
    for n in r.poly_sizes:
        yield start, int(n)
        start += int(n)


def analyse(r, shape, tol, sample_dev=400):
    out = {}
    v = r.verts.astype(np.float64)
    loops = r.loops.astype(np.int64)
    sizes = r.poly_sizes.astype(np.int64)
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    nxt = np.arange(len(loops)) + 1
    nxt[starts + sizes - 1] = starts
    a, b = loops, loops[nxt]
    # closedness + orientation: each directed edge once, its reverse once
    und = np.sort(np.stack([a, b], 1), 1)
    uniq, inv, cnt = np.unique(und, axis=0, return_inverse=True, return_counts=True)
    out["open_edges"] = int((cnt == 1).sum())
    out["nonmanifold_edges"] = int((cnt > 2).sum())
    d, dcnt = np.unique(np.stack([a, b], 1), axis=0, return_counts=True)
    out["dup_directed"] = int((dcnt > 1).sum())  # orientation flips
    out["polys"] = int(len(sizes))
    out["verts"] = int(len(v))
    # repeated vertex inside a polygon
    rep = 0
    for s, n in zip(starts, sizes):
        if len(set(loops[s:s + n].tolist())) != n:
            rep += 1
    out["poly_repeat_vertex"] = rep
    # fan triangles
    tri, owner = [], []
    for p, (s, n) in enumerate(zip(starts, sizes)):
        for k in range(1, n - 1):
            tri.append((loops[s], loops[s + k], loops[s + k + 1]))
            owner.append(p)
    tri = np.array(tri, dtype=np.int64).reshape(-1, 3)
    owner = np.array(owner, dtype=np.int64)
    P0, P1, P2 = v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]]
    cr = np.cross(P1 - P0, P2 - P0)
    vol = np.einsum("ij,ij->i", P0, np.cross(P1, P2)).sum() / 6
    area_t = np.linalg.norm(cr, axis=1) / 2
    area = area_t.sum()
    out["mesh_volume"] = float(vol)
    out["brep_volume"] = float(r.volume)
    out["mesh_area"] = float(area)
    dv = r.volume - vol
    out["dvol"] = float(dv)
    out["dvol_over_area_tol"] = float(dv / max(area * tol, 1e-300))
    # polygon areas (Newell)
    parea = np.zeros(len(sizes))
    np.add.at(parea, owner, area_t)
    bbox = v.max(0) - v.min(0) if len(v) else np.zeros(3)
    diag = float(np.linalg.norm(bbox))
    out["diag"] = diag
    out["zero_area_polys"] = int((parea < 1e-12 * max(diag, 1e-9) ** 2).sum())
    # polygon corner angles
    def corner_angles():
        prev = np.arange(len(loops)) - 1
        prev[starts] = starts + sizes - 1
        e1 = v[loops[prev]] - v[loops]
        e2 = v[loops[nxt]] - v[loops]
        n1, n2 = np.linalg.norm(e1, axis=1), np.linalg.norm(e2, axis=1)
        c = np.einsum("ij,ij->i", e1, e2) / np.maximum(n1 * n2, 1e-300)
        return np.degrees(np.arccos(np.clip(c, -1, 1)))
    ang = corner_angles()
    poly_of_corner = np.repeat(np.arange(len(sizes)), sizes)
    pmin = np.full(len(sizes), 180.0)
    np.minimum.at(pmin, poly_of_corner, ang)
    faces = tessellate.face_map(shape)
    ftype = np.array([BRepAdaptor_Surface(f).GetType() for f in faces])
    pf = r.poly_face.astype(np.int64)
    curved = ftype[pf] != GeomAbs_Plane
    out["n_faces"] = len(faces)
    out["face_types"] = sorted({SURF.get(int(t), str(t)) for t in ftype})
    out["curved_polys"] = int(curved.sum())
    out["curved_min_angle"] = float(pmin[curved].min()) if curved.any() else None
    out["curved_lt1"] = int((pmin[curved] < 1.0).sum())
    out["curved_lt5"] = int((pmin[curved] < 5.0).sum())
    out["plane_lt1"] = int((pmin[~curved] < 1.0).sum())
    out["plane_polys"] = int((~curved).sum())
    # worst faces by curved slivers
    worst = {}
    for p in np.nonzero(curved & (pmin < 1.0))[0]:
        worst[int(pf[p])] = worst.get(int(pf[p]), 0) + 1
    out["sliver_faces"] = {f"{k}:{SURF.get(int(ftype[k]))}": c for k, c in sorted(worst.items(), key=lambda x: -x[1])[:6]}
    # normals: corner normal vs polygon normal (Newell)
    pn = np.zeros((len(sizes), 3))
    np.add.at(pn, owner, cr)
    pnn = pn / np.maximum(np.linalg.norm(pn, axis=1, keepdims=True), 1e-300)
    cn = r.corner_normals.astype(np.float64)
    dots = np.einsum("ij,ij->i", cn, pnn[poly_of_corner])
    big = parea[poly_of_corner] > 1e-9 * max(diag, 1e-9) ** 2
    out["normal_back"] = int(((dots < 0) & big).sum())
    out["normal_off60"] = int(((dots < 0.5) & big).sum())
    out["normal_min_dot"] = float(dots[big].min()) if big.any() else None
    allneg = np.ones(len(sizes), bool)
    np.logical_and.at(allneg, poly_of_corner, dots < 0)
    out["folded_polys"] = int((allneg & (parea > 1e-9 * max(diag, 1e-9) ** 2)).sum())
    # deviation: centroid of fan triangles on curved faces vs the face's surface
    devmax, devface = 0.0, None
    idx = np.nonzero(curved[owner])[0]
    if len(idx):
        rng = np.random.default_rng(0)
        pick = idx if len(idx) <= sample_dev else rng.choice(idx, sample_dev, replace=False)
        # prefer biggest triangles too
        big_idx = idx[np.argsort(-area_t[idx])[:100]]
        pick = np.unique(np.concatenate([pick, big_idx]))
        surfs = {}
        for t in pick:
            f = int(pf[owner[t]])
            if f not in surfs:
                surfs[f] = BRep_Tool.Surface_s(faces[f])
            c = (P0[t] + P1[t] + P2[t]) / 3
            pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*c), surfs[f])
            if pr.NbPoints():
                dd = pr.LowerDistance()
                if dd > devmax:
                    devmax, devface = dd, f"{f}:{SURF.get(int(ftype[f]))}"
    out["dev_max"] = devmax
    out["dev_face"] = devface
    out["dev_over_tol"] = devmax / tol
    # longest edge relative to diag
    el = np.linalg.norm(v[a] - v[b], axis=1)
    out["min_edge"] = float(el.min()) if len(el) else 0.0
    return out


def run_case(source, tol, ang=0.3):
    err = io.StringIO()
    runner.SHAPES._items.clear()
    t0 = time.perf_counter()
    with contextlib.redirect_stderr(err):
        r = runner.run_script(source, tol, ang, tag="case")
    wall = time.perf_counter() - t0
    res = {"ok": r.ok, "error": r.error, "wall": wall, "timing": r.timing,
           "fallbacks": err.getvalue().count("BRepMesh fallback"), "stderr": err.getvalue()[-500:]}
    if not r.ok:
        return res
    shape = runner.SHAPES.get("case")
    if shape is None or len(r.verts) == 0:
        res["empty"] = True
        return res
    res.update(analyse(r, shape.wrapped, tol))
    return res
