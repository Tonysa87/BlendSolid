"""Tool 6: Sketch. Draw paths (lines and tangent arcs), rectangles and circles on a part's flat face, on a sketch
already there, or on the 3D cursor's plane (a new part). Each is one entity in a sketch feature of the part script
(milestone 3a, ADR 0012):

    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.rect_1 = Pos(5.0, 0.0) * Rectangle(sketch_1_rect_1_width, sketch_1_rect_1_height)

A drag on a sketch not extruded yet (or on a face whose plane it lies on) adds to it; elsewhere on a face it starts
a new sketch there. Ends snap to the sketch's points (curve ends, centres) within a few pixels; Ctrl snaps to the
grid, like Draw Solid. The sketches themselves are drawn by the overlay at the end of this module: every
sketch not extruded yet, and all of them while a sketch tool is active.
"""
import json
import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, StringProperty
from mathutils import Matrix, Vector, geometry

from . import drawing, focus, part, script_model, sketching, trust

SHAPES = [("PATH", "Path", "Click points of a path of lines; drag while clicking (or A) for an arc tangent to it; "
                           "click the first point to close it, Enter or right-click to end it, Backspace or Ctrl+Z to remove "
                           "the last point", "IPO_LINEAR", 3),
          ("RECTANGLE", "Rectangle", "Drag the opposite corners of a rectangle", "MESH_PLANE", 0),
          ("CIRCLE", "Circle", "Drag from the centre of a circle to its rim", "MESH_CIRCLE", 1)]
DRAG_PX = 6  # a press moved this far before its release is a drag (an arc), not a click
SKETCH_TOOLS = {"blendsolid.sketch_tool", "blendsolid.groove_tool", "blendsolid.extrude_tool",
                "blendsolid.revolve_tool"}
CURVE_COLOUR = (1.0, 0.75, 0.2, 1.0)
USED_COLOUR = (0.8, 0.8, 0.8, 0.6)
REGION_COLOUR = (1.0, 0.75, 0.2, 0.12)
PICK_MARGIN = 0.25  # a click this far outside a sketch's curves (fraction of their size) still lands on its plane


# -- the part's sketches, as the worker last drew them ----------------------------------------------------------------

_cache = {}  # mesh session_uid -> (json text, parsed list)


def sketches_of(obj):
    """The sketch display dicts of obj's part (worker sketches.Sketch.display()), [] when it has none."""
    if obj is None or obj.type != "MESH" or obj.data is None:
        return []
    text = obj.data.get(part.SKETCHES_KEY)
    if not text:
        return []
    key = obj.data.session_uid
    cached = _cache.get(key)
    if cached is None or cached[0] != text:
        try:
            cached = (text, json.loads(text))
        except ValueError:
            cached = (text, [])
        _cache[key] = cached
    return cached[1]


def find_sketch(obj, name):
    for sketch in sketches_of(obj):
        if sketch["name"] == name:
            return sketch
    return None


def plane_matrix(obj, sketch, factor):
    """World matrix (Blender units) of a sketch's plane: X, Y in it, Z its normal."""
    o, x, y, z = sketch["plane"]
    m = Matrix.Identity(4)
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = x[i], y[i], z[i], o[i] * factor
    return obj.matrix_world @ m


def world_point(obj, sketch, uv, factor):
    return obj.matrix_world @ (Vector(sketching.from_plane(sketch, uv)) * factor)


def plane_uv(plane, point, factor):
    """Plane coordinates (mm) of world `point` on world plane matrix `plane`."""
    d = Vector(point) - plane.translation
    return d.dot(plane.col[0].xyz) / factor, d.dot(plane.col[1].xyz) / factor


def ray_uv(plane, origin, direction, factor):
    """(u, v) mm where the ray meets the plane, and the distance along the ray; None when parallel/behind."""
    hit = geometry.intersect_line_plane(Vector(origin), Vector(origin) + Vector(direction), plane.translation,
                                        plane.col[2].xyz)
    if hit is None:
        return None
    along = (hit - Vector(origin)).dot(Vector(direction).normalized())
    if along < 0:
        return None
    return plane_uv(plane, hit, factor), along


def sketch_parts(context):
    """Visible local parts that have sketches."""
    for obj in context.visible_objects:
        if obj.type == "MESH" and part.is_local_part(obj) and sketches_of(obj):
            yield obj


