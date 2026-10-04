"""OCP helpers for the worker: validity, volume, face numbering and tessellation with BRep face IDs.

Faces are numbered with TopExp.MapShapes (deterministic for a given shape): brep_face_id = 0-based index.

Tessellation (ADR 0010): every edge is discretized once and every face meshed from those nodes (meshing.py), so
neighbouring faces weld exactly: curved faces with four corners as structured grids, other curved faces as grids
trimmed by their boundary, flat faces from their boundary, then shown as one polygon or as convex pieces with
collars of radial quads around curved holes (ADR 0008 and its addendum). A full face of revolution (torus, cylinder or cone
bounded only by its seam, poles and v-iso circles) is a structured grid of staggered rings (ADR 0005), its
boundary rings taken from the shared edge nodes. A full sphere has no real boundary: it becomes a geodesic grid
(an octahedron subdivided and projected onto it), which has neither the thin pole triangles nor the seam of a
latitude-longitude grid.
"""
import math
from dataclasses import dataclass

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d, BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.ElSLib import ElSLib
from OCP.BRepTools import BRepTools
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as AncestorMap
from OCP.GeomAbs import (GeomAbs_Circle, GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Ellipse, GeomAbs_Line, GeomAbs_Plane,
                         GeomAbs_Sphere, GeomAbs_Torus)
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt, gp_Vec

import meshing

_TAU = 2 * math.pi
_REVOLUTION = (GeomAbs_Sphere, GeomAbs_Torus, GeomAbs_Cylinder, GeomAbs_Cone)
_WELD_DECIMALS = 7  # millimetres: coincident nodes (seam and pole copies) are closer than 1e-7 mm


def _map(shape, kind):
    m = ShapeMap()
    TopExp.MapShapes_s(shape, kind, m)
    return m


def face_map(shape):
    m = _map(shape, TopAbs_FACE)
    return [TopoDS.Face(m.FindKey(i)) for i in range(1, m.Extent() + 1)]


def edge_map(shape):
    m = _map(shape, TopAbs_EDGE)
    return [TopoDS.Edge(m.FindKey(i)) for i in range(1, m.Extent() + 1)]


def plane_normal(face):
    """(direction, point on the plane) of a planar face, the direction pointing out of the solid: the plane's
    frame axis, flipped for an indirect frame (a mirrored solid's planes) and for a reversed face."""
    pos = BRepAdaptor_Surface(face).Plane().Position()
    d = pos.Direction()
    n = np.array([d.X(), d.Y(), d.Z()])
    if not pos.Direct():
        n = -n  # an indirect frame: the surface's natural normal (X x Y) is -Direction
    if face.Orientation() == TopAbs_REVERSED:
        n = -n
    n[np.abs(n) < 1e-15] = 0.0  # no -0.0 / 1e-17 components on axis-aligned faces
    o = pos.Location()
    return n, np.array([o.X(), o.Y(), o.Z()])


def check(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return {"valid": BRepCheck_Analyzer(shape).IsValid(), "volume": props.Mass(),
            "faces": _map(shape, TopAbs_FACE).Extent(), "solids": _map(shape, TopAbs_SOLID).Extent()}


def _step(lin_defl, ang_defl, radius):
    """Angle between grid nodes on a circle of `radius`: a staggered triangle of side radius * step deviates
    from the surface by about radius * step**2 / 6 at its centre."""
    return min(ang_defl, math.sqrt(6 * lin_defl / radius))


class _Revolution:
    """A full face of revolution: u closed (0..2pi), each v end a pole, a circle, or (torus) the v seam."""

    def __init__(self, face, surf, ends):
        self.face, self.surf, self.kind = face, surf, surf.GetType()
        self.u0, self.v0, self.v1 = surf.FirstUParameter(), surf.FirstVParameter(), surf.LastVParameter()
        self.ends = ends  # (v0 end, v1 end): "pole", "circle" or "seam"

    def radius(self, v):
        s = self.surf
        if self.kind == GeomAbs_Cylinder:
            return s.Cylinder().Radius()
        if self.kind == GeomAbs_Cone:
            c = s.Cone()
            return abs(c.RefRadius() + v * math.sin(c.SemiAngle()))
        if self.kind == GeomAbs_Sphere:
            return s.Sphere().Radius()
        t = s.Torus()
        return t.MajorRadius() + t.MinorRadius()

    def max_circle_radius(self):
        return max(self.radius(self.v0), self.radius(self.v1))


def _revolution(face):
    """The face as a _Revolution, or None if it is trimmed (any edge that is not a seam, a pole or a v-iso)."""
    surf = BRepAdaptor_Surface(face)
    if surf.GetType() not in _REVOLUTION or not surf.IsUPeriodic():
        return None
    if abs(surf.LastUParameter() - surf.FirstUParameter() - _TAU) > 1e-9:
        return None
    v0, v1 = surf.FirstVParameter(), surf.LastVParameter()
    ends = ["seam", "seam"] if surf.IsVPeriodic() else [None, None]
    edges = _map(face, TopAbs_EDGE)
    for i in range(1, edges.Extent() + 1):
        edge = TopoDS.Edge(edges.FindKey(i))
        if BRep_Tool.IsClosed_s(edge, face):
            continue  # a seam
        pcurve = BRepAdaptor_Curve2d(edge, face)
        if pcurve.GetType() != GeomAbs_Line or abs(pcurve.Line().Direction().Y()) > 1e-9:
            return None
        v = pcurve.Value(pcurve.FirstParameter()).Y()
        end = 0 if abs(v - v0) < 1e-9 else 1 if abs(v - v1) < 1e-9 else None
        if end is None or ends[end] is not None:
            return None
        ends[end] = "pole" if BRep_Tool.Degenerated_s(edge) else "circle"
    if None in ends:
        return None
    return _Revolution(face, surf, tuple(ends))


def _triangulation(face):
    loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(face, loc)
    if tri is None:
        return None, None
    trsf = loc.Transformation()
    nodes = [tri.Node(i).Transformed(trsf) for i in range(1, tri.NbNodes() + 1)]
    pts = np.array([(q.X(), q.Y(), q.Z()) for q in nodes], dtype=np.float64).reshape(-1, 3)
    return tri, pts


def _rings(rev, n, lin_defl, ang_defl):
    """The grid rings from v0 to v1 as (v, node count); a pole end is a ring of one node. Each row is about as
    tall as a triangle side is wide, so the triangles stay near-equilateral."""
    v0, v1 = rev.v0, rev.v1
    if rev.kind == GeomAbs_Torus:
        rows = math.ceil((v1 - v0) / (_step(lin_defl, ang_defl, rev.surf.Torus().MinorRadius())
                                      * math.sqrt(3) / 2))
        rows = 8 * math.ceil(rows / 8)  # unstaggered rings at 0, 90, 180, 270 degrees: exact extents
        return [(v0 + (v1 - v0) * k / rows, n) for k in range(rows)]
    # Cylinder or cone. Between two circles the generatrix is straight: one row of triangles is exact along it
    # (a normal doesn't change along a generatrix), like Blender's own cylinder. Towards an apex, rows follow the
    # local node spacing and the node count halves as the radius shrinks, so the tip isn't a fan of slivers.
    forward = rev.ends[0] == "circle"
    start, stop = (v0, v1) if forward else (v1, v0)
    if rev.ends[1 if forward else 0] == "circle":
        return [(v0, n), (v1, n)]
    spacing0 = _TAU * rev.radius(start) / n
    rings, v, k = [(start, n)], start, n
    while True:
        h = _TAU * max(rev.radius(v), 1e-12) / k * math.sqrt(3) / 2
        if abs(stop - v) < 1.5 * h or k <= 3:
            break
        v += h if forward else -h
        # Halve while the nodes crowd (spacing well under the base ring's) and the coarser ring still meets the
        # linear deflection; the angular one would keep every ring at the base count all the way to the apex.
        while (k > 3 and _TAU * rev.radius(v) / k < 0.45 * spacing0
               and _TAU / math.ceil(k / 2) <= math.sqrt(6 * lin_defl / max(rev.radius(v), 1e-12))):
            k = max(3, math.ceil(k / 2))
        rings.append((v, k))
    rings.append((stop, 1))
    return rings if forward else rings[::-1]


def _zip(a, b, ua, ub, out):
    """Triangles between ring a (lower v) and ring b (upper v), both closed around u; counter-clockwise in
    (u, v). A ring of one index is a pole. ua/ub: the rings' u values (ascending, within one period)."""
    if len(a) == 1:
        out.extend((a[0], b[(j + 1) % len(b)], b[j]) for j in range(len(b)))
        return
    if len(b) == 1:
        out.extend((a[i], a[(i + 1) % len(a)], b[0]) for i in range(len(a)))
        return
    # Start ring b at its last node at or before a[0] (cyclically), unwrap both rings, walk them once around.
    ua, ub = np.asarray(ua, dtype=np.float64), np.asarray(ub, dtype=np.float64)
    back = np.mod(ua[0] - ub, _TAU)  # how far each b node lies before a[0]
    j0 = int(np.argmin(back))
    order = [(j0 + m) % len(b) for m in range(len(b))]
    bi = [b[j] for j in order]
    bu = ua[0] - back[j0] + np.mod(ub[order] - ub[j0], _TAU)
    au = np.append(ua[0] + np.mod(ua - ua[0], _TAU), ua[0] + _TAU)
    bu = np.append(bu, bu[0] + _TAU)
    i = j = 0
    na, nb = len(a), len(b)
    while i < na or j < nb:
        if j == nb or (i < na and (au[i] + au[i + 1]) / 2 <= (bu[j] + bu[j + 1]) / 2):
            out.append((a[i % na], a[(i + 1) % na], bi[j % nb]))
            i += 1
        else:
            out.append((a[i % na], bi[(j + 1) % nb], bi[j % nb]))
            j += 1


def _structured(rev, ends, lin_defl, ang_defl):
    """Staggered-ring grid of a face of revolution: (points, triangles), triangles oriented like the surface.
    ends: {0 or 1 (the v0 or v1 end): (u values ascending, points)} for each boundary circle, from the shared
    edge nodes (meshing.ring)."""
    s = rev.surf
    if ends:
        n = max(len(u) for u, _ in ends.values())
    else:  # torus: nodes on the axes (a multiple of 4) for exact extents
        n = 4 * math.ceil(_TAU / _step(lin_defl, ang_defl, rev.radius(rev.v0)) / 4)
    rings_u, rings_p = [], []
    rings = _rings(rev, n, lin_defl, ang_defl)
    for k, (v, count) in enumerate(rings):
        end = 0 if k == 0 else 1 if k == len(rings) - 1 and rev.ends[1] != "seam" else None
        if end is not None and rev.ends[end] == "circle":
            u, p = ends[end]
        elif count == 1:
            q = s.Value(rev.u0, v)
            u, p = np.array([rev.u0]), np.array([[q.X(), q.Y(), q.Z()]])
        else:
            u = rev.u0 + (np.arange(count) + 0.5 * (k % 2)) * _TAU / count
            p = np.array([(q.X(), q.Y(), q.Z()) for q in (s.Value(x, v) for x in u)])
        rings_u.append(u)
        rings_p.append(p)
    starts = np.cumsum([0] + [len(p) for p in rings_p])
    idx = [list(range(starts[k], starts[k + 1])) for k in range(len(rings_p))]
    tris = []
    for k in range(len(idx) - 1):
        _zip(idx[k], idx[k + 1], rings_u[k], rings_u[k + 1], tris)
    if rev.ends[1] == "seam":
        _zip(idx[-1], idx[0], rings_u[-1], rings_u[0], tris)
    return np.concatenate(rings_p), np.asarray(tris, dtype=np.int32).reshape(-1, 3)


def _octahedron():
    """Unit octahedron: its vertices on the sphere's axes give the mesh the sphere's exact extents."""
    v = np.array([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)], dtype=np.float64)
    f = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
    return v, f


