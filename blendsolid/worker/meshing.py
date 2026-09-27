"""Edge-first, grid-based tessellation of BRep faces (ADR 0010).

Every edge is discretized once (a list of curve parameters and 3D points); every face takes its boundary nodes
from those lists, so neighbouring faces weld exactly. Curved faces with four corners become structured grids
(transfinite interpolation of their sides, opposite sides matched in node count); other curved faces get a grid
in (u, v) trimmed by their boundary, the band along the boundary triangulated by constrained Delaunay; flat
faces are triangulated from their boundary alone. This is how Rhino, MoI and ACIS lay out display meshes: every
mesh edge runs along a surface direction or along a trim.
"""
import math
from dataclasses import dataclass, field

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d, BRepAdaptor_Surface
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.GCPnts import GCPnts_AbscissaPoint, GCPnts_TangentialDeflection
from OCP.GeomAbs import GeomAbs_Plane
from OCP.TopAbs import TopAbs_FORWARD, TopAbs_REVERSED, TopAbs_WIRE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Vertex
from OCP.gp import gp_Pnt, gp_Vec

_ASPECT = 4.0           # a face curved both ways: longest / shortest grid step
_STRAIGHT_ASPECT = 6.0  # a straight direction on a trimmed grid: at most this many times the other step (Rhino's tip)
_CORNER_DEG = 20.0      # a corner turns the boundary more than this; the joints that aren't corners, under half
_TINY = 0.25            # a side's interval under this fraction of its median: its grid line merges into the previous
_MARGIN = 0.6           # grid nodes kept at least this many cells from the boundary
_DIAGONAL_TIE = 0.01    # a cell's two diagonals within 1%: the fixed one (no alternating by round-off)
_EQUALIZE_ROUNDS = 200


def _xyz(p):
    return (p.X(), p.Y(), p.Z())


# -- topology: each face's loops of oriented edges ----------------------------------------------------------------

@dataclass
class Use:
    """One edge as a face's boundary walks it."""
    edge: int                # edge id (edge_map order)
    reversed: bool           # walked from its last parameter to its first
    pcurve: BRepAdaptor_Curve2d
    first: float             # the edge's parameter range
    last: float


@dataclass
class FaceInfo:
    loops: list                      # [[Use, ...], ...]: outer wire first (as OCCT gives them)
    surf: BRepAdaptor_Surface
    planar: bool
    step: tuple = (math.inf, math.inf)  # grid step in mm along u and v (inf: straight or flat)
    scale: tuple = (1.0, 1.0)           # mm per unit of u and of v (the largest on the face)
    sides: list = None                  # four-sided: [[edge ids], ...] per side, in walking order
    corners: list = None                # four-sided: the loop positions (Use indices) starting each side
    kind: str = "grid"                  # "plane", "tfi", "grid" or "other" (the caller meshes it)
    box: tuple = None                   # (u, v) box of the boundary: ((u0, v0), (u1, v1))


def face_loops(face, edge_index):
    loops = []
    exp = TopExp_Explorer(face, TopAbs_WIRE)
    while exp.More():
        wire = TopoDS.Wire(exp.Current())
        uses = []
        we = BRepTools_WireExplorer(wire, face)
        while we.More():
            e = we.Current()
            first, last = BRep_Tool.Range_s(e)
            uses.append(Use(edge_index(e), e.Orientation() == TopAbs_REVERSED, BRepAdaptor_Curve2d(e, face),
                            first, last))
            we.Next()
        if uses:
            loops.append(uses)
        exp.Next()
    return loops


# -- per-face grid steps from the surface's curvature -------------------------------------------------------------

