"""Parts that use other parts (tool 3, live cutters): `ref("<part id>")` in a part's script.

resolve() turns a part's references into the worker request's `deps` tree (each dependency's script, tag and
placements in the referencing part's frame — one per object showing it, so every linked duplicate of a cutter
cuts — recursively) and into the part's tag. The tag covers the
dependencies' tags and placements, so moving, rotating or editing a cutter makes the parts that use it stale,
and the reconcile loop recomputes them like any other change.

A deleted cutter keeps its script (part.keep_used_scripts()) and the parts using it remember where it was
(part.remember_cutters()): it goes on cutting from there, and can be restored or its cut removed (booleans()).
A reference that can't be used (the cutter's script is lost, parts use each other in a loop, the cutter's
script isn't trusted, the cutter is scaled) raises DepError, whose message is shown on the part; the part is
then not submitted, and error_tag() gives it a tag that changes as soon as the situation does.
"""
from dataclasses import dataclass, field

from . import blobs, part, script_model, trust

class DepError(Exception):
    """A reference that can't be resolved; str(e) is for the user."""


@dataclass(frozen=True)
class Resolved:
    tag: str
    deps: list = field(default_factory=list)  # WorkerClient.submit(deps=...)
    blobs: dict = field(default_factory=dict)  # blob id -> blob Text, of the part and the parts it uses (ADR 0016)

    def blob_data(self):
        """WorkerClient.submit(blobs=...): read only when submitting (a blob can be hundreds of KB)."""
        return {blob_id: blobs.data(text) for blob_id, text in self.blobs.items()}


def part_index(groups=None):
    """part id -> the objects of that local part, primary first (see part.part_groups())."""
    groups = part.part_groups() if groups is None else groups
    index = {}
    for objs in sorted(groups.values(), key=lambda g: g[0].name):
        pid = part.part_id(objs[0])
        if pid is not None and pid not in index:
            index[pid] = objs
    return index


def references(source):
    return script_model.references(source) if "ref(" in source else []  # cheap test first: tick runs often


def relative_matrix(target, dep, factor):
    """The 3x4 row-major transform from dep's frame to target's frame, translation in millimetres."""
    if part.is_scaled(target):
        # checked before composing the matrix: a scaled target skews the composed matrix's scale too, and
        # would otherwise be misreported as a scaled cutter (whichever cutter happens to be resolved first).
        raise DepError(f"This part {part.scaled_message(target)}")
    m = target.matrix_world.inverted_safe() @ dep.matrix_world
    if any(abs(s - 1.0) > part.SCALE_TOLERANCE for s in m.to_scale()):
        raise DepError(f"The cutter {part.scaled_message(dep)}")
    rows = [[m[i][j] for j in range(4)] for i in range(3)]
    for row in rows:
        row[3] /= factor  # Blender units -> script millimetres (ADR 0003)
    return [v for row in rows for v in row]


def _matrix_key(matrix):
    return ",".join(script_model.fmt(v) for v in matrix)  # rounded: float noise must not change the tag


def error_tag(source, factor, message):
    return part.tag_for(source, factor, [f"error:{message}"])


def _blobs_of(script, source, label=None):
    """{blob id: blob Text} of the imported() calls in `source` (ADR 0016); raises DepError when one is missing.
    The ids are in the script text, so the tag already covers the blobs' contents."""
    found = {}
    for blob_id in script_model.imports(source):
        text = blobs.find(script, blob_id)
        if text is None:
            whose = "Its" if label is None else f"'{label}' can't be used: its"
            raise DepError(f"{whose} imported shape's data is missing from this file (it was deleted or not "
                           f"appended): undo (Ctrl+Z) or import the file again")
        found[blob_id] = text
    return found


