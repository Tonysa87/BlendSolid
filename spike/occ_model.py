"""Spike geometry in pure OCP (no bpy): used both in Blender and in the worker.

Model: box + cylinder (union) + fillet on a vertical edge, with an optional "push face"
on the top face of the box. Faces are numbered with TopExp.MapShapes
(deterministic order for the same script) → brep_face_id = 0-based index.
"""
import time

import numpy as np

from OCP.BRep import BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepGProp import BRepGProp
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
from OCP.BRepTools import BRepTools
from OCP.GProp import GProp_GProps
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape  # OCP 8
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec

DEFAULT_PARAMS = {
    "box": (40.0, 30.0, 20.0),
    "cyl_radius": 6.0,
    "cyl_height": 25.0,   # the cylinder starts at z=0: it sticks out (cyl_height - box_z) above the box
    "fillet": 5.0,        # radius on the vertical edge at (0, 0)
    "push_top": 0.0,      # push of the top face of the box along +Z
}


def face_map(shape):
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, m)
    return [TopoDS.Face(m.FindKey(i)) for i in range(1, m.Extent() + 1)]


def face_frame(face):
    """Point and outward normal at the parametric center of a face."""
    ad = BRepAdaptor_Surface(face)
    u = 0.5 * (ad.FirstUParameter() + ad.LastUParameter())
    v = 0.5 * (ad.FirstVParameter() + ad.LastVParameter())
    props = BRepLProp_SLProps(ad, u, v, 1, 1e-6)
    p, n = props.Value(), props.Normal()
    if face.Orientation() == TopAbs_REVERSED:
        n.Reverse()
    return (p.X(), p.Y(), p.Z()), (n.X(), n.Y(), n.Z())


def top_face_index(shape, z):
    """Index of the planar face with +Z normal at height z (the top face of the box)."""
    for i, f in enumerate(face_map(shape)):
        ad = BRepAdaptor_Surface(f)
        if ad.GetType() != 0:  # GeomAbs_Plane
            continue
        p, n = face_frame(f)
        if n[2] > 0.999 and abs(p[2] - z) < 1e-6:
            return i
    raise ValueError(f"no top face at z={z}")


def push_face(shape, face, dist):
    """Push/pull of a planar face: prism of the face along its normal, then fuse or cut."""
    if abs(dist) < 1e-9:
        return shape
    _, n = face_frame(face)
    vec = gp_Vec(*[c * dist for c in n])
    prism = BRepPrimAPI_MakePrism(face, vec).Shape()
    op = BRepAlgoAPI_Fuse(shape, prism) if dist > 0 else BRepAlgoAPI_Cut(shape, prism)
    op.Build()
    if not op.IsDone():
        raise RuntimeError("push_face: boolean failed")
    unify = ShapeUpgrade_UnifySameDomain(op.Shape(), True, True, True)
    unify.Build()
    return unify.Shape()


def build(params=None):
    p = dict(DEFAULT_PARAMS, **(params or {}))
    bx, by, bz = p["box"]
    box = BRepPrimAPI_MakeBox(bx, by, bz).Shape()
    cyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(bx / 2, by / 2, 0), gp_Dir(0, 0, 1)),
                                   p["cyl_radius"], p["cyl_height"]).Shape()
    fuse = BRepAlgoAPI_Fuse(box, cyl)
    fuse.Build()
    shape = fuse.Shape()

    if p["fillet"] > 0:
        # vertical edge of the box at x=0, y=0
        edges = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_EDGE, edges)
        target = None
        for i in range(1, edges.Extent() + 1):
            e = TopoDS.Edge(edges.FindKey(i))
            v1, v2 = TopExp.FirstVertex_s(e), TopExp.LastVertex_s(e)
            a, b = BRep_Tool.Pnt_s(v1), BRep_Tool.Pnt_s(v2)
            if all(abs(q.X()) < 1e-9 and abs(q.Y()) < 1e-9 for q in (a, b)) and abs(a.Z() - b.Z()) > 1e-6:
                target = e
                break
        mf = BRepFilletAPI_MakeFillet(shape)
        mf.Add(p["fillet"], target)
        mf.Build()
        if not mf.IsDone():
            raise RuntimeError("fillet failed")
        shape = mf.Shape()

    if p["push_top"]:
        top = face_map(shape)[top_face_index(shape, bz)]
        shape = push_face(shape, top, p["push_top"])
    return shape


def check(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return {"valid": BRepCheck_Analyzer(shape).IsValid(), "volume": props.Mass(),
            "faces": len(face_map(shape))}


def tessellate(shape, lin_defl=0.1, ang_defl=0.3):
    """Tessellates the solid. Returns verts (N,3) float32, tris (M,3) int32, tri_face (M,) int32.

    Vertices are not shared between different faces (each face has its own): sharp edges
    and an unambiguous triangle→BRep face map.
    """
    BRepTools.Clean_s(shape)
    BRepMesh_IncrementalMesh(shape, lin_defl, False, ang_defl, True)
    verts, tris, tri_face = [], [], []
    offset = 0
    for fid, face in enumerate(face_map(shape)):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            raise RuntimeError(f"face {fid} has no triangulation")
        trsf = loc.Transformation()
        nn = tri.NbNodes()
        pts = np.empty((nn, 3), dtype=np.float64)
        for i in range(1, nn + 1):
            q = tri.Node(i).Transformed(trsf)
            pts[i - 1] = (q.X(), q.Y(), q.Z())
        nt = tri.NbTriangles()
        t = np.empty((nt, 3), dtype=np.int32)
        for i in range(1, nt + 1):
            t[i - 1] = tri.Triangle(i).Get()
        t -= 1
        if face.Orientation() == TopAbs_REVERSED:
            t = t[:, ::-1]
        verts.append(pts)
        tris.append(t + offset)
        tri_face.append(np.full(nt, fid, dtype=np.int32))
        offset += nn
    return (np.concatenate(verts).astype(np.float32), np.concatenate(tris),
            np.concatenate(tri_face))


def build_and_tessellate(params=None, lin_defl=0.1, ang_defl=0.3):
    """Full recompute with timings, used for the direct vs worker comparison."""
    t0 = time.perf_counter()
    shape = build(params)
    t1 = time.perf_counter()
    verts, tris, tri_face = tessellate(shape, lin_defl, ang_defl)
    t2 = time.perf_counter()
    return shape, (verts, tris, tri_face), {"build": t1 - t0, "tessellate": t2 - t1}
