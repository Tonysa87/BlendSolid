"""Fillets and chamfers with errors a Blender user can act on (research: docs/research/2026-09-28-fillet-edge-cases.md).

build123d's fillet() fails with "Failed creating a fillet with radius of 15, try a smaller value or use
max_fillet()", which speaks to script writers, and OCCT sometimes "succeeds" with an invalid solid (a hole inside
the fillet's band: IsDone, no faulty contour, self-intersecting result). The part scripts get these wrappers
instead (same signatures). A result is accepted only if it is one valid solid with a positive volume. On a
failure they raise BlendError on the fillet's own line:
- edges OCCT can't round at all (a seam inside one face, an edge between tangent faces, a free edge) are named
  as such (OCCT drops them silently when other edges are selected, and says "no suitable edges" otherwise);
- otherwise the sizes that work are searched by bisection below the failing size, within a time budget. The
  working sizes are usually an interval (0, limit) and the message gives the limit, rounded down. They are not
  always: with a hole inside the fillet's band, 1 mm fails while 1.5 mm works. When a smaller size failed too,
  the message says that something is in the way and lists what was tried, instead of "too large".
"""
import time

import build123d as bd
from OCP.BRep import BRep_Tool
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import GeomAbs_C0
from OCP.Standard import Standard_Failure
from OCP.StdFail import StdFail_NotDone
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS
from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as AncestorMap

STEPS = 12      # halvings of the failing size: the limit is found to size / 4096
BUDGET = 2.0    # seconds for the size search (each try is a whole fillet of the part)
SLIVER = 0.05   # mm: an edge this short next to the rounded edges is a sliver left by an earlier feature


class BlendError(Exception):
    """A fillet or chamfer that can't be made; the message says why and what would work."""


def _fmt(mm):
    if 0 < mm < 0.001:
        return f"{mm:.2g}"
    return f"{mm:.3f}".rstrip("0").rstrip(".")


def _floor3(mm):
    return int(mm * 1000) / 1000


def _valid(shape):
    """One valid solid with a positive volume (BRepCheck alone accepted a ShapeFix'ed fillet of volume 0)."""
    if shape is None or not BRepCheck_Analyzer(shape.wrapped).IsValid():
        return False
    solids = shape.solids()
    return len(solids) == 1 and solids[0].volume > 0


def _target(name, objects):
    """The part a fillet/chamfer of `objects` applies to (as build123d's own operations find it)."""
    context = bd.Builder._get_context(name)
    if context is not None:
        return context._obj
    first = next(iter(bd.flatten_sequence(objects)), None)
    return getattr(first, "topo_parent", None)


def _unroundable(target, edges):
    """(kind, count) of the selected edges OCCT can't round: seams, edges between tangent faces, free edges."""
    faces_of = AncestorMap()
    TopExp.MapShapesAndAncestors_s(target.wrapped, TopAbs_EDGE, TopAbs_FACE, faces_of)
    kinds = []
    for e in edges:
        edge = TopoDS.Edge(e.wrapped)
        if not faces_of.Contains(edge):
            kinds.append("free")
            continue
        faces = list(faces_of.FindFromKey(edge))
        distinct = []
        for f in faces:
            if not any(f.IsSame(g) for g in distinct):
                distinct.append(f)
        if len(distinct) < 2:
            kinds.append("seam" if len(distinct) == 1 else "free")
        elif BRep_Tool.Continuity_s(edge, TopoDS.Face(distinct[0]), TopoDS.Face(distinct[1])) != GeomAbs_C0:
            kinds.append("smooth")
        else:
            kinds.append(None)
    return kinds


_WHY = {"seam": "a seam inside one face", "smooth": "between tangent faces", "free": "on no face of the part"}


def _refuse_unroundable(target, edges):
    kinds = _unroundable(target, edges)
    if edges and all(kinds):
        found = sorted(set(kinds))
        what = "this edge is" if len(edges) == 1 else f"these {len(edges)} edges are"
        raise BlendError(f"{what} {' or '.join(_WHY[k] for k in found)}: there is nothing to round")


def _search(works, size):
    """Bisection below the failing `size`: ({size tried: worked}, largest working size found or 0)."""
    tried, lo, hi = {}, 0.0, size
    end = time.monotonic() + BUDGET
    for _ in range(STEPS):
        if time.monotonic() > end:
            break
        mid = (lo + hi) / 2
        tried[mid] = works(mid)
        if tried[mid]:
            lo = mid
        else:
            hi = mid
    # the working sizes may not be an interval: check below the limit found and above the failing size
    for probe in (lo * 0.5, lo * 0.75, size * 1.25, size * 1.5):
        if probe > 0 and probe not in tried and time.monotonic() < end:
            tried[probe] = works(probe)
    return tried, lo


