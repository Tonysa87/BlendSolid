"""Display-mesh topology: curved faces of revolution are structured grids, welded, within the deflection."""
import math

import build123d as bd
import numpy as np
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.BRep import BRep_Tool
from OCP.GeomAbs import GeomAbs_Plane
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