def resolve(obj, source, factor, index, memo=None, stack=()):
    """Resolved(tag, deps, blobs) for part `obj` whose script is `source`. `index`: part_index(); `memo`: a dict
    shared across one tick (dependency results by part id). Raises DepError."""
    ids = references(source)
    own_blobs = _blobs_of(obj.blendsolid_script, source)
    if not ids:
        return Resolved(part.tag_for(source, factor), blobs=own_blobs)
    memo = {} if memo is None else memo
    own = part.part_id(obj)
    chain = (*stack, own)
    deps, keys = [], []
    for pid in ids:
        if pid in chain:
            names = [index[p][0].name if p in index else "?" for p in (*chain[chain.index(pid):], pid)]
            raise DepError("Parts use each other in a loop (" + " -> ".join(names) + "): undo the change "
                           "(Ctrl+Z)")
        instances = index.get(pid)
        if instances is None:
            kept = _deleted_cutter(obj, pid, factor)
            if kept is None:
                raise DepError("This part uses a cutter part that no longer exists: undo its deletion (Ctrl+Z) or "
                               "Remove its cut (BlendSolid panel, Booleans)")
            kept, kept_blobs = kept
            own_blobs.update(kept_blobs)
            deps.append(kept)
            keys.append(f"{pid}:{kept['tag']}:" + ";".join(_matrix_key(m) for m in kept["matrices"]))
            continue
        dep = instances[0]
        if not trust.is_trusted(dep):
            raise DepError(f"This part uses '{dep.name}', whose script is not trusted: press Trust Scripts in "
                           f"This File")
        sub = memo.get(pid)
        if sub is None:
            try:
                sub = resolve(dep, part.source_of(dep), factor, index, memo, chain)
            except DepError as e:
                sub = e
            memo[pid] = sub
        if isinstance(sub, DepError):
            raise DepError(f"'{dep.name}' can't be used: {sub}")
        own_blobs.update(sub.blobs)
        matrices = [relative_matrix(obj, o, factor) for o in instances]
        # "name": for the worker's messages only (ADR 0002: users know parts by name); not part of the tag
        deps.append({"id": pid, "name": dep.name, "tag": sub.tag, "source": part.source_of(dep),
                     "matrices": matrices, "deps": sub.deps})
        keys.append(f"{pid}:{sub.tag}:" + ";".join(_matrix_key(m) for m in matrices))
    return Resolved(part.tag_for(source, factor, keys), deps, own_blobs)


def _deleted_cutter(obj, pid, factor):
    """(dependency entry, its blobs) of cutter `pid`, deleted but with its script kept and its placement
    remembered by obj, or None. Raises DepError when it can't be used as it is (untrusted, or itself using other
    parts)."""
    text, last = part.script_of_part(pid), part.last_cutter(obj, pid)
    if text is None or last is None:
        return None
    name, matrices = last
    if not trust.text_trusted(text):
        raise DepError(f"This part uses '{name}' (deleted), whose script is not trusted: press Trust Scripts in "
                       f"This File")
    source = text.as_string()
    if references(source):
        raise DepError(f"This part uses '{name}', which was deleted and uses other parts: restore it (BlendSolid "
                       f"panel, Booleans)")
    return ({"id": pid, "name": name, "tag": part.tag_for(source, factor), "source": source, "matrices": matrices,
             "deps": [], "deleted": True}, _blobs_of(text, source, name))


@dataclass(frozen=True)
class Boolean:
    """A boolean with a live cutter in a part's history (an insert(ref(...)) feature)."""
    feature: str        # the feature's name in the script
    part_id: str
    mode: str           # "ADD", "SUBTRACT" or "INTERSECT"
    name: str           # the cutter's name (as last seen when deleted)
    deleted: bool       # the cutter object is gone but its script is kept: restorable
    missing: bool       # gone with its script: only removing the cut is left


def booleans(obj, index=None):
    """The booleans of obj's history with a live cutter, in order (for the panel). [] if not canonical."""
    try:
        feats = script_model.features(part.source_of(obj))
    except script_model.NotCanonical:
        return []
    index = part_index() if index is None else index
    out = []
    for f in feats:
        if f.kind != "insert" or len(f.refs) != 1:
            continue
        pid = f.refs[0]
        if pid in index:
            out.append(Boolean(f.name, pid, f.mode, index[pid][0].name, False, False))
            continue
        last = part.last_cutter(obj, pid)
        kept = part.script_of_part(pid) is not None and last is not None
        out.append(Boolean(f.name, pid, f.mode, last[0] if last else "?", kept, not kept))
    return out


def tag_of(obj, factor=None, index=None):
    """The tag obj's mesh would carry if computed now (never raises: an unusable reference gives its
    error_tag). A full scan when `index` isn't given: for UI code and event handling, not per-tick loops."""
    factor = part.unit_factor() if factor is None else factor
    source = part.source_of(obj)
    if not references(source) and not script_model.imports(source):
        return part.tag_for(source, factor)
    try:
        return resolve(obj, source, factor, part_index() if index is None else index).tag
    except DepError as e:
        return error_tag(source, factor, str(e))


def uses(obj, pid, index, _seen=None):
    """Does obj's script use part `pid`, directly or through the parts it uses? (Tolerates loops.)"""
    seen = set() if _seen is None else _seen
    for ref_id in references(part.source_of(obj)):
        if ref_id == pid:
            return True
        instances = index.get(ref_id)
        if instances is not None and ref_id not in seen:
            seen.add(ref_id)
            if uses(instances[0], pid, index, seen):
                return True
    return False