def _geodesic_unit(freq):
    """Unit geodesic sphere: each octahedron face split into freq**2 triangles, projected; outward triangles."""
    corners, faces = _octahedron()
    i, j = (x.ravel() for x in np.meshgrid(np.arange(freq + 1), np.arange(freq + 1), indexing="ij"))
    keep = i + j <= freq
    i, j = i[keep], j[keep]
    index = np.full((freq + 2, freq + 2), -1)
    index[i, j] = np.arange(len(i))
    ti, tj = (x.ravel() for x in np.meshgrid(np.arange(freq), np.arange(freq), indexing="ij"))
    up = ti + tj < freq
    down = ti + tj < freq - 1
    local = np.concatenate([
        np.stack([index[ti[up], tj[up]], index[ti[up] + 1, tj[up]], index[ti[up], tj[up] + 1]], 1),
        np.stack([index[ti[down] + 1, tj[down]], index[ti[down] + 1, tj[down] + 1], index[ti[down], tj[down] + 1]], 1)])
    abc = corners[np.asarray(faces)]  # (8, 3 corners, xyz)
    w = np.stack([freq - i - j, i, j], 1) / freq  # barycentric weights of the grid nodes
    pts = np.einsum("nk,fkd->fnd", w, abc).reshape(-1, 3)
    tris = (local[None, :, :] + (np.arange(len(faces)) * len(i))[:, None, None]).reshape(-1, 3)
    unit = pts / np.linalg.norm(pts, axis=1, keepdims=True)
    _, first, inv = np.unique(np.round(unit, 12), axis=0, return_index=True, return_inverse=True)
    unit, t = unit[first], inv.ravel()[tris]
    normal = np.cross(unit[t[:, 1]] - unit[t[:, 0]], unit[t[:, 2]] - unit[t[:, 0]])
    outward = np.einsum("ij,ij->i", normal, unit[t].sum(axis=1)) > 0
    return unit, np.where(outward[:, None], t, t[:, ::-1])


def _geodesic(rev, lin_defl, ang_defl):
    """A full sphere as a geodesic grid, triangles oriented like the surface's natural normal. The frequency is
    the lowest whose flat triangles all lie within lin_defl of the sphere (the deviation of a triangle is the
    radius minus its plane's distance from the centre) and whose edges span at most ang_defl."""
    sph = rev.surf.Sphere()
    radius = sph.Radius()
    # The projection stretches the triangles at the middle of an octahedron face: start near the answer.
    freq = max(1, math.ceil(math.pi / 2 * 1.3 / _step(lin_defl, ang_defl, radius)))
    while True:
        unit, t = _geodesic_unit(freq)
        a, b, c = unit[t[:, 0]], unit[t[:, 1]], unit[t[:, 2]]
        n = np.cross(b - a, c - a)
        plane = np.abs(np.einsum("ij,ij->i", n, a)) / np.linalg.norm(n, axis=1)
        edge = np.arccos(np.clip(np.einsum("ij,ij->i", a, b), -1, 1))
        if radius * (1 - plane.min()) <= lin_defl and edge.max() <= ang_defl * 1.001:
            break
        freq += 1
    pos = sph.Position()
    frame = np.array([[d.X(), d.Y(), d.Z()] for d in (pos.XDirection(), pos.YDirection(), pos.Direction())])
    c = sph.Location()
    p = np.array([c.X(), c.Y(), c.Z()]) + radius * unit @ frame
    # The triangles are outward: flip them if the surface's natural normal (Su x Sv) points inward.
    q, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    rev.surf.D1(rev.u0 + 0.3, 0.2, q, du, dv)
    if du.Crossed(dv).Dot(gp_Vec(c, q)) < 0:
        t = t[:, ::-1]
    return p, np.ascontiguousarray(t, dtype=np.int32)


