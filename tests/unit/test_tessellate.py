"""Display-mesh topology: curved faces of revolution are structured grids, welded, within the deflection."""
import math

import build123d as bd
import numpy as np
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.BRep import BRep_Tool
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Torus
from OCP.gp import gp_Pnt

import tessellate  # worker module, imported as the worker does

LIN, ANG = 0.1, 0.3

SHAPES = {
    "sphere": lambda: bd.Sphere(10),
    "small_sphere": lambda: bd.Sphere(5),
    "big_sphere": lambda: bd.Sphere(200),
    "cylinder": lambda: bd.Cylinder(10, 20),
    "cone": lambda: bd.Cone(10, 5, 20),
    "pointed_cone": lambda: bd.Cone(10, 0, 20),
    "torus": lambda: bd.Torus(20, 5),
    "moved_sphere": lambda: bd.Location((5, -3, 7), (30, 20, 10)) * bd.Sphere(8),
    "hollow_sphere": lambda: bd.Sphere(10) - bd.Sphere(6),  # inner face reversed
    "box_with_hole": lambda: bd.Box(40, 30, 20) - bd.Cylinder(6, 30),
}
VOLUMES = {
    "sphere": 4 / 3 * math.pi * 1000, "small_sphere": 4 / 3 * math.pi * 125, "big_sphere": 4 / 3 * math.pi * 200 ** 3,
    "cylinder": math.pi * 100 * 20, "cone": math.pi * 20 / 3 * (100 + 50 + 25), "pointed_cone": math.pi * 20 / 3 * 100,
    "torus": 2 * math.pi ** 2 * 20 * 25, "moved_sphere": 4 / 3 * math.pi * 512,
    "hollow_sphere": 4 / 3 * math.pi * (1000 - 216), "box_with_hole": 40 * 30 * 20 - math.pi * 36 * 20,
}


def mesh(name):
    shape = SHAPES[name]().wrapped
    v, t, f = tessellate.tessellate(shape, LIN, ANG)
    return shape, v.astype(np.float64), t, f


def edges_of(t):
    e = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
    return np.unique(e, axis=0, return_counts=True)


def min_angles(v, t):
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]

    def ang(p, q, r):
        u, w = q - p, r - p
        return np.degrees(np.arccos(np.clip((u * w).sum(1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(w, axis=1)),
                                            -1, 1)))
    return np.minimum(np.minimum(ang(a, b, c), ang(b, c, a)), ang(c, a, b))


def curved_faces(shape):
    return [(fid, face) for fid, face in enumerate(tessellate.face_map(shape))
            if BRepAdaptor_Surface(face).GetType() != GeomAbs_Plane]


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_volume_and_orientation(name):
    _, v, t, _ = mesh(name)
    vol = np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum() / 6
    area = np.linalg.norm(np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]]), axis=1).sum() / 2
    assert vol > 0 and abs(vol - VOLUMES[name]) < area * LIN  # no point of the mesh farther than LIN


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_each_face_is_welded_and_has_no_degenerate_triangles(name):
    # Vertices are shared inside a face (seams welded) but not between faces (sharp edges between BRep faces).
    shape, v, t, f = mesh(name)
    owners = [np.unique(t[f == fid]) for fid in np.unique(f)]
    assert sum(len(o) for o in owners) == len(v)  # every vertex belongs to exactly one face
    for fid, used in zip(np.unique(f), owners):
        ft = t[f == fid]
        assert len(np.unique(np.round(v[used], 6), axis=0)) == len(used)
        assert (ft[:, 0] != ft[:, 1]).all() and (ft[:, 1] != ft[:, 2]).all() and (ft[:, 0] != ft[:, 2]).all()
        area = np.linalg.norm(np.cross(v[ft[:, 1]] - v[ft[:, 0]], v[ft[:, 2]] - v[ft[:, 0]]), axis=1) / 2
        assert area.min() > 1e-9
        _, counts = edges_of(ft)
        assert counts.max() == 2  # manifold inside the face: an edge has one triangle (boundary) or two


@pytest.mark.parametrize("name", ["sphere", "small_sphere", "big_sphere", "torus", "moved_sphere", "hollow_sphere"])
def test_closed_curved_faces_are_regular_grids(name):
    # Sphere: geodesic grid on an octahedron. Torus: staggered rings, periodic both ways.
    shape, v, t, f = mesh(name)
    for fid, _ in curved_faces(shape):
        ft = t[f == fid]
        e, counts = edges_of(ft)
        assert (counts == 2).all()  # closed: the seam is welded
        valence = np.bincount(e.ravel())[np.unique(ft)]
        assert set(np.unique(valence)) <= {4, 6}  # 4 only at the 6 octahedron corners of a sphere
        assert (valence == 4).sum() in (0, 6)
        assert min_angles(v, ft).min() > 10


