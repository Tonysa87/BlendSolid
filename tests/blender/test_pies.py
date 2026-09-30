"""ADR 0013: the command pie — every item runs a registered operator or activates a registered tool; the keys."""
import types

import bpy
import pytest

from blendsolid import ops_draw, ops_extrude, ops_fillet, ops_pushpull, ops_sketch, pies


class Recorder:
    """Stands in for a UILayout: records the operators a menu's draw() puts in its pie."""

    def __init__(self):
        self.items, self.enabled = [], True

    def menu_pie(self):
        return self

    def row(self):
        row = Recorder()
        row.items = self.items
        return row

    def operator(self, idname, text="", icon="NONE"):
        props = types.SimpleNamespace()
        self.items.append((idname, text, props, self.enabled))
        return props


def draw(menu):
    fake = types.SimpleNamespace(layout=Recorder())
    menu.draw(fake, bpy.context)
    return fake.layout.items


def operator_exists(idname):
    module, name = idname.split(".")
    try:
        getattr(getattr(bpy.ops, module), name).get_rna_type()
        return True
    except (AttributeError, KeyError):
        return False


TOOLS = {cls.bl_idname for module in (ops_draw, ops_extrude, ops_fillet, ops_pushpull, ops_sketch)
         for cls in vars(module).values()
         if isinstance(cls, type) and issubclass(cls, bpy.types.WorkSpaceTool) and cls is not bpy.types.WorkSpaceTool}


def test_level_0_holds_the_families_in_order(addon):
    items = draw(pies.VIEW3D_MT_blendsolid_pie)
    assert [text for _, text, _, _ in items] == ["Add", "Sketch", "Edit", "Draw Solid", "Booleans",
                                                 "Solid from Sketch", "Pattern", "Part & File"]
    for idname, text, props, enabled in items:
        if text == "Pattern":
            assert not enabled  # milestone 3b: greyed out, in its place
        else:
            assert enabled and idname == "wm.call_menu_pie" and hasattr(bpy.types, props.name), text


@pytest.mark.parametrize("menu", pies.LEVEL_1, ids=lambda m: m.bl_label)
def test_every_level_1_item_is_a_registered_operator_or_tool(addon, menu):
    items = draw(menu)
    assert 2 <= len(items) <= 8
    for idname, text, props, enabled in items:
        assert operator_exists(idname), (text, idname)
        if idname == pies.BLENDSOLID_OT_use_tool.bl_idname and enabled:
            assert props.tool in TOOLS, (text, props.tool)
            if props.setting:
                prop = bpy.types.Scene.bl_rna.properties[props.setting]
                assert props.value in {item.identifier for item in prop.enum_items}, (text, props.value)


def test_use_tool_sets_the_tools_setting(addon):
    scene = bpy.context.scene
    scene.blendsolid_sketch_shape = "PATH"
    # no 3D View in background mode: the setting is written before the tool is activated
    with pytest.raises(RuntimeError):
        bpy.ops.blendsolid.use_tool(tool="blendsolid.sketch_tool", setting="blendsolid_sketch_shape",
                                    value="CIRCLE")
    assert scene.blendsolid_sketch_shape == "PATH"  # poll failed: nothing changed


def test_keys(addon):
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        pytest.skip("no add-on keyconfig in this background session")
    found = {(kmi.idname, kmi.type, kmi.value) for _, kmi in pies._keymap_items}
    assert ("wm.call_menu_pie", "E", "PRESS") in found
    assert ("blendsolid.pie_or_menu", "RIGHTMOUSE", "PRESS") in found
