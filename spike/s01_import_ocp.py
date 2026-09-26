"""Objective 1: import OCP inside Blender, with no crash and no DLL conflicts.

Usage: blender -b --factory-startup --python spike/s01_import_ocp.py
(also without -b, for the GUI test: the script prints the result and quits Blender)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402

import bpy  # noqa: E402

KEYS = ("tbb", "freetype", "openexr", "imath", "zlib", "png", "jpeg", "tiff", "msvcp", "vcomp", "tk")


def interesting(mods):
    return sorted(m for m in mods if any(k in os.path.basename(m).lower() for k in KEYS))


def main():
    before = set(_common.loaded_modules())
    print("SITE", _common.add_ocp_path())

    t0 = time.perf_counter()
    import OCP  # noqa: F401
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    t_import = time.perf_counter() - t0

    box = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(box, props)
    valid = BRepCheck_Analyzer(box).IsValid()

    after = set(_common.loaded_modules())
    new = after - before
    print("BLENDER", bpy.app.version_string, "background" if bpy.app.background else "GUI")
    print("PYTHON", sys.version.split()[0], sys.platform)
    from importlib.metadata import version
    print("OCP", version("cadquery-ocp-novtk"), getattr(OCP, "__version__", ""))
    print(f"IMPORT_TIME {t_import:.3f}s")
    print(f"BOX volume={props.Mass():.3f} valid={valid}")
    print(f"NEW_NATIVE_MODULES {len(new)}")
    print("--- relevant modules loaded AFTER importing OCP")
    for m in interesting(new):
        print("  +", m)
    print("--- relevant modules already loaded by Blender")
    for m in interesting(before):
        print("  =", m)
    ok = valid and abs(props.Mass() - 6000.0) < 1e-6
    print("RESULT", "PASS" if ok else "FAIL")


try:
    main()
except Exception:
    import traceback
    traceback.print_exc()
    print("RESULT FAIL")

if not bpy.app.background:
    bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=1.0)
