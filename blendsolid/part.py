"""BlendSolid parts: a mesh object whose geometry comes from a history script stored in a Text datablock.

The script is the source of truth; the mesh is a cache tagged with the hash of the script that produced it.
"""
import hashlib
import os

import bpy
import numpy as np

from . import params, trust

FACE_ATTR = "brep_face_id"
HASH_KEY = "bs_source_hash"
ERROR_TAG_KEY = "bs_error_tag"
_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "default_part.py")
_syncing = False


def default_source():
    with open(_TEMPLATE, encoding="utf-8") as f:
        return f.read()


def is_syncing():
    return _syncing


def part_objects():
    return [o for o in bpy.data.objects if o.type == "MESH" and o.blendsolid_script is not None]


def source_of(obj):
    return obj.blendsolid_script.as_string()


def source_hash(source):
    return hashlib.sha1(source.encode("utf-8")).hexdigest()


def current_tag(obj):
    """The tag a mesh computed from obj's current script carries (compare with applied_hash())."""
    return source_hash(source_of(obj))


def applied_hash(obj):
    return obj.data.get(HASH_KEY)


def new_part(context, source=None, name="Part"):
    source = default_source() if source is None else source
    text = bpy.data.texts.new(f".{name}.py")  # dot name: hidden from Blender's ID menus (ADR 0002)
    text.from_string(source)
    trust.mark_trusted(text)  # created in this session: the user's own script (ADR 0004)
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    context.collection.objects.link(obj)
    obj.blendsolid_script = text
    sync_params(obj, source)
    return obj


def apply_result(obj, event):
    fill_mesh(obj.data, event["verts"], event["tris"], event["tri_face"])
    obj.data[HASH_KEY] = event["tag"]
    set_error(obj, "")


def set_error(obj, message, line=None, tag=None):
    """Set (or clear, with message="") the part's error. `tag` records the script hash this error refers
    to, as an ID property (not a registered RNA field): tick() clears the error once the object's current
    script tag no longer matches it. A runtime-set error passes the tag of the script that failed; a
    UI-set error (e.g. a ParamError from ui._on_param_value) passes the current (unwritten) script's hash,
    so it survives while the script is unchanged and clears once it changes — including by reverting to a
    previously-good source. tag=None (the default) clears the stored tag along with the message."""
    obj.blendsolid_error = message
    obj.blendsolid_error_line = line or 0
    if tag is None:
        if ERROR_TAG_KEY in obj:
            del obj[ERROR_TAG_KEY]
    else:
        obj[ERROR_TAG_KEY] = tag


def error_tag(obj):
    return obj.get(ERROR_TAG_KEY)


def fill_mesh(mesh, verts, tris, tri_face):
    mesh.clear_geometry()
    nt = len(tris)
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", np.ascontiguousarray(verts, dtype=np.float32).ravel())
    mesh.loops.add(nt * 3)
    mesh.loops.foreach_set("vertex_index", np.ascontiguousarray(tris, dtype=np.int32).ravel())
    mesh.polygons.add(nt)
    mesh.polygons.foreach_set("loop_start", np.arange(0, nt * 3, 3, dtype=np.int32))
    mesh.polygons.foreach_set("use_smooth", np.ones(nt, dtype=bool))  # sharp between faces: verts not shared
    attr = mesh.attributes.get(FACE_ATTR) or mesh.attributes.new(FACE_ATTR, "INT", "FACE")
    attr.data.foreach_set("value", np.ascontiguousarray(tri_face, dtype=np.int32))
    mesh.update()


def mesh_volume(mesh):
    v = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", v)
    t = np.empty(len(mesh.polygons) * 3, dtype=np.int32)
    mesh.polygons.foreach_get("vertices", t)
    v, t = v.reshape(-1, 3), t.reshape(-1, 3)
    return float(np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum() / 6)


def sync_params(obj, source=None):
    """Mirror the script's parameter block into obj.blendsolid_params (no-op if the script doesn't parse)."""
    global _syncing
    try:
        found = params.parse_params(source_of(obj) if source is None else source)
    except (SyntaxError, params.ParamError):
        return
    coll = obj.blendsolid_params
    _syncing = True
    try:
        if [p.name for p in coll] != [p.name for p in found]:
            coll.clear()
            for p in found:
                item = coll.add()
                item.name = p.name
        for item, p in zip(coll, found):
            if item.is_int != p.is_int:
                item.is_int = p.is_int
            if abs(item.value - p.value) > 1e-6 * max(1.0, abs(p.value)):
                item.value = p.value
    finally:
        _syncing = False


def set_param(obj, name, value):
    obj.blendsolid_script.from_string(params.set_param(source_of(obj), name, value))


def ensure_unique_scripts():
    """Reconcile scripts after object/mesh operations BlendSolid doesn't observe directly:

    - Ctrl+L (Link Object Data), or any other way several objects end up sharing one mesh: those objects
      are ONE part (controller ruling), so they must share one script too. The later ones (sorted by name)
      adopt the first one's script.
    - Shift+D (full duplicate): the object and its mesh are copied but the Text is not; an independent copy
      (ends up on a different mesh than the object it was copied from) gets its own script. Alt+D (linked
      duplicate) already shares both mesh and script, so it is left untouched by this step.
    """
    by_mesh = {}
    for obj in part_objects():
        by_mesh.setdefault(obj.data.name, []).append(obj)
    for objs in by_mesh.values():
        if len(objs) < 2:
            continue
        objs.sort(key=lambda o: o.name)
        first = objs[0]
        for obj in objs[1:]:
            if obj.blendsolid_script != first.blendsolid_script:
                obj.blendsolid_script = first.blendsolid_script

    by_text = {}
    for obj in part_objects():
        by_text.setdefault(obj.blendsolid_script.name, []).append(obj)
    for objs in by_text.values():
        objs.sort(key=lambda o: o.name)
        first_mesh = objs[0].data.name
        for obj in objs[1:]:
            if obj.data.name != first_mesh:  # an independent copy, not a linked duplicate
                source_text = obj.blendsolid_script
                obj.blendsolid_script = source_text.copy()
                if trust.text_trusted(source_text):
                    trust.mark_trusted(obj.blendsolid_script)  # a copy is exactly as trusted as its source


def primary_objects():
    """One object per distinct mesh: the one whose name sorts first. Objects sharing a mesh are one part
    (see ensure_unique_scripts): only the primary object needs to be reconciled/submitted for that part."""
    by_mesh = {}
    for obj in part_objects():
        current = by_mesh.get(obj.data.name)
        if current is None or obj.name < current.name:
            by_mesh[obj.data.name] = obj
    return sorted(by_mesh.values(), key=lambda o: o.name)


def mesh_siblings(obj):
    """Other part objects sharing obj's mesh (e.g. after Ctrl+L Link Object Data, or Alt+D). These are not
    reconciled themselves (see primary_objects()), but their own blendsolid_params/blendsolid_error must
    still reflect the primary's state, since Task 7's panel shows them per object."""
    return [o for o in part_objects() if o is not obj and o.data.name == obj.data.name]


def primary(obj):
    """The primary object for obj's part: obj itself, or whichever object sharing its mesh sorts first by
    name (see primary_objects()). runtime._inflight/_failed/_synced are keyed by the primary's object name,
    so anything that must act on the actual part (e.g. the Recompute operator) needs to resolve this first
    rather than acting on whatever object happens to be active."""
    return min((obj, *mesh_siblings(obj)), key=lambda o: o.name)
