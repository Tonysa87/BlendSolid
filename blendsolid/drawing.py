"""Geometry of the Draw Solid tool (tool 2), without operators or drawing: the plane the user draws on, the
solid a drag describes, and the numbers written into the script. Uses mathutils (Blender tests only).

A drawing plane is a 4x4 world matrix (Blender units): origin on the plane, X and Y in it, Z its normal (for a
part's face: pointing out of the part). A drawn solid has a *frame* (the centre of its base on the plane, same
axes) and dimensions in millimetres; its height goes along +Z (union, new part) or -Z (cut) of the frame.
"""
import math
from dataclasses import dataclass

from mathutils import Euler, Matrix, Vector, geometry

AXIS_SNAP = 1e-4  # a face normal this close to one of the part's axes is taken as that axis exactly
# Snap steps in millimetres, chosen with Ctrl+Wheel; Ctrl snaps to the step, Shift+Ctrl to a tenth of it.
STEPS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1000.0, 2000.0, 5000.0, 10000.0)


def next_step(step, direction):
    """The step `direction` places up (+1) or down (-1) the ladder from `step`, clamped at both ends."""
    i = min(range(len(STEPS)), key=lambda k: abs(STEPS[k] - step))
    return STEPS[max(0, min(len(STEPS) - 1, i + direction))]


@dataclass(frozen=True)
class Drawn:
    shape: str                  # "BOX" or "CYLINDER"
    frame: Matrix               # world, Blender units: base centre and axes (Z = plane normal)
    length: float = 0.0         # mm (box)
    width: float = 0.0          # mm (box)
    radius: float = 0.0         # mm (cylinder)
    height: float = 0.0         # mm, signed: > 0 along +Z of the frame (out of a face), < 0 into it
    local: "LocalPlane | None" = None  # the frame in the part's own coordinates, exact (plane_on_part_face)


@dataclass(frozen=True)
class LocalPlane:
    """A plane or frame in a part's own coordinates, in float64 (mathutils matrices are float32, whose noise
    left skins and slivers in booleans): origin in millimetres, unit axes (Z the plane normal)."""
    origin: tuple
    x: tuple
    y: tuple
    z: tuple

    def moved(self, u_mm, v_mm):
        o = tuple(self.origin[i] + self.x[i] * u_mm + self.y[i] * v_mm for i in range(3))
        return LocalPlane(o, self.x, self.y, self.z)

    def matrix(self, factor):
        """As a mathutils 4x4 matrix in Blender units (float32: for display and ray casting only)."""
        m = Matrix.Identity(4)
        for i in range(3):
            m[i][0], m[i][1], m[i][2], m[i][3] = self.x[i], self.y[i], self.z[i], self.origin[i] * factor
        return m


def euler_zyx(x, y, z):
    """The 'ZYX' Euler angles (radians, float64) of the rotation whose columns are unit axes x, y, z: what
    mathutils' to_euler("ZYX") gives (R = Rx @ Ry @ Rz), without its float32 rounding."""
    m = [[x[0], y[0], z[0]], [x[1], y[1], z[1]], [x[2], y[2], z[2]]]
    sy = max(-1.0, min(1.0, m[0][2]))
    ry = math.asin(sy)
    if abs(sy) < 1.0 - 1e-12:
        rx, rz = math.atan2(-m[1][2], m[2][2]), math.atan2(-m[0][1], m[0][0])
    else:  # gimbal lock: put the whole remaining rotation on X
        rx, rz = math.atan2(m[2][1], m[1][1]), 0.0
    return tuple(a + 0.0 for a in (rx, ry, rz))  # + 0.0: no -0.0


def _frame(origin, x_axis, z_axis):
    z = z_axis.normalized()
    x = (x_axis - z * x_axis.dot(z)).normalized()
    y = z.cross(x)
    m = Matrix.Identity(4)
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = x[i], y[i], z[i], origin[i]
    return m


def _snap_axis(v):
    for axis in (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))):
        for signed in (axis, -axis):
            if (v - signed).length < AXIS_SNAP:
                return signed.copy()
    return v


