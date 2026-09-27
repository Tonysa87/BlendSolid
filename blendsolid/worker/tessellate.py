"""OCP helpers for the worker: validity, volume, face numbering and tessellation with BRep face IDs.

Faces are numbered with TopExp.MapShapes (deterministic for a given shape): brep_face_id = 0-based index.

Tessellation (ADR 0010): every edge is discretized once and every face meshed from those nodes (meshing.py), so
neighbouring faces weld exactly: curved faces with four corners as structured grids, other curved faces as grids
trimmed by their boundary, flat faces from their boundary. A full face of revolution (torus, cylinder or cone
bounded only by its seam, poles and v-iso circles) is a structured grid of staggered rings (ADR 0005), its
boundary rings taken from the shared edge nodes. A full sphere has no real boundary: it becomes a geodesic grid
(an octahedron subdivided and projected onto it), which has neither the thin pole triangles nor the seam of a
latitude-longitude grid.
"""
import math
from dataclasses import dataclass

import numpy as np
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve2d, BRepAdaptor_Surface
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
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus
from OCP.GProp import GProp_GProps
from OCP.IMeshTools import IMeshTools_Parameters
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound
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
    layout = meshing.plan(faces, edge_map(shape), kinds, rings, lin_defl, seg_angle)
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


def _merge_convex(t, pts):
    """Hertel-Mehlhorn: triangles `t` of a flat face merged across their shared edges,
    shortest first, while both ends of the removed edge stay convex. A face with holes can't be one Blender
    polygon, and its triangles' short chords (ears along an arc) clamp Blender's Bevel (Clamp Overlap, its
    default, limits the whole bevel to the tightest spot); measured: the default part's 1 mm bevel removed
    0.22 mm³ with triangles, 25 with the fewest simple (concave) polygons, and 82 — the unclamped value — with
    convex ones. Returns the polygons as vertex lists in the triangles' winding."""
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
        del polys[q]
        polys[p] = merged
        for k in range(m):
            owner[(merged[k], merged[(k + 1) % m])] = p
        owner.pop((a, b), None)
        owner.pop((b, a), None)
    return list(polys.values())


def _polygons(shape, verts, tris, tri_face):
    """(loops, poly_sizes, poly_face): a flat face whose triangles have one boundary cycle becomes that one
    polygon (Blender's Bevel clamps to the shortest chord of a triangulated cap; Blender's own primitives have
    n-gon caps); a flat face with holes becomes convex polygons (_merge_convex); curved faces keep their
    triangles."""
    loops, sizes, faces = [], [], []
    for fid, face in enumerate(face_map(shape)):
        t = tris[tri_face == fid]
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() == GeomAbs_Plane and len(t) > 1:
            cycle = _boundary_loop(t)
            if cycle is None:
                pieces = _merge_convex(t, verts.astype(np.float64))
            else:
                pieces = [cycle]
            for piece in pieces:
                loops.append(np.array(piece, dtype=np.int64))
                sizes.append(len(piece))
                faces.append(fid)
        else:
            loops.append(t.ravel().astype(np.int64))
            sizes.extend([3] * len(t))
            faces.extend([fid] * len(t))
    return np.concatenate(loops), np.array(sizes, dtype=np.int32), np.array(faces, dtype=np.int32)


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
    loops, sizes, poly_face = _polygons(shape, verts, tris, tri_face)
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
