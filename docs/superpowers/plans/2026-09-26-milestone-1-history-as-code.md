# Milestone 1 — History as Code: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A BlendSolid part is a build123d script stored in the `.blend`; editing one of its parameters (or the script) recomputes the solid in a separate worker process and updates the Blender mesh, without ever blocking or corrupting Blender.

**Architecture:** The add-on (`blendsolid/`) never imports OCP or build123d. A persistent worker process (Blender's own Python, isolated mode, private library folder) runs the scripts and returns tessellated meshes with BRep face IDs over a localhost socket (JSON headers + raw numpy buffers, no pickle). On the Blender side the script lives in a `Text` datablock (so it is in the undo history); the mesh is a *cache* tagged with the hash of the script that produced it, and a timer reconciles any mismatch (parameter edits, script edits, undo/redo, file load).

**Tech Stack:** Blender 5.2 LTS (Python 3.13), build123d 0.13.0, cadquery-ocp-novtk 8.0.1 (OCCT), numpy, `multiprocessing.connection`, pytest.

**Spec:** `docs/spec.md` (milestone 1 row), with `SPIKE_REPORT.md` ("Proposed spec changes") and `docs/decisions/0001-shipping-build123d.md`.

## Design choices made in this plan (confirm before executing)

1. **Parameters** are the leading top-level `name = <number>` assignments of the script (after imports/docstring). The panel shows them as draggable fields; editing one rewrites that literal in the script. Everything else in the script is free-form build123d.
2. **Script contract:** the script assigns the final shape to `result` (a build123d shape or a `BuildPart` builder). `from build123d import *` is implicit.
3. **Source of truth = script text.** The mesh stores `bs_source_hash`; a timer (every 50 ms) resubmits any part whose script hash differs from its mesh hash. No logic in `undo_post` (spike lesson), no handler writing the script (spike lesson): parameter edits go through RNA properties, so the script change lands in the same undo step.
4. **Failures never loop:** a script error or worker crash is shown on the part and the failing hash is remembered, so it is not resubmitted until the script changes or the user presses *Recompute*.
5. **One worker, per-part coalescing:** while a part is being computed, newer requests for the same part replace older pending ones; different parts queue in order.
6. **Script visibility (ADR 0002, decided):** hidden from standard users — stored in a dot-named `Text` (`.Part.py`), no *Edit Script* button, errors without line numbers; an add-on preference *Show history scripts* reveals them for advanced users.
7. **Out of scope:** text/fonts, push-face/proxies, selectors from clicks (milestone 2), store packaging, CI.

## Global Constraints

- Blender **5.2 LTS**, Python **3.13**; pins `build123d==0.13.0`, `cadquery-ocp-novtk==8.0.1.0.0`.
- Everything in the repository in **English** (code, comments, UI strings, docs, commits).
- Blender's interpreter must never import `OCP` or `build123d` (ADR 0001).
- The add-on must not change Blender's `sys.path`/`sys.modules`, install packages, access the network, or write into its own directory (extensions guidelines). Writable data goes to `bpy.utils.extension_path_user(__package__, ...)`.
- Add-on modules use **relative imports**. Modules in `blendsolid/worker/` run inside the worker with that folder on `sys.path` and import each other as top-level modules (`import protocol`); the Blender side only imports `blendsolid.worker.protocol`.
- `blendsolid/__init__.py` must not import `bpy` at module level (so bpy-free modules are unit-testable).
- Geometric results are verified with numbers (volumes, validity, face counts), never by eye.
- Tests: `tools/test.sh` (unit tests with Blender's Python + headless Blender tests). Manual tests only for GUI behaviour, with exact steps.

## Review Focus

1. **A broken script** (syntax error, exception, no `result`, not a solid): the last good mesh stays, the panel shows the message with the script line, and Blender stays responsive. → Task 4 (runner), Task 6 (`test_error_keeps_previous_mesh`).
2. **Fast parameter dragging:** many edits while a recompute is running must end with the mesh matching the *latest* value, never a stale one. → Task 5 (`test_coalescing_per_key`), Task 6 (`test_stale_result_is_discarded`).
3. **Worker crash or hang** (OCCT segfault, infinite loop): Blender keeps running, the part shows an error, no crash loop, the next edit restarts the worker. → Task 5 (`test_crash_*`, `test_timeout`), Task 6 (`test_crash_does_not_loop`).
4. **Undo/redo after a parameter change:** the mesh must end up matching the restored script, even when the undo step captured a mesh one step behind. → Task 6 (`test_reconcile_after_simulated_undo`), Task 8 manual check.
5. **Duplicating a part (Shift+D) or saving/reopening the file:** a duplicate must be independent (its own script); reopening must not recompute parts that are already up to date. → Task 6 (`test_duplicate_gets_own_script`, `test_reload_does_not_recompute`).

---

## File Structure

```
blendsolid/                         the extension (package name `blendsolid`)
  blender_manifest.toml             extension manifest (dev: all platforms; build script narrows it)
  __init__.py                       register()/unregister(); no bpy import at module level
  paths.py                          python executable, server script, worker libs, pycache dir
  params.py                         parse/rewrite the parameter block of a script (pure Python)
  client.py                         WorkerClient: spawn, handshake, submit, poll, coalesce, crash/timeout (bpy-free)
  part.py                           bpy: part objects, Text storage, hashes, mesh apply, params mirror
  runtime.py                        bpy: client singleton, reconcile timer, event handling
  ui.py                             bpy: properties, operators, sidebar panel
  templates/default_part.py         script of a new part
  worker/protocol.py                message framing over multiprocessing Connection (shared by both sides)
  worker/tessellate.py              OCP: validity/volume/face map/tessellation with BRep face IDs
  worker/runner.py                  exec a history script with build123d → RunResult
  worker/server.py                  worker process entry point
tests/unit/                         pytest, run with Blender's Python (no bpy)
tests/blender/                      pytest, run inside `blender -b`
tools/setup_dev.sh                  creates .dev/worker_libs and .dev/pytest
tools/test.sh                       runs unit + Blender tests
tools/worker-requirements.txt       pinned worker dependencies
tools/build_extension.py            per-platform zip with bundled worker libs
tools/smoke_installed.py            headless smoke test of an installed zip
```

---

### Task 1: Package skeleton, dev environment, test runners

**Files:**
- Create: `blendsolid/blender_manifest.toml`, `blendsolid/__init__.py`, `blendsolid/paths.py`
- Create: `tools/worker-requirements.txt`, `tools/setup_dev.sh`, `tools/test.sh`
- Create: `tests/unit/conftest.py`, `tests/unit/test_paths.py`, `tests/blender/run.py`, `tests/blender/conftest.py`, `tests/blender/test_register.py`
- Modify: `.gitignore`, `CLAUDE.md` (commands section)

**Interfaces:**
- Produces: `paths.PKG_DIR: str`, `paths.python_executable() -> str`, `paths.server_script() -> str`, `paths.worker_libs() -> str` (raises `FileNotFoundError`), `paths.pycache_dir(package: str) -> str`; `blendsolid.register()`, `blendsolid.unregister()`; Blender test helpers in `tests/blender/conftest.py`: fixture `addon` (session), fixture `clean` (function), function `wait_for(predicate, timeout=90.0) -> None`.

- [ ] **Step 1: Write the manifest, requirements and dev scripts**

`blendsolid/blender_manifest.toml`:
```toml
schema_version = "1.0.0"

id = "blendsolid"
version = "0.1.0"
name = "BlendSolid"
tagline = "Exact BRep/NURBS CAD modeling with a parametric history written as code"
maintainer = "Antonio Sartini <antonio.sartini@gmail.com>"
type = "add-on"
website = "https://github.com/Tonysa87/BlendSolid"
tags = ["Modeling", "Mesh"]

blender_version_min = "5.2.0"
license = ["SPDX:GPL-3.0-or-later"]

# tools/build_extension.py narrows this to the one platform of each zip
platforms = ["windows-x64", "linux-x64", "macos-arm64"]

[build]
paths_exclude_pattern = ["__pycache__/", "*.pyc"]
```

`tools/worker-requirements.txt`:
```
build123d==0.13.0
cadquery-ocp-novtk==8.0.1.0.0
```

`tools/setup_dev.sh`:
```bash
#!/usr/bin/env bash
# Creates .dev/worker_libs (build123d + all dependencies, for the worker) and .dev/pytest,
# using the Python bundled with the Blender in $BL.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BL="${BL:-$HOME/blender/blender-5.2.2-linux-x64/blender}"
PY="$(dirname "$BL")/5.2/python/bin/python3.13"
"$PY" -m pip install --upgrade --target "$ROOT/.dev/worker_libs" -r "$ROOT/tools/worker-requirements.txt"
"$PY" -m pip install --upgrade --target "$ROOT/.dev/pytest" pytest
echo "dev environment ready in $ROOT/.dev"
```

`tools/test.sh`:
```bash
#!/usr/bin/env bash
# Unit tests (Blender's Python, no bpy) then Blender tests (headless Blender).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BL="${BL:-$HOME/blender/blender-5.2.2-linux-x64/blender}"
PY="$(dirname "$BL")/5.2/python/bin/python3.13"
PYTHONPATH="$ROOT:$ROOT/.dev/pytest" "$PY" -m pytest "$ROOT/tests/unit" -q -p no:cacheprovider "$@"
"$BL" -b --factory-startup --python-exit-code 1 --python "$ROOT/tests/blender/run.py" -- "$@"
```

Append to `.gitignore`:
```
/.dev/
```

- [ ] **Step 2: Run the dev setup**

Run: `chmod +x tools/*.sh && tools/setup_dev.sh`
Expected: ends with `dev environment ready in .../.dev`; `.dev/worker_libs/build123d` and `.dev/worker_libs/OCP` exist.

- [ ] **Step 3: Write the failing unit test for `paths`**

`tests/unit/conftest.py`:
```python
"""Unit tests run with Blender's Python but without bpy. Worker modules are imported the way the worker
imports them: with blendsolid/worker and the worker libraries on sys.path (this is the test process,
not Blender, so changing sys.path here is fine)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKER_DIR = os.path.join(ROOT, "blendsolid", "worker")
DEV_LIBS = os.path.join(ROOT, ".dev", "worker_libs")

for p in (WORKER_DIR, DEV_LIBS):
    if p not in sys.path:
        sys.path.append(p)
```

`tests/unit/test_paths.py`:
```python
import os
import sys

from blendsolid import paths


def test_server_script_exists():
    assert os.path.isfile(paths.server_script())


def test_python_executable_is_a_python():
    exe = os.path.basename(paths.python_executable()).lower()
    assert exe.startswith("python"), exe


def test_worker_libs_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("BLENDSOLID_WORKER_LIBS", str(tmp_path))
    assert paths.worker_libs() == str(tmp_path)


def test_worker_libs_finds_dev_folder(monkeypatch):
    monkeypatch.delenv("BLENDSOLID_WORKER_LIBS", raising=False)
    assert paths.worker_libs().endswith(os.path.join(".dev", "worker_libs"))


def test_pycache_dir_without_blender_falls_back_to_temp():
    d = paths.pycache_dir("blendsolid")
    assert os.path.isdir(d)
    assert "bpy" not in sys.modules
```

- [ ] **Step 4: Run it to see it fail**

Run: `tools/test.sh -k paths`
Expected: FAIL — `ModuleNotFoundError: No module named 'blendsolid'` (or `paths`).

- [ ] **Step 5: Implement `__init__.py` and `paths.py`**

`blendsolid/__init__.py`:
```python
"""BlendSolid — exact BRep/NURBS CAD modeling in Blender with a parametric history written as code.

bpy is imported only inside register()/unregister(), so the bpy-free modules can be unit tested.
"""


def register():
    from . import runtime, ui
    ui.register()
    runtime.register()


def unregister():
    from . import runtime, ui
    runtime.unregister()
    ui.unregister()
```

`blendsolid/paths.py`:
```python
"""Where the add-on finds the worker's interpreter, entry point, libraries and bytecode cache."""
import os
import sys
import tempfile

PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def python_executable():
    """Blender's bundled Python (in Blender 5.2 `sys.executable` is the python binary, not blender)."""
    return sys.executable


def server_script():
    return os.path.join(PKG_DIR, "worker", "server.py")


def worker_libs():
    """Private library folder of the worker: env override, bundled folder, then the dev checkout's .dev/."""
    env = os.environ.get("BLENDSOLID_WORKER_LIBS")
    if env:
        return env
    for candidate in (os.path.join(PKG_DIR, "worker_libs"),
                      os.path.join(os.path.dirname(PKG_DIR), ".dev", "worker_libs")):
        if os.path.isdir(candidate):
            return candidate
    raise FileNotFoundError(
        "BlendSolid worker libraries not found: run tools/setup_dev.sh or set BLENDSOLID_WORKER_LIBS")


def pycache_dir(package):
    """Writable bytecode cache for the worker (the extension folder may be read-only)."""
    try:
        import bpy
        return bpy.utils.extension_path_user(package, path="pycache", create=True)
    except Exception:  # not running as an installed extension (dev checkout, unit tests)
        d = os.path.join(tempfile.gettempdir(), "blendsolid-pycache")
        os.makedirs(d, exist_ok=True)
        return d
```

Create an empty placeholder so `server_script()` resolves (Task 5 fills it): `blendsolid/worker/server.py` containing only `"""Worker entry point (implemented in Task 5)."""`. Create stub modules `blendsolid/runtime.py` and `blendsolid/ui.py` with `def register(): pass` / `def unregister(): pass` so `register()` works until Tasks 6–7 replace them.

- [ ] **Step 6: Write the Blender test bootstrap and a registration test**

`tests/blender/run.py`:
```python
"""Runs the Blender test suite inside `blender -b` (see tools/test.sh)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, ".dev", "pytest")]  # test harness only, not the add-on

import pytest  # noqa: E402

extra = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
code = pytest.main([os.path.join(ROOT, "tests", "blender"), "-q", "-p", "no:cacheprovider", *extra])
if code:
    raise SystemExit(int(code))
```

`tests/blender/conftest.py`:
```python
import time

import bpy
import pytest

import blendsolid


@pytest.fixture(scope="session")
def addon():
    blendsolid.register()
    yield blendsolid
    blendsolid.unregister()


@pytest.fixture
def clean(addon):
    """Empty scene and fresh runtime state for each test."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for text in list(bpy.data.texts):
        bpy.data.texts.remove(text)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    from blendsolid import runtime
    if hasattr(runtime, "reset_state"):
        runtime.reset_state()
    yield


def wait_for(predicate, timeout=90.0):
    """Timers don't run in background mode: pump the add-on's reconcile tick by hand."""
    from blendsolid import runtime
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        runtime.tick()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not reached within %.0f s" % timeout)
```

`tests/blender/test_register.py`:
```python
def test_register_and_unregister(addon):
    import blendsolid
    blendsolid.unregister()
    blendsolid.register()
```

- [ ] **Step 7: Run all tests**

Run: `tools/test.sh`
Expected: unit `5 passed`; Blender `1 passed`; exit code 0.

- [ ] **Step 8: Add the commands to CLAUDE.md and commit**

In `CLAUDE.md` → "Useful commands", add:
```bash
tools/setup_dev.sh      # once: .dev/worker_libs (build123d + deps) and .dev/pytest for Linux Blender
tools/test.sh           # unit tests (Blender's Python) + Blender tests (blender -b); extra args go to pytest
```

```bash
git add blendsolid tools tests .gitignore CLAUDE.md
git commit -m "Add extension skeleton, dev environment and test runners"
```

---

### Task 2: Message protocol

**Files:**
- Create: `blendsolid/worker/protocol.py`, `blendsolid/worker/__init__.py` (empty)
- Test: `tests/unit/test_protocol.py`

**Interfaces:**
- Produces: `protocol.ProtocolError(RuntimeError)`; `protocol.send_message(conn, header: dict, arrays: dict[str, np.ndarray] | None = None) -> None`; `protocol.recv_message(conn) -> tuple[dict, dict[str, np.ndarray]]`. Allowed dtypes: `float32`, `int32`. `recv_message` removes the internal `"buffers"` key from the header.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_protocol.py`:
```python
import json
from multiprocessing import Pipe

import numpy as np
import pytest

import protocol  # imported as the worker does (blendsolid/worker on sys.path)


def test_roundtrip_header_and_arrays():
    a, b = Pipe()
    verts = np.arange(12, dtype=np.float32).reshape(4, 3)
    tris = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    protocol.send_message(a, {"type": "result", "job": 7}, {"verts": verts, "tris": tris})
    header, arrays = protocol.recv_message(b)
    assert header == {"type": "result", "job": 7}
    np.testing.assert_array_equal(arrays["verts"], verts)
    np.testing.assert_array_equal(arrays["tris"], tris)


def test_empty_array_keeps_its_shape():
    a, b = Pipe()
    protocol.send_message(a, {"type": "result"}, {"tris": np.zeros((0, 3), dtype=np.int32)})
    _, arrays = protocol.recv_message(b)
    assert arrays["tris"].shape == (0, 3)


def test_message_without_arrays():
    a, b = Pipe()
    protocol.send_message(a, {"type": "ping"})
    assert protocol.recv_message(b) == ({"type": "ping"}, {})


def test_rejects_unsupported_dtype_on_send():
    a, _ = Pipe()
    with pytest.raises(protocol.ProtocolError):
        protocol.send_message(a, {"type": "x"}, {"v": np.zeros(3, dtype=np.float64)})


def test_rejects_malformed_header():
    a, b = Pipe()
    a.send_bytes(b"not json")
    with pytest.raises(protocol.ProtocolError):
        protocol.recv_message(b)


def test_rejects_header_without_type():
    a, b = Pipe()
    a.send_bytes(json.dumps({"job": 1}).encode())
    with pytest.raises(protocol.ProtocolError):
        protocol.recv_message(b)


def test_rejects_buffer_size_mismatch():
    a, b = Pipe()
    a.send_bytes(json.dumps({"type": "r", "buffers": [{"name": "v", "dtype": "float32", "shape": [4, 3]}]}).encode())
    a.send_bytes(np.zeros(5, dtype=np.float32).tobytes())
    with pytest.raises(protocol.ProtocolError):
        protocol.recv_message(b)
```

- [ ] **Step 2: Run to see them fail**

Run: `tools/test.sh -k protocol`
Expected: FAIL — `ModuleNotFoundError: No module named 'protocol'`.

- [ ] **Step 3: Implement `protocol.py`**

```python
"""Message framing between Blender and the worker, over a multiprocessing Connection.

A message is one JSON header frame followed by one raw frame per numpy array. No pickle: nothing received
can execute code. Imported as `protocol` inside the worker and as `blendsolid.worker.protocol` in Blender,
so it must not import other project modules.
"""
import json

import numpy as np

ALLOWED_DTYPES = {"float32", "int32"}


class ProtocolError(RuntimeError):
    pass


def send_message(conn, header, arrays=None):
    specs, blobs = [], []
    for name, arr in (arrays or {}).items():
        arr = np.ascontiguousarray(arr)
        if arr.dtype.name not in ALLOWED_DTYPES:
            raise ProtocolError(f"array '{name}' has unsupported dtype {arr.dtype.name}")
        specs.append({"name": name, "dtype": arr.dtype.name, "shape": list(arr.shape)})
        blobs.append(arr.tobytes())
    conn.send_bytes(json.dumps({**header, "buffers": specs}).encode("utf-8"))
    for blob in blobs:
        conn.send_bytes(blob)


def recv_message(conn):
    raw = conn.recv_bytes()
    try:
        header = json.loads(raw)
    except ValueError as e:
        raise ProtocolError(f"malformed header: {e}") from None
    if not isinstance(header, dict) or "type" not in header:
        raise ProtocolError("the header must be a JSON object with a 'type'")
    arrays = {}
    for spec in header.pop("buffers", []):
        if spec.get("dtype") not in ALLOWED_DTYPES:
            raise ProtocolError(f"unsupported dtype {spec.get('dtype')!r}")
        arr = np.frombuffer(conn.recv_bytes(), dtype=spec["dtype"])
        shape = [int(n) for n in spec["shape"]]
        if arr.size != int(np.prod(shape, dtype=np.int64)):
            raise ProtocolError(f"array '{spec['name']}': {arr.size} items, shape {shape}")
        arrays[spec["name"]] = arr.reshape(shape)
    return header, arrays
```

- [ ] **Step 4: Run the tests**

Run: `tools/test.sh -k protocol`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add blendsolid/worker tests/unit/test_protocol.py
git commit -m "Add worker message protocol (JSON headers + raw numpy buffers)"
```

---

### Task 3: Script parameters

**Files:**
- Create: `blendsolid/params.py`
- Test: `tests/unit/test_params.py`

**Interfaces:**
- Produces: `params.ParamError(ValueError)`; `params.Param` (frozen dataclass: `name: str`, `value: float`, `is_int: bool`, `lineno: int`); `params.parse_params(source: str) -> list[Param]` (raises `SyntaxError` for invalid Python, `ParamError` for duplicates); `params.set_param(source: str, name: str, value: float) -> str`; `params.format_value(value: float, is_int: bool) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_params.py`:
```python
import pytest

from blendsolid import params

SCRIPT = '''"""A bracket."""
from math import pi

length = 40.0
count = 4
offset = -2.5
width = 30.0  # mm

with BuildPart() as p:
    Box(length, width, 10)
depth = 3.0
result = p.part
'''


def test_parse_leading_numeric_assignments():
    ps = params.parse_params(SCRIPT)
    assert [(p.name, p.value, p.is_int) for p in ps] == [
        ("length", 40.0, False), ("count", 4.0, True), ("offset", -2.5, False), ("width", 30.0, False)]


def test_assignments_after_code_are_not_parameters():
    assert "depth" not in [p.name for p in params.parse_params(SCRIPT)]


def test_set_float_param_keeps_the_rest_of_the_line():
    out = params.set_param(SCRIPT, "width", 12.0)
    assert "width = 12.0  # mm\n" in out
    assert out.replace("width = 12.0", "width = 30.0") == SCRIPT


def test_set_param_rounds_float32_noise():
    out = params.set_param(SCRIPT, "length", 12.300000190734863)  # a Blender FloatProperty value
    assert "length = 12.3\n" in out


def test_set_int_param_stays_int():
    assert "count = 6\n" in params.set_param(SCRIPT, "count", 5.7)


def test_set_negative_param():
    assert "offset = -3.0\n" in params.set_param(SCRIPT, "offset", -3)


def test_unknown_param():
    with pytest.raises(params.ParamError):
        params.set_param(SCRIPT, "height", 1.0)


def test_duplicate_param():
    with pytest.raises(params.ParamError):
        params.parse_params("a = 1.0\na = 2.0\n")


def test_non_ascii_before_the_value():
    src = "città = 1.5  # Unicode names are valid Python\nresult = None\n"
    assert "città = 2.5  #" in params.set_param(src, "città", 2.5)


def test_invalid_python_raises_syntax_error():
    with pytest.raises(SyntaxError):
        params.parse_params("length = \n")
```

- [ ] **Step 2: Run to see them fail**

Run: `tools/test.sh -k params`
Expected: FAIL — `ImportError: cannot import name 'params'`.

- [ ] **Step 3: Implement `params.py`**

```python
"""Parameters of a history script: its leading top-level `name = <number>` assignments.

The docstring and imports may come first; the parameter block ends at the first other statement.
Editing a parameter rewrites only the number literal, keeping comments and formatting.
"""
import ast
from dataclasses import dataclass


class ParamError(ValueError):
    pass


@dataclass(frozen=True)
class Param:
    name: str
    value: float
    is_int: bool
    lineno: int


def _numeric_assignment(node):
    """(name, value, is_int, value_node) for `name = <number>` or `name = -<number>`, else None."""
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
        return None
    value, sign = node.value, 1
    if isinstance(value, ast.UnaryOp) and isinstance(value.op, (ast.USub, ast.UAdd)):
        sign = -1 if isinstance(value.op, ast.USub) else 1
        value = value.operand
    if isinstance(value, ast.Constant) and type(value.value) in (int, float):
        return node.targets[0].id, sign * value.value, type(value.value) is int, node.value
    return None


def _parameter_nodes(tree):
    for i, node in enumerate(tree.body):
        if i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            continue  # module docstring
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        found = _numeric_assignment(node)
        if found is None:
            return
        yield node, found


def parse_params(source):
    out, seen = [], set()
    for node, (name, value, is_int, _) in _parameter_nodes(ast.parse(source)):
        if name in seen:
            raise ParamError(f"parameter '{name}' is assigned twice (line {node.lineno})")
        seen.add(name)
        out.append(Param(name, float(value), is_int, node.lineno))
    return out


def format_value(value, is_int):
    if is_int:
        return str(int(round(value)))
    return repr(round(float(value), 6))  # drops float32 noise from Blender properties


def set_param(source, name, value):
    parse_params(source)  # validates duplicates
    for node, (pname, _, is_int, value_node) in _parameter_nodes(ast.parse(source)):
        if pname != name:
            continue
        if value_node.lineno != value_node.end_lineno:
            raise ParamError(f"parameter '{name}' must be written on one line")
        lines = source.splitlines(keepends=True)
        line = lines[value_node.lineno - 1].encode("utf-8")  # AST column offsets are UTF-8 byte offsets
        new = format_value(value, is_int).encode("utf-8")
        lines[value_node.lineno - 1] = (line[:value_node.col_offset] + new
                                        + line[value_node.end_col_offset:]).decode("utf-8")
        return "".join(lines)
    raise ParamError(f"unknown parameter '{name}'")
```

- [ ] **Step 4: Run the tests**

Run: `tools/test.sh -k params`
Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add blendsolid/params.py tests/unit/test_params.py
git commit -m "Add parsing and rewriting of script parameters"
```

---

### Task 4: Tessellation and script runner (worker side)

**Files:**
- Create: `blendsolid/worker/tessellate.py`, `blendsolid/worker/runner.py`
- Test: `tests/unit/test_runner.py`

**Interfaces:**
- Consumes: OCP 8 API (`OCP.collections.IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher`, `TopoDS.Face(x)`), build123d 0.13.
- Produces: `tessellate.check(shape: TopoDS_Shape) -> dict(valid: bool, volume: float, faces: int, solids: int)`; `tessellate.tessellate(shape, lin_defl=0.1, ang_defl=0.3) -> (verts float32 (N,3), tris int32 (M,3), tri_face int32 (M,))`; `runner.SCRIPT_NAME = "<history>"`; `runner.RunResult` dataclass (`ok, error="", line=None, volume=0.0, faces=0, verts=None, tris=None, tri_face=None, timing={}`); `runner.run_script(source: str, lin_defl=0.1, ang_defl=0.3) -> RunResult`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_runner.py`:
```python
import math

import numpy as np

import runner  # worker module, imported as the worker does

MODEL = """
length = 40.0
with BuildPart() as p:
    Box(length, 30, 20, align=Align.MIN)
    with Locations((20, 15, 0)):
        Cylinder(6, 25, align=(Align.CENTER, Align.CENTER, Align.MIN))
    fillet(p.edges().filter_by(Axis.Z).sort_by_distance((0, 0, 0))[0], radius=5)
result = p.part
"""
EXPECTED = 40 * 30 * 20 + math.pi * 36 * 5 - (1 - math.pi / 4) * 25 * 20


def mesh_volume(v, t):
    v = v.astype(np.float64)
    return np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum() / 6


def test_spike_model_volume_and_mesh():
    r = runner.run_script(MODEL)
    assert r.ok, r.error
    assert abs(r.volume - EXPECTED) < 1e-6
    assert r.verts.dtype == np.float32 and r.tris.dtype == np.int32 and r.tri_face.dtype == np.int32
    assert set(np.unique(r.tri_face)) == set(range(r.faces))
    assert abs(mesh_volume(r.verts, r.tris) - EXPECTED) / EXPECTED < 0.01


def test_builder_is_accepted_as_result():
    r = runner.run_script("with BuildPart() as p:\n    Box(1, 2, 3)\nresult = p\n")
    assert r.ok and abs(r.volume - 6.0) < 1e-9


def test_syntax_error_reports_line():
    r = runner.run_script("length = 1.0\nresult = Box(length,\n")
    assert not r.ok and r.error.startswith("SyntaxError") and r.line == 2


def test_runtime_error_reports_script_line():
    r = runner.run_script("a = 1.0\nb = 2.0\nresult = Box(a, b, undefined_name)\n")
    assert not r.ok and "NameError" in r.error and r.line == 3


def test_missing_result():
    r = runner.run_script("x = Box(1, 1, 1)\n")
    assert not r.ok and "`result`" in r.error


def test_result_must_be_a_shape():
    r = runner.run_script("result = 42\n")
    assert not r.ok and "build123d shape" in r.error


def test_result_without_solid():
    r = runner.run_script("result = Rectangle(10, 10)\n")
    assert not r.ok and "no solid" in r.error


def test_sys_exit_in_script_is_an_error_not_an_exit():
    r = runner.run_script("import sys\nsys.exit(3)\n")
    assert not r.ok and "sys.exit" in r.error
```

- [ ] **Step 2: Run to see them fail**

Run: `tools/test.sh -k runner`
Expected: FAIL — `ModuleNotFoundError: No module named 'runner'`.

- [ ] **Step 3: Implement `tessellate.py`**

```python
"""OCP helpers for the worker: validity, volume, face numbering and tessellation with BRep face IDs.

Faces are numbered with TopExp.MapShapes (deterministic for a given shape): brep_face_id = 0-based index.
"""
import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS


def _map(shape, kind):
    m = ShapeMap()
    TopExp.MapShapes_s(shape, kind, m)
    return m


def face_map(shape):
    m = _map(shape, TopAbs_FACE)
    return [TopoDS.Face(m.FindKey(i)) for i in range(1, m.Extent() + 1)]


def check(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return {"valid": BRepCheck_Analyzer(shape).IsValid(), "volume": props.Mass(),
            "faces": _map(shape, TopAbs_FACE).Extent(), "solids": _map(shape, TopAbs_SOLID).Extent()}


def tessellate(shape, lin_defl=0.1, ang_defl=0.3):
    """Vertices are not shared between faces: sharp edges between BRep faces, unambiguous face map."""
    BRepTools.Clean_s(shape)
    BRepMesh_IncrementalMesh(shape, lin_defl, False, ang_defl, True)
    verts, tris, tri_face, offset = [], [], [], 0
    for fid, face in enumerate(face_map(shape)):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            raise RuntimeError(f"face {fid} has no triangulation")
        trsf = loc.Transformation()
        nodes = [tri.Node(i).Transformed(trsf) for i in range(1, tri.NbNodes() + 1)]
        pts = np.array([(q.X(), q.Y(), q.Z()) for q in nodes], dtype=np.float64).reshape(-1, 3)
        t = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)],
                     dtype=np.int32).reshape(-1, 3) - 1
        if face.Orientation() == TopAbs_REVERSED:
            t = t[:, ::-1]
        verts.append(pts)
        tris.append(t + offset)
        tri_face.append(np.full(len(t), fid, dtype=np.int32))
        offset += len(pts)
    if not verts:
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32), np.zeros(0, np.int32)
    return (np.concatenate(verts).astype(np.float32), np.ascontiguousarray(np.concatenate(tris), dtype=np.int32),
            np.concatenate(tri_face))
```

- [ ] **Step 4: Implement `runner.py`**

```python
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
```

- [ ] **Step 5: Run the tests**

Run: `tools/test.sh -k runner`
Expected: `8 passed`.

- [ ] **Step 6: Commit**

```bash
git add blendsolid/worker/tessellate.py blendsolid/worker/runner.py tests/unit/test_runner.py
git commit -m "Add worker script runner and tessellation with BRep face IDs"
```

---

### Task 5: Worker process and client

**Files:**
- Modify: `blendsolid/worker/server.py` (replace the Task 1 placeholder)
- Create: `blendsolid/client.py`
- Test: `tests/unit/test_client.py`

**Interfaces:**
- Consumes: `protocol.send_message/recv_message` (Task 2), `runner.run_script` (Task 4), `paths.*` (Task 1).
- Produces: worker CLI `python -I server.py <port> <libs_dir> <pycache_dir>` with env `BLENDSOLID_WORKER_TOKEN`; requests `{"type": "run", "job", "key", "tag", "source", "lin_defl", "ang_defl"}`, `{"type": "ping"}`, `{"type": "quit"}`; events returned by `WorkerClient.poll()`:
  - `{"type": "ready", "build123d": str, "import_s": float}`
  - `{"type": "result", "job", "key", "tag", "ok": bool, "error": str, "line": int|None, "volume", "faces", "timing", "verts", "tris", "tri_face"}` (arrays only when `ok`)
  - `{"type": "crashed", "job": int|None, "key": str|None, "tag": str|None, "error": str, "dropped": list[[key, tag]]}` — `key` is the job that was running (None if the worker died before running anything); `dropped` are the queued requests the crash discarded
- `client.WorkerStartError(RuntimeError)`; `client.WorkerClient(python, server, libs, pycache_dir="", start_timeout=30.0, job_timeout=120.0)` with `start()`, `submit(key: str, source: str, tag: str, lin_defl=0.1, ang_defl=0.3) -> None`, `poll() -> list[dict]`, `stop()`, attributes `state` (`"stopped" | "starting" | "idle" | "busy"`), `info: dict`, `submitted: int`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_client.py`:
```python
import time

import pytest

from blendsolid import paths
from blendsolid.client import WorkerClient

BOX = "size = 10.0\nresult = Box(size, size, size)\n"


@pytest.fixture
def client():
    c = WorkerClient(paths.python_executable(), paths.server_script(), paths.worker_libs(),
                     paths.pycache_dir("blendsolid"), job_timeout=60.0)
    yield c
    c.stop()


def collect(c, n_results, timeout=120.0):
    """Poll until n result/crashed events arrived; returns every event seen."""
    events, end = [], time.monotonic() + timeout
    while time.monotonic() < end:
        events += c.poll()
        if sum(e["type"] in ("result", "crashed") for e in events) >= n_results:
            return events
        time.sleep(0.01)
    raise AssertionError(f"timed out; events: {[e['type'] for e in events]}")


def results(events):
    return [e for e in events if e["type"] in ("result", "crashed")]


def test_ready_then_result(client):
    client.submit("A", BOX, "t1")
    events = collect(client, 1)
    assert events[0]["type"] == "ready" and events[0]["build123d"] == "0.13.0"
    (r,) = results(events)
    assert r["ok"] and r["key"] == "A" and r["tag"] == "t1" and abs(r["volume"] - 1000.0) < 1e-9
    assert r["verts"].shape[1] == 3 and len(r["tri_face"]) == len(r["tris"])
    assert client.state == "idle"


def test_script_error_is_a_result_not_a_crash(client):
    client.submit("A", "result = Box(1, 1,\n", "bad")
    (r,) = results(collect(client, 1))
    assert r["type"] == "result" and not r["ok"] and r["line"] == 1


def test_crash_is_reported_and_worker_restarts(client):
    client.submit("A", "import os\nos._exit(3)\n", "crash")
    (r,) = results(collect(client, 1))
    assert r["type"] == "crashed" and r["key"] == "A" and r["tag"] == "crash"
    assert client.state == "stopped"
    client.submit("A", BOX, "ok")
    (r,) = results(collect(client, 1))
    assert r["ok"] and r["tag"] == "ok"


def test_crash_before_ready_drops_queued_requests(tmp_path):
    c = WorkerClient(paths.python_executable(), paths.server_script(), str(tmp_path),  # no build123d there
                     paths.pycache_dir("blendsolid"))
    try:
        c.submit("A", BOX, "a")
        c.submit("B", BOX, "b")
        (r,) = results(collect(c, 1, timeout=60))
        assert r["type"] == "crashed" and r["key"] is None and "build123d" in r["error"]
        assert sorted(r["dropped"]) == [["A", "a"], ["B", "b"]]
    finally:
        c.stop()


def test_timeout_kills_the_worker():
    c = WorkerClient(paths.python_executable(), paths.server_script(), paths.worker_libs(),
                     paths.pycache_dir("blendsolid"), job_timeout=1.0)
    try:
        c.submit("A", "import time\ntime.sleep(30)\nresult = Box(1, 1, 1)\n", "slow")
        # the first job also pays the worker's cold start: allow for it before the 1 s job timeout applies
        (r,) = results(collect(c, 1, timeout=60))
        assert r["type"] == "crashed" and "timed out" in r["error"]
    finally:
        c.stop()


def test_coalescing_per_key(client):
    client.submit("A", "import time\ntime.sleep(1.5)\nresult = Box(1, 1, 1)\n", "a1")
    collect_until_busy(client)
    client.submit("A", BOX, "a2")
    client.submit("B", BOX, "b1")
    client.submit("A", BOX, "a3")  # replaces a2, still queued behind B
    tags = [r["tag"] for r in results(collect(client, 3))]
    assert tags == ["a1", "b1", "a3"]


def collect_until_busy(c, timeout=60.0):
    end = time.monotonic() + timeout
    while c.state != "busy" and time.monotonic() < end:
        c.poll()
        time.sleep(0.01)
    assert c.state == "busy"


def test_stop_is_idempotent(client):
    client.stop()
    client.stop()
    assert client.state == "stopped"
```

- [ ] **Step 2: Run to see them fail**

Run: `tools/test.sh -k client`
Expected: FAIL — `ModuleNotFoundError: No module named 'blendsolid.client'`.

- [ ] **Step 3: Implement the worker entry point**

`blendsolid/worker/server.py`:
```python
"""BlendSolid geometry worker: runs history scripts with build123d in its own Python process.

Started by blendsolid.client with Blender's Python in isolated mode:
    python -I server.py <port> <libs_dir> <pycache_dir>     (env: BLENDSOLID_WORKER_TOKEN)
It connects back to Blender on 127.0.0.1:<port>, proves the token, imports build123d, reports "ready",
then answers one request at a time. This process, not Blender, owns sys.path and the heavy imports.
"""
import os
import socket
import sys
import time
from multiprocessing.connection import Connection


def main():
    port, libs = int(sys.argv[1]), sys.argv[2]
    if len(sys.argv) > 3 and sys.argv[3]:
        sys.pycache_prefix = sys.argv[3]
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path[:0] = [libs, here]  # -I doesn't add the script folder; our libraries win over Blender's

    import protocol

    conn = Connection(socket.create_connection(("127.0.0.1", port)).detach())
    conn.send_bytes(os.environ["BLENDSOLID_WORKER_TOKEN"].encode("ascii"))
    t0 = time.perf_counter()
    try:
        import build123d
        import runner
    except Exception as e:
        protocol.send_message(conn, {"type": "fatal", "error": f"cannot load build123d: {type(e).__name__}: {e}"})
        return 1
    protocol.send_message(conn, {"type": "ready", "build123d": build123d.__version__,
                                 "import_s": time.perf_counter() - t0})
    while True:
        try:
            header, _ = protocol.recv_message(conn)
        except EOFError:
            return 0
        kind = header["type"]
        if kind == "quit":
            return 0
        if kind == "ping":
            protocol.send_message(conn, {"type": "pong"})
        elif kind == "run":
            r = runner.run_script(header["source"], header.get("lin_defl", 0.1), header.get("ang_defl", 0.3))
            reply = {"type": "result", "job": header["job"], "key": header["key"], "tag": header["tag"],
                     "ok": r.ok, "error": r.error, "line": r.line, "volume": r.volume, "faces": r.faces,
                     "timing": r.timing}
            arrays = {"verts": r.verts, "tris": r.tris, "tri_face": r.tri_face} if r.ok else None
            protocol.send_message(conn, reply, arrays)
        else:
            protocol.send_message(conn, {"type": "error", "error": f"unknown request {kind!r}"})


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Implement the client**

`blendsolid/client.py`:
```python
"""Blender-side handle on the geometry worker. bpy-free: every call returns immediately except start(),
which waits only for the worker process to connect (not for build123d to load).

Requests are coalesced per key (a part): a newer request for the same key replaces a queued one.
"""
import hmac
import os
import secrets
import socket
import subprocess
import tempfile
import time
from collections import OrderedDict
from multiprocessing.connection import Connection

from .worker import protocol


class WorkerStartError(RuntimeError):
    pass


class WorkerClient:
    def __init__(self, python, server, libs, pycache_dir="", start_timeout=30.0, job_timeout=120.0):
        self.python, self.server, self.libs, self.pycache_dir = python, server, libs, pycache_dir
        self.start_timeout, self.job_timeout = start_timeout, job_timeout
        self.state = "stopped"
        self.info = {}
        self.submitted = 0
        self._proc = self._conn = self._stderr = None
        self._pending = OrderedDict()  # key -> request header
        self._running = None           # (job, key, tag, started_at)
        self._ready_at = None
        self._next_job = 1

    # -- lifecycle ---------------------------------------------------------------------------------------

    def start(self):
        if self.state != "stopped":
            return
        token = secrets.token_hex(16)
        server = socket.create_server(("127.0.0.1", 0))
        server.settimeout(self.start_timeout)
        self._stderr = tempfile.TemporaryFile()
        env = dict(os.environ, BLENDSOLID_WORKER_TOKEN=token)
        self._proc = subprocess.Popen(
            [self.python, "-I", self.server, str(server.getsockname()[1]), self.libs, self.pycache_dir],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=self._stderr)
        try:
            sock, _ = server.accept()
        except OSError as e:
            self._kill()
            raise WorkerStartError(f"the worker did not connect: {e}") from None
        finally:
            server.close()
        conn = Connection(sock.detach())
        if not conn.poll(self.start_timeout) or not hmac.compare_digest(conn.recv_bytes(), token.encode("ascii")):
            conn.close()
            self._kill()
            raise WorkerStartError("the worker failed the handshake")
        self._conn = conn
        self.state = "starting"
        self._ready_at = time.monotonic()

    def stop(self):
        if self._conn is not None and self._proc is not None and self._proc.poll() is None:
            try:
                protocol.send_message(self._conn, {"type": "quit"})
                self._proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self._kill()

    def _kill(self):
        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait()
        if self._conn is not None:
            self._conn.close()
        self._proc = self._conn = None
        self._running = None
        self.state = "stopped"

    # -- requests ----------------------------------------------------------------------------------------

    def submit(self, key, source, tag, lin_defl=0.1, ang_defl=0.3):
        self._pending[key] = {"type": "run", "key": key, "tag": tag, "source": source,
                              "lin_defl": lin_defl, "ang_defl": ang_defl}
        self._pending.move_to_end(key)
        if self.state == "stopped":
            self.start()
        self._dispatch()

    def _dispatch(self):
        if self.state != "idle" or not self._pending:
            return
        key, req = self._pending.popitem(last=False)
        req["job"] = self._next_job
        self._next_job += 1
        protocol.send_message(self._conn, req)
        self.submitted += 1
        self._running = (req["job"], key, req["tag"], time.monotonic())
        self.state = "busy"

    # -- events ------------------------------------------------------------------------------------------

    def poll(self):
        events = []
        if self.state == "stopped":
            return events
        try:
            while self._conn.poll(0):
                header, arrays = protocol.recv_message(self._conn)
                kind = header["type"]
                if kind == "ready":
                    self.info = header
                    self.state = "idle"
                elif kind == "result":
                    header.update(arrays)
                    self._running = None
                    self.state = "idle"
                elif kind == "fatal":
                    events.append(self._crash(header["error"]))
                    return events
                events.append(header)
                self._dispatch()
        except (EOFError, OSError, protocol.ProtocolError) as e:
            events.append(self._crash(f"lost the connection to the worker ({type(e).__name__})"))
            return events
        now = time.monotonic()
        if self._proc.poll() is not None:
            events.append(self._crash(f"the worker exited with code {self._proc.returncode}"))
        elif self._running and now - self._running[3] > self.job_timeout:
            events.append(self._crash(f"the recompute timed out after {self.job_timeout:.0f} s"))
        elif self.state == "starting" and now - self._ready_at > self.start_timeout:
            events.append(self._crash(f"the worker was not ready after {self.start_timeout:.0f} s"))
        return events

    def _crash(self, reason):
        job, key, tag = (self._running or (None, None, None, None))[:3]
        dropped = [[k, req["tag"]] for k, req in self._pending.items()]
        self._pending.clear()  # the caller decides what to resubmit; never restart in a loop by ourselves
        tail = self._stderr_tail()
        self._kill()
        return {"type": "crashed", "job": job, "key": key, "tag": tag, "dropped": dropped,
                "error": reason + (f"\n{tail}" if tail else "")}

    def _stderr_tail(self, limit=2000):
        if self._stderr is None:
            return ""
        try:
            self._stderr.seek(0)
            return self._stderr.read().decode("utf-8", "replace")[-limit:].strip()
        except OSError:
            return ""
```

Note for the timeout test: the job clock starts when the request is *sent*, which happens only after `ready`, so the worker's cold start doesn't count against `job_timeout`.

- [ ] **Step 5: Run the tests**

Run: `tools/test.sh -k client`
Expected: `7 passed` (≈15–30 s: each test starts a real worker).

- [ ] **Step 6: Run on Windows once**

The unit tests run on Linux. Check the socket handshake and `-I` on Windows with the portable Blender:

Run:
```bash
BW=/mnt/e/blender-5.2.2-windows-x64
"$BW/5.2/python/bin/python.exe" -m pip install --target 'E:\blender-5.2.2-windows-x64\bs_pytest' pytest
export BLENDSOLID_WORKER_LIBS='E:\blender-5.2.2-windows-x64\full_libs'
export PYTHONPATH="$(wslpath -w .);E:\blender-5.2.2-windows-x64\bs_pytest"
export WSLENV=BLENDSOLID_WORKER_LIBS:PYTHONPATH   # pass both, unchanged, to the Windows process
"$BW/5.2/python/bin/python.exe" -m pytest "$(wslpath -w tests/unit/test_client.py)" -q -p no:cacheprovider
```
Expected: `7 passed`. (`full_libs` is the full dependency set installed during ADR 0001; recreate it with `pip install --target ... -r tools/worker-requirements.txt` if missing.)

- [ ] **Step 7: Commit**

```bash
git add blendsolid/worker/server.py blendsolid/client.py tests/unit/test_client.py
git commit -m "Add persistent geometry worker with handshake, coalescing, crash and timeout handling"
```

---

### Task 6: Parts in Blender and the reconcile loop

**Files:**
- Create: `blendsolid/part.py`, `blendsolid/templates/default_part.py`
- Modify: `blendsolid/runtime.py` (replace the Task 1 stub)
- Create (minimal, completed in Task 7): `blendsolid/ui.py` with the property registration only
- Test: `tests/blender/test_parts.py`

**Interfaces:**
- Consumes: `WorkerClient` (Task 5), `params` (Task 3), `paths` (Task 1).
- Produces:
  - `ui.BS_Param` PropertyGroup (`name`, `value: FloatProperty`, `is_int: BoolProperty`); Object properties `blendsolid_script: PointerProperty(type=Text)`, `blendsolid_params: CollectionProperty(type=BS_Param)`, `blendsolid_error: StringProperty`, `blendsolid_error_line: IntProperty`.
  - `part.FACE_ATTR = "brep_face_id"`, `part.HASH_KEY = "bs_source_hash"`; `part.default_source() -> str`; `part.new_part(context, source=None, name="Part") -> Object`; `part.part_objects() -> list[Object]`; `part.source_of(obj) -> str`; `part.source_hash(source) -> str`; `part.applied_hash(obj) -> str | None`; `part.apply_result(obj, event) -> None`; `part.set_error(obj, message, line=None)`; `part.sync_params(obj, source=None)`; `part.set_param(obj, name, value)`; `part.is_syncing() -> bool`; `part.ensure_unique_scripts() -> None`; `part.mesh_volume(mesh) -> float`.
  - `runtime.tick() -> float`; `runtime.client() -> WorkerClient`; `runtime.force(obj)`; `runtime.reset_state()`; `runtime.register()`, `runtime.unregister()`; `runtime.TICK_INTERVAL = 0.05`.

- [ ] **Step 1: Write the default part template**

`blendsolid/templates/default_part.py` (it is data read as text, not imported):
```python
# BlendSolid part. The numbers below are its parameters: edit them here or in the BlendSolid panel.
length = 40.0
width = 30.0
height = 20.0
boss_radius = 6.0
boss_height = 25.0
fillet_radius = 5.0

with BuildPart() as part:
    Box(length, width, height, align=Align.MIN)
    with Locations((length / 2, width / 2, 0)):
        Cylinder(boss_radius, boss_height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    fillet(part.edges().filter_by(Axis.Z).sort_by_distance((0, 0, 0))[0], radius=fillet_radius)

result = part.part
```

Add to the manifest's `[build]` nothing: `.py` templates are packaged by default.

- [ ] **Step 2: Write the failing Blender tests**

`tests/blender/test_parts.py`:
```python
import math
import os
import tempfile

import bpy

from blendsolid import part, runtime
from conftest import wait_for


def expected_volume(length=40.0, width=30.0, height=20.0, r=6.0, bh=25.0, f=5.0):
    return length * width * height + math.pi * r * r * (bh - height) - (1 - math.pi / 4) * f * f * height


def up_to_date(obj):
    return part.applied_hash(obj) == part.source_hash(part.source_of(obj))


def new_part():
    obj = part.new_part(bpy.context)
    wait_for(lambda: up_to_date(obj))
    return obj


def test_new_part_builds_mesh_with_face_ids(clean):
    obj = new_part()
    assert abs(part.mesh_volume(obj.data) - expected_volume()) / expected_volume() < 0.01
    ids = {v.value for v in obj.data.attributes[part.FACE_ATTR].data}
    assert ids == set(range(len(ids))) and len(ids) >= 9
    assert [p.name for p in obj.blendsolid_params] == [
        "length", "width", "height", "boss_radius", "boss_height", "fillet_radius"]
    assert obj.blendsolid_error == ""


def test_param_edit_rewrites_script_and_recomputes(clean):
    obj = new_part()
    obj.blendsolid_params["height"].value = 22.0
    assert "height = 22.0\n" in part.source_of(obj)
    wait_for(lambda: up_to_date(obj))
    assert abs(part.mesh_volume(obj.data) - expected_volume(height=22.0)) / expected_volume(height=22.0) < 0.01


def test_error_keeps_previous_mesh(clean):
    obj = new_part()
    n_polys = len(obj.data.polygons)
    good_hash = part.applied_hash(obj)
    obj.blendsolid_script.from_string(part.source_of(obj).replace("result = part.part", "result = part.prt"))
    wait_for(lambda: obj.blendsolid_error != "")
    assert "AttributeError" in obj.blendsolid_error and obj.blendsolid_error_line > 0
    assert len(obj.data.polygons) == n_polys and part.applied_hash(obj) == good_hash
    obj.blendsolid_script.from_string(part.source_of(obj).replace("part.prt", "part.part"))
    wait_for(lambda: obj.blendsolid_error == "" and up_to_date(obj))


def test_stale_result_is_discarded(clean):
    obj = new_part()
    obj.blendsolid_params["length"].value = 50.0
    runtime.tick()                                   # submits length=50
    obj.blendsolid_params["length"].value = 60.0     # before the first result arrives
    wait_for(lambda: up_to_date(obj))
    assert "length = 60.0\n" in part.source_of(obj)
    assert abs(part.mesh_volume(obj.data) - expected_volume(length=60.0)) / expected_volume(length=60.0) < 0.01


def test_reconcile_after_simulated_undo(clean):
    obj = new_part()
    source_a = part.source_of(obj)
    obj.blendsolid_params["width"].value = 35.0
    wait_for(lambda: up_to_date(obj))
    # an undo step can restore the script while the mesh is one step behind: the tick must repair it
    obj.blendsolid_script.from_string(source_a)
    assert not up_to_date(obj)
    wait_for(lambda: up_to_date(obj))
    assert abs(part.mesh_volume(obj.data) - expected_volume()) / expected_volume() < 0.01


def test_crash_does_not_loop(clean):
    obj = new_part()
    obj.blendsolid_script.from_string("import os\nos._exit(7)\n")
    wait_for(lambda: "crashed" in obj.blendsolid_error or "exited" in obj.blendsolid_error)
    submitted = runtime.client().submitted
    for _ in range(20):
        runtime.tick()
    assert runtime.client().submitted == submitted
    obj.blendsolid_script.from_string(part.default_source())
    wait_for(lambda: obj.blendsolid_error == "" and up_to_date(obj))


def test_duplicate_gets_own_script(clean):
    obj = new_part()
    dup = obj.copy()
    dup.data = obj.data.copy()
    bpy.context.collection.objects.link(dup)
    runtime.tick()
    assert dup.blendsolid_script != obj.blendsolid_script
    dup.blendsolid_params["length"].value = 70.0
    wait_for(lambda: up_to_date(dup))
    assert "length = 40.0\n" in part.source_of(obj)


def test_reload_does_not_recompute(clean):
    obj = new_part()
    path = os.path.join(tempfile.mkdtemp(), "part.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    submitted = runtime.client().submitted
    for _ in range(10):
        runtime.tick()
    obj = bpy.data.objects["Part"]
    assert up_to_date(obj) and runtime.client().submitted == submitted
```

- [ ] **Step 3: Run to see them fail**

Run: `tools/test.sh -k parts`
Expected: FAIL — `ImportError: cannot import name 'part'`.

- [ ] **Step 4: Implement the properties in `ui.py` (operators and panel come in Task 7)**

`blendsolid/ui.py`:
```python
"""Properties, operators and panel of BlendSolid."""
import bpy
from bpy.props import BoolProperty, CollectionProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import part


def _on_param_value(self, context):
    if part.is_syncing():
        return
    part.set_param(self.id_data, self.name, self.value)


class BS_Param(bpy.types.PropertyGroup):
    value: FloatProperty(name="Value", update=_on_param_value, precision=3)
    is_int: BoolProperty(default=False)


CLASSES = [BS_Param]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.blendsolid_script = PointerProperty(name="Script", type=bpy.types.Text)
    bpy.types.Object.blendsolid_params = CollectionProperty(type=BS_Param)
    bpy.types.Object.blendsolid_error = StringProperty()
    bpy.types.Object.blendsolid_error_line = IntProperty()


def unregister():
    for name in ("blendsolid_error_line", "blendsolid_error", "blendsolid_params", "blendsolid_script"):
        delattr(bpy.types.Object, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
```

- [ ] **Step 5: Implement `part.py`**

```python
"""BlendSolid parts: a mesh object whose geometry comes from a history script stored in a Text datablock.

The script is the source of truth; the mesh is a cache tagged with the hash of the script that produced it.
"""
import hashlib
import os

import bpy
import numpy as np

from . import params

FACE_ATTR = "brep_face_id"
HASH_KEY = "bs_source_hash"
_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "default_part.py")
_syncing = False


def default_source():
    with open(_TEMPLATE, encoding="utf-8") as f:
        return f.read()


def is_syncing():
    return _syncing


def part_objects():
    return [o for o in bpy.data.objects if o.type == "MESH" and o.blendsolid_script is not None]


def source_of(obj):
    return obj.blendsolid_script.as_string()


def source_hash(source):
    return hashlib.sha1(source.encode("utf-8")).hexdigest()


def applied_hash(obj):
    return obj.data.get(HASH_KEY)


def new_part(context, source=None, name="Part"):
    source = default_source() if source is None else source
    text = bpy.data.texts.new(f".{name}.py")  # dot name: hidden from Blender's ID menus (ADR 0002)
    text.from_string(source)
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    context.collection.objects.link(obj)
    obj.blendsolid_script = text
    sync_params(obj, source)
    return obj


def apply_result(obj, event):
    fill_mesh(obj.data, event["verts"], event["tris"], event["tri_face"])
    obj.data[HASH_KEY] = event["tag"]
    obj.blendsolid_error = ""
    obj.blendsolid_error_line = 0


def set_error(obj, message, line=None):
    obj.blendsolid_error = message
    obj.blendsolid_error_line = line or 0


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


def ensure_unique_scripts():
    """Shift+D copies the object and its mesh but shares the Text: give each independent copy its own script.
    Objects sharing the same mesh (Alt+D, linked duplicates) keep sharing the script."""
    by_text = {}
    for obj in part_objects():
        by_text.setdefault(obj.blendsolid_script.name, []).append(obj)
    for objs in by_text.values():
        objs.sort(key=lambda o: o.name)
        first_mesh = objs[0].data.name
        for obj in objs[1:]:
            if obj.data.name != first_mesh:  # an independent copy, not a linked duplicate
                obj.blendsolid_script = obj.blendsolid_script.copy()
```

- [ ] **Step 6: Implement `runtime.py`**

```python
"""Keeps every BlendSolid part's mesh in sync with its script, through the worker.

A timer runs tick(): it applies worker events, then submits every part whose script hash differs from the
hash stored on its mesh. Parameter edits, script edits, undo/redo and file loads all converge through this
single path; nothing is decided in undo handlers (evaluated data isn't ready there — spike finding).
"""
import bpy
from bpy.app.handlers import persistent

from . import part, paths
from .client import WorkerClient, WorkerStartError

TICK_INTERVAL = 0.05
_client = None
_inflight = {}  # object name -> script hash being computed
_failed = {}    # object name -> script hash that failed (not resubmitted until the script changes)


def client():
    global _client
    if _client is None:
        _client = WorkerClient(paths.python_executable(), paths.server_script(), paths.worker_libs(),
                               paths.pycache_dir(__package__))
    return _client


def reset_state():
    _inflight.clear()
    _failed.clear()


def force(obj):
    """Recompute even if the script is unchanged (the Recompute button)."""
    _failed.pop(obj.name, None)
    if part.HASH_KEY in obj.data:
        del obj.data[part.HASH_KEY]


def _handle(event):
    kind = event["type"]
    if kind == "crashed":
        for key, tag in event.get("dropped", []):
            if _inflight.get(key) == tag:
                del _inflight[key]      # resubmitted by the next tick (restarting the worker)...
            if event["key"] is None:    # ...unless the worker can't even start: don't loop
                _failed[key] = tag
                obj = bpy.data.objects.get(key)
                if obj is not None:
                    part.set_error(obj, f"The geometry worker failed: {event['error']}")
    if kind not in ("result", "crashed") or not event.get("key"):
        return
    key, tag = event["key"], event["tag"]
    if _inflight.get(key) == tag:
        del _inflight[key]
    obj = bpy.data.objects.get(key)
    if obj is None or obj.blendsolid_script is None:
        return
    if tag != part.source_hash(part.source_of(obj)):
        return  # stale: the script changed meanwhile, the next tick submits the new one
    if kind == "result" and event["ok"]:
        _failed.pop(key, None)
        part.apply_result(obj, event)
    else:
        _failed[key] = tag
        message = event["error"] if kind == "result" else f"The geometry worker crashed: {event['error']}"
        part.set_error(obj, message, event.get("line"))


def tick():
    c = client()
    for event in c.poll():
        _handle(event)
    part.ensure_unique_scripts()
    for obj in part.part_objects():
        source = part.source_of(obj)
        tag = part.source_hash(source)
        if tag in (part.applied_hash(obj), _inflight.get(obj.name), _failed.get(obj.name)):
            continue
        part.sync_params(obj, source)
        try:
            c.submit(obj.name, source, tag)
        except WorkerStartError as e:
            _failed[obj.name] = tag
            part.set_error(obj, f"Cannot start the geometry worker: {e}")
            continue
        _inflight[obj.name] = tag
    return TICK_INTERVAL


def _timer():
    try:
        return tick()
    except Exception as e:  # a timer that raises is unregistered by Blender: log and keep running
        print(f"BlendSolid: {type(e).__name__}: {e}")
        return 1.0


@persistent
def _on_load(*_):
    reset_state()


def register():
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.timers.register(_timer, first_interval=TICK_INTERVAL, persistent=True)


def unregister():
    global _client
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if _client is not None:
        _client.stop()
        _client = None
    reset_state()
```

Note on `test_reload_does_not_recompute`: `open_mainfile` fires `load_post`, which clears the runtime state; the mesh keeps `bs_source_hash` in the `.blend`, so the tick sees the part as up to date and submits nothing.

- [ ] **Step 7: Run the Blender tests**

Run: `tools/test.sh -k "parts or register"`
Expected: `9 passed`.

- [ ] **Step 8: Commit**

```bash
git add blendsolid/part.py blendsolid/runtime.py blendsolid/ui.py blendsolid/templates tests/blender/test_parts.py
git commit -m "Add parts stored as scripts and the reconcile loop with the worker"
```

---

### Task 7: Operators and panel

**Files:**
- Modify: `blendsolid/ui.py`
- Test: `tests/blender/test_ui.py`

**Interfaces:**
- Consumes: `part.*`, `runtime.force` (Task 6).
- Produces: operators `blendsolid.new_part` (REGISTER, UNDO), `blendsolid.edit_script` (only when scripts are shown), `blendsolid.recompute` (REGISTER, UNDO); panel `BLENDSOLID_PT_part` in the 3D Viewport sidebar, tab "BlendSolid"; add-on preferences `BLENDSOLID_AP_preferences` with `show_scripts: BoolProperty` (default False); `ui.scripts_visible(context) -> bool` (False when the add-on isn't registered as an extension, e.g. in tests, unless `ui.FORCE_SHOW_SCRIPTS` is set).

- [ ] **Step 1: Write the failing tests**

`tests/blender/test_ui.py`:
```python
import bpy

from blendsolid import part
from conftest import wait_for


def test_new_part_operator(clean):
    assert bpy.ops.blendsolid.new_part() == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    assert obj is not None and obj.blendsolid_script is not None and obj.select_get()
    wait_for(lambda: part.applied_hash(obj) == part.source_hash(part.source_of(obj)))


def test_recompute_operator_resubmits(clean):
    bpy.ops.blendsolid.new_part()
    obj = bpy.context.view_layer.objects.active
    wait_for(lambda: part.applied_hash(obj) is not None)
    assert bpy.ops.blendsolid.recompute() == {"FINISHED"}
    assert part.applied_hash(obj) is None
    wait_for(lambda: part.applied_hash(obj) is not None)


def test_panel_is_registered(addon):
    assert hasattr(bpy.types, "BLENDSOLID_PT_part")


def test_script_is_hidden_by_default(clean):
    from blendsolid import ui
    bpy.ops.blendsolid.new_part()
    obj = bpy.context.view_layer.objects.active
    assert obj.blendsolid_script.name.startswith(".")
    assert not ui.scripts_visible(bpy.context)
    assert not bpy.ops.blendsolid.edit_script.poll()
    ui.FORCE_SHOW_SCRIPTS = True
    try:
        assert ui.scripts_visible(bpy.context)
    finally:
        ui.FORCE_SHOW_SCRIPTS = False
```

- [ ] **Step 2: Run to see them fail**

Run: `tools/test.sh -k ui`
Expected: FAIL — `AttributeError: ... has no attribute 'new_part'`.

- [ ] **Step 3: Add operators and panel to `ui.py`**

Add after `BS_Param` (keep the existing property code):
```python
class BLENDSOLID_OT_new_part(bpy.types.Operator):
    """Add a new BlendSolid part defined by a build123d script"""
    bl_idname = "blendsolid.new_part"
    bl_label = "New Part"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for obj in context.selected_objects:
            obj.select_set(False)
        obj = part.new_part(context)
        obj.location = context.scene.cursor.location
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


FORCE_SHOW_SCRIPTS = False  # tests: the add-on isn't registered as an extension there, so it has no preferences


class BLENDSOLID_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    show_scripts: BoolProperty(
        name="Show history scripts",
        description="Advanced: show and edit the build123d script behind each part",
        default=False)

    def draw(self, context):
        self.layout.prop(self, "show_scripts")


def scripts_visible(context):
    if FORCE_SHOW_SCRIPTS:
        return True
    addon = context.preferences.addons.get(__package__)
    return bool(addon and addon.preferences and addon.preferences.show_scripts)


class BLENDSOLID_OT_edit_script(bpy.types.Operator):
    """Show the part's script in a Text Editor"""
    bl_idname = "blendsolid.edit_script"
    bl_label = "Edit Script"

    @classmethod
    def poll(cls, context):
        return (scripts_visible(context) and context.object is not None
                and context.object.blendsolid_script is not None)

    def execute(self, context):
        editors = [a for a in context.screen.areas if a.type == "TEXT_EDITOR"]
        if not editors:
            self.report({"WARNING"}, "Open a Text Editor area to edit the script")
            return {"CANCELLED"}
        editors[0].spaces.active.text = context.object.blendsolid_script
        return {"FINISHED"}


class BLENDSOLID_OT_recompute(bpy.types.Operator):
    """Recompute the part even if its script didn't change"""
    bl_idname = "blendsolid.recompute"
    bl_label = "Recompute"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.blendsolid_script is not None

    def execute(self, context):
        from . import runtime
        runtime.force(context.object)
        return {"FINISHED"}


class BLENDSOLID_PT_part(bpy.types.Panel):
    bl_label = "BlendSolid"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlendSolid"

    def draw(self, context):
        layout = self.layout
        obj = context.object
        layout.operator("blendsolid.new_part", icon="ADD")
        if obj is None or obj.blendsolid_script is None:
            return
        col = layout.column(align=True)
        for item in obj.blendsolid_params:
            col.prop(item, "value", text=item.name.replace("_", " ").capitalize())
        advanced = scripts_visible(context)
        if obj.blendsolid_error:
            box = layout.box()
            box.label(text="The part could not be rebuilt", icon="ERROR")
            line = f" (line {obj.blendsolid_error_line})" if advanced and obj.blendsolid_error_line else ""
            for i, text in enumerate(obj.blendsolid_error.splitlines()[:6]):
                box.label(text=(text + line) if i == 0 else text, icon="BLANK1")
        row = layout.row(align=True)
        if advanced:
            row.operator("blendsolid.edit_script", icon="TEXT")
        row.operator("blendsolid.recompute", icon="FILE_REFRESH")
```

Replace `CLASSES = [BS_Param]` with:
```python
CLASSES = [BS_Param, BLENDSOLID_AP_preferences, BLENDSOLID_OT_new_part, BLENDSOLID_OT_edit_script,
           BLENDSOLID_OT_recompute, BLENDSOLID_PT_part]
```

- [ ] **Step 4: Run all tests**

Run: `tools/test.sh`
Expected: all unit and Blender tests pass.

- [ ] **Step 5: Commit**

```bash
git add blendsolid/ui.py tests/blender/test_ui.py
git commit -m "Add New Part, Edit Script and Recompute operators and the sidebar panel"
```

---

### Task 8: Packaging, install smoke test, manual GUI test

**Files:**
- Create: `tools/build_extension.py`, `tools/smoke_installed.py`
- Modify: `README.md` (roadmap status, how to try), `CLAUDE.md` (commands), `SPIKE_REPORT.md` untouched
- Create: `docs/milestone-1-report.md`

**Interfaces:**
- Consumes: everything above.
- Produces: `python tools/build_extension.py --platform {windows-x64,linux-x64,macos-arm64} --blender <exe> [--out dist]` → `dist/blendsolid-<version>-<platform>.zip`; `blender -b --python tools/smoke_installed.py` prints `SMOKE PASS` or exits non-zero.

- [ ] **Step 1: Write the build script**

`tools/build_extension.py`:
```python
"""Build a per-platform BlendSolid extension zip, with the worker libraries bundled in blendsolid/worker_libs.

Run it with Blender's Python (pip downloads the target platform's binary wheels):
    <blender>/5.2/python/bin/python3.13 tools/build_extension.py --platform windows-x64 --blender <blender>
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATFORM_TAGS = {
    "windows-x64": ["win_amd64"],
    "linux-x64": ["manylinux_2_28_x86_64", "manylinux_2_27_x86_64", "manylinux_2_17_x86_64",
                  "manylinux2014_x86_64", "linux_x86_64"],
    "macos-arm64": ["macosx_14_0_arm64", "macosx_12_0_arm64", "macosx_11_0_arm64"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True, choices=sorted(PLATFORM_TAGS))
    ap.add_argument("--blender", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    args = ap.parse_args()

    stage = os.path.join(args.out, f"stage-{args.platform}", "blendsolid")
    shutil.rmtree(os.path.dirname(stage), ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "blendsolid"), stage,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "worker_libs"))
    manifest = os.path.join(stage, "blender_manifest.toml")
    with open(manifest, encoding="utf-8") as f:
        text = f.read()
    version = re.search(r'^version = "([^"]+)"', text, re.M).group(1)
    text = re.sub(r"^platforms = \[.*\]$", f'platforms = ["{args.platform}"]', text, flags=re.M)
    with open(manifest, "w", encoding="utf-8") as f:
        f.write(text)

    pip = [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--target", os.path.join(stage, "worker_libs"),
           "--only-binary=:all:", "--python-version", "3.13", "--implementation", "cp"]
    for tag in PLATFORM_TAGS[args.platform]:
        pip += ["--platform", tag]
    subprocess.run(pip + ["-r", os.path.join(ROOT, "tools", "worker-requirements.txt")], check=True)

    os.makedirs(args.out, exist_ok=True)
    zip_path = os.path.join(args.out, f"blendsolid-{version}-{args.platform}.zip")
    subprocess.run([args.blender, "--command", "extension", "build", "--source-dir", stage,
                    "--output-filepath", zip_path], check=True)
    print(f"built {zip_path} ({os.path.getsize(zip_path) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the smoke test**

`tools/smoke_installed.py`:
```python
"""Headless smoke test of an installed BlendSolid extension: new part → worker → mesh.

Usage: blender -b --python tools/smoke_installed.py
(no --factory-startup: it would skip the preferences, where installed extensions are enabled)
"""
import importlib
import math
import sys
import time

import bpy

mod = next((m for m in sys.modules if m.endswith(".blendsolid") and m.startswith("bl_ext.")), None)
if mod is None:
    print("SMOKE FAIL: the blendsolid extension is not enabled")
    sys.exit(1)
part = importlib.import_module(mod + ".part")
runtime = importlib.import_module(mod + ".runtime")

bpy.ops.blendsolid.new_part()
obj = bpy.context.view_layer.objects.active
t0 = time.monotonic()
while time.monotonic() - t0 < 180:
    runtime.tick()
    if part.applied_hash(obj) or obj.blendsolid_error:
        break
    time.sleep(0.05)
expected = 40 * 30 * 20 + math.pi * 36 * 5 - (1 - math.pi / 4) * 25 * 20
vol = part.mesh_volume(obj.data) if part.applied_hash(obj) else 0.0
ok = not obj.blendsolid_error and abs(vol - expected) / expected < 0.01
print(f"first result after {time.monotonic() - t0:.1f} s, volume {vol:.1f} (expected {expected:.1f}), "
      f"error: {obj.blendsolid_error or '-'}")
print("SMOKE PASS" if ok else "SMOKE FAIL")
runtime.unregister()
sys.exit(0 if ok else 1)
```

- [ ] **Step 3: Build and smoke-test on Linux**

Run:
```bash
BL=~/blender/blender-5.2.2-linux-x64/blender; PY=~/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13
$PY tools/build_extension.py --platform linux-x64 --blender $BL
$BL --command extension install-file -r user_default -e dist/blendsolid-0.1.0-linux-x64.zip
$BL -b --python tools/smoke_installed.py
```
Expected: `built dist/blendsolid-0.1.0-linux-x64.zip (~250 MB)`, then `SMOKE PASS`.
If `extension build` rejects the bundled binaries in `worker_libs`, stop and report the exact message: it decides how the full build must be packaged (ADR 0001 follow-up).

- [ ] **Step 4: Build and smoke-test on Windows (portable Blender)**

Run:
```bash
$PY tools/build_extension.py --platform windows-x64 --blender $BL
BW=/mnt/e/blender-5.2.2-windows-x64/blender.exe
"$BW" --command extension install-file -r user_default -e "$(wslpath -w dist/blendsolid-0.1.0-windows-x64.zip)"
"$BW" -b --python "$(wslpath -w tools/smoke_installed.py)"
```
Expected: `SMOKE PASS`; note the "first result after" time (cold start on Windows).

- [ ] **Step 5: Manual GUI test on Windows — give the maintainer these exact steps and record what they observe**

Launch `E:\blender-5.2.2-windows-x64\blender.exe` (the extension from Step 4 is installed there).
1. 3D Viewport → `N` → tab **BlendSolid** → **New Part**. Expected: after a moment (up to ~10 s the very first time) the box-with-boss appears; the panel lists 6 parameters.
2. Drag **Height** slowly from 20 to 30. Expected: the solid follows, possibly a little behind the mouse, and ends exactly at the final value; Blender never freezes.
3. `Ctrl+Z` three times, then `Ctrl+Shift+Z` twice. Expected: each time the solid matches the parameter values shown in the panel.
4. Check that the panel has **no** *Edit Script* button. Then Edit → Preferences → Add-ons → BlendSolid → enable **Show history scripts**. Split the viewport, make one area a **Text Editor**, press **Edit Script**; change `fillet_radius = 5.0` to `12.0` in the text. Expected: the fillet grows within a second, and the panel shows 12.0.
5. In the text, change `result = part.part` to `result = part.prt`. Expected: the old solid stays, the panel shows an `AttributeError` with its line. Fix the text: the error disappears.
6. `Shift+D` the part, move it, change its **Length**. Expected: only the copy changes.
7. Save the file, close Blender, reopen the file. Expected: the part appears immediately, identical, without a recompute delay.
Record for each step: OK / what happened instead.

- [ ] **Step 6: Write the milestone report and update docs**

Create `docs/milestone-1-report.md` with: success criterion of milestone 1 from `docs/spec.md` and whether it is met; the test counts from `tools/test.sh`; zip sizes and smoke-test times (Steps 3–4); the manual test results (Step 5); problems found and what changed in the plan.
In `README.md`, set milestone 1 status to "✅ Done" (or "⚠️ Partial" with the reason) and add a "Try it" section with the three commands of Step 3. In `CLAUDE.md` add `tools/build_extension.py` and `tools/smoke_installed.py` to the commands.

- [ ] **Step 7: Commit**

```bash
git add tools/build_extension.py tools/smoke_installed.py docs/milestone-1-report.md README.md CLAUDE.md
git commit -m "Package the extension with bundled worker libraries; milestone 1 report"
```