def surface_steps(surf, uv_box, lin_defl, ang_defl, samples=7):
    """(step along u, step along v) in mm and (mm per unit u, mm per unit v): the chord of a step sags at most
    lin_defl and turns at most ang_defl on the sampled normal curvature; inf where the surface is straight."""
    (u0, v0), (u1, v1) = uv_box
    su, sv, ku, kv = [], [], 0.0, 0.0
    for u in np.linspace(u0, u1, samples):
        for v in np.linspace(v0, v1, samples):
            props = BRepLProp_SLProps(surf, float(u), float(v), 2, 1e-9)
            du, dv = props.D1U(), props.D1V()
            su.append(du.Magnitude())
            sv.append(dv.Magnitude())
            if props.IsNormalDefined() and du.Magnitude() > 1e-12 and dv.Magnitude() > 1e-12:
                n = gp_Vec(props.Normal().XYZ())
                ku = max(ku, abs(props.D2U().Dot(n)) / du.SquareMagnitude())
                kv = max(kv, abs(props.D2V().Dot(n)) / dv.SquareMagnitude())
    # the largest length per unit: a cell is never longer than its step anywhere on the face (on a sphere the
    # cells narrow towards the poles, as on a latitude-longitude grid)
    scale = (max(float(np.max(su)), 1e-12), max(float(np.max(sv)), 1e-12))
    steps = tuple(min(math.sqrt(8 * lin_defl / k), ang_defl / k) if k > 1e-9 else math.inf for k in (ku, kv))
    if all(math.isfinite(s) for s in steps):
        low = min(steps)
        steps = tuple(min(s, _ASPECT * low) for s in steps)
    return steps, scale


def _loop_uv_box(loops):
    pts = []
    for loop in loops:
        for use in loop:
            for t in np.linspace(use.first, use.last, 5):
                p = use.pcurve.Value(float(t))
                pts.append((p.X(), p.Y()))
    pts = np.asarray(pts)
    return pts.min(axis=0), pts.max(axis=0)


# -- edges: one discretization shared by both faces ---------------------------------------------------------------

@dataclass
class EdgeInfo:
    edge: object
    degenerate: bool
    first: float
    last: float
    length: float = 0.0
    count: int = 1                      # intervals
    params: np.ndarray = None
    points: np.ndarray = None           # (count + 1, 3)
    own: int = 1                        # intervals its own curve needs
    need: list = field(default_factory=list)


def edge_info(edge):
    first, last = BRep_Tool.Range_s(edge)
    degenerate = BRep_Tool.Degenerated_s(edge)
    info = EdgeInfo(edge, degenerate, first, last)
    if not degenerate:
        curve = BRepAdaptor_Curve(edge)
        info.length = GCPnts_AbscissaPoint.Length_s(curve)
    return info


def own_count(info, lin_defl, ang_defl):
    """Intervals the edge's curve needs on its own: evenly spaced by arc length, every chord's sag within
    lin_defl and every turn within ang_defl."""
    if info.degenerate or info.length < 1e-9:
        return 1
    curve = BRepAdaptor_Curve(info.edge)
    try:
        td = GCPnts_TangentialDeflection(curve, ang_defl, lin_defl, 2)
        n = max(1, td.NbPoints() - 1)
    except Exception:
        n = 1
    while n < 100000 and not _even_ok(curve, info, n, lin_defl, ang_defl):
        n = max(n + 1, int(n * 1.25))
    return n


def even_params(curve, info, n):
    """n + 1 parameters evenly spaced by arc length."""
    if n <= 1 or info.length < 1e-12:
        return np.linspace(info.first, info.last, n + 1)
    out = [info.first]
    step = info.length / n
    for k in range(1, n):
        ap = GCPnts_AbscissaPoint(curve, step * k, info.first)
        out.append(ap.Parameter() if ap.IsDone() else info.first + (info.last - info.first) * k / n)
    out.append(info.last)
    return np.asarray(out, dtype=np.float64)


def _even_ok(curve, info, n, lin_defl, ang_defl):
    params = even_params(curve, info, n)
    pts = np.array([_xyz(curve.Value(float(t))) for t in params])
    mids = np.array([_xyz(curve.Value(float(t))) for t in (params[:-1] + params[1:]) / 2])
    chord = pts[1:] - pts[:-1]
    clen = np.linalg.norm(chord, axis=1)
    if (clen < 1e-12).any():
        return True
    w = mids - pts[:-1]
    sag = np.linalg.norm(w - (np.einsum("ij,ij->i", w, chord) / clen ** 2)[:, None] * chord, axis=1)
    if sag.max() > lin_defl:
        return False
    d = chord / clen[:, None]
    turn = np.arccos(np.clip(np.einsum("ij,ij->i", d[1:], d[:-1]), -1, 1)) if len(d) > 1 else np.zeros(1)
    return turn.max() <= ang_defl * 2  # consecutive chords of arcs each within ang_defl


