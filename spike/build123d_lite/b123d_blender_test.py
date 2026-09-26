"""Run the build123d history scripts in the lite worker, launched from inside Blender.

Checks that: build123d is never imported by Blender's own interpreter; Blender keeps its bundled
typing_extensions while the worker uses the newer one; every script produces a valid solid whose volume
matches the full-dependency reference; the mesh comes back to Blender with BRep face IDs.

Usage: blender -b --factory-startup --python b123d_blender_test.py -- <libs_dir> <ocp_site_dir> [reference.json]
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]  # spike code only; nothing from build123d/OCP here

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import bl_bridge  # noqa: E402
from scripts import SCRIPTS  # noqa: E402
from worker import read_msg, write_msg  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
libs, ocp_site = argv[0], argv[1]
reference = json.load(open(argv[2])) if len(argv) > 2 else {}

t0 = time.perf_counter()
proc = subprocess.Popen([sys.executable, "-u", os.path.join(HERE, "b123d_worker.py"), libs, ocp_site],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
hello = read_msg(proc.stdout)
if hello is None:
    print(proc.stderr.read().decode(errors="replace"))
    raise SystemExit("worker failed to start")
t_cold = time.perf_counter() - t0

import typing_extensions  # noqa: E402  (Blender's own copy)
from importlib.metadata import version  # noqa: E402

print(f"[b123d] platform {sys.platform}; worker cold start {t_cold * 1e3:.0f} ms "
      f"(imports inside worker {hello['import'] * 1e3:.0f} ms), build123d {hello['build123d']}")
print(f"[b123d] typing_extensions: Blender {version('typing_extensions')} | worker {hello['typing_extensions']} "
      f"from {hello['typing_extensions_file']}")

fails = 0
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
for name, code in SCRIPTS.items():
    t1 = time.perf_counter()
    write_msg(proc.stdin, {"op": "run", "name": name, "script": code})
    r = read_msg(proc.stdout)
    rt = time.perf_counter() - t1
    if not r["ok"]:
        fails += 1
        print(f"[b123d] {name:30s} FAIL {r['error']} stubs={r['stubs_used']}")
        continue
    obj = bl_bridge.ensure_object(name)
    bl_bridge.fill_mesh(obj.data,
                        np.frombuffer(r["verts"], np.float32).reshape(-1, 3),
                        np.frombuffer(r["tris"], np.int32).reshape(-1, 3),
                        np.frombuffer(r["tri_face"], np.int32))
    ref = reference.get(name)
    match = ref is None or abs(r["volume"] - ref) <= 1e-6 * max(1.0, abs(ref))
    ok = r["valid"] and match and len(obj.data.polygons) > 0
    fails += not ok
    print(f"[b123d] {name:30s} {'ok  ' if ok else 'FAIL'} valid={r['valid']} faces={r['faces']:3d} "
          f"volume={r['volume']:12.3f} ref={'-' if ref is None else f'{ref:12.3f}'} "
          f"script={r['timing']['script'] * 1e3:6.1f} ms round trip={rt * 1e3:6.1f} ms stubs={r['stubs_used']}")
write_msg(proc.stdin, {"op": "quit"})
proc.wait(timeout=10)

in_blender = sorted(m for m in sys.modules if m.split(".")[0] in ("build123d", "OCP", "lite_shim"))
print(f"[b123d] modules loaded in Blender's interpreter: {in_blender or 'none'}")
print("[b123d] RESULT", "PASS" if fails == 0 and not in_blender else "FAIL")
