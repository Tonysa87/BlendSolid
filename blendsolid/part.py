"""BlendSolid parts: a mesh object whose geometry comes from a history script stored in a Text datablock.

The script is the source of truth; the mesh is a cache tagged with the hash of the script that produced it
and of the unit factor it was converted with (ADR 0003: scripts are in millimetres, meshes in Blender units).
"""
import hashlib
import math
import os
import uuid

import bpy
import numpy as np

from . import params, trust

FACE_ATTR = "brep_face_id"
EDGE_ATTR = "brep_edge_id"  # per mesh edge: the BRep edge it lies on, -1 inside a face (ADR 0008)
HASH_KEY = "bs_source_hash"
KEPT_KEY = "bs_kept"  # on a part's Text: given a fake user because a part uses it (see keep_used_scripts())
LAST_KEY = "bs_ref_last"  # on a part's Text: {cutter part id: {"name", "matrices"}} last seen (remember_cutters())
FACE_REFS_KEY = "bs_face_refs"  # per BRep face: the reference a click writes, e.g. 'face("box_1", "+Z")'
EDGE_REFS_KEY = "bs_edge_refs"  # per BRep edge: the same, e.g. 'edge_between(face(...), face(...))'
WARNINGS_KEY = "bs_warnings"  # the last result's doubtful references: ["<line>\t<message>", ...] (ADR 0009)
PLANES_KEY = "bs_face_planes"  # per BRep face: exact plane (nx, ny, nz, d mm, part frame) or NaN, flattened
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


DEFAULT_TOLERANCE = 1.0  # millimetres
MESH_FORMAT = 10  # part of every tag: bumping it recomputes saved meshes (2: face planes, 3: exact normals, 4: welded,
#                 5: trimmed curved faces re-triangulated, ADR 0005 addendum; 6: edge-first grids, ADR 0010;
#                 7: collars around curved holes in flat faces, ADR 0008 addendum; 8: face-point rule 10°;
#                 9: partial collars on the outer loop's curved runs, collars shrink instead of cancelling;
#                 10: coplanar triangle pairs of curved faces as quads)


def tolerance(scene=None):
    """The scene's display tolerance in millimetres: the largest distance allowed between a part's mesh and
    its exact surface (smaller: smoother and heavier meshes)."""
    if scene is None:
        scene = getattr(bpy.context, "scene", None)
        if scene is None and bpy.data.scenes:
            scene = bpy.data.scenes[0]
    value = getattr(scene, "blendsolid_tolerance", DEFAULT_TOLERANCE) if scene is not None else DEFAULT_TOLERANCE
    return value if value > 0 else DEFAULT_TOLERANCE


def tag_for(source, factor, deps=(), tol=None):
    """The tag stored on a mesh computed from `source`, tessellated with tolerance `tol` (default: the scene's)
    and converted with `factor` (see applied_hash()): changing any of them makes the mesh stale. `deps`: one
    string per part the script uses through ref() (its id, tag and placement: see deps.resolve()), so changing
    a cutter makes this part stale too."""
    tol = tolerance() if tol is None else tol
    return source_hash(f"{source}\0unit-factor={factor!r}\0tolerance={tol!r}\0mesh={MESH_FORMAT}"
                       + "".join(f"\0ref={d}" for d in deps))


def current_tag(obj, factor=None):
    """The tag a mesh computed from obj's current script (and cutters) carries (compare with applied_hash())."""
    from . import deps
    return deps.tag_of(obj, factor)


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
    fill_mesh(obj.data, verts, event["loops"], event["poly_sizes"], event["poly_face"], event.get("corner_normals"),
              event.get("edges"), event.get("edge_ids"), event.get("edge_sharp"))
    planes = event.get("planes")
    if planes is not None:
        obj.data[PLANES_KEY] = np.asarray(planes, dtype=np.float64).ravel().tolist()
    elif PLANES_KEY in obj.data:
        del obj.data[PLANES_KEY]
    for key, refs in ((FACE_REFS_KEY, event.get("face_refs")), (EDGE_REFS_KEY, event.get("edge_refs"))):
        if refs is not None:
            obj.data[key] = list(refs)
        elif key in obj.data:
            del obj.data[key]
    warnings = [f"{line or 0}\t{text}" for line, text in event.get("warnings") or ()]
    if warnings:
        obj.data[WARNINGS_KEY] = warnings
    elif WARNINGS_KEY in obj.data:
        del obj.data[WARNINGS_KEY]
    obj.data[HASH_KEY] = event["tag"]
    set_error(obj, "")