def face_need(face_info, use, info):
    """Intervals the face's grid asks of an edge it bounds: the edge's length over the face's step in the
    edge's direction (the steps along u and v combined as an ellipse)."""
    su, sv = face_info.step
    if info.degenerate or not (math.isfinite(su) or math.isfinite(sv)):
        return 1
    tmid = (use.first + use.last) / 2
    p2, d2 = _p2d(use.pcurve, tmid)
    props = BRepLProp_SLProps(face_info.surf, p2[0], p2[1], 1, 1e-9)
    du, dv = props.D1U(), props.D1V()
    # the edge's direction in the surface: d2 (in u, v) times the lengths per unit
    a, b = abs(d2[0]) * du.Magnitude(), abs(d2[1]) * dv.Magnitude()
    norm = math.hypot(a, b)
    if norm < 1e-15:
        return 1
    a, b = a / norm, b / norm
    inv = math.hypot(a / su if math.isfinite(su) else 0.0, b / sv if math.isfinite(sv) else 0.0)
    if inv < 1e-15:
        return 1
    return max(1, math.ceil(info.length * inv - 1e-6))


def _p2d(pcurve, t):
    from OCP.gp import gp_Pnt2d, gp_Vec2d
    p, d = gp_Pnt2d(), gp_Vec2d()
    pcurve.D1(t, p, d)
    return (p.X(), p.Y()), (d.X(), d.Y())


def build_points(info):
    """The edge's parameters and 3D points; its ends are the exact vertex points (shared with the next edge)."""
    edge = info.edge
    if info.degenerate:
        v = TopExp.FirstVertex_s(edge)
        p = _xyz(BRep_Tool.Pnt_s(v))
        info.params = np.linspace(info.first, info.last, info.count + 1)
        info.points = np.tile(np.array(p, dtype=np.float64), (info.count + 1, 1))
        return
    curve = BRepAdaptor_Curve(edge)
    info.params = even_params(curve, info, info.count)
    info.points = np.array([_xyz(curve.Value(float(t))) for t in info.params], dtype=np.float64)
    fwd = TopoDS.Edge(edge.Oriented(TopAbs_FORWARD))
    v1, v2 = TopoDS_Vertex(), TopoDS_Vertex()
    TopExp.Vertices_s(fwd, v1, v2)
    if not v1.IsNull():
        info.points[0] = _xyz(BRep_Tool.Pnt_s(v1))
    if not v2.IsNull():
        info.points[-1] = _xyz(BRep_Tool.Pnt_s(v2))


# -- corners and sides of a face ----------------------------------------------------------------------------------

def _tangent3d(face_info, edges, use, at_end):
    """Unit 3D tangent of the edge as the loop walks it, at its start or end (in the surface for a degenerate
    edge, from its pcurve)."""
    info = edges[use.edge]
    t = (use.first if use.reversed else use.last) if at_end else (use.last if use.reversed else use.first)
    sign = -1.0 if use.reversed else 1.0
    if not info.degenerate:
        curve = BRepAdaptor_Curve(info.edge)
        p, d = gp_Pnt(), gp_Vec()
        curve.D1(t, p, d)
        v = np.array(_xyz(d)) * sign
    else:
        (u, w), (du, dv) = _p2d(use.pcurve, t)
        props = BRepLProp_SLProps(face_info.surf, u, w, 1, 1e-9)
        v = (np.array(_xyz(props.D1U())) * face_info.scale[0] / max(props.D1U().Magnitude(), 1e-12) * du
             + np.array(_xyz(props.D1V())) * face_info.scale[1] / max(props.D1V().Magnitude(), 1e-12) * dv) * sign
    n = np.linalg.norm(v)
    return v / n if n > 1e-15 else v