def plane_on_face(location, normal, obj_matrix):
    """The drawing plane on the face hit at `location` with world `normal`, of an object with world matrix
    `obj_matrix`: its axes follow the object's (the normal snapped to an object axis when it is one, the plane
    X from the object's X, or its Y when X is along the normal), so a top face gives a rotation of zero. Its
    origin is the object's origin projected onto the face, so the snapping grid is the part's own."""
    rot = obj_matrix.to_3x3().normalized()
    n = rot @ _snap_axis((rot.inverted() @ Vector(normal)).normalized())
    local_n = rot.inverted() @ n
    local_x = Vector((1, 0, 0)) if abs(local_n.x) < 0.9 else Vector((0, 1, 0))
    o = obj_matrix.translation
    return _frame(o + n * (Vector(location) - o).dot(n), rot @ local_x, n)


def plane_on_part_face(normal, d_mm):
    """The drawing plane on a part's flat face as a LocalPlane (float64, the part's own coordinates), from the
    face's exact plane (unit `normal` in the part's frame, n . p = d_mm): origin the part's origin projected
    on it, axes as plane_on_face. Built without the float32 mesh or matrix_world, so placements are exact."""
    n = [float(c) for c in normal]
    length = math.sqrt(sum(c * c for c in n))
    n = [c / length for c in n]
    for i in range(3):  # an axis-aligned face gets an exact axis
        if abs(abs(n[i]) - 1.0) < AXIS_SNAP:
            n = [0.0, 0.0, 0.0]
            n[i] = math.copysign(1.0, normal[i])
    x = [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0]
    dot = sum(x[i] * n[i] for i in range(3))
    x = [x[i] - n[i] * dot for i in range(3)]
    length = math.sqrt(sum(c * c for c in x))
    x = [c / length for c in x]
    y = [n[1] * x[2] - n[2] * x[1], n[2] * x[0] - n[0] * x[2], n[0] * x[1] - n[1] * x[0]]
    return LocalPlane(tuple(c * d_mm + 0.0 for c in n), tuple(x), tuple(c + 0.0 for c in y), tuple(n))


def plane_at_cursor(cursor_matrix):
    """The drawing plane through the 3D cursor, with its rotation."""
    m = cursor_matrix.normalized()
    return _frame(m.translation, m.col[0].xyz, m.col[2].xyz)


def plane_coords(plane, ray_origin, ray_direction):
    """(u, v) in Blender units where the mouse ray meets the plane, or None (ray parallel to the plane)."""
    origin, normal = plane.translation, plane.col[2].xyz
    hit = geometry.intersect_line_plane(Vector(ray_origin), Vector(ray_origin) + Vector(ray_direction),
                                        origin, normal)
    if hit is None:
        return None
    d = hit - origin
    return d.dot(plane.col[0].xyz), d.dot(plane.col[1].xyz)


def height_along_normal(plane, base_center, ray_origin, ray_direction):
    """Signed distance (Blender units) along the plane normal from `base_center` to where the mouse ray
    passes closest to the normal line through it."""
    normal = plane.col[2].xyz
    ro = Vector(ray_origin)
    found = geometry.intersect_line_line(base_center, base_center + normal, ro, ro + Vector(ray_direction))
    if found is None:
        return 0.0
    return (found[0] - base_center).dot(normal)


def snap(value, step):
    return value if step <= 0 else round(value / step) * step


def grid_node(plane, p, factor, step_mm):
    """Plane coords `p` (Blender units) moved to the nearest node of the plane's grid of `step_mm` millimetres
    (unchanged when step_mm is 0). The grid starts at the plane's origin: the 3D cursor, or a part's origin."""
    return tuple(snap(x / factor, step_mm) * factor for x in p)