def editable(obj):
    return (part.is_local_part(obj) and not part.is_scaled(obj) and trust.is_trusted(obj)
            and script_model.is_canonical(part.source_of(obj)))


def pick_sketch(context, origin, direction, used=True, within_regions=False):
    """(part, sketch, (u, v) mm, distance along the ray) of the nearest sketch plane the mouse ray meets near a
    sketch's curves (or inside one of its regions with `within_regions`), or None. `used`: include sketches
    already extruded."""
    factor = part.unit_factor(context.scene)
    best = None
    for obj in sketch_parts(context):
        for sketch in sketches_of(obj):
            if not used and sketch["used"]:
                continue
            plane = plane_matrix(obj, sketch, factor)
            found = ray_uv(plane, origin, direction, factor)
            if found is None:
                continue
            uv, along = found
            if within_regions:
                if sketching.region_at(sketch, uv) is None:
                    continue
            else:
                box = sketching.bounds(sketch)
                if box is None:
                    continue
                margin = PICK_MARGIN * max(box[2] - box[0], box[3] - box[1], 1.0)
                if not (box[0] - margin <= uv[0] <= box[2] + margin and box[1] - margin <= uv[1] <= box[3] + margin):
                    continue
            if best is None or along < best[3]:
                best = (obj, sketch, uv, along)
    return best


def _in_front(distance):
    """A sketch plane this far along the ray still counts as in front of a solid hit at `distance` (a sketch on a
    face lies exactly on it; float32 hits wobble)."""
    return distance + max(1e-4, distance * 1e-4)


def solid_distance(context, origin, direction):
    """Distance along the ray to the first solid object hit (through wire-display cutters), or inf."""
    from . import ops_draw
    hit = ops_draw._first_hit(context, context.evaluated_depsgraph_get(), origin, direction)
    return math.inf if hit is None else (hit[0] - Vector(origin)).length


# -- where a drag draws ---------------------------------------------------------------------------------------------

_projected = (None, [])  # (key, points) of part_points' last call: the hover marker asks on every redraw


def part_points(target):
    """The part's exact snap points projected on `target`'s plane, [((u, v) mm, kind index)]; [] on a new part."""
    global _projected
    if target.obj is None or target.frame is None:
        return []
    key = (target.obj.data.name, target.obj.data.get(part.HASH_KEY), tuple(tuple(v) for v in target.frame))
    if _projected[0] != key:
        _projected = (key, sketching.project_points(target.frame, part.snap_points(target.obj)))
    return _projected[1]


def snap_to_points(context, target, uv, factor, projected, path=()):
    """((u, v), label) of the point nearest `uv` (plane mm) within SNAP_PX pixels: the sketch's points and the
    path's ("point"), the part's `projected` points ("vertex", "midpoint", "centre"); or None."""
    from . import ops_draw
    candidates = [(tuple(p), "point") for p in list(target.points) + list(path)]
    candidates += [(q, sketching.SNAP_KINDS[kind]) for q, kind in projected]
    if not candidates:
        return None
    at = target.plane @ Vector((uv[0] * factor, uv[1] * factor, 0))
    pixel = ops_draw._pixel_size(context.region, context.region_data, at)
    if pixel is None:
        return None
    return sketching.nearest_snap(candidates, uv, sketching.SNAP_PX * ops_draw.ui_scale(context) * pixel / factor)


class Target:
    """Where a drag draws: an existing sketch of a part, a new sketch on a part's face, or a new part on the
    cursor's plane. `plane` is the world plane matrix; `local` the plane in the part's frame (for new sketches on
    a face, drawing.LocalPlane) so coordinates are exact."""

    def __init__(self, plane, obj=None, sketch=None, plane_code="", points=(), frame=None):
        self.plane, self.obj, self.sketch, self.plane_code, self.points = plane, obj, sketch, plane_code, points
        self.frame = frame  # the plane in the part's frame (origin, x, y, z; mm, float64), None on a new part