def warnings(obj):
    """[(script line or None, message)] of the part's last result: references that resolved doubtfully."""
    out = []
    for item in obj.data.get(WARNINGS_KEY, ()) if obj.data is not None else ():
        line, _, text = str(item).partition("\t")
        out.append((int(line) or None, text))
    return out


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


def fill_mesh(mesh, verts, loops, poly_sizes, poly_face, corner_normals=None, edges=None, edge_ids=None,
              edge_sharp=None):
    """The worker's welded display mesh (ADR 0008): closed, so Blender's modifiers see real edges. CAD edges carry
    their BRep edge id; those where the faces meet at an angle are sharp and bevel-weighted (Bevel's Limit Method
    Weight rounds exactly them); the exact normals are per face corner. A flat face without holes is one
    polygon, the rest triangles."""
    mesh.clear_geometry()
    sizes = np.ascontiguousarray(poly_sizes, dtype=np.int32)
    n_polys, n_loops = len(sizes), int(sizes.sum())
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", np.ascontiguousarray(verts, dtype=np.float32).ravel())
    mesh.loops.add(n_loops)
    mesh.loops.foreach_set("vertex_index", np.ascontiguousarray(loops, dtype=np.int32))
    mesh.polygons.add(n_polys)
    mesh.polygons.foreach_set("loop_start", np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int32))
    mesh.polygons.foreach_set("use_smooth", np.ones(n_polys, dtype=bool))  # sharp edges come from sharp_edge
    attr = _attribute(mesh, FACE_ATTR, "INT", "FACE")
    attr.data.foreach_set("value", np.ascontiguousarray(poly_face, dtype=np.int32))
    mesh.update(calc_edges=True)
    ids = np.full(len(mesh.edges), -1, dtype=np.int32)
    sharp = np.zeros(len(mesh.edges), dtype=bool)
    if edges is not None and len(edges):
        found = _edge_indices(mesh, np.asarray(edges, dtype=np.int64))
        ok = found >= 0
        ids[found[ok]] = np.asarray(edge_ids, dtype=np.int32)[ok]
        sharp[found[ok]] = np.asarray(edge_sharp, dtype=bool)[ok]
    _attribute(mesh, EDGE_ATTR, "INT", "EDGE").data.foreach_set("value", ids)
    _attribute(mesh, "sharp_edge", "BOOLEAN", "EDGE").data.foreach_set("value", sharp)
    _attribute(mesh, "bevel_weight_edge", "FLOAT", "EDGE").data.foreach_set("value", sharp.astype(np.float32))
    if corner_normals is not None and len(corner_normals) == n_loops:
        # The exact surface normals (the worker's): shading doesn't depend on the triangles' shapes.
        custom = _attribute(mesh, "custom_normal", "FLOAT_VECTOR", "CORNER")
        custom.data.foreach_set("vector", np.ascontiguousarray(corner_normals, dtype=np.float32).ravel())
    elif "custom_normal" in mesh.attributes:
        mesh.attributes.remove(mesh.attributes["custom_normal"])
    mesh.update()


def _attribute(mesh, name, data_type, domain):
    """mesh's attribute `name`, created or recreated with this type and domain (an older mesh format may have
    it on another domain)."""
    attr = mesh.attributes.get(name)
    if attr is not None and (attr.domain != domain or attr.data_type != data_type):
        mesh.attributes.remove(attr)
        attr = None
    return attr or mesh.attributes.new(name, data_type, domain)


def _edge_indices(mesh, pairs):
    """Index in mesh.edges of each vertex pair (-1 if missing)."""
    ev = np.empty(len(mesh.edges) * 2, dtype=np.int64)
    mesh.edges.foreach_get("vertices", ev)
    ev = np.sort(ev.reshape(-1, 2), axis=1)
    n = max(int(ev.max(initial=0)), int(pairs.max(initial=0))) + 1
    keys = ev[:, 0] * n + ev[:, 1]
    pairs = np.sort(pairs, axis=1)
    wanted = pairs[:, 0] * n + pairs[:, 1]
    order = np.argsort(keys)
    pos = np.searchsorted(keys[order], wanted)
    pos = np.minimum(pos, len(keys) - 1)
    hit = keys[order][pos] == wanted
    return np.where(hit, order[pos], -1)


def face_id(mesh, polygon_index):
    """The BRep face id of `mesh`'s polygon (a part's mesh, or its evaluated mesh after modifiers, which
    propagate the attribute), or None (no such attribute or polygon, or a negative id)."""
    attr = mesh.attributes.get(FACE_ATTR)
    if attr is None or attr.domain != "FACE" or not 0 <= polygon_index < len(attr.data):
        return None
    fid = attr.data[polygon_index].value
    return fid if fid >= 0 else None