def _weld(pts, t):
    """Merge coincident nodes (BRepMesh's seam and pole copies); drop the triangles that collapse. Returns the
    kept nodes' indices into `pts` too."""
    _, first, inv = np.unique(np.round(pts, _WELD_DECIMALS), axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    t = inv[t]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    return pts[first], t, first


def _unit(a):
    length = np.linalg.norm(a, axis=1, keepdims=True)
    return np.divide(a, length, out=np.full_like(a, np.nan), where=length > 1e-12)


def _vec(d):
    return np.array([d.X(), d.Y(), d.Z()])


def _surface_normals(face, pts, uv=None):
    """Unit normals of face's exact surface at points `pts` (on it), up to sign: closed forms for planes,
    cylinders, spheres and tori; the surface's derivatives at the (u, v) parameters otherwise (`uv`, or
    projected for a cone). NaN where the normal is undefined (a pole, an apex)."""
    surf = BRepAdaptor_Surface(face)
    kind = surf.GetType()
    if kind == GeomAbs_Plane:
        return np.tile(_vec(surf.Plane().Axis().Direction()), (len(pts), 1))
    if kind in (GeomAbs_Cylinder, GeomAbs_Sphere, GeomAbs_Torus):
        geom = {GeomAbs_Cylinder: surf.Cylinder, GeomAbs_Sphere: surf.Sphere, GeomAbs_Torus: surf.Torus}[kind]()
        axis = geom.Position()
        c, d = _vec(axis.Location()), _vec(axis.Direction())
        w = pts - c
        if kind == GeomAbs_Sphere:
            return _unit(w)
        radial = w - np.outer(w @ d, d)
        if kind == GeomAbs_Cylinder:
            return _unit(radial)
        return _unit(w - _unit(radial) * geom.MajorRadius())
    if uv is None and kind == GeomAbs_Cone:
        cone = surf.Cone()
        uv = [ElSLib.Parameters_s(cone, gp_Pnt(*p)) for p in pts]
    out = np.full((len(pts), 3), np.nan)
    if uv is None:
        return out
    for i, (u, v) in enumerate(uv):
        props = BRepLProp_SLProps(surf, u, v, 1, 1e-9)
        if props.IsNormalDefined():
            out[i] = _vec(props.Normal())
    return out


def _oriented(normals, pts, t):
    """Normals turned to the side the triangles face (they are the face's outside, orientation included);
    undefined ones (NaN) replaced by the average of their triangles' normals."""
    tri_n = np.cross(pts[t[:, 1]] - pts[t[:, 0]], pts[t[:, 2]] - pts[t[:, 0]])
    acc = np.zeros_like(pts)
    for k in range(3):
        np.add.at(acc, t[:, k], tri_n)
    ok = ~np.isnan(normals[:, 0])
    if ok.any() and np.einsum("ij,ij->", normals[ok], acc[ok]) < 0:
        normals = -normals
    normals = np.where(ok[:, None], normals, _unit(acc))
    return np.nan_to_num(normals)


def face_planes(shape):
    """Per face (face_map order): the exact plane of a flat face as (nx, ny, nz, d), the normal pointing out of
    the solid and d = n . p for its points (millimetres, float64); NaN for a curved face. Tools place solids
    on these instead of the float32 display mesh, whose noise would leave skins and slivers in booleans."""
    out = np.full((len(face_map(shape)), 4), np.nan)
    for fid, face in enumerate(face_map(shape)):
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() != GeomAbs_Plane:
            continue
        n, o = plane_normal(face)
        out[fid] = (*n, float(n @ o) + 0.0)
    return out


SNAP_VERTEX, SNAP_MIDPOINT, SNAP_CENTRE = 0, 1, 2


def snap_points(shape):
    """Points a sketch can snap to, as (x, y, z, kind) rows (millimetres, part frame, float64): the vertices, the
    midpoint of every edge (by parameter: a straight edge's middle, an arc's middle point) and the centres of
    circular and elliptic edges. Exact, so a point snapped to them is written without the display mesh's float32
    noise."""
    rows, seen = [], set()

    def add(p, kind):
        key = (round(p.X(), 6), round(p.Y(), 6), round(p.Z(), 6))
        if key not in seen:
            seen.add(key)
            rows.append((p.X() + 0.0, p.Y() + 0.0, p.Z() + 0.0, kind))

    m = _map(shape, TopAbs_VERTEX)
    for i in range(1, m.Extent() + 1):
        add(BRep_Tool.Pnt_s(TopoDS.Vertex(m.FindKey(i))), SNAP_VERTEX)
    for edge in edge_map(shape):
        if BRep_Tool.Degenerated_s(edge):
            continue
        curve = BRepAdaptor_Curve(edge)
        add(curve.Value(0.5 * (curve.FirstParameter() + curve.LastParameter())), SNAP_MIDPOINT)
        kind = curve.GetType()
        if kind == GeomAbs_Circle:
            add(curve.Circle().Location(), SNAP_CENTRE)
        elif kind == GeomAbs_Ellipse:
            add(curve.Ellipse().Location(), SNAP_CENTRE)
    return np.array(rows, dtype=np.float64).reshape(-1, 4)


def _self_contained(rev):
    """A full sphere or torus shares no circle with another face: its grid needs nothing from BRepMesh."""
    return rev is not None and rev.kind in (GeomAbs_Sphere, GeomAbs_Torus)


def tessellate(shape, lin_defl=0.1, ang_defl=0.3):
    """Vertices are not shared between faces: sharp edges between BRep faces, unambiguous face map."""
    return tessellate_with_normals(shape, lin_defl, ang_defl)[:3]


def tessellate_with_normals(shape, lin_defl=0.1, ang_defl=0.3):
    """tessellate() plus each vertex's exact surface normal (float32, unit, on the side the face's triangles
    face): Blender shades with these (custom normals) instead of averaging the triangles around a vertex,
    which goes wrong on long thin triangles.

    Every edge is discretized once and every face meshed from those nodes (ADR 0010, meshing.py); full faces of
    revolution keep their structured grids (ADR 0005). A face that can't be meshed from its boundary falls back
    to BRepMesh (reported on stderr: the mesh is open along that face's edges)."""
    BRepTools.Clean_s(shape)
    faces = face_map(shape)
    revolutions = [_revolution(face) for face in faces]
    # BRepMesh (ADR 0005's meshes, checked by the maintainer) turns a curve by at most half its angular
    # deflection per segment: a 10 mm circle at 0.3 rad got 42 segments. Edges and the grids meeting them keep
    # that density (interpolated normals within 1.4 degrees on a one-row cone side).
    seg_angle = ang_defl / 2
    kinds, rings = [], []
    for face, rev in zip(faces, revolutions):
        if _self_contained(rev):
            kinds.append("self")
        elif rev is not None:
            kinds.append("revolution")
        elif BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane:
            kinds.append("plane")
        else:
            kinds.append("curved")
        # a multiple of 4: nodes on the axes (the circle starts at its seam vertex) give the exact extents
        rings.append(4 * math.ceil(_TAU / _step(lin_defl, seg_angle, rev.max_circle_radius()) / 4)
                     if rev is not None and "circle" in rev.ends else 1)
    edges = edge_map(shape)
    if not _plausible(shape, edges):
        raise RuntimeError("the result has an edge far longer than the part itself (a known OCCT failure, seen after "
                           "fillets): try another radius or size")
    layout = meshing.plan(faces, edges, kinds, rings, lin_defl, seg_angle)
    fallback = None
    verts, tris, tri_face, normals, offset = [], [], [], [], 0
    for fid, (face, rev, fi) in enumerate(zip(faces, revolutions, layout.faces)):
        uv = None
        if rev is not None and rev.kind == GeomAbs_Sphere and _self_contained(rev):
            pts, t = _geodesic(rev, lin_defl, ang_defl)
        elif rev is not None and rev.kind == GeomAbs_Torus and _self_contained(rev):
            pts, t = _structured(rev, {}, lin_defl, ang_defl)
        elif rev is not None:
            ends = {}
            for loop in fi.loops:
                for use in loop:
                    if layout.edges[use.edge].degenerate or meshing._is_seam(use, fi):
                        continue
                    u, p, v = meshing.ring(use, fi, layout.edges, rev.u0)
                    ends[0 if abs(v - rev.v0) <= abs(v - rev.v1) else 1] = (u, p)
            pts, t = _structured(rev, ends, lin_defl, ang_defl)
        else:
            surf = fi.surf
            periods = (surf.UPeriod() if surf.IsUPeriodic() else None, surf.VPeriod() if surf.IsVPeriodic() else None)
            out = meshing.mesh_face(fi, layout.edges, periods)
            if out is not None:
                uv_all, pts, t = out
                t = t.astype(np.int32)
            else:
                import sys
                print(f"BlendSolid: face {fid} couldn't be meshed from its edges: BRepMesh fallback (the mesh is "
                      "open along its edges)", file=sys.stderr)
                if fallback is None:
                    fallback = True
                    BRepMesh_IncrementalMesh(shape, lin_defl, False, ang_defl, True)
                tri, pts = _triangulation(face)
                if tri is None:
                    raise RuntimeError(f"face {fid} has no triangulation")
                t = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)],
                             dtype=np.int32).reshape(-1, 3) - 1
                uv_all = [(tri.UVNode(i + 1).X(), tri.UVNode(i + 1).Y()) for i in range(len(pts))]
                t = _uv_ccw(t, np.asarray(uv_all))
            pts, t, kept = _weld(pts, t)
            uv = [tuple(uv_all[i]) for i in kept]
        if face.Orientation() == TopAbs_REVERSED:
            t = t[:, ::-1]
        normals.append(_oriented(_surface_normals(face, pts, uv), pts, t))
        verts.append(pts)
        tris.append(t + offset)
        tri_face.append(np.full(len(t), fid, dtype=np.int32))
        offset += len(pts)
    if not verts:
        empty = np.zeros((0, 3), np.float32)
        return empty, np.zeros((0, 3), np.int32), np.zeros(0, np.int32), empty
    return (np.concatenate(verts).astype(np.float32), np.ascontiguousarray(np.concatenate(tris), dtype=np.int32),
            np.concatenate(tri_face), np.concatenate(normals).astype(np.float32))