@pytest.mark.parametrize("name", ["cylinder", "cone", "box_with_hole"])
def test_side_between_two_circles_is_one_row(name):
    # The generatrix is straight: one row of triangles between the two circles, every triangle touching both.
    shape, v, t, f = mesh(name)
    for fid, _ in curved_faces(shape):
        ft = t[f == fid]
        e, counts = edges_of(ft)
        rim = np.unique(e[counts == 1])
        assert len(rim) == len(np.unique(ft))  # no interior vertices
        assert len(ft) == len(rim)  # n quads split in two: 2n triangles for 2n rim vertices
        assert (counts == 2).sum() == len(ft)  # seam welded: n diagonals + n generatrix edges are shared


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_triangles_stay_within_the_deflection(name):
    shape, v, t, f = mesh(name)
    for fid, face in curved_faces(shape):
        ft = t[f == fid]
        surf = BRep_Tool.Surface_s(face)
        a, b, c = v[ft[:, 0]], v[ft[:, 1]], v[ft[:, 2]]
        for p in np.concatenate([(a + b + c) / 3, (a + b) / 2, (b + c) / 2, (c + a) / 2]):
            proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*p), surf)
            assert proj.NbPoints() > 0 and proj.LowerDistance() < LIN * 1.05


def test_curved_face_boundary_matches_the_neighbouring_faces():
    shape, v, t, f = mesh("cylinder")
    (side, _), = curved_faces(shape)
    st = t[f == side]
    e, counts = edges_of(st)
    rim = {tuple(p) for p in np.round(v[np.unique(e[counts == 1])], 6)}
    caps = {tuple(p) for p in np.round(v[np.unique(t[f != side])], 6)}
    assert rim and rim <= caps


def test_face_planes_are_exact_and_outward():
    # Draw Solid places solids on these planes: they must be exact (float64), not the float32 display mesh.
    shape = (bd.Box(40, 30, 130, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)) - bd.Cylinder(5, 300)).wrapped
    planes = tessellate.face_planes(shape)
    assert planes.dtype == np.float64 and planes.shape == (len(tessellate.face_map(shape)), 4)
    rows = {tuple(p) for p in planes if not np.isnan(p[0])}
    assert (0.0, 0.0, 1.0, 130.0) in rows and (0.0, 0.0, -1.0, 0.0) in rows
    assert (1.0, 0.0, 0.0, 20.0) in rows and (0.0, -1.0, 0.0, 15.0) in rows
    assert np.isnan(planes[:, 0]).sum() == 1  # the hole's cylindrical face has no plane


NORMAL_SHAPES = {
    **SHAPES,
    "cut_cylinder": lambda: bd.Cylinder(150, 300) - bd.Pos(150, 0, 0) * bd.Rot(0, 90, 0) * bd.Cylinder(60, 200)
    - bd.Pos(0, 150, 50) * bd.Rot(90, 0, 0) * bd.Cylinder(40, 200),
    "filleted": lambda: bd.fillet(bd.Box(40, 30, 20).edges().filter_by(bd.Axis.Z), radius=5),
}


@pytest.mark.parametrize("name", sorted(NORMAL_SHAPES))
def test_vertex_normals_are_the_exact_surface_normals(name):
    # Shading uses these as custom normals: long thin triangles on a trimmed curved face then shade right.
    shape = NORMAL_SHAPES[name]().wrapped
    v, t, f, n = tessellate.tessellate_with_normals(shape, LIN, ANG)
    v, n = v.astype(np.float64), n.astype(np.float64)
    assert n.shape == v.shape and np.allclose(np.linalg.norm(n, axis=1), 1.0, atol=1e-5)
    tri_n = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    for k in range(3):  # every corner normal on the triangle's outer side
        assert (np.einsum("ij,ij->i", tri_n, n[t[:, k]]) > 0).all()
    for fid, face in enumerate(tessellate.face_map(shape)):
        surf = BRep_Tool.Surface_s(face)
        idx = np.unique(t[f == fid])
        for i in idx[:: max(1, len(idx) // 40)]:
            proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*v[i]), surf)
            u, w = proj.LowerDistanceParameters()
            from OCP.GeomLProp import GeomLProp_SLProps
            props = GeomLProp_SLProps(surf, u, w, 1, 1e-9)
            if not props.IsNormalDefined():
                continue  # a pole or an apex
            e = props.Normal()
            assert abs(abs(e.X() * n[i, 0] + e.Y() * n[i, 1] + e.Z() * n[i, 2]) - 1.0) < 1e-5


# -- the display mesh: faces welded along BRep edges (milestone 2, ADR 0008) --------------------------------------

