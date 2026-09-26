"""Objectives 3 (click), 4, 5, 6: interactive Blender session with GUI.

Usage: blender --factory-startup --python spike/gui_session.py

Creates:
- BS_Solid: mesh of the OCCT solid (brep_face_id attribute). Applied parameters stored as custom properties
  (bs_push_top, bs_cyl_height) → they are part of Blender's undo.
- BS_Proxy_Top: Empty on the top face of the box. Its displacement along the normal (+Z) = face push.
- GN modifier "BS_Params" on BS_Solid, with a GizmoLinear on the "Cylinder Height" input.
- depsgraph_update_post handler: if the proxy or the GN input differ from the applied parameters → OCCT recompute.
- undo_post/redo_post handlers: check consistency between parameters, proxy, modifier and mesh.
- N panel "BlendSolid" with the picking operator (click → BRep face ID).
Every event is printed to stdout with the [BS] prefix.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402

_common.add_ocp_path()

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bpy.app.handlers import persistent  # noqa: E402
from bpy_extras import view3d_utils  # noqa: E402

import bl_bridge  # noqa: E402
import occ_model  # noqa: E402

SOLID, PROXY, NG, MOD = "BS_Solid", "BS_Proxy_Top", "BS_Params", "BS_Params"
BASE_Z = occ_model.DEFAULT_PARAMS["box"][2]
PROXY_XY = (32.0, 8.0)  # a point on the top face (its center falls inside the cylinder hole)
T0 = time.perf_counter()
_busy = False


def log(*a):
    print(f"[BS {time.perf_counter() - T0:8.3f}]", *a, flush=True)


# ---------------------------------------------------------------- state

def height_socket_id():
    return bpy.data.node_groups[NG].interface.items_tree["Cylinder Height"].identifier


def wanted():
    """Wanted parameters read from the controls: proxy (push) and GN modifier input (height)."""
    obj, proxy = bpy.data.objects[SOLID], bpy.data.objects[PROXY]
    push = round(proxy.matrix_world.translation.z - BASE_Z, 6)  # projection onto the +Z normal
    # Blender 5.2: GN modifier inputs are no longer IDProperties (mod["Socket_1"]),
    # but RNA: mod.properties.inputs.<identifier>.value
    h = round(float(getattr(obj.modifiers[MOD].properties.inputs, height_socket_id()).value), 6)
    return push, h


def applied(obj):
    return round(obj["bs_push_top"], 6), round(obj["bs_cyl_height"], 6)


def mesh_volume(mesh):
    v = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    t = np.empty(len(mesh.polygons) * 3, dtype=np.int32)
    mesh.polygons.foreach_get("vertices", t)
    t = t.reshape(-1, 3)
    return np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum() / 6


def rebuild(obj, push, h):
    t0 = time.perf_counter()
    try:
        shape, (verts, tris, tri_face), tm = occ_model.build_and_tessellate(
            {"push_top": push, "cyl_height": h})
    except Exception as e:  # previous state untouched: the mesh does not change
        obj["bs_error"] = str(e)
        log(f"RECOMPUTE FAILED push={push} h={h}: {e}")
        return False
    t1 = time.perf_counter()
    bl_bridge.fill_mesh(obj.data, verts, tris, tri_face)
    obj["bs_push_top"], obj["bs_cyl_height"] = push, h
    obj["bs_error"] = ""
    t2 = time.perf_counter()
    log(f"RECOMPUTE push={push:+.3f} h={h:.3f} faces={tri_face.max() + 1} tris={len(tris)} "
        f"occt={1e3 * (t1 - t0):.1f}ms (build {1e3 * tm['build']:.1f}, tess {1e3 * tm['tessellate']:.1f}) "
        f"mesh={1e3 * (t2 - t1):.1f}ms")
    return True


def consistency(tag):
    """Consistency between applied parameters, controls (proxy/GN) and mesh."""
    obj = bpy.data.objects.get(SOLID)
    if obj is None:
        log(f"{tag}: BS_Solid does not exist")
        return
    push, h = applied(obj)
    w_push, w_h = wanted()
    expected = occ_model.check(occ_model.build({"push_top": push, "cyl_height": h}))["volume"]
    mv = mesh_volume(obj.data)
    mesh_ok = abs(mv - expected) / expected < 0.01
    ctrl_ok = abs(w_push - push) < 1e-6 and abs(w_h - h) < 1e-6
    log(f"{tag}: applied push={push:+.3f} h={h:.3f} | proxy push={w_push:+.3f} GN h={w_h:.3f} | "
        f"mesh vol={mv:.1f} expected={expected:.1f} | mesh↔params {'OK' if mesh_ok else 'MISMATCH'} | "
        f"controls↔params {'OK' if ctrl_ok else 'MISMATCH (handler will recompute)'}")


# ---------------------------------------------------------------- handler

@persistent
def on_depsgraph(scene, depsgraph):
    global _busy
    if _busy:
        return
    obj = bpy.data.objects.get(SOLID)
    if obj is None or PROXY not in bpy.data.objects:
        return
    w_push, w_h = wanted()
    push, h = applied(obj)
    if abs(w_push - push) < 1e-6 and abs(w_h - h) < 1e-6:
        return
    who = "proxy" if abs(w_push - push) >= 1e-6 else "gizmo GN"
    log(f"CHANGE from {who}: push {push:+.3f}→{w_push:+.3f}, h {h:.3f}→{w_h:.3f}")
    _busy = True
    try:
        rebuild(obj, w_push, w_h)
    finally:
        _busy = False


@persistent
def on_undo_pre(scene, *_):
    consistency("UNDO_PRE ")


@persistent
def on_undo_post(scene, *_):
    consistency("UNDO_POST")


@persistent
def on_redo_post(scene, *_):
    consistency("REDO_POST")


# ---------------------------------------------------------------- UI

class BS_OT_pick_face(bpy.types.Operator):
    """Click on the solid: reports the ID of the BRep face under the mouse (Esc/right click to exit)"""
    bl_idname = "bs.pick_face"
    bl_label = "BS Pick Face"

    def modal(self, context, event):
        if event.type in {"RIGHTMOUSE", "ESC"}:
            context.area.header_text_set(None)
            return {"CANCELLED"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            region, rv3d = context.region, context.region_data
            co = (event.mouse_region_x, event.mouse_region_y)
            origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, co)
            direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, co)
            dg = context.evaluated_depsgraph_get()
            hit, loc, nor, index, obj, _ = context.scene.ray_cast(dg, origin, direction)
            if hit and obj.name == SOLID:
                ev = obj.evaluated_get(dg).data
                fid = ev.attributes[bl_bridge.FACE_ATTR].data[index].value
                shape = occ_model.build({"push_top": obj["bs_push_top"], "cyl_height": obj["bs_cyl_height"]})
                face = occ_model.face_map(shape)[fid]
                kind = occ_model.BRepAdaptor_Surface(face).GetType().name
                msg = f"PICK poly={index} → brep_face_id={fid} ({kind}) at {tuple(round(c, 2) for c in loc)}"
                # highlight the polygons of the BRep face (selection in edit mode)
                ids = bl_bridge.face_ids(obj.data)
                obj.data.polygons.foreach_set("select", ids == fid)
            else:
                msg = f"PICK no hit on {SOLID}" + (f" (hit {obj.name})" if hit else "")
            log(msg)
            self.report({"INFO"}, msg)
            context.area.header_text_set(msg + "   —   Esc to exit")
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}

    def invoke(self, context, event):
        if context.area.type != "VIEW_3D":
            return {"CANCELLED"}
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set("BS Pick Face: left click on the solid, Esc to exit")
        return {"RUNNING_MODAL"}


class BS_OT_report(bpy.types.Operator):
    """Prints the consistency state of the solid to the log"""
    bl_idname = "bs.report"
    bl_label = "BS Report State"

    def execute(self, context):
        consistency("REPORT   ")
        return {"FINISHED"}


class BS_PT_panel(bpy.types.Panel):
    bl_label = "BlendSolid spike"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlendSolid"

    def draw(self, context):
        col = self.layout.column()
        col.operator("bs.pick_face")
        col.operator("bs.report")
        obj = bpy.data.objects.get(SOLID)
        if obj:
            col.label(text=f"applied push: {obj['bs_push_top']:+.3f}")
            col.label(text=f"cylinder height: {obj['bs_cyl_height']:.3f}")
            if obj.get("bs_error"):
                col.label(text=f"error: {obj['bs_error']}", icon="ERROR")


# ---------------------------------------------------------------- scene

def make_node_group():
    ng = bpy.data.node_groups.new(NG, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    s = ng.interface.new_socket("Cylinder Height", in_out="INPUT", socket_type="NodeSocketFloat")
    s.default_value, s.min_value, s.max_value = occ_model.DEFAULT_PARAMS["cyl_height"], 1.0, 200.0
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n = ng.nodes
    gin, gout = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    giz = n.new("GeometryNodeGizmoLinear")
    xyz = n.new("ShaderNodeCombineXYZ")
    join = n.new("GeometryNodeJoinGeometry")
    bx, by, _ = occ_model.DEFAULT_PARAMS["box"]
    xyz.inputs["X"].default_value, xyz.inputs["Y"].default_value = bx / 2, by / 2
    giz.inputs["Direction"].default_value = (0, 0, 1)
    ng.links.new(gin.outputs["Cylinder Height"], giz.inputs["Value"])
    ng.links.new(gin.outputs["Cylinder Height"], xyz.inputs["Z"])  # the gizmo sits on top of the cylinder
    ng.links.new(xyz.outputs["Vector"], giz.inputs["Position"])
    ng.links.new(gin.outputs["Geometry"], join.inputs["Geometry"])
    ng.links.new(giz.outputs["Transform"], join.inputs["Geometry"])
    ng.links.new(join.outputs["Geometry"], gout.inputs["Geometry"])
    gin.location, giz.location, xyz.location, join.location, gout.location = \
        (-400, 0), (0, -200), (-200, -250), (200, 0), (400, 0)
    return ng


def setup_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    obj = bl_bridge.ensure_object(SOLID)
    obj["bs_push_top"], obj["bs_cyl_height"], obj["bs_error"] = 0.0, occ_model.DEFAULT_PARAMS["cyl_height"], ""
    rebuild(obj, 0.0, occ_model.DEFAULT_PARAMS["cyl_height"])
    mod = obj.modifiers.new(MOD, "NODES")
    mod.node_group = make_node_group()

    proxy = bpy.data.objects.new(PROXY, None)
    proxy.empty_display_type = "SINGLE_ARROW"
    proxy.empty_display_size = 8
    proxy.location = (*PROXY_XY, BASE_Z)
    proxy.lock_location = (True, True, False)  # optional: only Z matters for the push
    bpy.context.scene.collection.objects.link(proxy)
    bpy.context.view_layer.objects.active = proxy
    proxy.select_set(True)
    bpy.context.view_layer.update()


def setup_view():
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            space = area.spaces.active
            space.show_gizmo_object_translate = True
            space.clip_end = 10000
            with bpy.context.temp_override(area=area, region=area.regions[-1]):
                bpy.ops.view3d.view_all()
            area.spaces.active.region_3d.view_distance = 130
    return None


def register():
    for c in (BS_OT_pick_face, BS_OT_report, BS_PT_panel):
        bpy.utils.register_class(c)
    for lst, fn in ((bpy.app.handlers.depsgraph_update_post, on_depsgraph),
                    (bpy.app.handlers.undo_pre, on_undo_pre),
                    (bpy.app.handlers.undo_post, on_undo_post),
                    (bpy.app.handlers.redo_post, on_redo_post)):
        lst.append(fn)


setup_scene()
register()
log("SESSION READY. OCP", occ_model.__name__, "Blender", bpy.app.version_string)
consistency("START    ")
if not bpy.app.background:
    bpy.app.timers.register(setup_view, first_interval=0.5)