def _plausible(shape, edges):
    """False if an edge is far longer than the part (measured between its vertices): OCCT's fillets sometimes
    leave such edges (a 335 m edge on a 1 m part, its pcurve wound thousands of times), which neither our grids
    nor BRepMesh can follow in reasonable time; the part reports an error instead of hanging the worker."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_AbscissaPoint
    vertices = _map(shape, TopAbs_VERTEX)
    pts = np.array([_vec(BRep_Tool.Pnt_s(TopoDS.Vertex(vertices.FindKey(i))))
                    for i in range(1, vertices.Extent() + 1)]).reshape(-1, 3)
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    mass = props.Mass()
    if mass < 0:
        return False  # inside out: the same broken fillet results have a negative volume
    # the part's size: its vertices' extent, the side of a cube of its volume (a torus has one vertex), or twice its
    # material's RMS distance from its centre of mass (a revolved ring's vertices all sit on its seam). Not a
    # bounding box: the broken edges themselves would enlarge it.
    inertia = props.MatrixOfInertia()
    trace = inertia.Value(1, 1) + inertia.Value(2, 2) + inertia.Value(3, 3)
    diagonal = max(float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))) if len(pts) else 0.0, mass ** (1 / 3),
                   2 * math.sqrt(max(trace, 0.0) / (2 * mass)) if mass > 0 else 0.0)
    for e in edges:
        if not BRep_Tool.Degenerated_s(e) and GCPnts_AbscissaPoint.Length_s(BRepAdaptor_Curve(e)) > 20 * diagonal + 1.0:
            return False
    return True


def _uv_ccw(t, uv):
    a, b, c = uv[t[:, 0]], uv[t[:, 1]], uv[t[:, 2]]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    return t if area.sum() >= 0 else t[:, ::-1]


# -- the display mesh: faces welded along BRep edges (ADR 0008) ---------------------------------------------------

_DISPLAY_WELD = 1e-6  # mm: boundary nodes of neighbouring faces are the same BRepMesh edge nodes
_DISPLAY_WELD_OPEN = 1e-5  # mm: second pass for pairs the rounding grid split
_SHARP = 1e-3  # radians between the two faces' normals at an edge: below, the faces are tangent (smooth)


@dataclass
class DisplayMesh:
    verts: np.ndarray           # (n, 3) float32, millimetres
    loops: np.ndarray           # (L,) int32: vertex of each polygon corner, polygon after polygon
    poly_sizes: np.ndarray      # (P,) int32: corners per polygon (3, or a flat face's whole boundary)
    poly_face: np.ndarray       # (P,) int32: BRep face id (face_map order)
    corner_normals: np.ndarray  # (L, 3) float32: exact surface normal at each corner
    edges: np.ndarray           # (e, 2) int32: mesh edges on BRep edges (sorted vertex pairs)
    edge_ids: np.ndarray        # (e,) int32: BRep edge id (edge_map order)
    edge_sharp: np.ndarray      # (e,) int32: 1 where the two faces meet at an angle, 0 where tangent


def _weld_all(verts, loops):
    """Merge coincident vertices across faces: the rounding grid first, then open-edge vertices it split.
    `loops` holds polygon corners as vertex indices; returns (verts, loops) with unused vertices dropped."""
    key = np.round(verts.astype(np.float64) / _DISPLAY_WELD).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    verts, loops = verts[first], inv.ravel()[loops]
    return verts, loops


def _merge_open(verts, loops, pairs):
    """Merge the vertices of open edges (one polygon only) that lie within _DISPLAY_WELD_OPEN of each other."""
    uniq, counts = np.unique(np.sort(pairs, axis=1), axis=0, return_counts=True)
    open_verts = np.unique(uniq[counts == 1])
    if not len(open_verts):
        return loops, False
    remap = np.arange(len(verts))
    p = verts[open_verts].astype(np.float64)
    for i, vi in enumerate(open_verts):
        if remap[vi] != vi:
            continue
        close = open_verts[i + 1:][np.linalg.norm(p[i + 1:] - p[i], axis=1) < _DISPLAY_WELD_OPEN]
        remap[close] = vi
    return remap[loops], True


def _boundary_loop(t):
    """The boundary of triangles `t` (one face) as one cycle of vertex indices in the triangles' winding, or None
    if it isn't a single cycle (a face with holes)."""
    directed = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    keys = {(int(a), int(b)) for a, b in directed}
    nxt = {a: b for a, b in keys if (b, a) not in keys}
    if len(nxt) < 3 or len(set(nxt.values())) != len(nxt):
        return None
    start = next(iter(nxt))
    cycle, v = [start], nxt[start]
    while v != start:
        if v not in nxt or len(cycle) > len(nxt):
            return None
        cycle.append(v)
        v = nxt[v]
    return cycle if len(cycle) == len(nxt) else None


def _convex_at(pts, loop, v, normal):
    """Does `loop` turn the same way as `normal` at vertex v (pure Python: called for every merge)?"""
    i = loop.index(v)
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = pts[loop[i - 1]], pts[v], pts[loop[(i + 1) % len(loop)]]
    ux, uy, uz, wx, wy, wz = bx - ax, by - ay, bz - az, cx - bx, cy - by, cz - bz
    return ((uy * wz - uz * wy) * normal[0] + (uz * wx - ux * wz) * normal[1]
            + (ux * wy - uy * wx) * normal[2]) >= -1e-12


_STRAIGHT = math.radians(10)  # a BRep vertex's corner turning less than this keeps an interior edge


def _straight_at(pts, loop, v, limit=_STRAIGHT):
    """Does `loop` turn by less than `limit` at vertex v?"""
    i = loop.index(v)
    a, b, c = pts[loop[i - 1]], pts[v], pts[loop[(i + 1) % len(loop)]]
    u = [y - x for x, y in zip(a, b)]
    w = [y - x for x, y in zip(b, c)]
    dot = sum(x * y for x, y in zip(u, w))
    norm = math.sqrt(sum(x * x for x in u) * sum(x * x for x in w))
    return norm > 0 and dot > norm * math.cos(limit)


_COLLINEAR = math.radians(1)  # a run of collar nodes, not an arc's nodes (an arc keeps its face point near it)
_FACE_POINT_ANGLE = math.radians(10)  # at a straight corner, least angle from its sides to the face point
# (20 until the maintainer's review of test2.blend: wedges from the corners; 10 keeps Bevel 2 mm fold-free, 6 doesn't)


def _thin_children(pts, loop):
    """Would Catmull-Clark make thin (foldable) children in polygon `loop`? Subdivision Surface puts the face
    point at the vertex average; at a nearly straight corner the child quad spans that corner, its two edge
    points (almost on the corner's line) and the face point, so a face point seen from the corner almost along
    its sides gives a sliver child that the edge points' pull toward the face point flips (measured on the
    default part: a collar's side of 9 collinear nodes in one outer polygon folded)."""
    m = len(loop)
    f = [sum(pts[v][k] for v in loop) / m for k in range(3)]
    for i in range(m):
        if not _straight_at(pts, loop, loop[i], _COLLINEAR):
            continue
        a, b = pts[loop[i - 1]], pts[loop[i]]
        u = [y - x for x, y in zip(a, b)]
        w = [y - x for x, y in zip(b, f)]
        cross = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        nu, nw = math.sqrt(sum(x * x for x in u)), math.sqrt(sum(x * x for x in w))
        if nu * nw > 0 and math.sqrt(sum(x * x for x in cross)) < math.sin(_FACE_POINT_ANGLE) * nu * nw:
            return True
    return False


def _merge_convex(t, pts, keep=()):
    """Hertel-Mehlhorn: triangles `t` of a flat face merged across their shared edges,
    shortest first, while both ends of the removed edge stay convex. A face with holes can't be one Blender
    polygon, and its triangles' short chords (ears along an arc) clamp Blender's Bevel (Clamp Overlap, its
    default, limits the whole bevel to the tightest spot); measured: the default part's 1 mm bevel removed
    0.22 mm³ with triangles, 25 with the fewest simple (concave) polygons, and 82 — the unclamped value — with
    convex ones. A vertex in `keep` (a BRep vertex) never becomes a nearly straight corner: where a bevelled
    CAD edge ends in a tangent arc (a fillet's), Bevel slides along the vertex's next edge, and the arc's first
    chord, nearly collinear, flipped polygons (measured on the default part with collars). Returns the polygons as
    vertex lists in the triangles' winding."""
    tri_n = np.cross(pts[t[:, 1]] - pts[t[:, 0]], pts[t[:, 2]] - pts[t[:, 0]]).sum(axis=0)
    normal = tuple(float(c) for c in tri_n)  # the side the triangles face (outward, orientation included)
    pts = [tuple(float(c) for c in p) for p in pts]
    polys = {i: [int(a), int(b), int(c)] for i, (a, b, c) in enumerate(t)}
    owner = {}  # directed edge -> polygon
    for i, loop in polys.items():
        for k in range(3):
            owner[(loop[k], loop[(k + 1) % 3])] = i
    interior = [(a, b) for (a, b) in owner if a < b and (b, a) in owner]
    interior.sort(key=lambda e: sum((x - y) ** 2 for x, y in zip(pts[e[0]], pts[e[1]])))

    for a, b in interior:
        p, q = owner.get((a, b)), owner.get((b, a))
        if p is None or q is None or p == q:
            continue
        lp, lq = polys[p], polys[q]
        # p runs a -> b; q runs b -> a. Merged: p from b round to a, then q from a round to b (both exclusive).
        i, j = lp.index(b), lq.index(a)
        merged = lp[i:] + lp[:i]           # b ... a
        rest = lq[j:] + lq[:j]             # a ... b
        merged = merged + rest[1:-1]       # b ... a, (q's vertices between a and b)
        if len(set(merged)) != len(merged):
            continue  # the two polygons touch elsewhere: the merge wouldn't be a simple polygon
        m = len(merged)
        if not (_convex_at(pts, merged, a, normal) and _convex_at(pts, merged, b, normal)):
            continue
        if (a in keep and _straight_at(pts, merged, a)) or (b in keep and _straight_at(pts, merged, b)):
            continue
        if _thin_children(pts, merged):
            continue
        del polys[q]
        polys[p] = merged
        for k in range(m):
            owner[(merged[k], merged[(k + 1) % m])] = p
        owner.pop((a, b), None)
        owner.pop((b, a), None)
    return list(polys.values())


_COLLAR_MIN_NODES = 8  # holes with fewer nodes (pockets, polygonal cuts) already decompose into few good pieces
_COLLAR_SHARE = 0.35  # of a collar's clearance to the other loops. Neighbours keep a gap between their collars;
# a narrower collar leaves room outside it for fat pieces (0.45: Bevel 2 mm + Subdivision folded slivers from a
# corner to the collar's side on the default part; 0.25-0.35: none on the test parts, Bevel not clamped)


def _cycles(t):
    """The boundary cycles of triangles `t` (one face) in the triangles' winding, or None if a boundary vertex
    has more than one outgoing boundary edge (loops touching at a vertex)."""
    directed = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    keys = {(int(a), int(b)) for a, b in directed}
    nxt = {}
    for a, b in keys:
        if (b, a) not in keys:
            if a in nxt:
                return None
            nxt[a] = b
    cycles, seen = [], set()
    for start in nxt:
        if start in seen:
            continue
        cycle, v = [start], nxt[start]
        seen.add(start)
        while v != start:
            if v not in nxt or v in seen:
                return None
            cycle.append(v)
            seen.add(v)
            v = nxt[v]
        cycles.append(cycle)
    return cycles