DISPLAY_SHAPES = {**SHAPES, "filleted_box": lambda: bd.fillet(bd.Box(40, 30, 20).edges().filter_by(bd.Axis.Z), 5),
                  "box": lambda: bd.Box(40, 30, 20)}


def display(name):
    shape = DISPLAY_SHAPES[name]().wrapped
    return shape, tessellate.display_mesh(shape, LIN, ANG)


def poly_starts(m):
    return np.concatenate([[0], np.cumsum(m.poly_sizes)[:-1]]).astype(np.int64)


def fan(m):
    """(triangles (t, 3) of vertex indices, polygon of each triangle): each polygon fan-triangulated."""
    tris, owner = [], []
    for p, (start, size) in enumerate(zip(poly_starts(m), m.poly_sizes)):
        loop = m.loops[start:start + size]
        for k in range(1, size - 1):
            tris.append((loop[0], loop[k], loop[k + 1]))
            owner.append(p)
    return np.array(tris, dtype=np.int64), np.array(owner)


def sides(m):
    """(sorted vertex pair, polygon) of every polygon side."""
    starts = poly_starts(m)
    nxt = np.arange(len(m.loops)) + 1
    ends = starts + m.poly_sizes
    nxt[ends - 1] = starts
    pairs = np.sort(np.stack([m.loops, m.loops[nxt]], axis=1), axis=1)
    return pairs, np.repeat(np.arange(len(m.poly_sizes)), m.poly_sizes)


def volume(v, t):
    v = v.astype(np.float64)
    return np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum() / 6


def _brep_edges_to_mesh(shape):
    """BRep edges a display mesh must carry: not seams, not degenerate (poles, apexes)."""
    from OCP.BRep import BRep_Tool as BT
    wanted = set()
    faces = tessellate.face_map(shape)
    for eid, edge in enumerate(tessellate.edge_map(shape)):
        if BT.Degenerated_s(edge) or any(BT.IsClosed_s(edge, f) for f in faces):
            continue
        wanted.add(eid)
    return wanted


@pytest.mark.parametrize("name", sorted(DISPLAY_SHAPES))
def test_display_mesh_is_closed(name):
    shape, m = display(name)
    pairs, _ = sides(m)
    _, counts = np.unique(pairs, axis=0, return_counts=True)
    assert (counts == 2).all()  # every mesh edge has two polygons: welded along the BRep edges
    v, t, _, _ = tessellate.tessellate_with_normals(shape, LIN, ANG)
    assert volume(m.verts, fan(m)[0]) == pytest.approx(volume(v, t), rel=1e-6)
    if _brep_edges_to_mesh(shape):  # faces that meet share their boundary vertices now
        assert len(m.verts) < len(v)
    assert len(m.poly_face) == len(m.poly_sizes) and m.corner_normals.shape == (len(m.loops), 3)
    assert m.poly_sizes.sum() == len(m.loops) and m.poly_sizes.min() >= 3


def test_flat_faces_without_holes_are_one_polygon():
    # Blender's Bevel (Clamp Overlap on) clamps to the tightest vertex: a triangulated cap has short chords
    _, box = display("box")
    assert sorted(box.poly_sizes.tolist()) == [4] * 6
    shape, cyl = display("cylinder")
    flat = [fid for fid, face in enumerate(tessellate.face_map(shape))
            if BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane]
    for fid in flat:
        assert (cyl.poly_face == fid).sum() == 1 and cyl.poly_sizes[cyl.poly_face == fid][0] > 8
    assert (cyl.poly_sizes[~np.isin(cyl.poly_face, flat)] == 3).all()
    shape, holed = display("box_with_hole")  # top and bottom have a hole: convex polygons, a collar around it
    per_face = np.bincount(holed.poly_face)
    assert sum(1 for c in per_face if c == 1) == 4  # the four sides
    starts = poly_starts(holed)
    v = holed.verts.astype(np.float64)
    for fid, face in enumerate(tessellate.face_map(shape)):
        if BRepAdaptor_Surface(face).GetType() != GeomAbs_Plane or per_face[fid] == 1:
            continue
        polys = np.nonzero(holed.poly_face == fid)[0]
        assert holed.poly_sizes[polys].min() >= 3  # radial quads; outside, triangles where a merge would fold
        normal = np.zeros(3)
        for p in polys:  # every polygon convex, all turning the same way
            loop = v[holed.loops[starts[p]:starts[p] + holed.poly_sizes[p]]]
            assert len(set(holed.loops[starts[p]:starts[p] + holed.poly_sizes[p]].tolist())) == len(loop)
            turns = np.cross(np.roll(loop, -1, 0) - loop, np.roll(loop, -2, 0) - np.roll(loop, -1, 0))
            normal = turns.sum(0) if not normal.any() else normal
            assert (turns @ normal > -1e-9).all()


