"""BlendSolid parts: a mesh object whose geometry comes from a history script stored in a Text datablock.

The script is the source of truth; the mesh is a cache tagged with the hash of the script that produced it
and of the unit factor it was converted with (ADR 0003: scripts are in millimetres, meshes in Blender units).
"""
import hashlib
import os
import uuid

import bpy
import numpy as np

from . import params, trust

FACE_ATTR = "brep_face_id"
HASH_KEY = "bs_source_hash"
ERROR_TAG_KEY = "bs_error_tag"
PART_ID_KEY = "bs_part_id"  # on the part's Text: identity follows the script (Shift+D copies it, Alt+D and
                            # Ctrl+L share it — see ensure_unique_scripts()), which is what ref() names
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


def unit_factor(scene=None):
    """Blender units per script millimetre (ADR 0003): 0.001 / scale_length, so a 40 mm box is 0.04 in a
    default (metre) scene and 40 in a scene whose unit scale is 0.001. Parts follow the active scene."""
    if scene is None:
        scene = getattr(bpy.context, "scene", None)
        if scene is None and bpy.data.scenes:
            scene = bpy.data.scenes[0]
    scale = scene.unit_settings.scale_length if scene is not None else 1.0
    return 0.001 / scale if scale > 0 else 0.001


def tag_for(source, factor):
    """The tag stored on a mesh computed from `source` and converted with `factor` (see applied_hash()):
    changing either one makes the mesh stale."""
    return source_hash(f"{source}\0unit-factor={factor!r}")


def current_tag(obj, factor=None):
    """The tag a mesh computed from obj's current script carries (compare with applied_hash())."""
    return tag_for(source_of(obj), unit_factor() if factor is None else factor)


def applied_hash(obj):
    return obj.data.get(HASH_KEY)


def new_part(context, source=None, name="Part"):
    source = default_source() if source is None else source
    text = bpy.data.texts.new(f".{name}.py")  # dot name: hidden from Blender's ID menus (ADR 0002)
    text.from_string(source)
    text.use_fake_user = False  # texts.new() adds a fake user: a deleted part would leave its script behind
    text[PART_ID_KEY] = new_part_id()
    trust.mark_trusted(text)  # created in this session: the user's own script (ADR 0004)
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    context.collection.objects.link(obj)
    obj.blendsolid_script = text
    sync_params(obj, source)
    return obj


def apply_result(obj, event, factor):
    """`factor`: the unit factor event["tag"] was computed with (the caller checked it is still current)."""
    verts = np.asarray(event["verts"], dtype=np.float64) * factor  # millimetres -> Blender units
    fill_mesh(obj.data, verts, event["tris"], event["tri_face"])
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
            if p.is_int and item.value_int != int(p.value):
                item.value_int = int(p.value)  # the panel shows integer parameters through this mirror
    finally:
        _syncing = False


def set_param(obj, name, value):
    obj.blendsolid_script.from_string(params.set_param(source_of(obj), name, value))


def is_linked(obj):
    """Does obj's part come (even partly) from a library? Such parts are read-only: never written to, never
    submitted (their file's own session keeps them up to date)."""
    script = obj.blendsolid_script
    return bool(obj.library or obj.data.library or (script is not None and script.library))


def is_local_part(obj):
    """Is obj a BlendSolid part this session owns (a mesh object with a script, not linked from a library)?
    Used wherever code needs to tell a real, writable part from anything else (part_groups(), and later
    tools that scan bpy.data.objects for parts to offer as cutters/selectors)."""
    return obj.type == "MESH" and obj.blendsolid_script is not None and not is_linked(obj)


def part_groups():
    """One pass over bpy.data.objects: every local part object, grouped by mesh IDENTITY (session_uid, not
    name: a linked library mesh can share a local mesh's name), each group sorted by object name. Objects
    sharing a mesh are one part; the first of each group is its primary, the only one reconciled/submitted.
    Linked parts (is_linked) are left out entirely. tick() builds this once and passes it around, so the
    tick stays linear in the number of objects."""
    groups = {}
    for obj in bpy.data.objects:
        if not is_local_part(obj):
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


def ensure_unique_part_ids(groups):
    """Reconcile part ids after operations ensure_unique_scripts() doesn't cover: Copy/paste, Append, or
    copying a Text datablock can produce a separate Text (a different session_uid) that still carries the
    same PART_ID_KEY as another one. Left alone, later code that indexes parts by id would keep only one of
    them (e.g. a cutter silently not cutting). `groups` comes from part_groups(), already reconciled by
    ensure_unique_scripts() (each group now shares exactly one script). Every Text after the first — ordered
    by the name of the first object using it, for a deterministic winner — gets a fresh id; texts are
    compared by session_uid, never by name."""
    first_name_by_text = {}
    for objs in groups.values():
        text = objs[0].blendsolid_script
        if text is None:
            continue
        name = objs[0].name
        if text.session_uid not in first_name_by_text or name < first_name_by_text[text.session_uid][1]:
            first_name_by_text[text.session_uid] = (text, name)
    by_id = {}
    for text, name in first_name_by_text.values():
        pid = text.get(PART_ID_KEY)
        if pid is not None:
            by_id.setdefault(pid, []).append((name, text))
    for entries in by_id.values():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda e: e[0])
        for _, text in entries[1:]:
            text[PART_ID_KEY] = new_part_id()


def copy_script(text):
    copy = text.copy()
    copy.use_fake_user = False  # (copy() keeps the source's fake user)
    copy[PART_ID_KEY] = new_part_id()  # an independent copy is a different part (copy() kept the source's id)
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


def new_part_id():
    return uuid.uuid4().hex


def part_id(obj):
    """The part's stable identity (a hex string stored on its script), or None (e.g. a milestone 1 file)."""
    script = obj.blendsolid_script
    return None if script is None else script.get(PART_ID_KEY)


def ensure_part_id(obj):
    """part_id(obj), giving the part one first if it has none. Only call it from an operator (undoable)."""
    if part_id(obj) is None:
        obj.blendsolid_script[PART_ID_KEY] = new_part_id()
    return part_id(obj)


def is_scaled(obj, tolerance=1e-6):
    """Parts keep scale 1 (sizes belong in the script): gizmos and cutters refuse scaled ones."""
    return any(abs(s - 1.0) > tolerance for s in obj.matrix_world.to_scale())