def _area(p):
    return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def _convex2d(p):
    """Is the polygon `p` (2D, CCW) convex (180° corners allowed)?"""
    d = np.roll(p, -1, axis=0) - p
    cross = d[:, 0] * np.roll(d[:, 1], -1) - d[:, 1] * np.roll(d[:, 0], -1)
    return _area(p) > 0 and bool((cross >= -1e-12 * float(np.max(np.abs(d))) ** 2).all())


def _segment_distance(points, loop):
    """Smallest distance from `points` to the closed polygon `loop` (both 2D)."""
    return float(meshing._distance_to(points, np.stack([loop, np.roll(loop, -1, axis=0)], axis=1)).min())


def _room(lo, hi, taken):
    """How far the rectangle [lo, hi] may grow before it overlaps one of the `taken` rectangles (lo, hi): half
    the gap to the nearest (the other half is that one's side), or 0 where they already overlap."""
    room = math.inf
    for tlo, thi in taken:
        gap = float(max(np.max(tlo - hi), np.max(lo - thi)))
        room = min(room, 0.5 * gap if gap > 0 else 0.0)
    return room


def _collar(hole, others, lo, hi, taken=()):
    """Radial pieces around a curved hole (2D, the hole in the face's winding: clockwise), out to its bounding
    rectangle [lo, hi] grown by a share of the rectangle's clearance to the `others` loops, and by at most half
    its gap to the `taken` rectangles (collars already placed). Returns (collar polygon CCW, pieces as lists of
    indices: < len(hole) a hole node, else collar node - len(hole)), or None if the hole isn't star-shaped from
    its centroid or a piece isn't convex."""
    centre = hole.mean(axis=0)
    rel = hole - centre
    if not np.all(np.linalg.norm(rel, axis=1) > 0):
        return None
    ang = np.arctan2(rel[:, 1], rel[:, 0])
    turn = (np.roll(ang, -1) - ang + math.pi) % (2 * math.pi) - math.pi
    if not (np.all(turn < 0) and abs(turn.sum() + 2 * math.pi) < 1e-6):
        return None  # not strictly clockwise around the centroid once: not star-shaped from it
    rect = np.array([lo, [hi[0], lo[1]], hi, [lo[0], hi[1]]])
    clearance = min(_segment_distance(rect, o) for o in others) if others else math.inf
    for o in others:  # a loop reaching inside the rectangle's edges from outside (no rectangle corner near it)
        clearance = min(clearance, float(meshing._distance_to(o, np.stack([rect, np.roll(rect, -1, axis=0)],
                                                                           axis=1)).min()))
    margin = min(_COLLAR_SHARE * clearance, 0.5 * float(np.max(hi - lo)), _room(lo, hi, taken))
    if not margin > 1e-6:
        return None
    lo, hi = lo - margin, hi + margin
    # each hole node's ray from the centre onto the grown rectangle, then the corners between two rays
    ray = []
    for d in rel:
        s = min((hi[0] - centre[0]) / d[0] if d[0] > 0 else (lo[0] - centre[0]) / d[0] if d[0] < 0 else math.inf,
                (hi[1] - centre[1]) / d[1] if d[1] > 0 else (lo[1] - centre[1]) / d[1] if d[1] < 0 else math.inf)
        p = centre + s * d
        # exactly on the side it hits, so the collar's straight sides stay straight (180° corners, not dents);
        # a ray through a corner (a hole node on a diagonal) lands on that corner
        tol = 1e-7 * float(np.max(hi - lo))
        for k, bound in ((0, lo[0]), (0, hi[0]), (1, lo[1]), (1, hi[1])):
            if abs(p[k] - bound) <= tol:
                p[k] = bound
        ray.append(p)
    corners = np.array([lo, [hi[0], lo[1]], hi, [lo[0], hi[1]]])
    # a ray landing close to a corner (next to a node on the diagonal) moves onto it: no stub side next to the
    # corner (the pieces' convexity is checked below)
    near = 0.2 * 2 * float(np.sum(hi - lo)) / len(ray)
    for c in corners:
        dist = [float(np.max(np.abs(p - c))) for p in ray]
        k = int(np.argmin(dist))
        if dist[k] <= near:
            ray[k][:] = c
    corner_ang = np.arctan2(corners[:, 1] - centre[1], corners[:, 0] - centre[0])
    nodes, pieces, n = [], [], len(hole)
    ray_index = []
    for p in ray:
        ray_index.append(len(nodes))
        nodes.append(p)
    corner_index = []
    for c in corners:
        hit = [i for i, p in enumerate(ray) if np.array_equal(p, c)]
        corner_index.append(ray_index[hit[0]] if hit else len(nodes))
        if not hit:
            nodes.append(c)
    nodes = np.asarray(nodes)
    for i in range(n):
        j = (i + 1) % n
        # between ray j and ray i (counter-clockwise from j to i): the rectangle corners there
        a0 = math.atan2(*(ray[j] - centre)[::-1])
        span = (math.atan2(*(ray[i] - centre)[::-1]) - a0) % (2 * math.pi)
        between = sorted(((ca - a0) % (2 * math.pi), k) for k, ca in enumerate(corner_ang)
                         if 1e-12 < (ca - a0) % (2 * math.pi) < span - 1e-12
                         and corner_index[k] not in (ray_index[i], ray_index[j]))
        piece = [i, j, n + ray_index[j]] + [n + corner_index[k] for _, k in between] + [n + ray_index[i]]
        pts = np.array([hole[x] if x < n else nodes[x - n] for x in piece])
        if not _convex2d(pts):
            return None
        pieces.append(piece)
    # the collar's outline, counter-clockwise: ray points and unused corners by angle around the centre
    outline = sorted(range(len(nodes)), key=lambda k: math.atan2(*(nodes[k] - centre)[::-1]))
    # inside the face: a rectangle's corner can lie beyond a rounded outer corner, or its side cut a loop,
    # at a positive distance from every loop (measured: a speaker's frame, its cone's hole nearly touching it)
    if others:
        segs = np.concatenate([np.stack([o, np.roll(o, -1, axis=0)], axis=1) for o in others])
        ring = nodes[outline]
        if not meshing._inside(ring, segs).all() or any(
                _segments_cross(p0, p1, segs) for p0, p1 in zip(ring, np.roll(ring, -1, axis=0))):
            return None
    return nodes[outline], outline, pieces, lo, hi


_ARC_MIN_SEGMENTS = 4  # a run of a loop curving away from the face this long takes a partial collar
_ARC_TURN = math.radians(45)  # at most this turn per node: a curved edge's discretization, not a corner
_ARC_SIDE_MIN = math.radians(15)  # a partial collar's side spanning less of the arc joins its neighbour
_AXIS_TOL = math.radians(10)  # an arc ending this close to a frame axis gets a side square to it (as a hole's rectangle)


def _reflex_runs(p, ends=()):
    """Where a loop (2D, the face on its left) curves away from the face: (a, b) indices of the nodes before and
    after each maximal run of reflex nodes turning less than _ARC_TURN, at least _ARC_MIN_SEGMENTS segments
    from a to b. A run that isn't one circle's arc is split at its nodes in `ends` (BRep vertices: a slot's cap
    and its long side), not at a vertex inside one circle (a cylinder's seam). A loop reflex all round (a hole)
    has no run: it is a whole collar's job."""
    n = len(p)
    d = np.roll(p, -1, axis=0) - p
    din = np.roll(d, 1, axis=0)
    turn = np.arctan2(din[:, 0] * d[:, 1] - din[:, 1] * d[:, 0], np.einsum("ij,ij->i", din, d))
    reflex = (turn < -1e-9) & (turn > -_ARC_TURN)
    if reflex.all() or not reflex.any():
        return []
    start = int(np.argmin(reflex))
    runs, run = [], []
    for s in range(1, n + 1):
        i = (start + s) % n
        if reflex[i]:
            run.append(i)
            continue
        if len(run):
            runs.append(((run[0] - 1) % n, (run[-1] + 1) % n))
        run = []
    ends, out = set(ends), []
    while runs:
        a, b = runs.pop()
        idx = [(a + i) % n for i in range((b - a) % n + 1)]
        if len(idx) - 1 < _ARC_MIN_SEGMENTS or a == b:
            continue
        centre, radius = _circle(p[idx])
        cut = [i for i in idx[1:-1] if i in ends]
        if cut and np.abs(np.linalg.norm(p[idx] - centre, axis=1) - radius).max() > 1e-3 * radius:
            bounds = [a] + cut + [b]
            runs.extend(zip(bounds[:-1], bounds[1:]))
        else:
            out.append((a, b))
    return out


def _circle(p):
    """Least-squares circle through 2D points `p`: (centre, radius)."""
    m = np.column_stack([2 * p, np.ones(len(p))])
    sol, *_ = np.linalg.lstsq(m, (p ** 2).sum(axis=1), rcond=None)
    centre = sol[:2]
    return centre, math.sqrt(max(0.0, float(sol[2] + centre @ centre)))