def _plane_polygons(shape, m):
    """{flat face id: [polygon vertices (float64)]} of the flat faces meshed as more than one polygon."""
    starts = poly_starts(m)
    v = m.verts.astype(np.float64)
    out = {}
    for fid, face in enumerate(tessellate.face_map(shape)):
        polys = np.nonzero(m.poly_face == fid)[0]
        if BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane and len(polys) > 1:
            out[fid] = [v[m.loops[starts[p]:starts[p] + m.poly_sizes[p]]] for p in polys]
    return out


def _corner_angles(loop):
    a, b = np.roll(loop, 1, 0) - loop, np.roll(loop, -1, 0) - loop
    cos = (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


COLLARED = {  # (part, smallest polygon corner in degrees on its holed faces; before the collars 0.13-1.16)
    "plate_small_hole": (lambda: bd.Box(200, 200, 5) - bd.Cylinder(3, 20), 40),
    "washer": (lambda: bd.Cylinder(20, 5) - bd.Cylinder(8, 20), 40),
    "slot": (lambda: bd.Box(60, 30, 10) - bd.extrude(bd.SlotOverall(30, 8), 20, both=True), 8),
    # the bosses are 4 mm from the face's edge: the thin strip between their collars and that edge can only be
    # fans to the edge's two ends (no vertex may be added on a BRep edge)
    "two_bosses": (lambda: bd.Box(100, 40, 100) + [bd.Pos(x, -20, 38) * bd.Rot(90, 0, 0) * bd.Cylinder(8, 30)
                                                    for x in (-25, 25)], 0.1),
    "bolt_circle": (lambda: bd.Cylinder(50, 5) - [bd.Pos(35 * math.cos(a), 35 * math.sin(a), 0) * bd.Cylinder(4, 20)
                                                   for a in np.arange(6) * math.pi / 3], 30),
}


@pytest.mark.parametrize("name", sorted(COLLARED))
def test_curved_holes_in_flat_faces_get_collars(name):
    # Without interior vertices a flat face's convex pieces next to a curved hole reach its outer corners: fans
    # of slivers (0.13-1.16 degrees). Collars of radial quads keep every piece convex and well shaped
    # (docs/research/2026-09-28-planar-faces-with-holes.md).
    make, min_angle = COLLARED[name]
    shape = make().wrapped
    m = tessellate.display_mesh(shape, 1.0, ANG)
    pairs, _ = sides(m)
    _, counts = np.unique(np.sort(pairs, axis=1), axis=0, return_counts=True)
    assert (counts == 2).all()  # closed: the collars' nodes are shared by their pieces only
    v, t, f, _ = tessellate.tessellate_with_normals(shape, 1.0, ANG)
    v = v.astype(np.float64)
    holed = _plane_polygons(shape, m)
    assert holed
    for fid, polys in holed.items():
        normal = np.cross(polys[0][1] - polys[0][0], polys[0][2] - polys[0][0])
        area = 0.0
        for loop in polys:
            a, b = np.roll(loop, -1, 0) - loop, np.roll(loop, -2, 0) - np.roll(loop, -1, 0)
            sin = np.cross(a, b) @ (normal / np.linalg.norm(normal)) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
            assert (sin > -1e-5).all()  # convex (a collar's sides have straight corners, up to float32 rounding)
            assert _corner_angles(loop).min() > min_angle
            area += np.linalg.norm(np.cross(loop, np.roll(loop, -1, 0)).sum(0)) / 2
        tri = t[f == fid]
        expected = np.linalg.norm(np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]]), axis=1).sum() / 2
        assert area == pytest.approx(expected, rel=1e-6)  # the pieces tile the face's boundary polygon


def _catmull_clark_folds(m):
    """Child polygons of one Catmull-Clark step (Subdivision Surface on a closed mesh) facing against their
    parent polygon."""
    v = m.verts.astype(np.float64)
    polys = [m.loops[s:s + n].tolist() for s, n in zip(poly_starts(m), m.poly_sizes)]
    fp = np.array([v[p].mean(0) for p in polys])
    edge_faces, vert_faces, vert_edges = {}, {}, {}
    for i, p in enumerate(polys):
        for k in range(len(p)):
            a, b = p[k], p[(k + 1) % len(p)]
            edge_faces.setdefault((min(a, b), max(a, b)), []).append(i)
            vert_faces.setdefault(a, []).append(i)
    for e in edge_faces:
        for x in e:
            vert_edges.setdefault(x, []).append(e)
    ep = {e: (v[e[0]] + v[e[1]] + fp[f].sum(0)) / (2 + len(f)) for e, f in edge_faces.items()}
    vp = {}
    for x, fs in vert_faces.items():
        n = len(fs)
        mid = np.mean([(v[a] + v[b]) / 2 for a, b in vert_edges[x]], axis=0)
        vp[x] = (fp[fs].mean(0) + 2 * mid + (n - 3) * v[x]) / n
    folds = 0
    for i, p in enumerate(polys):
        parent = sum(np.cross(v[p[k]] - fp[i], v[p[(k + 1) % len(p)]] - fp[i]) for k in range(len(p)))
        for k in range(len(p)):
            a, b, c = p[k - 1], p[k], p[(k + 1) % len(p)]
            q = [vp[b], ep[(min(b, c), max(b, c))], fp[i], ep[(min(a, b), max(a, b))]]
            child = np.cross(q[1] - q[0], q[3] - q[0]) + np.cross(q[3] - q[2], q[1] - q[2])
            folds += np.dot(child, parent) <= 0
    return folds


