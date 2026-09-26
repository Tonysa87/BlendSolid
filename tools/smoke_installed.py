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