def pick_target(context, origin, direction, near=()):
    from . import ops_draw
    factor = part.unit_factor(context.scene)
    on_sketch = pick_sketch(context, origin, direction, used=False)
    if on_sketch is not None and editable(on_sketch[0]) \
            and on_sketch[3] <= _in_front(solid_distance(context, origin, direction)):
        obj, sketch = on_sketch[0], on_sketch[1]
        return Target(plane_matrix(obj, sketch, factor), obj, sketch["name"], points=sketch["points"],
                      frame=sketch["plane"])
    plane, obj, local = ops_draw.pick(context, origin, direction, near=near)
    if obj is not None and local is not None:
        # a flat face of a part: an unused sketch on that plane gets the entity, else a new sketch on the face
        frame = (local.origin, local.x, local.y, local.z)
        for sketch in sketches_of(obj):
            if not sketch["used"] and sketching.same_plane(sketch["plane"], frame):
                return Target(plane_matrix(obj, sketch, factor), obj, sketch["name"], points=sketch["points"],
                      frame=sketch["plane"])
        fid = _face_under(context, origin, direction, near)
        reference = part.face_reference(obj, fid) if fid is not None else ""
        if reference.startswith("face("):
            return Target(plane, obj, plane_code=f"on_face({reference})", frame=frame)
    if obj is not None and local is None:
        return None  # a curved face: sketches go on flat faces and planes
    plane = drawing.plane_at_cursor(context.scene.cursor.matrix)
    # an unused sketch on the cursor's plane (e.g. the one this plane made a moment ago) gets the entity
    for other in sketch_parts(context):
        if not editable(other):
            continue
        for sketch in sketches_of(other):
            if not sketch["used"] and _same_world_plane(plane_matrix(other, sketch, factor), plane):
                return Target(plane_matrix(other, sketch, factor), other, sketch["name"], points=sketch["points"],
                              frame=sketch["plane"])
    return Target(plane)


STICKY_REACH = 1.5  # the hovered face's plane stays the drawing plane within this many part radii of its centre
_sticky = None  # the last part plane hovered: (part name, script, matrix_world, plane, sketch, plane code, points,
#                frame)


def hover_target(context, origin, direction, near=()):
    """pick_target, but the plane of the last part face (or sketch) hovered sticks while the mouse leaves it for
    empty space near the part, so a path can start just off the face (Shapr3D and Plasticity pick the plane by
    hover before the first click). Another face, a curved face, or empty space far from the part ends it; so does
    any change to the part's script or placement."""
    global _sticky
    target = pick_target(context, origin, direction, near)
    if target is None or target.obj is not None:
        _sticky = None if target is None else (target.obj.name, part.source_of(target.obj),
                                                target.obj.matrix_world.copy(), target.plane.copy(), target.sketch,
                                                target.plane_code, target.points, target.frame)
        return target
    if _sticky is None:
        return target
    name, source, matrix, plane, sketch, plane_code, points, frame = _sticky
    obj = part.local_part(name)
    if obj is None or not editable(obj) or part.source_of(obj) != source or obj.matrix_world != matrix:
        _sticky = None
        return target
    factor = part.unit_factor(context.scene)
    found = ray_uv(plane, origin, direction, factor)
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    centre = sum(corners, Vector()) / 8
    radius = max(max((c - centre).length for c in corners), 1.0 * factor)
    if found is None or (plane @ Vector((found[0][0] * factor, found[0][1] * factor, 0.0)) - centre).length \
            > STICKY_REACH * radius:
        _sticky = None
        return target
    return Target(plane, obj, sketch, plane_code, points, frame)


def _same_world_plane(a, b, tolerance=1e-6):
    """Do two world plane matrices lie on the same plane (same normal, same offset; Blender units)?"""
    za, zb = a.col[2].xyz.normalized(), b.col[2].xyz.normalized()
    if za.dot(zb) < 1 - 1e-6:
        return False
    return abs((b.translation - a.translation).dot(za)) < tolerance * max(1.0, a.translation.length)


def _face_under(context, origin, direction, near):
    from . import ops_draw
    depsgraph = context.evaluated_depsgraph_get()
    hits = [ops_draw._first_hit(context, depsgraph, origin, direction)]
    if hits[0] is None:
        view = Vector(direction).normalized()
        hits = [h for h in (ops_draw._first_hit(context, depsgraph, o, d) for o, d in near) if h is not None]
        hits = sorted(hits, key=lambda h: -abs(Vector(h[1]).normalized().dot(view)))[:1]
    if not hits:
        return None
    location, _, index, obj = hits[0]
    return part.face_id(obj.evaluated_get(depsgraph).data, index)


# -- the operator: one entity -----------------------------------------------------------------------------------------

