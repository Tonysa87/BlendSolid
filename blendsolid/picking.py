"""The CAD edge or face under the mouse, for tools that write references into a part's script (milestone 2).

The ray hits the evaluated mesh (after modifiers), whose polygons carry the BRep face id they come from; the CAD
edges around that face are read from the part's own mesh (`brep_edge_id` on its edges), so a Bevel modifier that
rounded them away doesn't hide them. An edge within EDGE_PX pixels of the hit is picked; otherwise the face
(meaning all its edges). What a pick writes is the worker's reference text (ADR 0009).
"""
from dataclasses import dataclass, field

import numpy as np
from mathutils import Vector, geometry

from . import part

EDGE_PX = 10  # an edge this close to the hit (on screen, before the interface scale) is the one picked

_cache = {}  # mesh session_uid -> (mesh tag, _EdgeData)


@dataclass
class Pick:
    obj: object
    kind: str                 # "EDGE" or "FACE"
    id: int                   # BRep edge or face id
    reference: str            # what a tool writes: edge_between(...) or edges_of(face(...))
    segments: list = field(default_factory=list)  # [(Vector, Vector)] world: the edge, or the face's edges


@dataclass
class _EdgeData:
    co: np.ndarray            # (n, 3) local vertex positions
    face_edges: dict          # BRep face id -> array of BRep edge ids around it
    edge_pairs: dict          # BRep edge id -> (k, 2) vertex index pairs of its mesh edges
    edge_polys: dict          # BRep edge id -> (k, 2) the polygons on either side of each of those mesh edges
    poly_normal: np.ndarray   # (p, 3) local polygon normals
    poly_centre: np.ndarray   # (p, 3) local polygon centres


