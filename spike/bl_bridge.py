"""Bridge between tessellated arrays (occ_model.tessellate) and Blender meshes."""
import bpy
import numpy as np

FACE_ATTR = "brep_face_id"


def fill_mesh(mesh, verts, tris, tri_face):
    """Rewrites the geometry of `mesh` and the face attribute holding the BRep ID."""
    mesh.clear_geometry()
    nv, nt = len(verts), len(tris)
    mesh.vertices.add(nv)
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(nt * 3)
    mesh.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
    mesh.polygons.add(nt)
    mesh.polygons.foreach_set("loop_start", np.arange(0, nt * 3, 3, dtype=np.int32))
    # vertices not shared between BRep faces → smooth within a face, sharp edge between faces
    mesh.polygons.foreach_set("use_smooth", np.ones(nt, dtype=bool))
    attr = mesh.attributes.get(FACE_ATTR) or mesh.attributes.new(FACE_ATTR, "INT", "FACE")
    attr.data.foreach_set("value", tri_face.astype(np.int32))
    mesh.update()
    mesh.validate(verbose=False)
    return mesh


def face_ids(mesh):
    a = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.attributes[FACE_ATTR].data.foreach_get("value", a)
    return a


def ensure_object(name, collection=None):
    obj = bpy.data.objects.get(name)
    if obj is None:
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        (collection or bpy.context.scene.collection).objects.link(obj)
    return obj