def four_sides(face_info, edges):
    """[[use index, ...] * 4] if the face's single loop has four clear corners, else None. Like SALOME's
    quadrangle mapping: the four sharpest turns, each sharper than _CORNER_DEG, every other turn smooth (under
    it, with a margin)."""
    if len(face_info.loops) != 1:
        return None
    loop = face_info.loops[0]
    m = len(loop)
    if m < 2:
        return None
    turns = []
    for k in range(m):
        a = _tangent3d(face_info, edges, loop[k - 1], True)
        b = _tangent3d(face_info, edges, loop[k], False)
        if np.linalg.norm(a) < 0.5 or np.linalg.norm(b) < 0.5:
            turns.append(180.0)
        else:
            turns.append(math.degrees(math.acos(max(-1.0, min(1.0, float(a @ b))))))
    order = sorted(range(m), key=lambda k: -turns[k])
    if m < 4 or turns[order[3]] < _CORNER_DEG or (m > 4 and turns[order[4]] > _CORNER_DEG / 2):
        return None
    corners = sorted(order[:4])
    return [[(corners[s] + j) % m for j in range((corners[(s + 1) % 4] - corners[s]) % m or m)] for s in range(4)]


# -- boundary nodes of a face -------------------------------------------------------------------------------------

def use_nodes(use, edges):
    """(uv (n, 2), xyz (n, 3)) of an edge as the loop walks it, both ends included."""
    info = edges[use.edge]
    params, pts = info.params, info.points
    if use.reversed:
        params, pts = params[::-1], pts[::-1]
    uv = np.array([(lambda p: (p.X(), p.Y()))(use.pcurve.Value(float(t))) for t in params])
    return uv, pts


def loop_nodes(loop, edges, periods=(None, None)):
    """A closed loop's nodes (each once): uv, xyz, and the index where each use starts. Pcurves of a periodic
    surface can be a period apart: each is shifted to continue the previous one."""
    uvs, xyzs, starts = [], [], []
    prev = None
    for use in loop:
        uv, xyz = use_nodes(use, edges)
        if prev is not None:
            for axis, period in enumerate(periods):
                if period:
                    uv[:, axis] += round((prev[axis] - uv[0, axis]) / period) * period
        starts.append(sum(len(x) for x in uvs))
        uvs.append(uv[:-1])
        xyzs.append(xyz[:-1])
        prev = uv[-1]
    return np.concatenate(uvs), np.concatenate(xyzs), starts


# -- structured grid of a four-sided face (transfinite interpolation) --------------------------------------------

def _normalized(xyz):
    d = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(xyz, axis=0), axis=1))])
    return d / d[-1] if d[-1] > 1e-15 else np.linspace(0, 1, len(xyz))


def tfi(face_info, edges, periods):
    """(uv, xyz, triangles CCW in (u, v)) of a four-sided face, or None if the interpolated grid folds."""
    loop = face_info.loops[0]
    uv, xyz, starts = loop_nodes(loop, edges, periods)
    n = len(uv)
    corner_idx = [starts[s[0]] for s in face_info.sides]

    def side(s):
        a, b = corner_idx[s], corner_idx[(s + 1) % 4]
        idx = [(a + k) % n for k in range(((b - a) % n) + 1)]
        return idx
    bottom, right, top, left = side(0), side(1), side(2)[::-1], side(3)[::-1]
    if len(bottom) != len(top) or len(left) != len(right):
        return None
    ni, nj = len(bottom), len(left)
    xb, xt = _normalized(xyz[bottom]), _normalized(xyz[top])
    yl, yr = _normalized(xyz[left]), _normalized(xyz[right])
    c0, c1, c2, c3 = uv[bottom[0]], uv[bottom[-1]], uv[top[-1]], uv[top[0]]
    index = np.full((ni, nj), -1, dtype=np.int64)
    index[:, 0], index[:, -1] = bottom, top
    index[0, :], index[-1, :] = left, right
    all_uv, all_xyz = list(uv), list(xyz)
    surf = face_info.surf
    for i in range(1, ni - 1):
        for j in range(1, nj - 1):
            x0, x1, y0, y1 = xb[i], xt[i], yl[j], yr[j]
            x = (x0 + y0 * (x1 - x0)) / (1 - (y1 - y0) * (x1 - x0))
            y = y0 + x * (y1 - y0)
            p = ((1 - y) * uv[bottom[i]] + x * uv[right[j]] + y * uv[top[i]] + (1 - x) * uv[left[j]]
                 - ((1 - x) * (1 - y) * c0 + x * (1 - y) * c1 + x * y * c2 + (1 - x) * y * c3))
            index[i, j] = len(all_uv)
            all_uv.append(p)
            all_xyz.append(_xyz(surf.Value(float(p[0]), float(p[1]))))
    all_uv, all_xyz = np.asarray(all_uv), np.asarray(all_xyz, dtype=np.float64)
    # A tiny edge on a side (a sliver of a face left by a boolean or a fillet's end) would run a column of slivers
    # across the whole face: its interior grid line merges into the previous one; the cells between collapse
    # (their triangles are dropped as degenerate) and the tiny edge closes with one triangle at each end.
    for i, into in _tiny(xb, xt):
        index[i, 1:-1] = index[into, 1:-1]
    for j, into in _tiny(yl, yr):
        index[1:-1, j] = index[1:-1, into]
    tris = _cells(index, all_xyz)
    tris = tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])]
    area = _area2d(all_uv, tris)
    sign = np.sign(area.sum())
    if sign == 0 or (np.sign(area) != sign)[np.abs(area) > 1e-14 * np.abs(area).max()].any():
        return None  # folded (a boundary bulging past the opposite one)
    if sign < 0:
        tris = tris[:, ::-1]
    return all_uv, all_xyz, tris


