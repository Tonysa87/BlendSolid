"""Objective 7: recompute of objective 2, direct (in Blender) vs worker in a separate process.

Usage: blender -b --factory-startup --python spike/s07_worker_bench.py [-- --defl 0.1 --n 30]
"""
import os
import statistics as st
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402

SITE = _common.add_ocp_path()

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import bl_bridge  # noqa: E402
import occ_model  # noqa: E402
from worker import read_msg, write_msg  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
DEFL = float(argv[argv.index("--defl") + 1]) if "--defl" in argv else 0.1
ANG = float(argv[argv.index("--ang") + 1]) if "--ang" in argv else 0.3
N = int(argv[argv.index("--n") + 1]) if "--n" in argv else 30
PARAMS = [{"push_top": (i % 7) - 3.0, "cyl_height": 25.0 + (i % 5)} for i in range(N)]


def ms(xs):
    return f"median {1e3 * st.median(xs):6.1f} ms  min {1e3 * min(xs):6.1f}  max {1e3 * max(xs):6.1f}"


for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
obj = bl_bridge.ensure_object("BS_Solid")

# --- direct: OCCT in the Blender process
direct = []
for p in PARAMS:
    t0 = time.perf_counter()
    _, (v, t, f), _ = occ_model.build_and_tessellate(p, DEFL, ANG)
    bl_bridge.fill_mesh(obj.data, v, t, f)
    direct.append(time.perf_counter() - t0)
ref = (len(v), len(t))

# --- worker: same Python interpreter as Blender, separate process
py = sys.executable  # in Blender 5.2 this is the bundled python.exe
worker_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker.py")
t0 = time.perf_counter()
proc = subprocess.Popen([py, "-u", worker_py, SITE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, bufsize=0)
hello = read_msg(proc.stdout)
t_cold = time.perf_counter() - t0

roundtrip, in_worker, transfer, unpack_fill, sizes = [], [], [], [], []
for p in PARAMS:
    t0 = time.perf_counter()
    write_msg(proc.stdin, {"op": "build", "params": p, "lin_defl": DEFL, "ang_defl": ANG})
    r = read_msg(proc.stdout)
    t1 = time.perf_counter()
    assert r["ok"], r
    v = np.frombuffer(r["verts"], dtype=np.float32).reshape(-1, 3)
    t = np.frombuffer(r["tris"], dtype=np.int32).reshape(-1, 3)
    f = np.frombuffer(r["tri_face"], dtype=np.int32)
    bl_bridge.fill_mesh(obj.data, v, t, f)
    t2 = time.perf_counter()
    work = r["timing"]["build"] + r["timing"]["tessellate"]
    roundtrip.append(t2 - t0)
    in_worker.append(work)
    transfer.append((t1 - t0) - work)
    unpack_fill.append(t2 - t1)
    sizes.append(len(r["verts"]) + len(r["tris"]) + len(r["tri_face"]))
write_msg(proc.stdin, {"op": "quit"})
proc.wait(timeout=10)
same = (len(v), len(t)) == ref

print(f"[7] platform {sys.platform}, deflection lin {DEFL} ang {ANG}, {N} recomputes, last mesh {ref[0]} vertices / {ref[1]} tris,"
      f" mean payload {st.mean(sizes) / 1024:.1f} KiB")
print(f"[7] DIRECT   (OCCT + mesh in Blender)      : {ms(direct)}")
print(f"[7] WORKER   cold start (spawn + import)   : {1e3 * t_cold:6.1f} ms (OCP import in worker {1e3 * hello['import']:.1f} ms)")
print(f"[7] WORKER   warm round trip               : {ms(roundtrip)}")
print(f"[7]            of which OCCT in worker      : {ms(in_worker)}")
print(f"[7]            of which IPC (pipe + pickle) : {ms(transfer)}")
print(f"[7]            of which mesh in Blender     : {ms(unpack_fill)}")
print(f"[7] worker overhead vs direct (medians)     : {1e3 * (st.median(roundtrip) - st.median(direct)):+.1f} ms")
print("[7] RESULT", "PASS" if same and proc.returncode == 0 else "FAIL")
