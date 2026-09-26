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


def source_of(obj):
    return obj.blendsolid_script.as_string()


def source_hash(source):
    return hashlib.sha1(source.encode("utf-8")).hexdigest()


def tag_for(source):
    """The tag stored on a mesh computed from `source` (see applied_hash())."""
    return source_hash(source)


def current_tag(obj):
    """The tag a mesh computed from obj's current script carries (compare with applied_hash())."""
    return tag_for(source_of(obj))


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


def is_linked(obj):
    """Does obj's part come (even partly) from a library? Such parts are read-only: never written to, never
    submitted (their file's own session keeps them up to date)."""
    script = obj.blendsolid_script
    return bool(obj.library or obj.data.library or (script is not None and script.library))


def part_groups():
    """One pass over bpy.data.objects: every local part object, grouped by mesh IDENTITY (session_uid, not
    name: a linked library mesh can share a local mesh's name), each group sorted by object name. Objects
    sharing a mesh are one part; the first of each group is its primary, the only one reconciled/submitted.
    Linked parts (is_linked) are left out entirely. tick() builds this once and passes it around, so the
    tick stays linear in the number of objects."""
    groups = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.blendsolid_script is None or is_linked(obj):
            continue
        groups.setdefault(obj.data.session_uid, []).append(obj)
    for objs in groups.values():
        if len(objs) > 1:
            objs.sort(key=lambda o: o.name)
    return groups


def ensure_unique_scripts(groups, tag_of):
    """Reconcile scripts after object/mesh operations BlendSolid doesn't observe directly. `groups` comes from
    part_groups(); `tag_of(text)` gives the tag a mesh computed from that script would carry.

    - Ctrl+L (Link Object Data), or any other way several objects end up sharing one mesh: those objects
      are ONE part (controller ruling), so they must share one script too. The winner is the script whose
      tag equals the mesh's applied hash, i.e. the script the shared mesh was computed from (with Ctrl+L,
      the active object's); only if none matches, the first object's by name.
    - Shift+D (full duplicate): the object and its mesh are copied but the Text is not; an independent copy
      (a different mesh sharing the script of another part) gets its own copy of the script. Alt+D (linked
      duplicate) already shares both mesh and script, so it is left untouched by this step.
    Texts are compared by identity, never by name.
    """
    for objs in groups.values():
        if len(objs) < 2:
            continue
        first_script = objs[0].blendsolid_script
        if all(o.blendsolid_script == first_script for o in objs):
            continue
        applied = applied_hash(objs[0])
        winner = next((o.blendsolid_script for o in objs if tag_of(o.blendsolid_script) == applied), first_script)
        for obj in objs:
            if obj.blendsolid_script != winner:
                obj.blendsolid_script = winner

    by_text = {}
    for objs in groups.values():  # every object of a group now shares one script
        by_text.setdefault(objs[0].blendsolid_script.session_uid, []).append(objs)
    for group_list in by_text.values():
        if len(group_list) < 2:
            continue
        group_list.sort(key=lambda g: g[0].name)
        for objs in group_list[1:]:  # an independent copy, not a linked duplicate
            source_text = objs[0].blendsolid_script
            copy = copy_script(source_text)
            for obj in objs:
                obj.blendsolid_script = copy


def copy_script(text):
    copy = text.copy()
    if trust.text_trusted(text):
        trust.mark_trusted(copy)  # a copy is exactly as trusted as its source (ADR 0004)
    return copy


def mesh_siblings(obj):
    """Other local part objects sharing obj's mesh (e.g. after Ctrl+L Link Object Data, or Alt+D). A full
    scan: for UI code acting on one object; tick() uses part_groups() instead."""
    mesh = obj.data
    return [o for o in bpy.data.objects
            if o != obj and o.type == "MESH" and o.data == mesh and o.blendsolid_script is not None
            and not is_linked(o)]


def primary(obj):
    """The primary object for obj's part: obj itself, or whichever object sharing its mesh sorts first by
    name (see part_groups()). runtime state is keyed by the primary's object name, so anything that must act
    on the actual part (e.g. the Recompute operator) needs to resolve this first rather than acting on
    whatever object happens to be active."""
    return min((obj, *mesh_siblings(obj)), key=lambda o: o.name)
