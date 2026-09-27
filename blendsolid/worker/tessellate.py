"""OCP helpers for the worker: validity, volume, face numbering and tessellation with BRep face IDs.

Faces are numbered with TopExp.MapShapes (deterministic for a given shape): brep_face_id = 0-based index.

Tessellation: BRepMesh discretizes the edges and triangulates every face, but its Delaunay triangulation in the
(u, v) parameter space gives irregular triangles (fans, slivers, a distorted band along the seam) on curved faces.
A full face of revolution (torus, cylinder or cone bounded only by its seam, poles and v-iso circles) is
re-triangulated here as a structured grid of staggered rings: near-equilateral triangles, valence 6, seam welded,
its boundary rings taken from BRepMesh's own edge nodes so it stays conforming with the neighbouring faces. A full
sphere has no real boundary: it becomes a geodesic grid (an octahedron subdivided and projected onto it), which
has neither the thin pole triangles nor the seam of a latitude-longitude grid.
"""
import math

import numpy as np
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve2d, BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus
from OCP.GProp import GProp_GProps
from OCP.IMeshTools import IMeshTools_Parameters
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.gp import gp_Pnt, gp_Vec

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


def _mesh_parameters(revolutions, lin_defl, ang_defl):
    """BRepMesh parameters. Every circle bounding a face of revolution must carry as many nodes as that face's
    grid rings: one angular step for all edges, fine enough for the largest such circle, makes the angle (not
    the linear deflection) decide every circle's node count, so both circles of a cone get the same count."""
    p = IMeshTools_Parameters()
    p.Deflection, p.DeflectionInterior = lin_defl, lin_defl
    p.Angle, p.AngleInterior = ang_defl, ang_defl
    circles = [r.max_circle_radius() for r in revolutions if "circle" in r.ends]
    if circles:
        p.Angle = _step(lin_defl, ang_defl, max(circles)) * 0.999
    p.Relative, p.InParallel = False, True
    return p


def _triangulation(face):
    loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(face, loc)
    if tri is None:
        return None, None
    trsf = loc.Transformation()
    nodes = [tri.Node(i).Transformed(trsf) for i in range(1, tri.NbNodes() + 1)]
    pts = np.array([(q.X(), q.Y(), q.Z()) for q in nodes], dtype=np.float64).reshape(-1, 3)
    return tri, pts


def _boundary_ring(rev, tri, pts, v):
    """BRepMesh's nodes on the circle at parameter v, sorted by u, the seam copy dropped: (u values, points)."""
    us, ps = [], []
    for i in range(1, tri.NbNodes() + 1):
        uv = tri.UVNode(i)
        if abs(uv.Y() - v) < 1e-7 and abs(uv.X() - rev.u0 - _TAU) > 1e-7:
            us.append(uv.X())
            ps.append(pts[i - 1])
    order = np.argsort(us)
    return np.asarray(us)[order], np.asarray(ps).reshape(-1, 3)[order]


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


def _structured(rev, tri, pts, lin_defl, ang_defl):
    """Staggered-ring grid of a face of revolution: (points, triangles), triangles oriented like the surface."""
    s = rev.surf
    ends = {end: _boundary_ring(rev, tri, pts, v) for end, v in ((0, rev.v0), (1, rev.v1))
            if rev.ends[end] == "circle"}
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
    """Merge coincident nodes (BRepMesh's seam and pole copies); drop the triangles that collapse."""
    _, first, inv = np.unique(np.round(pts, _WELD_DECIMALS), axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    t = inv[t]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    return pts[first], t


def face_planes(shape):
    """Per face (face_map order): the exact plane of a flat face as (nx, ny, nz, d), the normal pointing out of
    the solid and d = n . p for its points (millimetres, float64); NaN for a curved face. Tools place solids
    on these instead of the float32 display mesh, whose noise would leave skins and slivers in booleans."""
    out = np.full((len(face_map(shape)), 4), np.nan)
    for fid, face in enumerate(face_map(shape)):
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() != GeomAbs_Plane:
            continue
        pos = surf.Plane().Position()
        d, o = pos.Direction(), pos.Location()
        n = np.array([d.X(), d.Y(), d.Z()])
        if face.Orientation() == TopAbs_REVERSED:
            n = -n
        n[np.abs(n) < 1e-15] = 0.0  # no -0.0 / 1e-17 components on axis-aligned faces
        out[fid] = (*n, float(n @ np.array([o.X(), o.Y(), o.Z()])) + 0.0)
    return out


def _self_contained(rev):
    """A full sphere or torus shares no circle with another face: its grid needs nothing from BRepMesh."""
    return rev is not None and rev.kind in (GeomAbs_Sphere, GeomAbs_Torus)


def tessellate(shape, lin_defl=0.1, ang_defl=0.3):
    """Vertices are not shared between faces: sharp edges between BRep faces, unambiguous face map."""
    BRepTools.Clean_s(shape)
    faces = face_map(shape)
    revolutions = [_revolution(face) for face in faces]
    # BRepMesh only where its triangles or edge nodes are used: meshing a big sphere or torus with it (to throw
    # the result away) would take seconds. The faces keep their edges, so shared edges stay consistent.
    builder, compound = BRep_Builder(), TopoDS_Compound()
    builder.MakeCompound(compound)
    for face, rev in zip(faces, revolutions):
        if not _self_contained(rev):
            builder.Add(compound, face)
    BRepMesh_IncrementalMesh(compound, _mesh_parameters([r for r in revolutions if r], lin_defl, ang_defl))
    verts, tris, tri_face, offset = [], [], [], 0
    for fid, (face, rev) in enumerate(zip(faces, revolutions)):
        if rev is not None and rev.kind == GeomAbs_Sphere:
            pts, t = _geodesic(rev, lin_defl, ang_defl)
        elif rev is not None and rev.kind == GeomAbs_Torus:
            pts, t = _structured(rev, None, None, lin_defl, ang_defl)
        else:
            tri, pts = _triangulation(face)
            if tri is None:
                raise RuntimeError(f"face {fid} has no triangulation")
            if rev is not None:
                pts, t = _structured(rev, tri, pts, lin_defl, ang_defl)
            else:
                t = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)],
                             dtype=np.int32).reshape(-1, 3) - 1
                pts, t = _weld(pts, t)
        if face.Orientation() == TopAbs_REVERSED:
            t = t[:, ::-1]
        verts.append(pts)
        tris.append(t + offset)
        tri_face.append(np.full(len(t), fid, dtype=np.int32))
        offset += len(pts)
    if not verts:
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32), np.zeros(0, np.int32)
    return (np.concatenate(verts).astype(np.float32), np.ascontiguousarray(np.concatenate(tris), dtype=np.int32),
            np.concatenate(tri_face))