@pytest.mark.parametrize("name", sorted(COLLARED))
def test_subdivision_folds_nothing_around_holes(name):
    # A convex polygon holding a long straight run of nodes (a collar's side) has its Catmull-Clark face point far
    # along the run: the children at the run's nodes are slivers that fold. Milestone 2's fans of slivers folded
    # too (plate 72, bolt circle 36, two bosses 17 children); plain collars as well (slot 32, two bosses 38).
    folds = _catmull_clark_folds(tessellate.display_mesh(COLLARED[name][0]().wrapped, 1.0, ANG))
    assert folds == 0


@pytest.mark.parametrize("name", sorted(DISPLAY_SHAPES))
def test_edges_carry_brep_edge_ids(name):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    shape, m = display(name)
    pairs, owner = sides(m)
    face = m.poly_face[owner]
    uniq, inv = np.unique(pairs, axis=0, return_inverse=True)
    between = {tuple(uniq[k]) for k in range(len(uniq)) if len(set(face[inv.ravel() == k])) > 1}
    assert between == {tuple(e) for e in m.edges}  # exactly the mesh edges between two faces
    assert set(m.edge_ids.tolist()) == _brep_edges_to_mesh(shape)
    brep = tessellate.edge_map(shape)
    for (a, b), eid in list(zip(m.edges, m.edge_ids))[:: max(1, len(m.edges) // 60)]:
        mid = (m.verts[a].astype(np.float64) + m.verts[b]) / 2
        dist = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*mid)).Vertex(), brep[eid])
        assert dist.Value() < LIN


def test_sharp_edges():
    # filleted box: 8 arcs + 8 straight top/bottom edges are sharp; the 8 vertical edges where the fillets meet
    # the flat sides are tangent
    for name, sharp, smooth in (("box", 12, 0), ("cylinder", 2, 0), ("filleted_box", 16, 8)):
        shape, m = display(name)
        ids = {int(e): bool(s) for e, s in zip(m.edge_ids, m.edge_sharp)}
        assert sum(ids.values()) == sharp and len(ids) - sum(ids.values()) == smooth, name
        per_edge = {}
        for e, s in zip(m.edge_ids, m.edge_sharp):
            per_edge.setdefault(int(e), set()).add(int(s))
        assert all(len(v) == 1 for v in per_edge.values())  # a BRep edge is sharp or smooth along its length


@pytest.mark.parametrize("name", ["filleted_box", "box_with_hole", "cone"])
def test_corner_normals_are_the_exact_surface_normals(name):
    from OCP.GeomLProp import GeomLProp_SLProps
    shape, m = display(name)
    faces = tessellate.face_map(shape)
    corner_poly = np.repeat(np.arange(len(m.poly_sizes)), m.poly_sizes)
    v = m.verts.astype(np.float64)
    for k in range(0, len(m.loops), max(1, len(m.loops) // 150)):
        face = faces[m.poly_face[corner_poly[k]]]
        surf = BRep_Tool.Surface_s(face)
        proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*v[m.loops[k]]), surf)
        props = GeomLProp_SLProps(surf, *proj.LowerDistanceParameters(), 1, 1e-9)
        if not props.IsNormalDefined():
            continue
        e = props.Normal()
        assert abs(abs(float(np.dot(m.corner_normals[k], (e.X(), e.Y(), e.Z())))) - 1) < 1e-5
    # a welded vertex on a sharp edge has one normal per face
    a, _ = m.edges[m.edge_sharp == 1][0]
    assert len({tuple(np.round(m.corner_normals[k], 4)) for k in np.nonzero(m.loops == a)[0]}) >= 2


# -- review findings (milestone 2 phase A) -------------------------------------------------------------------------

