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


@dataclass(frozen=True)
class Drawn:
    shape: str                  # "BOX" or "CYLINDER"
    frame: Matrix               # world, Blender units: base centre and axes (Z = plane normal)
    length: float = 0.0         # mm (box)
    width: float = 0.0          # mm (box)
    radius: float = 0.0         # mm (cylinder)
    height: float = 0.0         # mm, signed: > 0 along +Z of the frame (out of a face), < 0 into it


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
    X from the object's X, or its Y when X is along the normal), so a top face gives a rotation of zero."""
    rot = obj_matrix.to_3x3().normalized()
    local_n = _snap_axis((rot.inverted() @ Vector(normal)).normalized())
    local_x = Vector((1, 0, 0)) if abs(local_n.x) < 0.9 else Vector((0, 1, 0))
    return _frame(Vector(location), rot @ local_x, rot @ local_n)


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


def drawn_solid(shape, plane, p0, p1, height, factor, step_mm=0.0):
    """The solid of a drag: base from plane coords p0 to p1 (Blender units; a box's opposite corners, a
    cylinder's centre and a point on its rim), `height` in Blender units (signed). Dimensions snap to
    `step_mm` millimetres when it's > 0 (and so does the base centre, in plane coordinates)."""
    to_mm = 1.0 / factor
    (u0, v0), (u1, v1) = p0, p1
    if shape == "BOX":
        cu = snap((u0 + u1) / 2 * to_mm, step_mm / 2) / to_mm
        cv = snap((v0 + v1) / 2 * to_mm, step_mm / 2) / to_mm
        dims = {"length": snap(abs(u1 - u0) * to_mm, step_mm), "width": snap(abs(v1 - v0) * to_mm, step_mm)}
    else:
        cu, cv = snap(u0 * to_mm, step_mm) / to_mm, snap(v0 * to_mm, step_mm) / to_mm
        dims = {"radius": snap(math.hypot(u1 - u0, v1 - v0) * to_mm, step_mm)}
    center = plane.translation + plane.col[0].xyz * cu + plane.col[1].xyz * cv
    frame = plane.copy()
    frame.translation = center
    return Drawn(shape, frame, height=snap(height * to_mm, step_mm), **dims)


def placement(frame, reference, factor):
    """(location mm, rotation radians) of world `frame` in the frame of world matrix `reference` (a part's
    matrix_world, or None for the world). The rotation is an Euler in 'ZYX' order, which is build123d's
    Location(..., (rx, ry, rz)) convention (intrinsic XYZ, verified numerically)."""
    local = frame if reference is None else reference.inverted_safe() @ frame
    location = tuple(v / factor for v in local.translation)
    rotation = tuple(local.to_3x3().normalized().to_euler("ZYX"))
    return location, rotation


def frame_matrix(location_mm, rotation, factor):
    """Inverse of placement() for reference None: a 4x4 matrix in Blender units."""
    return Matrix.Translation(Vector(location_mm) * factor) @ Euler(rotation, "ZYX").to_matrix().to_4x4()


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