def _edge_data(obj):
    me = obj.data
    tag = me.get(part.HASH_KEY)
    cached = _cache.get(me.session_uid)
    if cached is not None and cached[0] == tag:
        return cached[1]
    edge_attr, face_attr = me.attributes.get(part.EDGE_ATTR), me.attributes.get(part.FACE_ATTR)
    if edge_attr is None or face_attr is None or edge_attr.domain != "EDGE":
        return None
    ids = np.empty(len(me.edges), np.int32)
    edge_attr.data.foreach_get("value", ids)
    ev = np.empty(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    loop_edge = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("edge_index", loop_edge)
    sizes = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", sizes)
    fids = np.empty(len(me.polygons), np.int32)
    face_attr.data.foreach_get("value", fids)
    face_of_loop = np.repeat(fids, sizes)
    on_cad = ids[loop_edge] >= 0
    pairs = np.unique(np.stack([face_of_loop[on_cad], ids[loop_edge[on_cad]]], axis=1), axis=0)
    face_edges = {}
    for fid, eid in pairs:
        face_edges.setdefault(int(fid), []).append(int(eid))
    # the two polygons of each mesh edge (a closed mesh: two loops per edge; a non-manifold edge has no id)
    poly_of_loop = np.repeat(np.arange(len(sizes)), sizes)
    by_edge = np.argsort(loop_edge, kind="stable")
    first = np.searchsorted(loop_edge[by_edge], np.arange(len(me.edges)))
    edge_pairs, edge_polys = {}, {}
    cad = np.nonzero(ids >= 0)[0]
    order = np.argsort(ids[cad], kind="stable")
    for eid, group in _groups(ids[cad][order], cad[order]):
        edge_pairs[eid] = ev[group]
        edge_polys[eid] = np.stack([poly_of_loop[by_edge[first[group]]],
                                    poly_of_loop[by_edge[np.minimum(first[group] + 1, len(by_edge) - 1)]]], axis=1)
    normals = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", normals)
    centres = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("center", centres)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    data = _EdgeData(co.reshape(-1, 3), {k: np.array(v) for k, v in face_edges.items()}, edge_pairs, edge_polys,
                     normals.reshape(-1, 3), centres.reshape(-1, 3))
    _cache[me.session_uid] = (tag, data)
    return data


def _groups(keys, values):
    """(key, values) runs of sorted `keys`."""
    if not len(keys):
        return
    cuts = np.nonzero(np.diff(keys))[0] + 1
    for start, end in zip(np.concatenate([[0], cuts]), np.concatenate([cuts, [len(keys)]])):
        yield int(keys[start]), values[start:end]


def edge_segments(obj, eid, data=None):
    """World segments of obj's BRep edge `eid` (its mesh edges)."""
    data = data or _edge_data(obj)
    if data is None or eid not in data.edge_pairs:
        return []
    mw = obj.matrix_world
    return [(mw @ Vector(data.co[a]), mw @ Vector(data.co[b])) for a, b in data.edge_pairs[eid]]


def face_segments(obj, fid, data=None):
    data = data or _edge_data(obj)
    if data is None:
        return []
    return [s for eid in data.face_edges.get(fid, ()) for s in edge_segments(obj, int(eid), data)]


def _distance(point, segments):
    best = float("inf")
    for a, b in segments:
        closest, t = geometry.intersect_point_line(point, a, b)
        closest = a if t < 0 else b if t > 1 else closest
        best = min(best, (point - closest).length)
    return best


def edge_is_sharp(obj, eid):
    """Is BRep edge `eid` of obj's mesh a sharp CAD edge (not between tangent faces, which can't be rounded)?"""
    me = obj.data
    ids, sharp = me.attributes.get(part.EDGE_ATTR), me.attributes.get("sharp_edge")
    if ids is None or sharp is None:
        return True  # unknown: let the worker decide
    values = np.empty(len(me.edges), np.int32)
    ids.data.foreach_get("value", values)
    found = np.nonzero(values == eid)[0]
    return not len(found) or bool(sharp.data[int(found[0])].value)


def pick(context, origin, direction, pixel):
    """The CAD edge (within EDGE_PX × `pixel` world units of the hit) or face of a writable part under the ray,
    or None (no part, or a part without reference texts: no features, or not recomputed yet)."""
    from . import ops_draw
    depsgraph = context.evaluated_depsgraph_get()
    found = ops_draw._first_hit(context, depsgraph, origin, direction)
    if found is None:
        return None
    location, _, index, obj = found
    if not part.is_local_part(obj):
        return None
    fid = part.face_id(obj.evaluated_get(depsgraph).data, index)
    face_ref = part.face_reference(obj, fid)
    data = _edge_data(obj)
    if not face_ref or data is None:
        return None
    location = Vector(location)
    best, best_eid = float("inf"), None
    for eid in data.face_edges.get(fid, ()):
        d = _distance(location, edge_segments(obj, int(eid), data))
        if d < best and part.edge_reference(obj, int(eid)):
            best, best_eid = d, int(eid)
    ui = (context.preferences.system.ui_scale if context.preferences else 0.0) or 1.0  # 0 in background mode
    if best_eid is not None and best <= EDGE_PX * ui * pixel:
        return Pick(obj, "EDGE", best_eid, part.edge_reference(obj, best_eid), edge_segments(obj, best_eid, data))
    return Pick(obj, "FACE", fid, f"edges_of({face_ref})", face_segments(obj, fid, data))


def segments_of(obj, reference):
    """World segments of what `reference` (a text a pick wrote) names on obj now, or [] if nothing does any more
    (the ids change with every recompute; the texts are what a selection keeps)."""
    data = _edge_data(obj)
    if data is None:
        return []
    edges = obj.data.get(part.EDGE_REFS_KEY) or []
    if reference in edges:
        return edge_segments(obj, list(edges).index(reference), data)
    faces = obj.data.get(part.FACE_REFS_KEY) or []
    if reference.startswith("edges_of(") and reference[len("edges_of("):-1] in faces:
        return face_segments(obj, list(faces).index(reference[len("edges_of("):-1]), data)
    return []


def edge_frames(obj, reference):
    """For each mesh segment of what `reference` names on obj: (a, b, n1, n2, c1, c2) in world space — the
    segment, its two faces' outward normals and a point of each face (drawing.fillet_preview's inputs)."""
    data = _edge_data(obj)
    if data is None:
        return []
    eids = []
    edges = list(obj.data.get(part.EDGE_REFS_KEY) or [])
    faces = list(obj.data.get(part.FACE_REFS_KEY) or [])
    if reference in edges:
        eids = [edges.index(reference)]
    elif reference.startswith("edges_of(") and reference[len("edges_of("):-1] in faces:
        eids = [int(e) for e in data.face_edges.get(faces.index(reference[len("edges_of("):-1]), ())]
    mw = obj.matrix_world
    rot = mw.to_3x3().inverted_safe().transposed()
    out = []
    for eid in eids:
        for (va, vb), (p1, p2) in zip(data.edge_pairs.get(eid, ()), data.edge_polys.get(eid, ())):
            out.append((mw @ Vector(data.co[va]), mw @ Vector(data.co[vb]),
                        (rot @ Vector(data.poly_normal[p1])).normalized(), (rot @ Vector(data.poly_normal[p2])).normalized(),
                        mw @ Vector(data.poly_centre[p1]), mw @ Vector(data.poly_centre[p2])))
    return out


def clear_cache():
    _cache.clear()
