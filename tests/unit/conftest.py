"""Unit tests run with Blender's Python but without bpy. Worker modules are imported the way the worker
imports them: with blendsolid/worker and the worker libraries on sys.path (this is the test process,
not Blender, so changing sys.path here is fine)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKER_DIR = os.path.join(ROOT, "blendsolid", "worker")
# Same precedence as paths.worker_libs(): an explicit override always wins over the Linux-only dev cache,
# so a Windows test run (which sets this to its own `full_libs`) never picks up incompatible .so files.
DEV_LIBS = os.environ.get("BLENDSOLID_WORKER_LIBS") or os.path.join(ROOT, ".dev", "worker_libs")

for p in (DEV_LIBS, WORKER_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)  # must win over Blender's bundled site-packages (e.g. typing_extensions)