def _arc_sides(phi_lo, phi_hi, tol=_AXIS_TOL):
    """A partial collar's straight sides for an arc spanning the angles [phi_lo, phi_hi] around its centre: one
    per quadrant the arc crosses (quadrants centred on the face frame's axes, as a whole collar's rectangle), its
    normal along the axis where the arc reaches it, else along the middle of the arc's part in that quadrant
    (a gentle arc gets one side parallel to its chord). Parts narrower than _ARC_SIDE_MIN join a neighbour.
    Returns the sides' normal angles, counter-clockwise."""
    k0 = math.floor((phi_lo + math.pi / 4) / (math.pi / 2))
    k1 = math.floor((phi_hi + math.pi / 4) / (math.pi / 2))
    parts = []
    for k in range(k0, k1 + 1):
        lo, hi = max(phi_lo, k * math.pi / 2 - math.pi / 4), min(phi_hi, k * math.pi / 2 + math.pi / 4)
        if hi > lo:
            parts.append([lo, hi, k])
    while len(parts) > 1:
        widths = [hi - lo for lo, hi, _ in parts]
        i = int(np.argmin(widths))
        if widths[i] >= _ARC_SIDE_MIN:
            break
        j = i + 1 if i == 0 else i - 1 if i == len(parts) - 1 else (i - 1 if widths[i - 1] < widths[i + 1] else i + 1)
        lo, hi = min(parts[i][0], parts[j][0]), max(parts[i][1], parts[j][1])
        keep = parts[j][2] if lo - tol <= parts[j][2] * math.pi / 2 <= hi + tol else parts[i][2]
        parts[min(i, j)] = [lo, hi, keep]
        del parts[max(i, j)]
    return [k * math.pi / 2 if lo - tol <= k * math.pi / 2 <= hi + tol else (lo + hi) / 2 for lo, hi, k in parts]


def _polyline_at(poly, cum, s):
    k = min(int(np.searchsorted(cum, s, side="right")) - 1, len(poly) - 2)
    k = max(k, 0)
    seg = cum[k + 1] - cum[k]
    return poly[k] + (poly[k + 1] - poly[k]) * ((s - cum[k]) / seg if seg > 0 else 0.0)


def _segments_cross(p0, p1, segs):
    """Does the segment p0-p1 properly cross any of `segs` ((m, 2, 2))?"""
    if not len(segs):
        return False
    a, b = segs[:, 0], segs[:, 1]

    def orient(x, y, z):
        return (y[..., 0] - x[..., 0]) * (z[..., 1] - x[..., 1]) - (y[..., 1] - x[..., 1]) * (z[..., 0] - x[..., 0])
    d1, d2 = orient(a, b, p0), orient(a, b, p1)
    d3, d4 = orient(p0, p1, a), orient(p0, p1, b)
    return bool(np.any((d1 * d2 < 0) & (d3 * d4 < 0)))


def _arc_collar(loop, a, b, obstacles):
    """Radial pieces between a curved run of a loop (2D, the face on its left; nodes a..b, both ends kept on the
    loop) and a polyline of straight sides a margin away from it: a whole collar's pieces, cut where the arc
    meets the rest of the loop. The polyline's ends are pulled in along it until they stand a margin away from
    the loop's segments at a and b (no vertex may be added on a BRep edge, and a collar node next to a bevelled
    edge would clamp Blender's Bevel to its distance). `obstacles`: segments ((m, 2, 2)) the collar must keep
    clear of (other loops, collars placed before). Returns (polyline nodes, pieces: indices < number of arc
    nodes are arc nodes a.., others polyline nodes offset by it, the collar's side segments a..b) or None."""
    n = len(loop)
    idx = [(a + i) % n for i in range((b - a) % n + 1)]
    arc = loop[idx]
    centre, radius = _circle(arc)
    rel = arc - centre
    if not (radius > 0 and np.all(np.linalg.norm(rel, axis=1) > 0)):
        return None
    phi = np.unwrap(np.arctan2(rel[:, 1], rel[:, 0]))
    if not (np.all(np.diff(phi) < 0) and phi[0] - phi[-1] < 2 * math.pi - 1e-6):
        return None  # not clockwise once around the centre: not star-shaped from it
    lines = [(loop[(a - 1) % n], loop[a]), (loop[b], loop[(b + 1) % n])]  # the loop's segments at the ends
    # the clearance, apart from the loop's segments at the arc's ends (the arc's first nodes are a chord from them)
    far = obstacles[~np.any([np.all(np.isclose(obstacles[:, e], x), axis=1) for e in (0, 1) for x in (arc[0], arc[-1])],
                           axis=0)] if len(obstacles) else obstacles
    clearance = float(meshing._distance_to(arc[1:-1], far).min()) if len(far) else math.inf
    margin = min(_COLLAR_SHARE * clearance, 0.5 * float(np.max(np.ptp(arc, axis=0))))
    # sides square to the frame's axes where the arc nearly reaches them, else (if those don't fit) square to
    # the arc's parts in each quadrant
    side_sets = [_arc_sides(float(phi[-1]), float(phi[0]), tol) for tol in (_AXIS_TOL, 0.0)]
    side_sets = [np.array([[math.cos(x), math.sin(x)] for x in normals]) for normals in side_sets]
    for attempt in range(8):
        margin_now = margin * 0.5 ** (attempt // 2)
        nvec = side_sets[attempt % 2]
        if not margin_now > 1e-6:
            return None
        reach = (rel @ nvec.T).max(axis=0)  # every arc node inside every side by the margin
        out = _arc_outline(centre, rel, nvec, reach + margin_now, lines, margin_now)
        if out is not None:
            poly, pieces = out
            nodes = np.concatenate([arc, poly])
            ok = all(_convex2d(nodes[piece]) for piece in pieces)
            path = np.concatenate([arc[:1], poly, arc[-1:]])
            segs = np.stack([path[:-1], path[1:]], axis=1)
            if ok and len(obstacles):
                ok = float(meshing._distance_to(poly, obstacles).min()) >= 0.5 * margin_now
                for p0, p1 in zip(path[:-1], path[1:]):
                    ok = ok and not _segments_cross(p0, p1, obstacles)
                # nothing inside the collar (a small hole between the arc and a side's corner)
                region = np.concatenate([segs, np.stack([arc[::-1][:-1], arc[::-1][1:]], axis=1)])
                ends = obstacles.reshape(-1, 2)
                ends = ends[(np.abs(ends - arc[0]).max(axis=1) > 1e-9) & (np.abs(ends - arc[-1]).max(axis=1) > 1e-9)]
                ok = ok and not meshing._inside(ends, region).any()
            if ok:
                return poly, pieces, segs
    return None


def _arc_outline(centre, rel, nvec, dist, lines, margin):
    """_arc_collar's polyline at one margin: (nodes, pieces) or None."""
    k = len(rel)
    # each arc node's ray from the centre onto the nearest side
    hits, side_of = [], []
    for d in rel / np.linalg.norm(rel, axis=1)[:, None]:
        c = nvec @ d
        s = np.where(c > 1e-9, dist / np.where(c > 1e-9, c, 1.0), np.inf)
        j = int(np.argmin(s))
        hits.append(centre + s[j] * d)
        side_of.append(j)
    # the polyline from the first node's hit to the last's, through the corners of the sides in between
    poly, params = [hits[0]], [0.0]
    for j in range(side_of[0], side_of[-1], -1 if side_of[-1] < side_of[0] else 1):
        jn = j - 1 if side_of[-1] < side_of[0] else j + 1
        m = np.array([nvec[j], nvec[jn]])
        if abs(np.linalg.det(m)) < 1e-12:
            return None
        poly.append(centre + np.linalg.solve(m, [dist[j], dist[jn]]))
    poly.append(hits[-1])
    poly = np.asarray(poly)
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(poly, axis=0), axis=1))])
    total = float(cum[-1])
    if not total > 0:
        return None

    def param(p, side):
        # the corner index before the side the ray hit: corners follow the sides in order
        seg = abs(side - side_of[0])
        return float(cum[seg] + np.linalg.norm(p - poly[seg]))
    t = np.array([param(h, j) for h, j in zip(hits, side_of)])
    # pull the ends in until they stand `margin` away from the loop's segments at the arc's ends
    samples = np.linspace(0.0, total, 257)

    def pull(line, order):
        p0, p1 = line
        u = (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-300)
        for s in order:
            q = _polyline_at(poly, cum, s) - p0
            if abs(q[0] * u[1] - q[1] * u[0]) >= margin:
                return s
        return None
    s0, s1 = pull(lines[0], samples), pull(lines[1], samples[::-1])
    if s0 is None or s1 is None or not s1 - s0 > 1e-9 * total:
        return None
    t = s0 + (t - t[0]) * (s1 - s0) / (t[-1] - t[0])
    pts = [_polyline_at(poly, cum, s) for s in t]
    corners = [(float(cum[i]), poly[i]) for i in range(1, len(poly) - 1)]
    # a node landing close to a corner moves onto it (no stub side next to the corner)
    near = 0.2 * (s1 - s0) / max(k - 1, 1)
    snapped = set()
    for ci, (cs, cp) in enumerate(corners):
        i = int(np.argmin(np.abs(t - cs)))
        if abs(t[i] - cs) <= near and 0 < i < k - 1:
            pts[i], t[i] = cp.copy(), cs
            snapped.add(ci)
    nodes, pieces, at = [], [], []
    for i in range(k):
        at.append(len(nodes))
        nodes.append(pts[i])
        if i < k - 1:
            for ci, (cs, cp) in enumerate(corners):
                if ci not in snapped and t[i] < cs < t[i + 1]:
                    nodes.append(cp)
    for i in range(k - 1):
        between = list(range(at[i] + 1, at[i + 1]))
        pieces.append([i, i + 1, k + at[i + 1]] + [k + x for x in between[::-1]] + [k + at[i]])
    return np.asarray(nodes), pieces


