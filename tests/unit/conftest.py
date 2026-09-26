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
