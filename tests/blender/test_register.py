def test_register_and_unregister(addon):
    import blendsolid
    blendsolid.unregister()
    blendsolid.register()


def test_enabled_at_startup():
    """Add-ons enabled at startup register while bpy.data is restricted (no bpy.data.filepath yet): register()
    must not touch it. Starts a second Blender with the add-on enabled from the command line."""
    import os
    import subprocess

    import bpy

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    probe = ("import sys, bpy; from blendsolid import trust; "
             "print('PROBE', hasattr(bpy.types, 'BLENDSOLID_PT_part'), trust.file_trusted())")
    out = subprocess.run(
        [bpy.app.binary_path, "-b", "--factory-startup", "--python-use-system-env", "--addons", "blendsolid",
         "--python-expr", probe],
        env=dict(os.environ, PYTHONPATH=root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        timeout=120).stdout
    assert "Traceback" not in out, out
    assert "PROBE True False" in out, out  # registered; factory settings: Auto Run off, file not trusted