def _sliver(target, edges):
    """The shortest edge (mm) of the faces around `edges`, if it is a sliver (< SLIVER mm), else None."""
    faces_of = AncestorMap()
    TopExp.MapShapesAndAncestors_s(target.wrapped, TopAbs_EDGE, TopAbs_FACE, faces_of)
    shortest = None
    for e in edges:
        edge = TopoDS.Edge(e.wrapped)
        if not faces_of.Contains(edge):
            continue
        for f in faces_of.FindFromKey(edge):
            for other in bd.Face(TopoDS.Face(f)).edges():
                length = other.length
                shortest = length if shortest is None else min(shortest, length)
    return shortest if shortest is not None and shortest < SLIVER else None


def _attempt(make):
    try:
        return _valid(make())
    except (ValueError, Standard_Failure, StdFail_NotDone, RuntimeError):
        return False


def _explain(what, size, count, tried, largest, sliver=None):
    edges = "this edge" if count == 1 else f"these {count} edges"
    if sliver is not None:
        return (f"{what} {_fmt(size)} mm: {edges} touch a face with a {_fmt(sliver)} mm edge, a sliver left by an "
                f"earlier feature; fix that feature (e.g. make the faces meet exactly) before rounding here")
    shown = _floor3(largest)
    if largest <= 0 or shown <= 0:
        return (f"{what} {_fmt(size)} mm: OCCT can't round {edges} at any size tried (down to "
                f"{_fmt(min(tried) if tried else size)} mm); try fewer edges at once")
    works = sorted(s for s, ok in tried.items() if ok)
    fails = sorted({size, *(s for s, ok in tried.items() if not ok)})
    if any(s < largest for s in fails) or any(s > size for s in works) or shown >= size:
        return (f"{what} {_fmt(size)} mm fails on {edges}: another face is in the way (a hole or a step inside "
                f"the rounding), so some sizes work and others don't. Works at "
                f"{', '.join(dict.fromkeys(_fmt(_floor3(s)) for s in works[-4:]))} mm; fails at "
                f"{', '.join(dict.fromkeys(_fmt(s) for s in fails[:4]))} mm")
    return f"{what} {_fmt(size)} mm is too large for {edges}: the largest that works is {_fmt(shown)} mm"


def _checked(name, make, objects, size, search):
    """Run build123d's operation `make`; on a failure or an unusable result raise BlendError, with the sizes
    `search(base part, edges, s)` accepts."""
    target = _target(name, objects)
    edges = list(bd.flatten_sequence(objects))
    solid = (target is not None and getattr(target, "_dim", 3) == 3 and edges
             and all(isinstance(e, bd.Edge) for e in edges))  # else build123d's own error
    if solid:
        _refuse_unroundable(target, edges)
    try:
        out = make()
    except (ValueError, Standard_Failure, StdFail_NotDone) as e:
        if not solid or "Failed creating" not in str(e):
            raise
        out = None
    if out is not None:
        if not solid:
            return out
        context = bd.Builder._get_context(name)
        if _valid(context._obj if context is not None else out):
            return out
    base = bd.Part(target.wrapped)
    tried, largest = _search(lambda s: _attempt(lambda: search(base, edges, s)), size)
    what = f"{name} {'radius' if name == 'fillet' else 'length'}"
    sliver = _sliver(target, edges) if largest < 0.01 * size else None
    raise BlendError(_explain(what, size, len(edges), tried, largest, sliver))


def fillet(objects, radius):
    """build123d's fillet(), raising BlendError with what would work when it fails."""
    return _checked("fillet", lambda: bd.fillet(objects, radius), objects, radius,
                    lambda base, edges, r: base.fillet(r, edges))


def _reference_face(objects, reference):
    """build123d wants one Face holding every chamfered edge; a script names it with face(), a list (a label can
    name several faces after a split): the one that holds them all."""
    if reference is None or isinstance(reference, bd.Face):
        return reference
    edges = list(bd.flatten_sequence(objects))
    for face in reference:
        held = face.edges()
        if all(any(e.wrapped.IsSame(h.wrapped) for h in held) for e in edges):
            return face
    raise BlendError("the chamfer's reference face doesn't hold all its edges: the first length is measured on a "
                     "face every chamfered edge lies on")


def chamfer(objects, length, length2=None, angle=None, reference=None):
    """build123d's chamfer(), raising BlendError with what would work when it fails (for a length-and-angle
    chamfer, build123d's own error). `reference` (with length2 or angle): the face the first length is measured
    on, a Face or a face() result."""
    reference = _reference_face(objects, reference)
    make = lambda: bd.chamfer(objects, length, length2, angle, reference)  # noqa: E731
    if angle is not None:
        return make()
    ratio = None if length2 is None else length2 / length
    return _checked("chamfer", make, objects, length,
                    lambda base, edges, s: base.chamfer(s, None if ratio is None else s * ratio, edges, reference))
