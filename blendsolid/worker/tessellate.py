"""OCP helpers for the worker: validity, volume, face numbering and tessellation with BRep face IDs.

Faces are numbered with TopExp.MapShapes (deterministic for a given shape): brep_face_id = 0-based index.
"""
import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS


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


def tessellate(shape, lin_defl=0.1, ang_defl=0.3):
    """Vertices are not shared between faces: sharp edges between BRep faces, unambiguous face map."""
    BRepTools.Clean_s(shape)
    BRepMesh_IncrementalMesh(shape, lin_defl, False, ang_defl, True)
    verts, tris, tri_face, offset = [], [], [], 0
    for fid, face in enumerate(face_map(shape)):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            raise RuntimeError(f"face {fid} has no triangulation")
        trsf = loc.Transformation()
        nodes = [tri.Node(i).Transformed(trsf) for i in range(1, tri.NbNodes() + 1)]
        pts = np.array([(q.X(), q.Y(), q.Z()) for q in nodes], dtype=np.float64).reshape(-1, 3)
        t = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)],
                     dtype=np.int32).reshape(-1, 3) - 1
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
