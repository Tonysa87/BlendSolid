"""Objectives 2 and 3: OCCT solid → Blender mesh with brep_face_id attribute; picking with ray_cast.

Usage: blender -b --factory-startup --python spike/s02_s03_mesh_pick.py [-- --save <file.blend>]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402

_common.add_ocp_path()

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex  # noqa: E402
from OCP.BRepExtrema import BRepExtrema_DistShapeShape  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402

import bl_bridge  # noqa: E402
import occ_model  # noqa: E402


def objective2():
    t0 = time.perf_counter()
    shape, (verts, tris, tri_face), tm = occ_model.build_and_tessellate()
    info = occ_model.check(shape)
    t1 = time.perf_counter()
    obj = bl_bridge.ensure_object("BS_Solid")
    bl_bridge.fill_mesh(obj.data, verts, tris, tri_face)
    t2 = time.perf_counter()
    print(f"[2] check={info}")
    print(f"[2] mesh: {len(obj.data.vertices)} vertices, {len(obj.data.polygons)} triangles, "
          f"BRep faces in the attribute: {len(set(bl_bridge.face_ids(obj.data)))}")
    print(f"[2] times ms: build={tm['build']*1e3:.1f} tessellate={tm['tessellate']*1e3:.1f} "
          f"total OCCT={(t1-t0)*1e3:.1f} mesh Blender={(t2-t1)*1e3:.1f}")
    expected = 40 * 30 * 20 + np.pi * 36 * 5 - (1 - np.pi / 4) * 25 * 20
    ok = info["valid"] and abs(info["volume"] - expected) < 1e-6 and len(obj.data.polygons) > 0
    # volume from the mesh too (closed and oriented): confirms triangle orientation
    v = np.array([vv.co for vv in obj.data.vertices])
    tri = np.array([p.vertices[:] for p in obj.data.polygons])
    mesh_vol = np.einsum("ij,ij->i", v[tri[:, 0]], np.cross(v[tri[:, 1]], v[tri[:, 2]])).sum() / 6
    print(f"[2] volume BRep={info['volume']:.3f} expected={expected:.3f} mesh={mesh_vol:.3f}")
    ok = ok and abs(mesh_vol - expected) / expected < 0.01
    print("[2] RESULT", "PASS" if ok else "FAIL")
    return shape, obj


def objective3(shape, obj):
    """For each BRep face: a ray from outside towards a point of the face; the attribute must return that ID."""
    faces = occ_model.face_map(shape)
    ids = bl_bridge.face_ids(obj.data)
    dg = bpy.context.evaluated_depsgraph_get()
    fails = 0
    for fid, face in enumerate(faces):
        # point certainly on the face: centroid of one of its mesh triangles
        polys = np.nonzero(ids == fid)[0]
        poly = obj.data.polygons[int(polys[len(polys) // 2])]
        p, n = poly.center.copy(), poly.normal.copy()
        origin = obj.matrix_world @ (p + n * 0.5)
        direction = (obj.matrix_world.to_3x3() @ -n).normalized()
        hit, loc, nor, index, hobj, _ = bpy.context.scene.ray_cast(dg, origin, direction)
        got = int(ids[index]) if hit and hobj == obj else None
        # check independent of the mesh: does the hit point lie on BRep face `got`?
        lp = obj.matrix_world.inverted() @ loc
        vtx = BRepBuilderAPI_MakeVertex(gp_Pnt(*lp)).Vertex()
        dist = BRepExtrema_DistShapeShape(vtx, faces[got]).Value() if got is not None else float("inf")
        good = got == fid and dist <= 0.1  # 0.1 = linear deflection of the tessellation
        status = "ok" if good else "FAIL"
        fails += not good
        print(f"[3] face {fid}: {occ_model.BRepAdaptor_Surface(face).GetType().name:>16} "
              f"ray → poly {index} → brep_face_id {got}, distance hit↔BRep face {dist:.4f} {status}")
    # same test with the object moved and rotated: scene ray_cast works in world space
    obj.location = (100, -50, 10)
    obj.rotation_euler = (0.3, 0.2, 1.0)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    moved_fails = 0
    for fid in range(len(faces)):
        polys = np.nonzero(ids == fid)[0]
        poly = obj.data.polygons[int(polys[0])]
        origin = obj.matrix_world @ (poly.center + poly.normal * 0.5)
        direction = (obj.matrix_world.to_3x3() @ -poly.normal).normalized()
        hit, loc, nor, index, hobj, _ = bpy.context.scene.ray_cast(dg, origin, direction)
        moved_fails += not (hit and hobj == obj and ids[index] == fid)
    obj.location = (0, 0, 0)
    obj.rotation_euler = (0, 0, 0)
    print(f"[3] {len(faces)} faces, errors={fails}, errors with transformed object={moved_fails}")
    print("[3] RESULT", "PASS" if fails == 0 and moved_fails == 0 else "FAIL")


for o in list(bpy.data.objects):  # remove the default cube: it would intercept the rays
    bpy.data.objects.remove(o)
shape, obj = objective2()
objective3(shape, obj)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if "--save" in argv:
    path = argv[argv.index("--save") + 1]
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("SAVED", path)