class BLENDSOLID_OT_sketch_entity(bpy.types.Operator):
    """Add a path, rectangle or circle to a sketch (a new sketch on a face, or a new part on the 3D cursor's
    plane)"""
    bl_idname = "blendsolid.sketch_entity"
    bl_label = "Sketch"
    bl_options = {"REGISTER", "UNDO"}

    shape: EnumProperty(name="Shape", items=SHAPES, default="PATH")
    target: StringProperty(name="Part", options={"SKIP_SAVE"},
                           description="The part the sketch belongs to (empty: a new part)")
    sketch: StringProperty(name="Sketch", options={"SKIP_SAVE"},
                           description="The sketch to add to (empty: a new sketch)")
    plane: StringProperty(name="Plane", options={"SKIP_SAVE"},
                          description="A new sketch's plane, e.g. on_face(face(\"box_1\", \"+Z\"))")
    start: FloatVectorProperty(name="Start", size=2, precision=3,
                               description="First corner, centre or line start, millimetres in the sketch's plane")
    end: FloatVectorProperty(name="End", size=2, precision=3,
                             description="Opposite corner, point on the circle or line end, millimetres")
    points: StringProperty(name="Points", options={"SKIP_SAVE"},
                           description="A path's points as JSON [[u, v, is_arc], ...], millimetres")
    closed: BoolProperty(name="Closed", options={"SKIP_SAVE"}, description="The path ends where it starts")
    matrix: FloatVectorProperty(size=16, options={"HIDDEN"})  # a new part's placement (the cursor plane)
    exact: StringProperty(options={"HIDDEN", "SKIP_SAVE"})  # float64 start/end while the float32 ones match

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        if self.shape == "PATH":
            layout.prop(self, "closed")
            return
        layout.prop(self, "shape")
        layout.label(text="Millimetres, in the sketch's plane")
        layout.prop(self, "start")
        layout.prop(self, "end")

    def _points(self):
        a, b = tuple(self.start), tuple(self.end)
        if self.exact:
            try:
                e = json.loads(self.exact)
                if all(_f32(x) == y for x, y in zip(e["start"] + e["end"], a + b)):
                    return tuple(e["start"]), tuple(e["end"])
            except (ValueError, KeyError, TypeError):
                pass
        return a, b

    def execute(self, context):
        from . import ui
        if self.shape == "PATH":
            try:
                points = [(float(u), float(v), bool(arc)) for u, v, arc in json.loads(self.points)]
            except (ValueError, TypeError):
                points = []
            if len(points) < 2:
                self.report({"ERROR"}, "A path needs at least two points")
                return {"CANCELLED"}
            spec = sketching.path_spec(points, self.closed)
        else:
            a, b = self._points()
            spec = sketching.entity_spec(self.shape, a, b)
        if spec is None:
            self.report({"ERROR"}, "The drag is too short to draw anything")
            return {"CANCELLED"}
        if not self.target:
            source, sketch, _ = script_model.new_sketch_script("Plane.XY", spec)
            for obj in context.selected_objects:
                obj.select_set(False)
            obj = part.new_part(context, source, name="Sketch")
            obj.matrix_world = Matrix([self.matrix[i * 4:i * 4 + 4] for i in range(4)])
            obj.select_set(True)
            context.view_layer.objects.active = obj
            focus.set_focus(obj, sketch)
            return {"FINISHED"}
        obj = part.local_part(self.target)
        if obj is None:
            self.report({"ERROR"}, f"There is no BlendSolid part named '{self.target}'")
            return {"CANCELLED"}
        if part.is_scaled(obj):
            self.report({"ERROR"}, part.scaled_message(obj))
            return {"CANCELLED"}
        blocked = part.blocking_error(obj)
        if blocked:
            self.report({"ERROR"}, blocked)
            return {"CANCELLED"}
        try:
            if self.sketch:
                source, _ = script_model.add_entity(part.source_of(obj), self.sketch, spec)
                sketch = self.sketch
            else:
                source, sketch, _ = script_model.append_sketch(part.source_of(obj), self.plane, spec)
        except script_model.NotCanonical as e:
            self.report({"ERROR"}, part.not_canonical_message(obj, e, detail=ui.scripts_visible(context)))
            return {"CANCELLED"}
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        obj.blendsolid_script.from_string(source)
        focus.set_focus(obj, sketch)
        return {"FINISHED"}

    # -- interactive drawing (the Sketch tool's left drag) ------------------------------------------------------

    def invoke(self, context, event):
        from . import ops_draw
        if context.area is None or context.area.type != "VIEW_3D" or context.region_data is None:
            return {"CANCELLED"}
        self.shape = context.scene.blendsolid_sketch_shape
        origin, direction = ops_draw._mouse_ray(context, event)
        near = ops_draw._near_rays(context, (event.mouse_region_x, event.mouse_region_y))
        self._target = hover_target(context, origin, direction, near)
        if self._target is None:
            self.report({"WARNING"}, "Sketches go on flat faces, sketches or the 3D cursor's plane")
            return {"CANCELLED"}
        blocked = part.blocking_error(self._target.obj)
        if blocked:
            self.report({"ERROR"}, blocked)
            return {"CANCELLED"}
        self._factor = part.unit_factor(context.scene)
        self._snap, self._snapped = 0.0, ""
        t = self._target
        self._part_points = part_points(t)
        p = self._uv(context, event)
        if p is None:
            return {"CANCELLED"}
        self._a = self._b = p
        self._path, self._press, self._arc_mode = [], None, False
        if self.shape == "PATH":
            self._press = ((event.mouse_region_x, event.mouse_region_y), p)
        self._handles = [bpy.types.SpaceView3D.draw_handler_add(_draw_drag, (self,), "WINDOW", "POST_VIEW"),
                         bpy.types.SpaceView3D.draw_handler_add(_draw_drag_label, (self,), "WINDOW", "POST_PIXEL")]
        _dragging.add(id(self))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _uv(self, context, event):
        """Plane coordinates (mm) under the mouse: with Shift on a path, on the nearest 15° direction from the
        last point; else snapped to a sketch point, or to the part's vertices, edge midpoints and circle centres
        projected on the plane, within SNAP_PX pixels; else to the grid while Ctrl is held."""
        from . import ops_draw
        origin, direction = ops_draw._mouse_ray(context, event)
        found = ray_uv(self._target.plane, origin, direction, self._factor)
        if found is None:
            return None
        uv = found[0]
        step = ops_draw.step_mm(context.scene)
        self._snap = (step / 10 if event.shift else step) if event.ctrl else 0.0
        self._snapped = ""
        path = getattr(self, "_path", [])
        if event.shift and not event.ctrl and path:
            self._snapped = f"{sketching.ANGLE_STEP:g}° lock"
            return sketching.angle_locked(path[-1][:2], uv)
        snapped = snap_to_points(context, self._target, uv, self._factor, getattr(self, "_part_points", []),
                                 [q[:2] for q in path])
        if snapped is not None:
            self._snapped = snapped[1]
            return tuple(snapped[0])
        if self._snap:
            return tuple(drawing.snap(c, self._snap) for c in uv)
        return tuple(round(c, 6) + 0.0 for c in uv)

    def modal(self, context, event):
        if self.shape == "PATH":
            return self._path_modal(context, event)
        from . import ops_draw
        if event.type in ops_draw.WHEEL and event.ctrl and event.value == "PRESS":
            ops_draw.change_step(context.scene, ops_draw.WHEEL[event.type])
            return {"RUNNING_MODAL"}
        if event.type in ops_draw.NAV_EVENTS:
            return {"PASS_THROUGH"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            return self._end(context, {"CANCELLED"})
        if event.type in {"MOUSEMOVE", "LEFT_CTRL", "RIGHT_CTRL", "LEFT_SHIFT", "RIGHT_SHIFT"}:
            p = self._uv(context, event)
            if p is not None:
                self._b = p
        elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
            p = self._uv(context, event)
            if p is not None:
                self._b = p
            self._end(context, None)
            if sketching.entity_spec(self.shape, self._a, self._b) is None:
                return {"CANCELLED"}  # a click without a drag
            t = self._target
            self.target = t.obj.name if t.obj is not None else ""
            self.sketch = t.sketch or ""
            self.plane = t.plane_code
            self.start, self.end = self._a, self._b
            self.exact = json.dumps({"start": list(self._a), "end": list(self._b)})
            if t.obj is None:
                self.matrix = [v for row in t.plane for v in row]
            return self.execute(context)
        context.area.header_text_set(
            f"Sketch: drag the {self.shape.lower()} | ends snap to sketch and part points | Ctrl: grid "
            f"{ops_draw.step_mm(context.scene):g} mm | Esc/right-click: cancel")
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    # -- the path: click, click, ...; a drag makes an arc -------------------------------------------------------

    def _path_modal(self, context, event):
        from . import ops_draw
        if event.type in ops_draw.WHEEL and event.ctrl and event.value == "PRESS":
            ops_draw.change_step(context.scene, ops_draw.WHEEL[event.type])
            return {"RUNNING_MODAL"}
        if event.type in ops_draw.NAV_EVENTS:
            return {"PASS_THROUGH"}
        if event.value == "PRESS" and event.type == "ESC":
            return self._end(context, {"CANCELLED"})
        if event.value == "PRESS" and event.type in {"RET", "NUMPAD_ENTER", "SPACE", "RIGHTMOUSE"}:
            return self._finish_path(context, closed=False)
        if event.value == "DOUBLE_CLICK" and event.type == "LEFTMOUSE":
            return self._finish_path(context, closed=False)
        if event.value == "PRESS" and (event.type == "BACK_SPACE" or event.type == "Z" and
                                       (event.ctrl or event.oskey) and not event.shift):  # Ctrl+Z: the reflex
            if self._path:
                self._path.pop()
            if not self._path:
                return self._end(context, {"CANCELLED"})
        elif event.value == "PRESS" and event.type == "A":
            self._arc_mode = not self._arc_mode
        elif event.type == "LEFTMOUSE" and event.value == "PRESS":
            p = self._uv(context, event)
            if p is not None:
                self._press = ((event.mouse_region_x, event.mouse_region_y), p)
        elif event.type == "LEFTMOUSE" and event.value == "RELEASE" and self._press is not None:
            p = self._uv(context, event)
            (x0, y0), start = self._press
            self._press = None
            dragged = math.hypot(event.mouse_region_x - x0, event.mouse_region_y - y0) > \
                DRAG_PX * ops_draw.ui_scale(context)
            if p is None:
                return {"RUNNING_MODAL"}
            if not self._path:
                self._path.append((start[0], start[1], False))
                if not dragged:
                    self._b = p
                    return self._status(context)
            if p == self._path[-1][:2]:
                return self._status(context)  # a click on the last point: nothing to add
            arc = (dragged or self._arc_mode) and len(self._path) >= 2
            if p == self._path[0][:2] and len(self._path) >= 2:
                if arc:
                    self._path.append((p[0], p[1], True))
                    self._path_closed_by_arc = True
                return self._finish_path(context, closed=True)
            self._path.append((p[0], p[1], arc))
            self._arc_mode = False
        if event.type in {"MOUSEMOVE", "LEFT_CTRL", "RIGHT_CTRL", "LEFT_SHIFT", "RIGHT_SHIFT"}:
            p = self._uv(context, event)
            if p is not None:
                self._b = p
        return self._status(context)

    def _status(self, context):
        from . import ops_draw
        mode = "arc" if self._arc_mode else "line (drag: arc)"
        context.area.header_text_set(
            f"Path: click the next point, {mode} | A: arc | first point: close | Enter/right-click/double-click: "
            f"end | Backspace/Ctrl+Z: remove the last point | Shift: 15° | Ctrl: grid {ops_draw.step_mm(context.scene):g} mm "
            f"| Esc: cancel")
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def preview_points(self):
        """The path drawn so far plus the segment to the mouse, as plane points (for the preview)."""
        pts = list(self._path)
        if pts and self._b != pts[-1][:2]:
            dragging = self._press is not None
            pts.append((self._b[0], self._b[1], (self._arc_mode or dragging) and len(pts) >= 2))
        return sketching.path_polyline(pts)

    def _finish_path(self, context, closed):
        self._end(context, None)
        if len(self._path) < 2:
            return {"CANCELLED"}
        t = self._target
        self.target = t.obj.name if t.obj is not None else ""
        self.sketch = t.sketch or ""
        self.plane = t.plane_code
        self.points = json.dumps([list(p) for p in self._path])
        self.closed = closed and not getattr(self, "_path_closed_by_arc", False)
        if t.obj is None:
            self.matrix = [v for row in t.plane for v in row]
        return self.execute(context)

    def _end(self, context, result):
        for handle in getattr(self, "_handles", []):
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        self._handles = []
        _dragging.discard(id(self))
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()
        return result


def _f32(x):
    import struct
    return struct.unpack("f", struct.pack("f", x))[0]


_dragging = set()


def entity_lines(shape, a, b, segments=48):
    """(u, v) segments of the entity a drag from `a` to `b` draws."""
    if shape == "RECTANGLE":
        c = [a, (b[0], a[1]), b, (a[0], b[1])]
        return [(c[i], c[(i + 1) % 4]) for i in range(4)]
    if shape == "CIRCLE":
        r = math.hypot(b[0] - a[0], b[1] - a[1])
        ring = [(a[0] + r * math.cos(2 * math.pi * k / segments), a[1] + r * math.sin(2 * math.pi * k / segments))
                for k in range(segments)]
        return [(ring[k], ring[(k + 1) % segments]) for k in range(segments)] + [(a, b)]
    return [(a, b)]


def _draw_drag(op):
    from . import ops_draw
    try:
        plane, factor, a, b, shape = op._target.plane, op._factor, op._a, op._b, op.shape
    except (ReferenceError, AttributeError):
        return
    at = lambda p: plane @ Vector((p[0] * factor, p[1] * factor, 0.0))
    colour = (1.0, 0.85, 0.3, 1.0)
    if shape == "PATH":
        pts = op.preview_points()
        segments = list(zip(pts, pts[1:]))
    else:
        segments = entity_lines(shape, a, b)
    lines = [(at(p), at(q), colour, colour) for p, q in segments]
    ui = ops_draw.ui_scale(bpy.context)
    ops_draw._draw_segments(bpy.context.region, lines, 2.5 * ui)
    if op._snap:
        region, rv3d = bpy.context.region, bpy.context.region_data
        pixel = ops_draw._pixel_size(region, rv3d, at(b))
        step = op._snap * factor
        shown = None if pixel is None else drawing.visible_grid_step(step, pixel)
        if shown is not None:
            ops_draw._draw_grid(bpy.context, plane, (b[0] * factor, b[1] * factor), shown, colour)


def _draw_drag_label(op):
    from . import ops_draw
    try:
        plane, factor, a, b, shape = op._target.plane, op._factor, op._a, op._b, op.shape
    except (ReferenceError, AttributeError):
        return
    if shape == "PATH":
        last = op._path[-1] if op._path else a
        text = f"{drawing.mm(math.hypot(b[0] - last[0], b[1] - last[1]))} mm"
    elif shape == "RECTANGLE":
        text = f"{drawing.mm(abs(b[0] - a[0]))} × {drawing.mm(abs(b[1] - a[1]))} mm"
    elif shape == "CIRCLE":
        text = f"R {drawing.mm(math.hypot(b[0] - a[0], b[1] - a[1]))} mm"
    else:
        text = f"{drawing.mm(math.hypot(b[0] - a[0], b[1] - a[1]))} mm"
    snapped = getattr(op, "_snapped", "")
    ops_draw.draw_text_lines(bpy.context, plane @ Vector((b[0] * factor, b[1] * factor, 0.0)),
                             [text] + ([snapped] if snapped else [f"snap {op._snap:g} mm"] if op._snap else []))


# -- the overlay: sketches, and the hover marker ------------------------------------------------------------------

def active_tool(context):
    try:
        return context.workspace.tools.from_space_view3d_mode(context.mode).idname
    except (AttributeError, RuntimeError):
        return ""


def _draw_sketches():
    from . import ops_draw
    context = bpy.context
    if context.region_data is None:
        return
    tool_active = active_tool(context) in SKETCH_TOOLS
    factor = part.unit_factor(context.scene)
    lines = []
    for obj in sketch_parts(context):
        for sketch in sketches_of(obj):
            if sketch["used"] and not tool_active:
                continue
            colour = USED_COLOUR if sketch["used"] else CURVE_COLOUR
            for curves in sketch["curves"].values():
                for curve in curves:
                    pts = [world_point(obj, sketch, p, factor) for p in curve]
                    lines += [(p, q, colour, colour) for p, q in zip(pts, pts[1:])]
    if lines:
        ops_draw._draw_segments(context.region, lines, 2.0 * ops_draw.ui_scale(context))


def region_triangles(obj, sketch, region, factor):
    """World triangles filling a sketch region (its loops, holes included)."""
    loops = [[Vector((p[0], p[1], 0.0)) for p in loop] for loop in region["loops"]]
    tris = geometry.tessellate_polygon(loops)
    flat = [p for loop in region["loops"] for p in loop]
    pts = [world_point(obj, sketch, p, factor) for p in flat]
    return [(pts[a], pts[b], pts[c]) for a, b, c in tris]


def draw_triangles(triangles, colour):
    if not triangles:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "TRIS", {"pos": [tuple(p) for t in triangles for p in t]})
    shader.uniform_float("color", colour)
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")
    batch.draw(shader)
    gpu.state.blend_set("NONE")