def drawn_solid(shape, plane, p0, p1, height, factor, step_mm=0.0, local=None):
    """The solid of a drag: base from plane coords p0 to p1 (Blender units; a box's opposite corners, a
    cylinder's centre and a point on its rim), `height` in Blender units (signed). With `step_mm` > 0 both
    corners (a cylinder's centre) go to the nearest grid nodes and the radius and height snap to the step.
    `local`: the same plane as a LocalPlane (plane_on_part_face): Drawn.local is then the exact frame."""
    to_mm = 1.0 / factor
    # In millimetres, so snapped dimensions are exact multiples of the step.
    a0, b0 = (snap(x * to_mm, step_mm) for x in p0)
    if shape == "BOX":
        a1, b1 = (snap(x * to_mm, step_mm) for x in p1)
        cu_mm, cv_mm = (a0 + a1) / 2, (b0 + b1) / 2
        dims = {"length": abs(a1 - a0), "width": abs(b1 - b0)}
    else:
        cu_mm, cv_mm = a0, b0
        dims = {"radius": snap(math.hypot(p1[0] * to_mm - a0, p1[1] * to_mm - b0), step_mm)}
    # The mouse is float32: 6 decimals, like the parameters (an exact placement is written with more).
    cu_mm, cv_mm = round(cu_mm, 6) + 0.0, round(cv_mm, 6) + 0.0
    frame = _moved(plane, cu_mm / to_mm, cv_mm / to_mm)
    return Drawn(shape, frame, height=snap(height * to_mm, step_mm), local=None if local is None
                 else local.moved(cu_mm, cv_mm), **dims)


def _moved(plane, u, v):
    frame = plane.copy()
    frame.translation = plane.translation + plane.col[0].xyz * u + plane.col[1].xyz * v
    return frame


def placement(frame, reference, factor):
    """(location mm, rotation radians) of world `frame` in the frame of world matrix `reference` (a part's
    matrix_world, or None for the world). The rotation is an Euler in 'ZYX' order, which is build123d's
    Location(..., (rx, ry, rz)) convention (intrinsic XYZ, verified numerically)."""
    local = frame if reference is None else reference.inverted_safe() @ frame
    location = tuple(v / factor for v in local.translation)
    rotation = tuple(local.to_3x3().normalized().to_euler("ZYX"))
    return location, rotation


def placement_local(local):
    """(location mm, rotation radians) of a LocalPlane frame: placement() for an exact frame."""
    return local.origin, euler_zyx(local.x, local.y, local.z)


def frame_matrix(location_mm, rotation, factor):
    """Inverse of placement() for reference None: a 4x4 matrix in Blender units."""
    return Matrix.Translation(Vector(location_mm) * factor) @ Euler(rotation, "ZYX").to_matrix().to_4x4()


# -- snap feedback (display only): colours by axis, a local grid, height ticks, labels -------------------------

GRID_HALF = 8      # the local grid reaches this many steps from the node under the mouse, fading out
GRID_MAJOR = 5     # every 5th grid line is a major one
MIN_GRID_PX = 8    # grid cells smaller than this on screen are not drawn


def axis_color(direction, axis_colors):
    """RGBA of a direction: the X/Y/Z axis colours (Blender's theme) mixed by the squared components of the
    unit direction, so an axis-aligned direction gets its axis colour and 45 degrees in XZ half of each."""
    d = Vector(direction).normalized()
    w = (d.x * d.x, d.y * d.y, d.z * d.z)
    return tuple(sum(w[i] * axis_colors[i][c] for i in range(3)) for c in range(3)) + (1.0,)


def marker_lines(point, plane, arm, axis_colors):
    """(start, end, colour) segments of the snap marker at world `point` on `plane`: a cross along the plane's
    axes and a stub along its normal (out of a face: where a union grows), each coloured by its world axis."""
    lines = []
    for axis in (plane.col[0].xyz, plane.col[1].xyz):
        colour = axis_color(axis, axis_colors)
        lines += [(point, point + axis * arm, colour), (point, point - axis * arm, colour)]
    normal = plane.col[2].xyz
    return lines + [(point, point + normal * arm, axis_color(normal, axis_colors))]