NON_MANIFOLD = {
    # two boxes touching along one edge (Draw Solid with corner snapping on a box makes this)
    "edge_contact": lambda: bd.Box(10, 10, 10) + bd.Pos(10, 10, 0) * bd.Box(10, 10, 10),
    # a square hole whose corner touches the side face
    "corner_touch": lambda: bd.Box(20, 20, 10) - bd.Pos(5, 0, 0) * bd.Rot(0, 0, 45) * bd.Box(50 ** 0.5, 50 ** 0.5, 20),
    # two solids sharing a face
    "two_solids": lambda: bd.Compound([bd.Box(10, 10, 10), bd.Pos(10, 0, 0) * bd.Box(10, 10, 10)]),
}


@pytest.mark.parametrize("name", sorted(NON_MANIFOLD))
def test_non_manifold_solids_still_get_a_mesh(name):
    shape = NON_MANIFOLD[name]().wrapped
    m = tessellate.display_mesh(shape, LIN, ANG)
    v, t, _, _ = tessellate.tessellate_with_normals(shape, LIN, ANG)
    assert volume(m.verts, fan(m)[0]) == pytest.approx(volume(v, t), rel=1e-6)
    pairs, _ = sides(m)
    _, counts = np.unique(pairs, axis=0, return_counts=True)
    assert (counts == 2).sum() > 0 and len(m.edges) == len(m.edge_ids) == len(m.edge_sharp)
    assert set(m.edge_ids.tolist()) <= set(range(len(tessellate.edge_map(shape))))


def test_mirrored_solids_have_outward_planes_and_merged_polygons():
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_IN
    box = bd.mirror(bd.Location((3, 4, 5), (10, 20, 30)) * bd.Box(40, 30, 20), bd.Plane.YZ).wrapped
    planes = tessellate.face_planes(box)
    for fid, face in enumerate(tessellate.face_map(box)):
        c = bd.Face(face).center()
        centre = np.array([c.X, c.Y, c.Z])
        assert abs(planes[fid, :3] @ centre - planes[fid, 3]) < 1e-9
        behind = BRepClass3d_SolidClassifier(box, gp_Pnt(*(centre - planes[fid, :3] * 0.1)), 1e-7)
        assert behind.State() == TopAbs_IN  # a step against the normal is inside: the normal points out
    holed = bd.mirror(bd.Box(40, 30, 20) - bd.Pos(5, 0, 0) * bd.Cylinder(6, 30), bd.Plane.YZ).wrapped
    m = tessellate.display_mesh(holed, LIN, ANG)
    assert m.poly_sizes.max() > 3  # the holed faces merged (the convexity test isn't inverted)


# -- trimmed curved faces (maintainer's fillet.blend, 2026-09-27): no fans of slivers ------------------------------

def _maintainer_fillet():
    """The maintainer's fillet.blend part (2026-09-27): a corner cut by a big cylinder, holes, and every edge of
    the cut filleted: toroidal and cylindrical fillet faces bounded by curves (not iso-lines) where they meet."""
    import os
    import provenance
    source = open(os.path.join(os.path.dirname(__file__), "data", "maintainer_fillet_part.py")).read()
    ns = provenance.namespace(provenance.Tracker())
    exec(provenance.instrument(source, "<part>"), ns)
    return ns["result"]


TRIMMED = {
    "maintainer_fillet": _maintainer_fillet,
    "holed_cylinder": lambda: bd.Cylinder(150, 300) - bd.Pos(150, 0, 0) * bd.Rot(0, 90, 0) * bd.Cylinder(60, 200),
}


@pytest.mark.parametrize("name", sorted(TRIMMED))
def test_trimmed_curved_faces_have_no_slivers(name):
    shape = TRIMMED[name]().wrapped
    lin = 1.0
    v, t, f, _ = tessellate.tessellate_with_normals(shape, lin, ANG)
    v = v.astype(np.float64)
    for fid, face in curved_faces(shape):
        ft = t[f == fid]
        kind = BRepAdaptor_Surface(face).GetType()
        if kind not in (GeomAbs_Cylinder, GeomAbs_Cone):  # curved both ways: a lattice, few thin triangles
            thin = (min_angles(v, ft) < 5).mean()  # BRepMesh on the fillet's torus: 82% under 10 degrees
            assert thin <= 0.05, f"face {fid}: {thin:.0%} of its triangles under 5 degrees"
        # no fans (the maintainer's screenshot): few triangles around any vertex (a cylinder's one row
        # along its straight generatrix is long thin triangles by design, ADR 0005)
        valence = np.bincount(ft.ravel())
        assert valence.max() <= 12, f"face {fid}: a vertex with {valence.max()} triangles"
        surf = BRep_Tool.Surface_s(face)
        a, b, c = v[ft[:, 0]], v[ft[:, 1]], v[ft[:, 2]]
        for p in np.concatenate([(a + b + c) / 3, (a + b) / 2])[:: max(1, len(ft) // 50)]:
            proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*p), surf)
            assert proj.NbPoints() > 0 and proj.LowerDistance() < lin * 1.05
    m = tessellate.display_mesh(shape, lin, ANG)
    pairs, _ = sides(m)
    _, counts = np.unique(pairs, axis=0, return_counts=True)
    assert (counts == 2).all()  # still welded to the neighbouring faces