class BLENDSOLID_GT_sketch_hover(bpy.types.Gizmo):
    """The Sketch tool's hover marker: where a drag would start, and on which plane (see ops_draw's marker)."""
    bl_idname = "BLENDSOLID_GT_sketch_hover"

    def setup(self):
        self.mouse = None

    def test_select(self, context, location):
        self.mouse = tuple(location)
        context.area.tag_redraw()
        return -1

    def draw(self, context):
        from . import ops_draw
        if self.mouse is None or context.region_data is None or _dragging:
            return
        origin, direction = ops_draw.mouse_ray(context, self.mouse)
        target = hover_target(context, origin, direction, ops_draw._near_rays(context, self.mouse))
        if target is None:
            return
        factor = part.unit_factor(context.scene)
        found = ray_uv(target.plane, origin, direction, factor)
        if found is None:
            return
        uv = found[0]
        snapped = snap_to_points(context, target, uv, factor, part_points(target))
        if snapped is not None:  # where a click lands: say so before the first click too, as the drag label does
            node = tuple(c * factor for c in snapped[0])
        else:
            step = ops_draw.step_mm(context.scene)
            node = tuple(drawing.snap(c, step) * factor for c in uv)
        point = target.plane @ Vector((node[0], node[1], 0.0))
        ops_draw.draw_marker(context, point, target.plane, target.obj, node)
        if snapped is not None:
            ops_draw.draw_text_lines(context, point, [snapped[1]], pixel_space=True)


