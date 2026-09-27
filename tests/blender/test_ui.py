import bpy

from blendsolid import part
from conftest import wait_for


def test_new_part_operator(clean):
    assert bpy.ops.blendsolid.new_part() == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    assert obj is not None and obj.blendsolid_script is not None and obj.select_get()
    wait_for(lambda: part.applied_hash(obj) == part.current_tag(obj))


def test_recompute_operator_resubmits(clean):
    bpy.ops.blendsolid.new_part()
    obj = bpy.context.view_layer.objects.active
    wait_for(lambda: part.applied_hash(obj) is not None)
    assert bpy.ops.blendsolid.recompute() == {"FINISHED"}
    assert part.applied_hash(obj) is None
    wait_for(lambda: part.applied_hash(obj) is not None)


def test_panel_is_registered(addon):
    assert hasattr(bpy.types, "BLENDSOLID_PT_part")


def test_script_is_hidden_by_default(clean):
    from blendsolid import ui
    bpy.ops.blendsolid.new_part()
    obj = bpy.context.view_layer.objects.active
    assert obj.blendsolid_script.name.startswith(".")
    assert not ui.scripts_visible(bpy.context)
    assert not bpy.ops.blendsolid.edit_script.poll()
    ui.FORCE_SHOW_SCRIPTS = True
    try:
        assert ui.scripts_visible(bpy.context)
    finally:
        ui.FORCE_SHOW_SCRIPTS = False


def test_recompute_operator_on_sibling_forces_primary(clean):
    """Objects sharing a mesh are one part (part.part_groups()): tick() only ever submits the primary,
    keyed by its own object name in runtime._inflight/_failed/_synced. If the primary previously failed and
    the user hits Recompute while a *non-primary* sibling is active, runtime.force() must still clear that
    failure record for the primary -- otherwise the shared mesh's applied hash is cleared but tick() keeps
    skipping the primary forever because its tag is still in runtime._failed."""
    from blendsolid import runtime

    a = part.new_part(bpy.context)
    wait_for(lambda: part.applied_hash(a) is not None)
    b = a.copy()  # Alt+D-style: shares a's mesh and script, so a and b are the same part
    bpy.context.collection.objects.link(b)
    assert b.data == a.data

    primary, sibling = sorted([a, b], key=lambda o: o.name)
    tag = part.current_tag(primary)
    runtime._failed[primary.name] = tag  # simulate: the primary previously failed to compute this exact tag

    bpy.context.view_layer.objects.active = sibling
    assert bpy.ops.blendsolid.recompute() == {"FINISHED"}

    assert primary.name not in runtime._failed  # forcing via the sibling must clear the primary's record
    wait_for(lambda: part.applied_hash(primary) == tag)


def test_sidebar_has_the_draw_solid_button_shape_and_step(clean):
    # The panel's draw code runs for real: a fake layout records what it shows.
    from types import SimpleNamespace

    from blendsolid import ui

    shown = []

    class Layout:
        def __getattr__(self, name):
            def record(*args, **kwargs):
                shown.append((name, args, kwargs))
                return self
            return record

    panel = SimpleNamespace(layout=Layout())
    ui.BLENDSOLID_PT_part.draw(panel, SimpleNamespace(object=None, scene=bpy.context.scene))
    ops = [a[0] for n, a, k in shown if n == "operator"]
    props = [a[1] for n, a, k in shown if n == "prop" and a and a[0] == bpy.context.scene]
    assert "wm.tool_set_by_id" in ops
    assert "blendsolid_draw_shape" in props and "blendsolid_snap_step" in props