def _collared(t, verts, normal, keep=()):
    """Convex polygons of a flat face with holes, curved holes wrapped in collars of radial quads (research:
    docs/research/2026-09-28-planar-faces-with-holes.md): without interior vertices every convex piece next to
    a curved hole reaches the outer boundary, a fan of slivers. Returns (polygons of vertex indices, new vertices
    (3D)) or None where no hole takes a collar or the collars don't fit (the caller merges the triangles)."""
    cycles = _cycles(t)
    if cycles is None or len(cycles) < 2:
        return None
    # the face's frame: z along the triangles' side, x along the outer loop's longest segment
    pts3 = verts.astype(np.float64)
    ez = normal / np.linalg.norm(normal)
    areas = []
    for cyc in cycles:
        c = pts3[cyc]
        areas.append(float(np.dot(np.cross(c, np.roll(c, -1, axis=0)).sum(axis=0), ez)) / 2)
    outer = int(np.argmax(areas))
    oc = pts3[cycles[outer]]
    seg = np.roll(oc, -1, axis=0) - oc
    ex = seg[int(np.argmax(np.linalg.norm(seg, axis=1)))]
    ex = ex - ez * np.dot(ex, ez)
    ex /= np.linalg.norm(ex)
    ey = np.cross(ez, ex)
    origin = oc[0]
    flat = [np.column_stack([(pts3[c] - origin) @ ex, (pts3[c] - origin) @ ey]) for c in cycles]
    # Biggest holes first; each collar takes a share of its clearance to the loops and at most half its gap to
    # the collars placed before it, so collars never overlap (a pair of overlapping collars used to drop every
    # collar of the face: 42% of the slivers of a STEP corpus of boards and parts, 2026-09-29).
    holes = sorted((k for k, cyc in enumerate(cycles) if k != outer and len(cyc) >= _COLLAR_MIN_NODES),
                   key=lambda k: -float(np.max(np.ptp(flat[k], axis=0))))
    collars, taken = {}, []
    for k in holes:
        p = flat[k]
        others = [q for j, q in enumerate(flat) if j != k]
        out = _collar(p, others, p.min(axis=0), p.max(axis=0), taken)
        if out is not None:
            collars[k] = out
            taken.append((out[3], out[4]))
    # partial collars on the other loops' curved runs that bend away from the face (a boss or a hole cutting
    # the face's edge or corner): without them the run's nodes fan out to one far corner
    obstacles = [np.stack([p, np.roll(p, -1, axis=0)], axis=1) for k, p in enumerate(flat) if k not in collars]
    obstacles += [np.stack([c[0], np.roll(c[0], -1, axis=0)], axis=1) for c in collars.values()]
    arcs = {}
    for k, p in enumerate(flat):
        if k in collars:
            continue
        for a, b in _reflex_runs(p, [i for i, v in enumerate(cycles[k]) if v in keep]):
            n = len(p)
            own = {(a + i) % n for i in range((b - a) % n)}  # the run's own segments (i -> i + 1)
            segs = np.concatenate(obstacles)
            mask = np.ones(len(segs), dtype=bool)
            mask[[sum(len(q) for j, q in enumerate(flat) if j < k and j not in collars) + i for i in own]] = False
            out = _arc_collar(p, a, b, segs[mask])
            if out is not None:
                arcs.setdefault(k, []).append((a, b) + out)
                obstacles.append(out[2])
    if not collars and not arcs:
        return None
    # nodes: the face's own, then each collar's
    q, index, extra = [], [], []
    polys, segs = [], []
    base = len(verts)
    for k, (cyc, p) in enumerate(zip(cycles, flat)):  # the region's loops, curved runs replaced by collar sides
        if k in collars:
            continue
        runs = {a: (b, poly, pieces) for a, b, poly, pieces, _ in arcs.get(k, [])}
        start, n = len(q), len(cyc)
        # walk the loop from a node inside no run, jumping from each run's first node to its last
        i0 = next(j for j in range(n) if not any(0 < (j - a) % n < (b - a) % n for a, (b, _, _) in runs.items()))
        i = i0
        while True:
            q.append(p[i])
            index.append(cyc[i])
            if i in runs:
                b, poly, pieces = runs[i]
                first = base + len(extra)
                extra.extend(poly)
                q.extend(poly)
                index.extend(range(first, first + len(poly)))
                m = (b - i) % n + 1
                for piece in pieces:
                    polys.append([cyc[(i + x) % n] if x < m else first + x - m for x in piece])
                i = b
            else:
                i = (i + 1) % n
            if i == i0:
                break
        segs.extend((start + j, start + (j + 1) % (len(q) - start)) for j in range(len(q) - start))
    for k, (outline, order, pieces, lo, hi) in collars.items():
        nodes_start = base + len(extra)
        # the collar's own nodes, in the order _collar numbered them
        n_nodes = len(outline)
        own = [None] * n_nodes
        for pos, node in zip(order, outline):
            own[pos] = node
        extra.extend(own)
        n_hole = len(cycles[k])
        for piece in pieces:
            polys.append([cycles[k][x] if x < n_hole else nodes_start + x - n_hole for x in piece])
        # the outline goes around the region's hole the other way (clockwise), in the region's winding
        ring = [nodes_start + pos for pos in order][::-1]
        start = len(q)
        q.extend(own[pos] for pos in order[::-1])
        index.extend(ring)
        segs.extend((start + i, start + (i + 1) % n_nodes) for i in range(n_nodes))
    q = np.asarray(q, dtype=np.float64)
    segs = np.asarray(segs, dtype=np.int64)
    from scipy.spatial import Delaunay
    try:
        tri = Delaunay(q).simplices
    except Exception:
        return None
    tri = meshing._recover(q, tri, segs)
    if tri is None:
        return None
    tri = tri[meshing._interior(tri, segs)]
    if not len(tri):
        return None
    signed = (q[tri[:, 1], 0] - q[tri[:, 0], 0]) * (q[tri[:, 2], 1] - q[tri[:, 0], 1]) - \
             (q[tri[:, 1], 1] - q[tri[:, 0], 1]) * (q[tri[:, 2], 0] - q[tri[:, 0], 0])
    tri = np.where((signed < 0)[:, None], tri[:, ::-1], tri)
    # merged in the face's frame: collinear collar nodes have exact coordinates there (straight 180° corners)
    index = np.asarray(index, dtype=np.int64)
    local_keep = {k for k, g in enumerate(index.tolist()) if g in keep}
    region_polys = _merge_convex(tri, np.column_stack([q, np.zeros(len(q))]), local_keep)
    polys.extend([int(index[v]) for v in piece] for piece in region_polys)
    extra3 = np.array([origin + x * ex + y * ey for x, y in extra], dtype=np.float64).reshape(-1, 3)
    # the pieces tile the face exactly once (a safety net: an overlapping piece would show as a dark fold)
    allp = np.concatenate([pts3, extra3])
    area = sum(float(np.dot(np.cross(allp[piece], np.roll(allp[piece], -1, axis=0)).sum(axis=0), ez)) / 2
               for piece in polys)
    tri = pts3[t]
    expected = float(np.dot(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]).sum(axis=0), ez)) / 2
    if not abs(area - expected) <= 1e-6 * abs(expected):
        return None
    return polys, extra3


def _brep_vertices(face, verts, t):
    """The mesh vertices of triangles `t` (one face) that lie on the face's BRep vertices."""
    used = np.unique(t)
    p = verts[used].astype(np.float64)
    out = set()
    explorer = TopExp_Explorer(face, TopAbs_VERTEX)
    while explorer.More():
        q = BRep_Tool.Pnt_s(TopoDS.Vertex(explorer.Current()))
        d = np.linalg.norm(p - (q.X(), q.Y(), q.Z()), axis=1)
        k = int(np.argmin(d))
        if d[k] < 1e-4:
            out.add(int(used[k]))
        explorer.Next()
    return out


_QUAD_PLANAR = math.radians(0.5)  # two triangles of a curved face's grid cell this close to coplanar: one quad
_QUAD_MIN_CORNER = math.radians(45)  # a grid cell, not any two triangles of a Delaunay patch (odd quads folded)


