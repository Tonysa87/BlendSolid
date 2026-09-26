"""Runs a BlendSolid history script with build123d and turns `result` into a tessellated mesh."""
import time
from dataclasses import dataclass, field

import numpy as np

import tessellate

SCRIPT_NAME = "<history>"


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


def run_script(source, lin_defl=0.1, ang_defl=0.3):
    t0 = time.perf_counter()
    ns = {"__name__": "__blendsolid_history__"}
    try:
        code = compile(source, SCRIPT_NAME, "exec")
        exec("from build123d import *", ns)
        exec(code, ns)
    except SyntaxError as e:
        return RunResult(False, f"SyntaxError: {e.msg}", e.lineno)
    except SystemExit:
        return RunResult(False, "the script called sys.exit()", None)
    except Exception as e:
        return RunResult(False, f"{type(e).__name__}: {e}", _script_line(e.__traceback__))
    t1 = time.perf_counter()

    try:
        if "result" not in ns:
            return RunResult(False, "the script must assign the final shape to `result`")
        shape = ns["result"]
        if not hasattr(shape, "wrapped") and hasattr(shape, "part"):  # a BuildPart builder
            shape = shape.part
        wrapped = getattr(shape, "wrapped", None)
        if wrapped is None:
            return RunResult(False, f"`result` must be a build123d shape, not {type(shape).__name__}")
        info = tessellate.check(wrapped)
        if info["solids"] == 0:
            return RunResult(False, "`result` contains no solid")
        if not info["valid"]:
            return RunResult(False, "`result` is not a valid solid (BRepCheck failed)")
        verts, tris, tri_face = tessellate.tessellate(wrapped, lin_defl, ang_defl)
        t2 = time.perf_counter()
        return RunResult(True, volume=info["volume"], faces=info["faces"], verts=verts, tris=tris, tri_face=tri_face,
                         timing={"script": t1 - t0, "tessellate": t2 - t1})
    except Exception as e:
        # tessellate.check/tessellate (and any OCCT call here) must never take down the worker process.
        return RunResult(False, f"{type(e).__name__}: {e}")
