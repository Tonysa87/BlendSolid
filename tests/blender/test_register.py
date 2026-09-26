def test_register_and_unregister(addon):
    import blendsolid
    blendsolid.unregister()
    blendsolid.register()


def test_enabled_at_startup():
    """Add-ons enabled at startup register while bpy.data is restricted (no bpy.data.filepath yet): register()
    must not touch it. Starts a second Blender with the add-on enabled from the command line."""
    from conftest import run_probe

    probe = ("import sys, bpy; from blendsolid import trust; "
             "print('PROBE', hasattr(bpy.types, 'BLENDSOLID_PT_part'), trust.file_trusted())")
    out = run_probe([], probe)
    assert "PROBE True False" in out, out  # registered; factory settings: Auto Run off, file not trusted
