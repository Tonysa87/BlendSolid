import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
import types
from blendsolid import ops_fillet, ops_pushpull, picking

def fake(cls, **attrs):
    ns = SimpleNamespace(**attrs)
    for name in ("_restore", "_end", "_header", "_preview", "_check_limit", "_write", "_update", "report"):
        if hasattr(cls, name):
            setattr(ns, name, types.MethodType(getattr(cls, name), ns))
    ns.report = lambda kind, msg: print("REPORT", kind, msg)
    return ns

def main():
    headers = []
    area = SimpleNamespace(header_text_set=lambda t: headers.append(t), tag_redraw=lambda: None)
    ctx = SimpleNamespace(area=area, window_manager=bpy.context.window_manager, scene=bpy.context.scene,
                          preferences=bpy.context.preferences)
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    box = settle("Box")
    refs = list(box.data[part.EDGE_REFS_KEY])
    box.scale = (2, 1, 1)
    bpy.context.view_layer.update()
    # picking accepts a scaled part? emulate: the click selection is just the refs
    ops_fillet.select(picking.Pick(box, "EDGE", 0, refs[0], []))
    src = part.source_of(box)
    h = bpy.types.SpaceView3D.draw_handler_add(lambda: None, (), "WINDOW", "POST_VIEW")
    op = fake(ops_fillet.BLENDSOLID_OT_fillet_click, _source=src, _target=box, _radius=2.0, _chamfer=False,
              _handles=[h], _timer=None, _limit=None, _snap=0.0)
    ops_fillet._dragging.add(id(op))
    ev = SimpleNamespace(type="LEFTMOUSE", value="RELEASE", ctrl=False, shift=False, mouse_region_x=0, mouse_region_y=0)
    try:
        print("modal ->", ops_fillet.BLENDSOLID_OT_fillet_click.modal(op, ctx, ev))
    except Exception as e:
        print("MODAL RAISED", type(e).__name__, e)
    check(not ops_fillet._dragging, "fillet: _dragging emptied after release on scaled part")
    check(not op._handles, "fillet: draw handlers removed after release on scaled part")
    check(headers and headers[-1] is None, f"fillet: header cleared ({headers})")
    ops_fillet._dragging.clear()

    # push/pull, same
    headers.clear()
    h = bpy.types.SpaceView3D.draw_handler_add(lambda: None, (), "WINDOW", "POST_VIEW")
    op = fake(ops_pushpull.BLENDSOLID_OT_push_pull_drag, _source=src, _target=box, _amount=3.0, _handles=[h],
              _reference='face("box_1", "+Z")', _snap=0.0)
    ops_pushpull._dragging.add(id(op))
    try:
        print("modal ->", ops_pushpull.BLENDSOLID_OT_push_pull_drag.modal(op, ctx, ev))
    except Exception as e:
        print("MODAL RAISED", type(e).__name__, e)
    check(not ops_pushpull._dragging, "push/pull: _dragging emptied after release on scaled part")
    check(headers and headers[-1] is None, f"push/pull: header cleared ({headers})")

    # does picking.pick filter scaled/untrusted parts? (it only checks is_local_part)
    import inspect
    print("picking.pick checks:", [w for w in ("is_scaled", "is_trusted", "is_canonical") if w in inspect.getsource(picking.pick)])

run(main)