def _cell_quads(t, pts):
    """A curved face's triangles `t` as polygons: two triangles sharing an edge become one quad where they are
    coplanar within _QUAD_PLANAR and the quad is convex, longest shared edges first (a grid cell's diagonal is
    its longest edge); the rest stay triangles. A cylinder, cone or extrusion is ruled: its cells between two
    generators are planar strips, which split into two triangles showed as long slivers (a fillet along an 86 mm
    edge: 0.37° corners, the diagonals reading as a fan in wireframe; test2.blend, 2026-09-29). Doubly curved
    cells (spheres, a fillet's corner patch) stay triangles, as Blender would split them anyway. Returns the
    polygons as vertex lists in the triangles' winding."""
    p = pts[t].astype(np.float64)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    norm = np.linalg.norm(n, axis=1)
    n = n / np.where(norm > 0, norm, 1.0)[:, None]
    owner = {}
    for i, tri in enumerate(t.tolist()):
        for k in range(3):
            owner[(tri[k], tri[(k + 1) % 3])] = i
    cos_limit = math.cos(_QUAD_PLANAR)
    shared = [(a, b, i, owner[(b, a)]) for (a, b), i in owner.items() if (b, a) in owner and a < b]
    shared = [(a, b, i, j) for a, b, i, j in shared if norm[i] > 0 and norm[j] > 0 and float(n[i] @ n[j]) >= cos_limit]
    shared.sort(key=lambda e: -float(np.linalg.norm(pts[e[0]].astype(np.float64) - pts[e[1]])))
    polys, used = [], set()
    for a, b, i, j in shared:
        if i in used or j in used:
            continue
        ti, tj = t[i].tolist(), t[j].tolist()
        if ti.index(b) != (ti.index(a) + 1) % 3:  # triangle i runs a -> b; j runs b -> a
            i, j, ti, tj = j, i, tj, ti
        c = ti[(ti.index(b) + 1) % 3]
        d = tj[(tj.index(a) + 1) % 3]
        quad = [b, c, a, d]
        q = pts[quad].astype(np.float64)
        turns = np.cross(q - np.roll(q, 1, axis=0), np.roll(q, -1, axis=0) - q) @ (n[i] + n[j])
        e0, e1 = np.roll(q, 1, axis=0) - q, np.roll(q, -1, axis=0) - q
        cos = np.einsum("ij,ij->i", e0, e1) / np.maximum(1e-300, np.linalg.norm(e0, axis=1) * np.linalg.norm(e1, axis=1))
        if (turns > 0).all() and cos.max() <= math.cos(_QUAD_MIN_CORNER):
            polys.append(quad)
            used.update((i, j))
    polys.extend(tri for i, tri in enumerate(t.tolist()) if i not in used)
    return polys


def _polygons(shape, verts, normals, tris, tri_face):
    """(loops, poly_sizes, poly_face, verts, normals): a flat face whose triangles have one boundary cycle
    becomes that one polygon (Blender's Bevel clamps to the shortest chord of a triangulated cap; Blender's own
    primitives have n-gon caps); a flat face with holes becomes convex polygons, curved holes wrapped in collars
    of radial quads (_collared, whose new vertices are appended) or else merged triangles (_merge_convex);
    curved faces keep their triangles, but a grid cell's two coplanar triangles make a quad (_cell_quads)."""
    loops, sizes, faces = [], [], []
    new_verts, new_normals, count = [], [], len(verts)
    for fid, face in enumerate(face_map(shape)):
        t = tris[tri_face == fid]
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() == GeomAbs_Plane and len(t) > 1:
            cycle = _boundary_loop(t)
            if cycle is None:
                normal = np.cross(verts[t[:, 1]].astype(np.float64) - verts[t[:, 0]],
                                  verts[t[:, 2]].astype(np.float64) - verts[t[:, 0]]).sum(axis=0)
                keep = _brep_vertices(face, verts, t)
                out = _collared(t, verts, normal, keep)
                if out is None:
                    pieces = _merge_convex(t, verts.astype(np.float64), keep)
                else:
                    pieces, extra = out
                    # _collared numbered its nodes from len(verts): shift them past the faces collared before
                    pieces = [[v if v < len(verts) else v + count - len(verts) for v in piece] for piece in pieces]
                    new_verts.append(extra)
                    new_normals.append(np.repeat(normals[t[:1, 0]], len(extra), axis=0))
                    count += len(extra)
            else:
                pieces = [cycle]
            for piece in pieces:
                loops.append(np.array(piece, dtype=np.int64))
                sizes.append(len(piece))
                faces.append(fid)
        else:
            for piece in _cell_quads(t, verts):
                loops.append(np.array(piece, dtype=np.int64))
                sizes.append(len(piece))
                faces.append(fid)
    if new_verts:
        verts = np.concatenate([verts, np.concatenate(new_verts).astype(verts.dtype)])
        normals = np.concatenate([normals, np.concatenate(new_normals)])
    return np.concatenate(loops), np.array(sizes, dtype=np.int32), np.array(faces, dtype=np.int32), verts, normals


def _sides(loops, sizes):
    """(vertex pair (unsorted), polygon, corner of the pair's first vertex) of every polygon side."""
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int64)
    nxt = np.arange(len(loops)) + 1
    nxt[starts + sizes - 1] = starts
    return np.stack([loops, loops[nxt]], axis=1), np.repeat(np.arange(len(sizes)), sizes), np.arange(len(loops)), nxt
def _brep_edge_of(shape, faces, edges):
    """(face a, face b) -> BRep edge ids shared by the two faces."""
    ancestors = AncestorMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, ancestors)
    face_ids = ShapeMap()
    for f in faces:
        face_ids.Add(f)
    edge_ids = ShapeMap()
    for e in edges:
        edge_ids.Add(e)
    shared = {}
    for i in range(1, ancestors.Extent() + 1):
        eid = edge_ids.FindIndex(ancestors.FindKey(i)) - 1
        fids = sorted({face_ids.FindIndex(f) - 1 for f in ancestors.FindFromIndex(i)})
        if len(fids) == 2:
            shared.setdefault(tuple(fids), []).append(eid)
    return shared


def _nearest_edge(candidates, edges, point):
    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, point))).Vertex()
    return min(candidates, key=lambda eid: BRepExtrema_DistShapeShape(vertex, edges[eid]).Value())


def display_mesh(shape, lin_defl=0.1, ang_defl=0.3):
    """The mesh Blender shows: tessellate_with_normals()'s faces welded along their BRep edges, so it is closed
    and Blender's modifiers see real edges; a flat face without holes as one polygon; the exact normals per
    polygon corner (a welded vertex on a sharp edge has one per face); and each mesh edge lying on a BRep edge
    with that edge's id and whether it is sharp (the faces meet at an angle) or smooth (tangent faces, e.g. a
    fillet and its flat neighbour). Seams and poles are inside a face: no edge id."""
    verts, tris, tri_face, normals = tessellate_with_normals(shape, lin_defl, ang_defl)
    loops, sizes, poly_face, verts, normals = _polygons(shape, verts, normals, tris, tri_face)
    corner_normals = normals[loops].astype(np.float32)
    verts, loops = _weld_all(verts, loops)
    pairs, _, _, _ = _sides(loops, sizes)
    loops, _ = _merge_open(verts, loops, pairs)
    used, loops = np.unique(loops, return_inverse=True)
    verts, loops = verts[used], loops.ravel().astype(np.int32)
    pairs, side_poly, side_corner, side_next = _sides(loops, sizes)
    sorted_pairs = np.sort(pairs, axis=1)
    uniq, inv = np.unique(sorted_pairs, axis=0, return_inverse=True)
    inv = inv.ravel()
    order = np.argsort(inv, kind="stable")  # each unique edge's sides, adjacent
    counts = np.bincount(inv, minlength=len(uniq))
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    # Only edges between exactly two polygons: a solid can be non-manifold where two parts of it touch along an
    # edge (4 polygons); such an edge carries no id (it can't be told which faces it belongs to pairwise).
    manifold = np.nonzero(counts == 2)[0]
    side_a, side_b = np.zeros(len(uniq), np.int64), np.zeros(len(uniq), np.int64)
    side_a[manifold], side_b[manifold] = order[starts[manifold]], order[starts[manifold] + 1]
    fa, fb = poly_face[side_poly[side_a]], poly_face[side_poly[side_b]]
    boundary = manifold[fa[manifold] != fb[manifold]]
    faces, brep_edges = face_map(shape), edge_map(shape)
    shared = _brep_edge_of(shape, faces, brep_edges)
    # the angle between the two faces' normals at each end of the edge (that vertex's corner on each side):
    # sharp where it is above _SHARP at either end
    a, b = side_a[boundary], side_b[boundary]
    sharp = np.zeros(len(boundary), dtype=bool)
    for end in (0, 1):
        v = uniq[boundary, end]
        corner_a = np.where(loops[side_corner[a]] == v, side_corner[a], side_next[a])
        corner_b = np.where(loops[side_corner[b]] == v, side_corner[b], side_next[b])
        na, nb = corner_normals[corner_a].astype(np.float64), corner_normals[corner_b].astype(np.float64)
        cos = np.einsum("ij,ij->i", na, nb) / np.maximum(1e-12, np.linalg.norm(na, axis=1) * np.linalg.norm(nb, axis=1))
        sharp |= np.arccos(np.clip(cos, -1.0, 1.0)) > _SHARP
    out_edges, out_ids, out_sharp = [], [], []
    for n, k in enumerate(boundary):
        candidates = shared.get((int(min(fa[k], fb[k])), int(max(fa[k], fb[k]))), [])
        if not candidates:
            continue
        p, q = uniq[k]
        eid = candidates[0] if len(candidates) == 1 else _nearest_edge(
            candidates, brep_edges, (verts[p].astype(np.float64) + verts[q]) / 2)
        out_edges.append((p, q))
        out_ids.append(eid)
        out_sharp.append(int(sharp[n]))
    return DisplayMesh(verts.astype(np.float32), loops, sizes, poly_face, corner_normals,
                       np.array(out_edges, dtype=np.int32).reshape(-1, 2), np.array(out_ids, dtype=np.int32),
                       np.array(out_sharp, dtype=np.int32))
