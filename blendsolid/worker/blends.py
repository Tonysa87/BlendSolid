"""Fillets and chamfers with errors a Blender user can act on.

build123d's fillet() fails with "Failed creating a fillet with radius of 15, try a smaller value or use
max_fillet()", which speaks to script writers; and OCCT sometimes "succeeds" with an invalid solid, which the
runner then reports without a line. The part scripts get these wrappers instead (same signatures): on a failure,
or an invalid result, they search the largest size that works on the same edges and raise BlendError on the
fillet's own line, e.g. "fillet radius 15 mm is too large for these 4 edges: the largest that works is 14.93 mm".
"""
import build123d as bd
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.Standard import Standard_Failure
from OCP.StdFail import StdFail_NotDone

STEPS = 12  # halvings of the failed size: the largest working size is found to size / 4096


class BlendError(Exception):
    """A fillet or chamfer that can't be made; the message says what size would work."""


def _fmt(mm):
    return f"{mm:.3f}".rstrip("0").rstrip(".")


def _valid(shape):
    return shape is not None and BRepCheck_Analyzer(shape.wrapped).IsValid()


def _target(name, objects):
    """The part a fillet/chamfer of `objects` applies to (as build123d's own operations find it)."""
    context = bd.Builder._get_context(name)
    if context is not None:
        return context._obj
    first = next(iter(bd.flatten_sequence(objects)), None)
    return getattr(first, "topo_parent", None)


def _largest(works, size):
    """The largest s in (0, size) with works(s), by bisection; 0 if even size / 4096 fails."""
    lo, hi = 0.0, size
    for _ in range(STEPS):
        mid = (lo + hi) / 2
        if works(mid):
            lo = mid
        else:
            hi = mid
    return lo


def _attempt(make):
    try:
        return _valid(make())
    except (ValueError, Standard_Failure, StdFail_NotDone, RuntimeError):
        return False


def _explain(what, size, count, largest):
    edges = "this edge" if count == 1 else f"these {count} edges"
    if largest <= 0:
        return (f"{what} {_fmt(size)} mm: OCCT can't round {edges} at any size (try fewer edges at once, or "
                f"fillet them in separate steps)")
    return f"{what} {_fmt(size)} mm is too large for {edges}: the largest that works is {_fmt(largest)} mm"


def _checked(name, make, objects, size, search):
    """Run build123d's operation `make`; on a size failure or an invalid result, raise BlendError with the
    largest size `search(base part, edges, s)` accepts."""
    target = _target(name, objects)
    edges = list(bd.flatten_sequence(objects))
    try:
        out = make()
    except (ValueError, Standard_Failure, StdFail_NotDone) as e:
        if target is None or getattr(target, "_dim", 3) != 3 or "Failed creating" not in str(e):
            raise
        out = None
    if out is not None:
        context = bd.Builder._get_context(name)
        if _valid(context._obj if context is not None else out):
            return out
    base = bd.Part(target.wrapped)
    largest = _largest(lambda s: _attempt(lambda: search(base, edges, s)), size)
    raise BlendError(_explain(f"{name} {'radius' if name == 'fillet' else 'length'}", size, len(edges), largest))


def fillet(objects, radius):
    """build123d's fillet(), raising BlendError with the largest working radius when it fails."""
    return _checked("fillet", lambda: bd.fillet(objects, radius), objects, radius,
                    lambda base, edges, r: base.fillet(r, edges))


def chamfer(objects, length, length2=None, angle=None, reference=None):
    """build123d's chamfer(), raising BlendError with the largest working length when it fails (for a
    length-and-angle chamfer, build123d's own error)."""
    make = lambda: bd.chamfer(objects, length, length2, angle, reference)  # noqa: E731
    if angle is not None:
        return make()
    ratio = None if length2 is None else length2 / length
    return _checked("chamfer", make, objects, length,
                    lambda base, edges, s: base.chamfer(s, None if ratio is None else s * ratio, edges, reference))