def _tiny(a, b):
    """(line, line it merges into) for every tiny interval on both opposite sides (normalized positions a, b):
    the interval's interior grid line merges into its other end (a boundary side if the interval is the last)."""
    gaps = np.minimum(np.diff(a), np.diff(b))
    median = np.median(np.maximum(np.diff(a), np.diff(b)))
    n, out = len(a), []
    for k in np.nonzero(gaps < _TINY * median)[0]:
        if k + 1 <= n - 2:
            out.append((k + 1, k))
        elif k >= 1:
            out.append((k, k + 1))
    return out


def _cells(index, xyz):
    """Two triangles per grid cell (index[i, j] a node), split by the shorter 3D diagonal (a fixed one on ties)."""
    a, b = index[:-1, :-1].ravel(), index[1:, :-1].ravel()
    c, d = index[1:, 1:].ravel(), index[:-1, 1:].ravel()
    ac = np.linalg.norm(xyz[a] - xyz[c], axis=1)
    bd = np.linalg.norm(xyz[b] - xyz[d], axis=1)
    use_bd = bd < ac * (1 - _DIAGONAL_TIE)
    t1 = np.where(use_bd[:, None], np.stack([a, b, d], 1), np.stack([a, b, c], 1))
    t2 = np.where(use_bd[:, None], np.stack([b, c, d], 1), np.stack([a, c, d], 1))
    return np.concatenate([t1, t2]).astype(np.int64)


def _area2d(p, t):
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    return (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])


# -- trimmed grid of any face: constrained Delaunay between the boundary and the grid cells ------------------------

def _inside(points, segments):
    """Even-odd test of 2D `points` against closed boundary `segments` ((m, 2, 2))."""
    inside = np.zeros(len(points), dtype=bool)
    a, b = segments[:, 0], segments[:, 1]
    dy = np.where(np.abs(b[:, 1] - a[:, 1]) < 1e-300, 1e-300, b[:, 1] - a[:, 1])
    for start in range(0, len(points), 2048):
        p = points[start:start + 2048, None, :]
        crosses = (a[None, :, 1] > p[..., 1]) != (b[None, :, 1] > p[..., 1])
        x = a[None, :, 0] + (p[..., 1] - a[None, :, 1]) * (b[None, :, 0] - a[None, :, 0]) / dy[None, :]
        inside[start:start + 2048] = (crosses & (p[..., 0] < x)).sum(axis=1) % 2 == 1
    return inside


def _distance_to(points, segments):
    out = np.full(len(points), np.inf)
    a, d = segments[:, 0], segments[:, 1] - segments[:, 0]
    dd = np.maximum(np.einsum("ij,ij->i", d, d), 1e-300)
    for start in range(0, len(points), 2048):
        p = points[start:start + 2048, None, :]
        s = np.clip(np.einsum("nmk,mk->nm", p - a[None], d) / dd[None], 0.0, 1.0)
        out[start:start + 2048] = np.linalg.norm(p - (a[None] + s[..., None] * d[None]), axis=2).min(axis=1)
    return out


def _orient(p, a, b, c):
    return (p[b, 0] - p[a, 0]) * (p[c, 1] - p[a, 1]) - (p[b, 1] - p[a, 1]) * (p[c, 0] - p[a, 0])