# -- ADR 0010: edge-first, grid-based tessellation ---------------------------------------------------------------

def _maintainer_big():
    """The maintainer's second screenshot: the same kind of corner cut on a bigger box, with bigger fillets."""
    import provenance
    source = """
with BuildPart() as part:
    Box(1000.0, 1000.0, 1000.0, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    extrude(face("box_1", "+Z"), amount=-200.0, mode=Mode.SUBTRACT)  # feature: push_1
    with Locations(Location((-500.0, 500.0, 800.0), (0.0, 0.0, 0.0))):  # feature: cut_1
        Cylinder(500.0, 4000.0, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    fillet(edges_of(face("cut_1", "side")), radius=40.0)  # feature: fillet_1

result = part.part
"""
    ns = provenance.namespace(provenance.Tracker())
    exec(provenance.instrument(source, "<part>"), ns)
    return ns["result"]


GRID_PARTS = {
    "maintainer_fillet": _maintainer_fillet,
    "maintainer_big": _maintainer_big,
    "filleted_box": lambda: bd.fillet(bd.Box(100, 80, 60).edges(), 10),
    "holed_cylinder": TRIMMED["holed_cylinder"],
    "cut_sphere": lambda: bd.Sphere(50) - bd.Box(60, 60, 60, align=(bd.Align.MIN,) * 3),
}


def _surface_type(face):
    return BRepAdaptor_Surface(face).GetType()


@pytest.mark.parametrize("name", sorted(GRID_PARTS))
def test_grid_parts_are_closed_valid_and_within_the_tolerance(name):
    shape = GRID_PARTS[name]().wrapped
    lin = 1.0
    m = tessellate.display_mesh(shape, lin, ANG)
    pairs, _ = sides(m)
    _, counts = np.unique(np.sort(pairs, axis=1), axis=0, return_counts=True)
    assert (counts == 2).all()  # every face meshed from the shared edge nodes: welded everywhere
    v, t, f, _ = tessellate.tessellate_with_normals(shape, lin, ANG)
    v = v.astype(np.float64)
    vol = np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum() / 6
    area = np.linalg.norm(np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]]), axis=1).sum() / 2
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    assert vol > 0 and abs(vol - props.Mass()) < area * lin
    for fid, face in curved_faces(shape):
        ft = t[f == fid]
        surf = BRep_Tool.Surface_s(face)
        a, b, c = v[ft[:, 0]], v[ft[:, 1]], v[ft[:, 2]]
        for p in np.concatenate([(a + b + c) / 3, (a + b) / 2, (b + c) / 2, (c + a) / 2])[:: max(1, len(ft) // 40)]:
            proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*p), surf)
            assert proj.NbPoints() > 0 and proj.LowerDistance() < lin * 1.05


def _interior_valence(ft):
    e, counts = edges_of(ft)
    rim = set(np.unique(e[counts == 1]).tolist())
    valence = np.bincount(ft.ravel())
    inner = [k for k in np.unique(ft) if k not in rim]
    return valence[inner]


@pytest.mark.parametrize("name", ["maintainer_fillet", "maintainer_big"])
def test_fillet_bands_are_structured_rows(name):
    # The maintainer's screenshots: a mosaic on the fillet band along the big cylinder (ADR 0005's addendum).
    # A structured grid split by one diagonal rule: every interior vertex has 6 triangles.
    shape = GRID_PARTS[name]().wrapped
    v, t, f, _ = tessellate.tessellate_with_normals(shape, 1.0, ANG)
    bands = [fid for fid, face in curved_faces(shape) if _surface_type(face) == GeomAbs_Torus
             and tessellate._revolution(face) is None]
    assert bands
    for fid in bands:
        valence = _interior_valence(t[f == fid])
        assert len(valence) and (valence == 6).mean() >= 0.95, f"face {fid}: {np.bincount(valence)}"


