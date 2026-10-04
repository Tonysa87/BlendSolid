"""Common harness for the sweep scenarios (imported by each scenario)."""
import sys, os, time, traceback, json, math
ROOT = "/home/tony/Projects/BlendSolid"
sys.path[:0] = [ROOT]
import bpy
import blendsolid
from blendsolid import part, runtime, script_model
from types import SimpleNamespace

_registered = False
def setup():
    global _registered
    if not _registered:
        blendsolid.register()
        _registered = True
    clean()

def clean():
    for coll in (bpy.data.objects, bpy.data.texts, bpy.data.meshes, bpy.data.libraries):
        bpy.data.batch_remove(list(coll))
    runtime.reset_state()

def wait_for(pred, timeout=60.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        runtime.tick()
        if pred():
            return True
        time.sleep(0.02)
    raise AssertionError("timeout")

def settle(obj_name, timeout=60.0):
    def ok():
        o = bpy.data.objects.get(obj_name)
        return o is not None and (part.applied_hash(o) == part.current_tag(o) or (o.blendsolid_error and part.error_tag(o) == part.current_tag(o)))
    wait_for(ok, timeout)
    return bpy.data.objects[obj_name]

def up_to_date(obj):
    return part.applied_hash(obj) == part.current_tag(obj)

def mm3(obj):
    return part.mesh_volume(obj.data) / part.unit_factor() ** 3

def state(name):
    o = bpy.data.objects.get(name)
    if o is None:
        return f"{name}: <missing>"
    src = part.source_of(o) if o.blendsolid_script else None
    feats = []
    try:
        feats = [f.name for f in script_model.features(src)]
    except Exception as e:
        feats = [f"<{e}>"]
    return (f"{name}: feats={feats} up_to_date={up_to_date(o)} vol={mm3(o):.3f} polys={len(o.data.polygons)} "
            f"err={o.blendsolid_error!r} line={o.blendsolid_error_line}")

FINDINGS = []
def check(cond, msg):
    if not cond:
        FINDINGS.append(msg)
        print("CHECK FAILED:", msg)
    else:
        print("ok:", msg)

def run(main):
    try:
        setup()
        main()
    except Exception:
        traceback.print_exc()
        print("SCENARIO EXCEPTION")
    print("FINDINGS:", json.dumps(FINDINGS, indent=1))
    try:
        if runtime._client is not None:
            runtime._client.kill()
    except Exception:
        pass
    sys.stdout.flush()
    os._exit(0)
