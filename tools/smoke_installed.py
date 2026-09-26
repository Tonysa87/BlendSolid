"""Headless smoke test of an installed BlendSolid extension: new part → worker → mesh, then a primitive cut by a
live cutter part (Shift+A operators, the Boolean operator, ref() resolved by the installed worker).

Usage: blender -b --python tools/smoke_installed.py
(no --factory-startup: it would skip the preferences, where installed extensions are enabled)
"""
import hashlib
import importlib
import math
import os
import sys
import time

import bpy

mod = next((m for m in sys.modules if m.endswith(".blendsolid") and m.startswith("bl_ext.")), None)
if mod is None:
    print("SMOKE FAIL: the blendsolid extension is not enabled")
    sys.exit(1)
pkg = importlib.import_module(mod)
installed_dir = os.path.dirname(os.path.abspath(pkg.__file__))
repo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blendsolid")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


diffs = []
for root, dirs, files in os.walk(repo_dir):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "worker_libs")]
    for name in files:
        if not name.endswith(".py"):
            continue
        rel = os.path.relpath(os.path.join(root, name), repo_dir)
        installed_file = os.path.join(installed_dir, rel)
        if not os.path.isfile(installed_file):
            diffs.append(f"{rel}: missing from the installed extension")
        elif sha256(os.path.join(root, name)) != sha256(installed_file):
            diffs.append(f"{rel}: content differs from the repository")
if diffs:
    print("SMOKE FAIL: installed extension doesn't match the repository")
    for d in diffs:
        print(f"  {d}")
    sys.exit(1)

part = importlib.import_module(mod + ".part")
runtime = importlib.import_module(mod + ".runtime")


def wait(objs, timeout=180):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        runtime.tick()
        if all(part.applied_hash(o) == part.current_tag(o) or o.blendsolid_error for o in objs):
            break
        time.sleep(0.05)
    return time.monotonic() - t0


def mm3(obj):
    # scripts are in millimetres, the mesh in scene units (ADR 0003): compare in mm³
    return part.mesh_volume(obj.data) / part.unit_factor() ** 3 if part.applied_hash(obj) else 0.0


bpy.ops.blendsolid.new_part()
obj = bpy.context.view_layer.objects.active
elapsed = wait([obj])
expected = 40 * 30 * 20 + math.pi * 36 * 5 - (1 - math.pi / 4) * 25 * 20
vol = mm3(obj)
ok = not obj.blendsolid_error and abs(vol - expected) / expected < 0.01
print(f"first result after {elapsed:.1f} s, volume {vol:.1f} mm³ (expected {expected:.1f}), "
      f"error: {obj.blendsolid_error or '-'}")

bpy.context.scene.cursor.location = (0.1, 0, 0)
bpy.ops.blendsolid.add_box(length=40, width=30, height=10)
plate = bpy.context.view_layer.objects.active
bpy.context.scene.cursor.location = (0.1, 0, -0.005)
bpy.ops.blendsolid.add_cylinder(radius=3, height=20)
pin = bpy.context.view_layer.objects.active
bpy.context.view_layer.update()
plate.select_set(True)
bpy.context.view_layer.objects.active = plate
bpy.ops.blendsolid.boolean(operation="DIFFERENCE")
elapsed = wait([plate, pin])
expected = 40 * 30 * 10 - math.pi * 9 * 10
vol = mm3(plate)
cut_ok = not plate.blendsolid_error and abs(vol - expected) / expected < 0.01
print(f"live cutter after {elapsed:.1f} s, volume {vol:.1f} mm³ (expected {expected:.1f}), "
      f"error: {plate.blendsolid_error or '-'}")

ok = ok and cut_ok
print("SMOKE PASS" if ok else "SMOKE FAIL")
runtime.unregister()
sys.exit(0 if ok else 1)