def _recover(q, tris, constraints):
    """Make every constraint segment an edge of the triangulation by flipping the edges that cross it (Sloan).
    Returns the triangles, or None if a segment can't be recovered."""
    tris = [tuple(int(x) for x in t) for t in tris]
    for t_i, t in enumerate(tris):
        if _orient(q, *t) < 0:
            tris[t_i] = (t[0], t[2], t[1])

    def edge_map():
        m = {}
        for i, (a, b, c) in enumerate(tris):
            for x, y in ((a, b), (b, c), (c, a)):
                m[(x, y)] = i
        return m
    em = edge_map()
    for a, b in constraints:
        if (a, b) in em or (b, a) in em:
            continue
        for _ in range(10 * len(tris)):
            if (a, b) in em or (b, a) in em:
                break
            flipped = False
            for (x, y), i in list(em.items()):
                if x > y or (y, x) not in em or len({x, y} & {a, b}):
                    continue
                # does segment xy properly cross ab?
                if not (_orient(q, a, b, x) * _orient(q, a, b, y) < 0 and _orient(q, x, y, a) * _orient(q, x, y, b) < 0):
                    continue
                j = em[(y, x)]
                u = [v for v in tris[i] if v not in (x, y)][0]
                w = [v for v in tris[j] if v not in (x, y)][0]
                # the quad u-x-w-y must be convex for the flip
                if _orient(q, u, w, x) * _orient(q, u, w, y) >= 0:
                    continue
                t1, t2 = (u, x, w), (w, y, u)
                if _orient(q, *t1) < 0:
                    t1 = (u, w, x)
                if _orient(q, *t2) < 0:
                    t2 = (w, u, y)
                tris[i], tris[j] = t1, t2
                em = edge_map()
                flipped = True
                break
            if not flipped:
                return None
        if (a, b) not in em and (b, a) not in em:
            return None
    return np.asarray(tris, dtype=np.int64)


def trimmed(face_info, edges, periods, grid=True):
    """(uv, xyz, triangles CCW in (u, v)) of a face from its boundary loops, with the interior nodes of a grid
    scaled by the face's steps (none on a flat face), or None if the boundary can't be recovered."""
    from scipy.spatial import Delaunay
    uvs, xyzs, segs, offset = [], [], [], 0
    for loop in face_info.loops:
        uv, xyz, _ = loop_nodes(loop, edges, periods)
        n = len(uv)
        uvs.append(uv)
        xyzs.append(xyz)
        segs.extend((offset + k, offset + (k + 1) % n) for k in range(n))
        offset += n
    uv, xyz = np.concatenate(uvs), np.concatenate(xyzs)
    scale = np.array(face_info.scale, dtype=np.float64)
    if grid:
        scale = scale / np.array(face_info.step)  # the grid step is 1 in both directions
    q = uv * scale
    segs = np.asarray(segs, dtype=np.int64)
    segments = q[segs]
    nb = len(q)
    index = None
    if grid:
        # the grid starts on the face's (u, v) box and fits it with whole cells (plan() sized the steps so), so
        # boundaries along iso-lines carry exactly the grid's nodes; those boundary nodes stand in for the grid's
        lo = np.asarray(face_info.box[0], dtype=np.float64) * scale
        hi = np.asarray(face_info.box[1], dtype=np.float64) * scale
        cols = lo[0] + np.arange(max(1, round(hi[0] - lo[0])) + 1, dtype=np.float64)
        rows = lo[1] + np.arange(max(1, round(hi[1] - lo[1])) + 1, dtype=np.float64)
        if len(cols) * len(rows) > 400000:
            return None
        gx, gy = np.meshgrid(cols, rows, indexing="ij")
        g = np.column_stack([gx.ravel(), gy.ravel()])
        from scipy.spatial import cKDTree
        dist, near = cKDTree(q).query(g)
        on_boundary = dist < 1e-6
        keep = ~on_boundary & _inside(g, segments)
        keep[keep] = _distance_to(g[keep], segments) > _MARGIN
        index = np.full(len(g), -1, dtype=np.int64)
        index[on_boundary] = near[on_boundary]
        index[keep] = nb + np.arange(keep.sum())
        index = index.reshape(len(cols), len(rows))
        q = np.concatenate([q, g[keep]])
    try:
        tri = Delaunay(q).simplices
    except Exception:
        return None
    tri = _recover(q, tri, segs)
    if tri is None:
        return None
    tri = tri[_inside(q[tri].mean(axis=1), segments)]
    uv_all = q / scale
    if index is not None:
        surf = face_info.surf
        grid_xyz = np.array([_xyz(surf.Value(float(u), float(v))) for u, v in uv_all[nb:]], dtype=np.float64)
        xyz_all = np.concatenate([xyz, grid_xyz.reshape(-1, 3)])
        tri = _regular_cells(tri, index, xyz_all, q[:nb])
    else:
        xyz_all = xyz
    if not len(tri):
        return None
    area = _area2d(q, tri)
    tri = np.where((area < 0)[:, None], tri[:, ::-1], tri)
    return uv_all, xyz_all, tri


