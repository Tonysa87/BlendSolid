def test_register_and_unregister(addon):
    import blendsolid
    blendsolid.unregister()
    blendsolid.register()
