"""Parts that use other parts (tool 3, live cutters): `ref("<part id>")` in a part's script.

resolve() turns a part's references into the worker request's `deps` tree (each dependency's script, tag and
placements in the referencing part's frame — one per object showing it, so every linked duplicate of a cutter
cuts — recursively) and into the part's tag. The tag covers the
dependencies' tags and placements, so moving, rotating or editing a cutter makes the parts that use it stale,
and the reconcile loop recomputes them like any other change.

A reference that can't be used (the cutter was deleted, parts use each other in a loop, the cutter's script
isn't trusted, the cutter is scaled) raises DepError, whose message is shown on the part; the part is then
not submitted, and error_tag() gives it a tag that changes as soon as the situation does.
"""
from dataclasses import dataclass, field

from . import part, script_model, trust

SCALE_TOLERANCE = 1e-5


class DepError(Exception):
    """A reference that can't be resolved; str(e) is for the user."""


@dataclass(frozen=True)
class Resolved:
    tag: str
    deps: list = field(default_factory=list)  # WorkerClient.submit(deps=...)


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
    m = target.matrix_world.inverted_safe() @ dep.matrix_world
    if any(abs(s - 1.0) > SCALE_TOLERANCE for s in m.to_scale()):
        raise DepError(f"The cutter {part.scaled_message(dep)}")
    rows = [[m[i][j] for j in range(4)] for i in range(3)]
    for row in rows:
        row[3] /= factor  # Blender units -> script millimetres (ADR 0003)
    return [v for row in rows for v in row]


def _matrix_key(matrix):
    return ",".join(script_model.fmt(v) for v in matrix)  # rounded: float noise must not change the tag


def error_tag(source, factor, message):
    return part.tag_for(source, factor, [f"error:{message}"])


def resolve(obj, source, factor, index, memo=None, stack=()):
    """Resolved(tag, deps) for part `obj` whose script is `source`. `index`: part_index(); `memo`: a dict
    shared across one tick (dependency results by part id). Raises DepError."""
    ids = references(source)
    if not ids:
        return Resolved(part.tag_for(source, factor))
    memo = {} if memo is None else memo
    own = part.part_id(obj)
    chain = (*stack, own)
    deps, keys = [], []
    for pid in ids:
        if pid in chain:
            names = [index[p][0].name if p in index else "?" for p in (*chain[chain.index(pid):], pid)]
            raise DepError("Parts use each other in a loop (" + " -> ".join(names) + "): remove one of their "
                           "boolean features")
        instances = index.get(pid)
        if instances is None:
            raise DepError("This part uses a cutter part that no longer exists (deleted?): undo the deletion "
                           "or remove the boolean feature")
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
        matrices = [relative_matrix(obj, o, factor) for o in instances]
        deps.append({"id": pid, "tag": sub.tag, "source": part.source_of(dep), "matrices": matrices,
                     "deps": sub.deps})
        keys.append(f"{pid}:{sub.tag}:" + ";".join(_matrix_key(m) for m in matrices))
    return Resolved(part.tag_for(source, factor, keys), deps)


def tag_of(obj, factor=None, index=None):
    """The tag obj's mesh would carry if computed now (never raises: an unusable reference gives its
    error_tag). A full scan when `index` isn't given: for UI code and event handling, not per-tick loops."""
    factor = part.unit_factor() if factor is None else factor
    source = part.source_of(obj)
    if not references(source):
        return part.tag_for(source, factor)
    try:
        return resolve(obj, source, factor, part_index() if index is None else index).tag
    except DepError as e:
        return error_tag(source, factor, str(e))