def _regular_cells(tri, index, xyz, boundary_q):
    """Grid cells whose four sides are edges of the triangulation (so exactly two triangles fill them) get the
    same diagonal rule as a structured grid: Delaunay picks co-circular cells' diagonals by round-off."""
    a, b, c, d = index[:-1, :-1], index[1:, :-1], index[1:, 1:], index[:-1, 1:]
    full = (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0)
    if not full.any():
        return tri
    edges = set()
    for x, y, z in tri:
        edges.update(((int(x), int(y)), (int(y), int(x)), (int(y), int(z)), (int(z), int(y)),
                      (int(z), int(x)), (int(x), int(z))))
    cells = [(i, j) for i, j in zip(*np.nonzero(full))
             if all((int(p), int(r)) in edges for p, r in ((a[i, j], b[i, j]), (b[i, j], c[i, j]),
                                                           (c[i, j], d[i, j]), (d[i, j], a[i, j])))]
    if not cells:
        return tri
    by_vertex = {}
    for i, j in cells:
        cset = frozenset((int(a[i, j]), int(b[i, j]), int(c[i, j]), int(d[i, j])))
        for v in cset:
            by_vertex.setdefault(v, []).append(cset)
    in_cell = np.array([any(set(map(int, t)) <= cset for cset in by_vertex.get(int(t[0]), ())) for t in tri])
    new = [_cells(index[i:i + 2, j:j + 2], xyz) for i, j in cells]
    return np.concatenate([tri[~in_cell]] + new)


# -- the plan: every face's kind and steps, every edge's count ----------------------------------------------------

@dataclass
class Plan:
    faces: list          # FaceInfo per face (face_map order)
    edges: list          # EdgeInfo per edge (edge_map order)
    unmatched: list      # four-sided faces whose opposite sides couldn't be matched (meshed as trimmed grids)


def plan(faces, edge_list, kinds, ring_counts, lin_defl, ang_defl):
    """kinds[f]: "plane", "revolution", "self" (meshed without edges) or "curved"; ring_counts[f]: node count of
    a revolution's circles (ADR 0005). Decides each curved face's layout and every edge's discretization."""
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
    emap = ShapeMap()
    for e in edge_list:
        emap.Add(e)
    edges = [edge_info(e) for e in edge_list]
    infos, pairs = [], []
    for f, (face, kind) in enumerate(zip(faces, kinds)):
        surf = BRepAdaptor_Surface(face)
        fi = FaceInfo(face_loops(face, lambda e: emap.FindIndex(e) - 1), surf, kind == "plane")
        fi.kind = {"plane": "plane", "revolution": "revolution", "self": "other"}.get(kind, "grid")
        if fi.kind in ("grid",) and fi.loops:
            lo, hi = _loop_uv_box(fi.loops)
            fi.box = (lo, hi)
            fi.step, fi.scale = surface_steps(surf, (lo, hi), lin_defl, ang_defl)
            fi.sides = four_sides(fi, edges)
            if fi.sides is not None:
                fi.kind = "tfi"
            else:
                fi.step = _fitted(fi, _capped(fi.step))
        infos.append(fi)
    for info in edges:
        info.own = own_count(info, lin_defl, ang_defl)
        info.count = info.own
    for f, fi in enumerate(infos):
        if fi.kind in ("tfi", "grid"):
            for loop in fi.loops:
                for use in loop:
                    e = edges[use.edge]
                    e.count = max(e.count, face_need(fi, use, e))
        elif fi.kind == "revolution":
            circles = [use.edge for loop in fi.loops for use in loop
                       if not edges[use.edge].degenerate and not _is_seam(use, fi)]
            for e in circles:
                edges[e].count = max(edges[e].count, ring_counts[f])
            if len(circles) == 2:
                pairs.append(([circles[0]], [circles[1]]))
    for fi in infos:
        if fi.kind == "tfi":
            loop = fi.loops[0]
            ids = [[loop[k].edge for k in side] for side in fi.sides]
            pairs.append((ids[0], ids[2]))
            pairs.append((ids[1], ids[3]))
    unmatched = equalize_pairs(pairs, edges)
    bad = set(map(frozenset, (map(tuple, p) for p in unmatched)))
    left = []
    for fi in infos:
        if fi.kind == "tfi":
            loop = fi.loops[0]
            ids = [tuple(loop[k].edge for k in side) for side in fi.sides]
            if frozenset((ids[0], ids[2])) in bad or frozenset((ids[1], ids[3])) in bad:
                fi.kind, fi.step = "grid", _fitted(fi, _capped(fi.step))
                left.append(fi)
    for info in edges:
        build_points(info)
    return Plan(infos, edges, left)