@pytest.mark.parametrize("name", ["maintainer_fillet", "maintainer_big"])
def test_trimmed_cylinder_is_aligned_columns(name):
    # The maintainer's blue face: a quarter cylinder between two fillets fanned irregularly (its top and bottom
    # edges had different node counts). Its straight direction is one row: every triangle touches both arcs,
    # which carry the same number of nodes (columns), so no vertex has more than 3 triangles.
    shape = GRID_PARTS[name]().wrapped
    v, t, f, _ = tessellate.tessellate_with_normals(shape, 1.0, ANG)
    v = v.astype(np.float64)
    big = [fid for fid, face in curved_faces(shape) if _surface_type(face) == GeomAbs_Cylinder
           and BRepAdaptor_Surface(face).Cylinder().Radius() > 100]
    assert len(big) == 1
    ft = t[f == big[0]]
    z = v[np.unique(ft), 2]
    top, bottom = np.isclose(z, z.max(), atol=1e-3), np.isclose(z, z.min(), atol=1e-3)
    assert (top | bottom).all() and top.sum() == bottom.sum()
    assert np.bincount(ft.ravel()).max() <= 3


def test_trimmed_grid_face_has_regular_cells():
    # A cylinder with a hole: a grid trimmed by the hole, iso-line boundaries on the grid's own nodes.
    shape = GRID_PARTS["holed_cylinder"]().wrapped
    v, t, f, _ = tessellate.tessellate_with_normals(shape, 1.0, ANG)
    side = [fid for fid, face in curved_faces(shape) if _surface_type(face) == GeomAbs_Cylinder
            and BRepAdaptor_Surface(face).Cylinder().Radius() > 100][0]
    valence = _interior_valence(t[f == side])
    assert (valence == 6).mean() >= 0.6, np.bincount(valence)


def test_tiny_edges_do_not_run_slivers_across_a_face():
    # The fillet band's ends have 0.05 mm edges (where the corner blends meet): their grid lines are merged, so
    # at most a couple of triangles per tiny edge are thin, not a column across the band.
    shape = GRID_PARTS["maintainer_fillet"]().wrapped
    v, t, f, _ = tessellate.tessellate_with_normals(shape, 1.0, ANG)
    v = v.astype(np.float64)
    for fid, face in curved_faces(shape):
        if _surface_type(face) == GeomAbs_Torus and tessellate._revolution(face) is None:
            assert (min_angles(v, t[f == fid]) < 5).sum() <= 4


def test_grid_tessellation_is_fast():
    import time
    shape = GRID_PARTS["maintainer_big"]().wrapped
    start = time.perf_counter()
    tessellate.display_mesh(shape, 1.0, ANG)
    assert time.perf_counter() - start < 1.0


# -- regressions found by fuzzing (2026-09-28: the maintainer's worker hung on a filleted corner cut) --------------

def _read_brep(name):
    import os
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Shape
    shape = TopoDS_Shape()
    BRepTools.Read_s(shape, os.path.join(os.path.dirname(__file__), "data", name), BRep_Builder())
    return shape


@pytest.mark.parametrize("name", [
    "hang_vertex_blend.brep",        # corner patches with curvature spikes: 10^15 nodes asked of a 33 mm edge
    "hang_thin_fillet.brep",         # a 0.7 mm fillet along a 1.1 m arc: thousands of columns from the 4:1 cap
    "open_collinear_boundary.brep",  # nearly collinear boundary nodes on a flat face: slivers kept by a centroid test
])
def test_fuzzed_parts_mesh_quickly_and_closed(name):
    import time
    shape = _read_brep(name)
    start = time.perf_counter()
    m = tessellate.display_mesh(shape, 1.0, ANG)
    assert time.perf_counter() - start < 2.0
    pairs, _ = sides(m)
    _, counts = np.unique(np.sort(pairs, axis=1), axis=0, return_counts=True)
    assert (counts == 2).all()


def test_implausible_fillet_edge_is_a_clear_error_not_a_hang():
    # An OCCT fillet left a 335 m edge on a 1 m part (its pcurve wound thousands of times): neither our grids nor
    # BRepMesh mesh it in reasonable time. The part reports an error the user can act on.
    import time
    shape = _read_brep("implausible_fillet_edge.brep")
    start = time.perf_counter()
    with pytest.raises(RuntimeError, match="far longer than the part"):
        tessellate.display_mesh(shape, 1.0, ANG)
    assert time.perf_counter() - start < 2.0


def test_invalid_part_is_rejected_before_tessellation():
    # The one fuzzed part whose face fell back to BRepMesh (mesh open along it) is an invalid OCCT result: a torus
    # fillet face whose boundary covers its v=0 circle more than once around (overlapping itself in (u, v)).
    # BRepCheck rejects it, and the runner reports "not a valid solid" before meshing (runner.run); display_mesh
    # still returns a mesh for it instead of hanging. 347 valid fuzzed parts (2026-09-28) had no fallback.
    shape = _read_brep("fallback_open.brep")
    assert not tessellate.check(shape)["valid"]
    tessellate.display_mesh(shape, 1.0, ANG)
