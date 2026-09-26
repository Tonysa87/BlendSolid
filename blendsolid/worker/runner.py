"""Runs a BlendSolid history script with build123d and turns `result` into a tessellated mesh.

A script may use other parts with `ref("<part id>")` (live cutters): the request carries those parts as
`deps`, a tree of {"id", "tag", "source", "matrices", "deps"} dicts. "matrices" holds one 3x4 row-major
transform (millimetres) per object showing that part (linked duplicates), from the part's own frame to the frame
of the part that references it. ref() builds the part (or takes it from the shape cache, by tag) and returns it
placed there: one shape, or a compound of every placement.
"""
import math
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np

import tessellate

SCRIPT_NAME = "<history>"
MAX_DEPTH = 32  # nested ref()s: Blender never sends cycles, this only bounds a malformed request


class RefError(Exception):
    """A ref() that can't be resolved; reported as an error of the part that calls ref()."""


class ResultError(Exception):
    """The script ran but its `result` isn't usable; the message is complete as it is."""


class ShapeCache:
    """Built shapes by tag, least recently used dropped first. A tag identifies a script together with its
    dependencies and their placements (Blender computes it), so a cached shape is never stale."""

    def __init__(self, size=64):
        self.size, self._items = size, OrderedDict()

    def get(self, tag):
        shape = self._items.get(tag)
        if shape is not None:
            self._items.move_to_end(tag)
        return shape

    def put(self, tag, shape):
        self._items[tag] = shape
        self._items.move_to_end(tag)
        while len(self._items) > self.size:
            self._items.popitem(last=False)

    def __len__(self):
        return len(self._items)


SHAPES = ShapeCache()


@dataclass
class RunResult:
    ok: bool
    error: str = ""
    line: int | None = None
    volume: float = 0.0
    faces: int = 0
    verts: np.ndarray | None = None
    tris: np.ndarray | None = None
    tri_face: np.ndarray | None = None
    timing: dict = field(default_factory=dict)


def _script_line(tb):
    line = None
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == SCRIPT_NAME:
            line = tb.tb_lineno
        tb = tb.tb_next
    return line


def _location(matrix):
    from build123d import Location
    from OCP.gp import gp_Trsf

    m = [float(v) for v in matrix]
    if len(m) != 12 or not all(math.isfinite(v) for v in m):
        raise RefError("the placement of a referenced part is malformed")
    rot = np.array([m[0:3], m[4:7], m[8:11]])
    if not np.allclose(rot @ rot.T, np.eye(3), atol=1e-5) or np.linalg.det(rot) < 0:
        raise RefError("a referenced part is scaled, sheared or mirrored: only moves and rotations are allowed")
    # Blender's matrix_world is float32: a "pure" rotation's determinant differs from 1 by ~1e-8 once widened
    # to float64 -- inside the tolerance above, but enough for gp_Trsf.SetValues to derive a non-unit scale
    # factor from it and fail BRepCheck. Re-orthonormalize so OCCT sees an exact rotation (scale exactly 1).
    u, _, vt = np.linalg.svd(rot)
    rot = u @ np.diag([1, 1, np.sign(np.linalg.det(u @ vt))]) @ vt
    trsf = gp_Trsf()
    trsf.SetValues(rot[0, 0], rot[0, 1], rot[0, 2], m[3],
                   rot[1, 0], rot[1, 1], rot[1, 2], m[7],
                   rot[2, 0], rot[2, 1], rot[2, 2], m[11])
    return Location(trsf)


def _make_ref(deps, cache, depth):
    by_id = {d["id"]: d for d in deps}

    def ref(part_id):
        dep = by_id.get(part_id)
        if dep is None:
            raise RefError(f"ref({part_id!r}): no such part was sent with this script")
        shape = cache.get(dep["tag"])
        if shape is None:
            if depth >= MAX_DEPTH:
                raise RefError(f"ref({part_id!r}): parts reference each other too deeply")
            try:
                shape = _build(dep["source"], f"<ref {part_id}>", dep.get("deps") or [], cache, depth + 1)
            except RefError:
                raise
            except Exception as e:
                raise RefError(f"the part used by ref({part_id!r}) could not be built: "
                               f"{type(e).__name__}: {e}") from None
            cache.put(dep["tag"], shape)
        placed = [shape.moved(_location(m)) for m in dep["matrices"]]
        if not placed:
            raise RefError(f"ref({part_id!r}): the part is not placed anywhere")
        if len(placed) == 1:
            return placed[0]
        from build123d import Compound
        return Compound(placed)

    return ref


def _result_shape(ns):
    if "result" not in ns:
        raise ResultError("the script must assign the final shape to `result`")
    shape = ns["result"]
    if not hasattr(shape, "wrapped") and hasattr(shape, "part"):  # a BuildPart builder
        shape = shape.part
    if getattr(shape, "wrapped", None) is None:
        raise ResultError(f"`result` must be a build123d shape, not {type(shape).__name__}")
    return shape


def _build(source, filename, deps, cache, depth=0):
    """Exec `source` (ref() available) and return its `result` shape. Raises whatever the script raises."""
    ns = {"__name__": "__blendsolid_history__"}
    code = compile(source, filename, "exec")
    exec("from build123d import *", ns)
    ns["ref"] = _make_ref(deps, cache, depth)
    exec(code, ns)
    return _result_shape(ns)


def run_script(source, lin_defl=0.1, ang_defl=0.3, deps=(), tag=None, cache=None):
    """`deps`: the parts ref() may use (see the module docstring). `tag`: when given, the built shape is
    cached under it, so parts that use this one don't rebuild it."""
    cache = SHAPES if cache is None else cache
    t0 = time.perf_counter()
    try:
        shape = _build(source, SCRIPT_NAME, list(deps or ()), cache)
    except SyntaxError as e:
        return RunResult(False, f"SyntaxError: {e.msg}", e.lineno)
    except SystemExit:
        return RunResult(False, "the script called sys.exit()", None)
    except ResultError as e:
        return RunResult(False, str(e), None)
    except RefError as e:
        return RunResult(False, str(e), _script_line(e.__traceback__))
    except Exception as e:
        return RunResult(False, f"{type(e).__name__}: {e}", _script_line(e.__traceback__))
    t1 = time.perf_counter()

    try:
        wrapped = shape.wrapped
        info = tessellate.check(wrapped)
        if info["solids"] == 0:
            return RunResult(False, "`result` contains no solid")
        if not info["valid"]:
            return RunResult(False, "`result` is not a valid solid (BRepCheck failed)")
        verts, tris, tri_face = tessellate.tessellate(wrapped, lin_defl, ang_defl)
        if tag is not None:
            cache.put(tag, shape)
        t2 = time.perf_counter()
        return RunResult(True, volume=info["volume"], faces=info["faces"], verts=verts, tris=tris, tri_face=tri_face,
                         timing={"script": t1 - t0, "tessellate": t2 - t1})
    except Exception as e:
        # tessellate.check/tessellate (and any OCCT call here) must never take down the worker process.
        return RunResult(False, f"{type(e).__name__}: {e}")