def face_reference(obj, fid):
    """The reference text a click on obj's BRep face `fid` writes into the script, or None (no provenance)."""
    refs = obj.data.get(FACE_REFS_KEY)
    return refs[fid] if refs is not None and fid is not None and 0 <= fid < len(refs) else None


def edge_reference(obj, eid):
    """The reference text a click on obj's BRep edge `eid` writes into the script, or None."""
    refs = obj.data.get(EDGE_REFS_KEY)
    return refs[eid] if refs is not None and eid is not None and 0 <= eid < len(refs) else None


def face_plane(obj, fid):
    """The exact plane (normal, d in millimetres, in obj's frame) of obj's BRep face `fid`, or None (a curved
    face, an unknown id, or a mesh computed before planes were stored)."""
    planes = obj.data.get(PLANES_KEY)
    if planes is None or fid is None or not 0 <= 4 * fid < len(planes):
        return None
    nx, ny, nz, d = planes[4 * fid:4 * fid + 4]
    return None if math.isnan(nx) else ((nx, ny, nz), d)


def is_curved_face(obj, fid):
    planes = obj.data.get(PLANES_KEY)
    return planes is not None and fid is not None and 0 <= 4 * fid < len(planes) and math.isnan(planes[4 * fid])


def curved_face_normal(obj, mesh, polygon_index, location):
    """The surface's world normal at world `location` on polygon `polygon_index` of `mesh` (obj's evaluated
    mesh), if that polygon belongs to a curved BRep face: the corner normals (the worker's exact ones, or what
    the modifiers made of them) interpolated across the triangle of the polygon's fan that holds the point (a
    curved face's polygons are triangles and planar quads) — the polygon's own normal jumps from polygon to
    polygon. None on a flat face."""
    if not is_curved_face(obj, face_id(mesh, polygon_index)):
        return None
    poly = mesh.polygons[polygon_index]
    from mathutils import Vector, geometry
    p = obj.matrix_world.inverted_safe() @ Vector(location)
    best = None
    for i in range(1, poly.loop_total - 1):
        loops = (poly.loop_start, poly.loop_start + i, poly.loop_start + i + 1)
        corners = [mesh.vertices[mesh.loops[k].vertex_index].co for k in loops]
        area = geometry.area_tri(*corners)
        if area <= 0.0:
            continue
        weights = [geometry.area_tri(p, corners[(k + 1) % 3], corners[(k + 2) % 3]) / area for k in range(3)]
        excess = sum(weights) - 1.0  # 0 inside the triangle, > 0 outside
        if best is None or excess < best[0]:
            best = (excess, loops, weights)
    if best is None:
        return None
    _, loops, weights = best
    n = sum((Vector(mesh.corner_normals[k].vector) * w for k, w in zip(loops, weights)), Vector())
    if n.length == 0.0:
        return None
    return (obj.matrix_world.to_3x3().inverted_safe().transposed() @ n).normalized()