def _capped(step):
    """A trimmed grid's steps: the band along its boundary has triangles up to about 1.4 cells across, so the
    steps shrink by sqrt(2) (their chords sag half as much); a straight direction at most _STRAIGHT_ASPECT times
    the other."""
    su, sv = (x / math.sqrt(2) for x in step)
    if math.isfinite(su) and not math.isfinite(sv):
        return su, _STRAIGHT_ASPECT * su
    if math.isfinite(sv) and not math.isfinite(su):
        return _STRAIGHT_ASPECT * sv, sv
    return su, sv


def _fitted(fi, step):
    """Steps shrunk so that whole cells fit the face's (u, v) box (the grid then meets iso-line boundaries on
    their nodes); a straight direction without a finite step: the whole box."""
    extent = (np.asarray(fi.box[1]) - np.asarray(fi.box[0])) * np.asarray(fi.scale)
    out = []
    for e, st in zip(extent, step):
        if not math.isfinite(st) or st >= e:
            out.append(max(float(e), 1e-9))
        else:
            out.append(float(e) / math.ceil(e / st - 1e-9))
    return tuple(out)


def _is_seam(use, fi):
    return any(u.edge == use.edge for loop in fi.loops for u in loop if u is not use)


def equalize_pairs(pairs, edges):
    """Raise edge counts until both lists of every pair carry as many intervals in total (edges are shared, so
    this runs along chains of faces); the extra intervals go to the edge with the longest ones. Returns the pairs
    it couldn't match within the round limit."""
    def total(ids):
        return sum(edges[i].count for i in ids)
    for _ in range(_EQUALIZE_ROUNDS):
        changed = False
        for a, b in pairs:
            ta, tb = total(a), total(b)
            if ta == tb:
                continue
            low = a if ta < tb else b
            for _ in range(abs(ta - tb)):
                e = max(low, key=lambda i: (edges[i].length / edges[i].count, -i))
                edges[e].count += 1
            changed = True
        if not changed:
            return []
    return [(a, b) for a, b in pairs if total(a) != total(b)]


def ring(use, fi, edges, u0):
    """A revolution's boundary circle as (u values ascending within [u0, u0 + 2pi), points), the closing node
    dropped."""
    uv, xyz = use_nodes(use, edges)
    uv, xyz = uv[:-1], xyz[:-1]
    u = u0 + np.mod(uv[:, 0] - u0, 2 * math.pi)
    order = np.argsort(u)
    return u[order], xyz[order], float(np.median(uv[:, 1]))


def mesh_face(fi, edges, periods):
    """(uv, xyz, triangles CCW in (u, v)) of a planned face, or None if it couldn't be meshed."""
    if fi.kind == "plane":
        return trimmed(fi, edges, periods, grid=False)
    if fi.kind == "tfi":
        out = tfi(fi, edges, periods)
        if out is not None:
            return out
        fi.step = _fitted(fi, _capped(fi.step))
        return trimmed(fi, edges, periods)
    if fi.kind == "grid":
        return trimmed(fi, edges, periods)
    return None