def visible_grid_step(step, pixel):
    """The grid step to draw (Blender units) for a snap `step` when one pixel is `pixel` Blender units: the
    step itself, only the major lines when cells would be too small, or None when even those are."""
    for s in (step, step * GRID_MAJOR):
        if s / pixel >= MIN_GRID_PX:
            return s
    return None


def _fade(t):
    return max(0.0, 1.0 - t) ** 2


def grid_segments(plane, centre, step, half=GRID_HALF):
    """(start, end, alpha start, alpha end, major) segments of the grid of `step` (Blender units) on `plane`
    around the node nearest `centre` (plane coords, Blender units). The lines go through the snap nodes
    (grid_node's grid: from the plane's origin); alpha is 1 at that node and 0 at `half` steps from it."""
    o, ax, ay = plane.translation, plane.col[0].xyz, plane.col[1].xyz
    kc = (round(centre[0] / step), round(centre[1] / step))
    at = lambda u, v: o + ax * (u * step) + ay * (v * step)
    alpha = lambda u, v: _fade(math.hypot(u - kc[0], v - kc[1]) / half)
    segments = []
    for across in (0, 1):  # lines of constant u, then of constant v
        for k in range(kc[across] - half, kc[across] + half + 1):
            for j in range(kc[1 - across] - half, kc[1 - across] + half):
                (u0, v0), (u1, v1) = ((k, j), (k, j + 1)) if across == 0 else ((j, k), (j + 1, k))
                segments.append((at(u0, v0), at(u1, v1), alpha(u0, v0), alpha(u1, v1), k % GRID_MAJOR == 0))
    return segments


def height_ticks(frame, height, step, tick, half=GRID_HALF):
    """(start, end, alpha) ticks every `step` (Blender units) along the normal of `frame` (a drawn solid's
    base) around `height` (Blender units, signed): short segments of length `tick` along the frame's X."""
    n, x, o = frame.col[2].xyz, frame.col[0].xyz, frame.translation
    kc = round(height / step)
    ticks = []
    for k in range(kc - half, kc + half + 1):
        c = o + n * (k * step)
        ticks.append((c - x * (tick / 2), c + x * (tick / 2), _fade(abs(k - kc) / (half + 1))))
    return ticks


def _mm(value):
    return f"{value:.3f}".rstrip("0").rstrip(".")


def labels(drawn, stage, snap_mm):
    """Text lines shown next to a solid being drawn: the base's size or the height, and the snap step while
    Ctrl snaps (`snap_mm` > 0)."""
    if stage == "HEIGHT":
        lines = [f"H {_mm(abs(drawn.height))} mm"]
    elif drawn.shape == "BOX":
        lines = [f"{_mm(drawn.length)} × {_mm(drawn.width)} mm"]
    else:
        lines = [f"R {_mm(drawn.radius)} mm"]
    return lines + ([f"snap {snap_mm:g} mm"] if snap_mm > 0 else [])

def preview_lines(drawn, factor, segments=32):
    """World-space line segments (pairs of points) outlining `drawn` (for the gpu preview)."""
    h = drawn.height * factor
    if drawn.shape == "BOX":
        a, b = drawn.length * factor / 2, drawn.width * factor / 2
        ring = [Vector((-a, -b, 0)), Vector((a, -b, 0)), Vector((a, b, 0)), Vector((-a, b, 0))]
    else:
        r = drawn.radius * factor
        ring = [Vector((r * math.cos(2 * math.pi * i / segments), r * math.sin(2 * math.pi * i / segments), 0))
                for i in range(segments)]
    top = [p + Vector((0, 0, h)) for p in ring]
    lines = []
    for loop in (ring, top) if h else (ring,):
        lines += [(loop[i], loop[(i + 1) % len(loop)]) for i in range(len(loop))]
    if h:
        step = 1 if drawn.shape == "BOX" else segments // 4
        lines += [(ring[i], top[i]) for i in range(0, len(ring), step)]
    return [(drawn.frame @ p, drawn.frame @ q) for p, q in lines]