def mesh_volume(mesh):
    """Signed volume of a closed mesh, its polygons fan-triangulated (exact for planar polygons)."""
    v = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", v)
    loops = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", loops)
    start = np.empty(len(mesh.polygons), dtype=np.int64)
    size = np.empty(len(mesh.polygons), dtype=np.int64)
    mesh.polygons.foreach_get("loop_start", start)
    mesh.polygons.foreach_get("loop_total", size)
    v = v.reshape(-1, 3)
    tri_poly = np.repeat(np.arange(len(size)), size - 2)  # polygon of each fan triangle
    k = np.arange(len(tri_poly)) - np.repeat(np.cumsum(size - 2) - (size - 2), size - 2)  # triangle within its fan
    first = start[tri_poly]
    a, b, c = v[loops[first]], v[loops[first + k + 1]], v[loops[first + k + 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)


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
    obj=None (e.g. context.object with nothing active) is not a part, not an error. Used wherever code needs
    to tell a real, writable part from anything else (part_groups(), and tools that scan bpy.data.objects, or
    poll() context.object, for parts to offer as targets/cutters/selectors)."""
    return obj is not None and obj.type == "MESH" and obj.blendsolid_script is not None and not is_linked(obj)


def local_part(name):
    """The writable local part called `name` (never a library object of the same name), or None."""
    obj = bpy.data.objects.get((name, None)) if name else None
    return obj if is_local_part(obj) else None


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
    part_groups(); `tag_of(obj)` gives the tag a mesh computed from obj's script (placed as obj) would carry.

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
        winner = next((o.blendsolid_script for o in objs if tag_of(o) == applied), first_script)
        for obj in objs:
            if obj.blendsolid_script != winner:
                obj.blendsolid_script = winner

    by_text = {}
    for objs in groups.values():  # every object of a group now shares one script
        by_text.setdefault(objs[0].blendsolid_script.session_uid, []).append(objs)
    for group_list in by_text.values():
        if len(group_list) < 2:
            continue
        group_list.sort(key=lambda g: g[0].session_uid)  # by age, not name: see ensure_unique_part_ids()
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
    ensure_unique_scripts() (each group now shares exactly one script). The Text of the OLDEST part (the
    lowest session_uid of a primary object using it) keeps the id and every other gets a fresh one: ties are
    broken by age, not name, because Blender names a duplicate with the lowest free suffix (duplicating
    'Cylinder.003' gives 'Cylinder.001'), and the copy must not take the id a ref() names. Texts are compared
    by session_uid, never by name."""
    oldest_by_text = {}
    for objs in groups.values():
        text, uid = objs[0].blendsolid_script, objs[0].session_uid
        if text.session_uid not in oldest_by_text or uid < oldest_by_text[text.session_uid][0]:
            oldest_by_text[text.session_uid] = (uid, text)
    by_id = {}
    for uid, text in oldest_by_text.values():
        pid = text.get(PART_ID_KEY)
        if pid is not None:
            by_id.setdefault(pid, []).append((uid, text))
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


SCALE_TOLERANCE = 1e-5  # |scale - 1| above this is "scaled" (also for deps.relative_matrix's composed matrix)


def is_scaled(obj, tolerance=SCALE_TOLERANCE):
    """Parts keep scale 1 (sizes belong in the script): gizmos and cutters refuse scaled ones."""
    return any(abs(s - 1.0) > tolerance for s in obj.matrix_world.to_scale())


def scaled_message(obj):
    """The message shown wherever a scaled part can't be used (gizmos, cutters): its own name, so callers can
    build a fuller sentence around it (e.g. deps.relative_matrix's "The cutter <this>")."""
    return f"'{obj.name}' is scaled: keep its scale 1 and change its size parameters instead"


def not_canonical_message(obj, error, detail=False):
    """The message shown wherever a tool refuses to edit obj's script because it isn't in the canonical
    feature layout (script_model.NotCanonical). Non-canonical for standard users (ADR 0002: no script syntax
    or line numbers); `detail`, when true (advanced users who can see scripts), appends str(error)."""
    message = f"{obj.name} was made by an older BlendSolid version or edited by hand: the tools can't add " \
              f"features to it"
    return f"{message} ({error})" if detail else message


def script_of_part(pid):
    """The local Text of part id `pid` (it may have no object any more: a deleted cutter), or None."""
    for text in bpy.data.texts:
        if text.library is None and text.get(PART_ID_KEY) == pid:
            return text
    return None


def keep_used_scripts(used_ids):
    """Give the scripts of parts that other parts use (`used_ids`) a fake user, so deleting such a cutter keeps
    its script in the file (restorable); take it back from those no part uses any more. Only fake users this
    function set are ever cleared."""
    for text in bpy.data.texts:
        pid = text.get(PART_ID_KEY)
        if text.library is not None or pid is None:
            continue
        if pid in used_ids:
            if not text.use_fake_user:
                text.use_fake_user = True
                text[KEPT_KEY] = True
        elif text.get(KEPT_KEY):
            text.use_fake_user = False
            del text[KEPT_KEY]


def remember_cutters(obj, resolved_deps):
    """Store on obj's script the name and placements (in obj's frame) of the cutters it uses, as resolved now:
    what a deleted cutter is used and restored with. Written only when something changed."""
    text = obj.blendsolid_script
    if text is None or text.library is not None:
        return
    last = text.get(LAST_KEY)
    known = {} if last is None else last.to_dict()
    wanted = {d["id"]: {"name": d["name"], "matrices": [v for m in d["matrices"] for v in m]}
              for d in resolved_deps if not d.get("deleted")}
    wanted = {**{k: v for k, v in known.items() if k in _refs_of(text)}, **wanted}
    if wanted != known:
        text[LAST_KEY] = wanted


def _refs_of(text):
    from . import script_model
    return set(script_model.references(text.as_string()))


def last_cutter(obj, pid):
    """(name, [3x4 row-major matrices, translation in mm]) of cutter `pid` as obj last used it, or None."""
    last = obj.blendsolid_script.get(LAST_KEY) if obj.blendsolid_script is not None else None
    entry = None if last is None else last.get(pid)
    if entry is None:
        return None
    flat = list(entry["matrices"])
    return entry["name"], [flat[i:i + 12] for i in range(0, len(flat), 12)]
