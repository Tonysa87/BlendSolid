"""1 region pixel = 1 mm, looking down -Z from z=1 BU; region (x, y) = world (x mm, y mm)."""
import types
from types import SimpleNamespace
import bpy
from mathutils import Vector
from blendsolid import ops_draw, part

PX = 0.1  # mm per region pixel

def install():
    f = lambda: part.unit_factor()
    ops_draw.mouse_ray = lambda ctx, coord: (Vector((coord[0] * PX * f(), coord[1] * PX * f(), 1.0)), Vector((0, 0, -1)))
    ops_draw._pixel_size = lambda region, rv3d, p: PX * f()
    ops_draw._near_rays = lambda ctx, coord, radius=4: []

headers = []
def context():
    area = SimpleNamespace(type="VIEW_3D", header_text_set=lambda t: headers.append(t), tag_redraw=lambda: None,
                           as_pointer=lambda: 1)
    c = bpy.context
    return SimpleNamespace(area=area, region=None, region_data=object(), scene=c.scene, preferences=c.preferences,
                           window_manager=SimpleNamespace(modal_handler_add=lambda op: None, event_timer_add=lambda *a, **k: 'T', event_timer_remove=lambda t: None), view_layer=c.view_layer, collection=c.collection,
                           selected_objects=list(c.selected_objects), visible_objects=list(c.visible_objects),
                           evaluated_depsgraph_get=c.evaluated_depsgraph_get, window=c.window,
                           mode="OBJECT", object=c.object, workspace=None)

def ev(t, value="PRESS", x=0, y=0, ctrl=False, shift=False, oskey=False):
    return SimpleNamespace(type=t, value=value, mouse_region_x=x, mouse_region_y=y, ctrl=ctrl, shift=shift,
                           oskey=oskey, alt=False)

def fake_op(cls, **props):
    ns = SimpleNamespace(**props)
    for name in dir(cls):
        attr = getattr(cls, name, None)
        if isinstance(attr, types.FunctionType):
            setattr(ns, name, types.MethodType(attr, ns))
    ns.reports = []
    ns.report = lambda kind, msg: (ns.reports.append((kind, msg)), print("REPORT", kind, msg))
    return ns
