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
    assert ("blendsolid.call_pie", "E", "PRESS") in found
    assert ("blendsolid.pie_or_menu", "RIGHTMOUSE", "PRESS") in found


def test_only_an_opened_pie_gives_add_its_origin(addon, monkeypatch):
    # every right-click remembered where it was, and any Add within 30 s took that point: Shift+A > Box after a
    # plain right-click (Blender's context menu) placed the part there, not at the 3D cursor (bug sweep, 2026-10-04)
    calls = []
    fake_bpy = types.SimpleNamespace(ops=types.SimpleNamespace(wm=types.SimpleNamespace(
        call_menu=lambda *a, **k: calls.append("menu"), call_menu_pie=lambda *a, **k: calls.append("pie"))))
    monkeypatch.setattr(pies, "bpy", fake_bpy)
    monkeypatch.setattr(pies, "_origin", None)
    area = types.SimpleNamespace(as_pointer=lambda: 7)
    context = types.SimpleNamespace(area=area, preferences=bpy.context.preferences,
                                    window_manager=types.SimpleNamespace(modal_handler_add=lambda op: None))

    def event(kind, value, x, y):
        return types.SimpleNamespace(type=kind, value=value, mouse_x=x, mouse_y=y, mouse_region_x=x, mouse_region_y=y)
    cls = pies.BLENDSOLID_OT_pie_or_menu
    click = types.SimpleNamespace()
    cls.invoke(click, context, event("RIGHTMOUSE", "PRESS", 10, 20))
    assert cls.modal(click, context, event("RIGHTMOUSE", "RELEASE", 10, 20)) == {"FINISHED"}
    assert calls == ["menu"] and pies.take_origin(context) is None
    drag = types.SimpleNamespace()
    cls.invoke(drag, context, event("RIGHTMOUSE", "PRESS", 10, 20))
    assert cls.modal(drag, context, event("MOUSEMOVE", "NOTHING", 60, 20)) == {"FINISHED"}
    assert calls == ["menu", "pie"] and pies.take_origin(context) == (10, 20)
    # and only the pie's own Add items use it
    items = draw(pies.VIEW3D_MT_blendsolid_pie_add)
    adds = [props for idname, _, props, _ in items if idname.startswith("blendsolid.add_")]
    assert adds and all(getattr(props, "from_pie", False) for props in adds)
    assert "from_pie" in bpy.ops.blendsolid.add_box.get_rna_type().properties