class BLENDSOLID_GGT_sketch_hover(bpy.types.GizmoGroup):
    bl_idname = "BLENDSOLID_GGT_sketch_hover"
    bl_label = "Sketch Snap Marker"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    def setup(self, context):
        from . import runtime
        runtime.warm_up()
        self.gizmos.new(BLENDSOLID_GT_sketch_hover.bl_idname)


class SketchTool(bpy.types.WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = "blendsolid.sketch_tool"
    bl_label = "Sketch"
    bl_description = ("Draw paths (click points; drag for a tangent arc), rectangles and circles on a part's flat "
                      "face, on a sketch, or on the 3D cursor's plane (a new part); points snap to the sketch's, "
                      "Ctrl to the grid. Paths guide grooves and ribs, and split the face they cross")
    bl_icon = "ops.gpencil.primitive_box"
    bl_widget = "BLENDSOLID_GGT_sketch_hover"
    bl_keymap = (
        ("blendsolid.sketch_entity", {"type": "LEFTMOUSE", "value": "PRESS", "any": True}, None),
        ("blendsolid.snap_step", {"type": "WHEELUPMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", 1)]}),
        ("blendsolid.snap_step", {"type": "WHEELDOWNMOUSE", "value": "PRESS", "ctrl": True},
         {"properties": [("direction", -1)]}),
    )

    def draw_settings(context, layout, tool):
        layout.prop(context.scene, "blendsolid_sketch_shape", expand=True)
        layout.prop(context.scene, "blendsolid_snap_step", text="Snap")


CLASSES = [BLENDSOLID_OT_sketch_entity, BLENDSOLID_GT_sketch_hover, BLENDSOLID_GGT_sketch_hover]
_overlay = None


def register():
    global _overlay
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.blendsolid_sketch_shape = EnumProperty(name="Shape", items=SHAPES, default="PATH",
                                                           description="What the Sketch tool draws")
    bpy.utils.register_tool(SketchTool, after={"blendsolid.push_pull_tool"})
    _overlay = bpy.types.SpaceView3D.draw_handler_add(_draw_sketches, (), "WINDOW", "POST_VIEW")


def unregister():
    global _overlay
    if _overlay is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_overlay, "WINDOW")
        _overlay = None
    bpy.utils.unregister_tool(SketchTool)
    del bpy.types.Scene.blendsolid_sketch_shape
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    _cache.clear()
