"""The Sketch and Extrude tools' geometry, without bpy: what an entity or an extrude writes into the script, and
the worker's sketch display data (part.SKETCHES_KEY) read in plane coordinates (millimetres).

A sketch's display (worker sketches.Sketch.display()) holds its plane in the part's frame (origin, x, y, z; mm),
each entity's curves and each region's loops as (u, v) points on that plane, and the points a click snaps to.
"""
import math

from .script_model import EntitySpec, FeatureSpec, fmt

SNAP_PX = 10  # a click this close (pixels) to a sketch point snaps to it


def rect_spec(a, b):
    """A rectangle with opposite corners `a` and `b` (plane coordinates, mm): centre literal, size parameters."""
    cu, cv = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    return EntitySpec("rect", (("width", abs(b[0] - a[0])), ("height", abs(b[1] - a[1]))),
                      f"Pos({fmt(cu)}, {fmt(cv)}) * Rectangle({{name}}_width, {{name}}_height)")


def circle_spec(centre, radius):
    return EntitySpec("circle", (("radius", radius),), f"Pos({fmt(centre[0])}, {fmt(centre[1])}) * Circle({{name}}_radius)")


def line_spec(a, b):
    return EntitySpec("line", (), f"Line(({fmt(a[0])}, {fmt(a[1])}), ({fmt(b[0])}, {fmt(b[1])}))")


ENTITY_SHAPES = ("RECTANGLE", "CIRCLE", "LINE")


def entity_spec(shape, a, b):
    """The entity a drag from `a` to `b` draws: a rectangle's corners, a circle's centre and a point on it, a
    line's ends. None for a drag too short to draw anything."""
    if shape == "RECTANGLE":
        return rect_spec(a, b) if min(abs(b[0] - a[0]), abs(b[1] - a[1])) >= MIN_MM else None
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length < MIN_MM:
        return None
    return circle_spec(a, length) if shape == "CIRCLE" else line_spec(a, b)


MIN_MM = 0.001


def point_in_loops(loops, p):
    """Even-odd test of plane point `p` against a region's loops (outer boundary and holes)."""
    inside = False
    x, y = p
    for loop in loops:
        n = len(loop)
        for i in range(n):
            (x0, y0), (x1, y1) = loop[i], loop[(i + 1) % n]
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                inside = not inside
    return inside


def region_at(sketch, p):
    """Index of the region of `sketch` (display dict) containing plane point `p`, or None."""
    for i, region in enumerate(sketch["regions"]):
        if point_in_loops(region["loops"], p):
            return i
    return None


def to_plane(sketch, point):
    """Plane coordinates (u, v, w) of a point in the part's frame (mm): w is its height above the plane."""
    o, x, y, z = sketch["plane"]
    d = [point[i] - o[i] for i in range(3)]
    return tuple(sum(d[i] * axis[i] for i in range(3)) for axis in (x, y, z))


def from_plane(sketch, uv):
    """The part-frame point (mm) at plane coordinates `uv`."""
    o, x, y, _ = sketch["plane"]
    return tuple(o[i] + x[i] * uv[0] + y[i] * uv[1] for i in range(3))


def same_plane(a, b, tolerance=1e-6):
    """Do two planes (origin, x, y, z; mm) coincide (same normal direction, same offset)?"""
    za, zb = a[3], b[3]
    if sum(za[i] * zb[i] for i in range(3)) < 1 - 1e-9:
        return False
    return abs(sum((b[0][i] - a[0][i]) * za[i] for i in range(3))) < tolerance


def nearest_point(points, p, radius):
    """The point of `points` nearest `p` within `radius` (plane units), or None."""
    best, found = radius, None
    for q in points:
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if d <= best:
            best, found = d, q
    return found


def bounds(sketch):
    """(umin, vmin, umax, vmax) of a sketch's curves."""
    pts = [p for curves in sketch["curves"].values() for curve in curves for p in curve]
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


OPERATIONS = ("ADD", "SUBTRACT", "INTERSECT")
EXTENTS = ("DISTANCE", "NEXT", "LAST")


def extrude_spec(sketch, seed, amount, operation="ADD", extent="DISTANCE", symmetric=False, taper=0.0):
    """The Extrude tool's feature: the region of `sketch` (feature name) at `seed` (plane coordinates, mm)
    extruded by `amount` mm (negative: against the plane's normal), or up to the next/last face in that
    direction. The distance and a nonzero taper are parameters; the direction is written as the sign."""
    region = f"regions({sketch}, ({fmt(seed[0])}, {fmt(seed[1])}))"
    values, args = [], [region]
    if extent == "DISTANCE":
        values.append(("amount", abs(float(amount))))
        args.append(("amount=-{name}_amount" if amount < 0 else "amount={name}_amount"))
        if symmetric:
            args.append("both=True")
        if taper:
            values.append(("taper", float(taper)))
            args.append("taper={name}_taper")
    else:
        if amount < 0:
            args.append(f"dir=-{sketch}.plane.z_dir")
        args.append(f"until=Until.{extent}")
    if operation != "ADD":
        args.append(f"mode=Mode.{operation}")
    prefix = {"ADD": "extrude", "SUBTRACT": "cut", "INTERSECT": "common"}[operation]
    return FeatureSpec(prefix, tuple(values), f"extrude({', '.join(args)})")


def revolve_spec(sketch, seed, axis_entity, angle=360.0, operation="ADD"):
    """The Revolve tool's feature: the region of `sketch` at `seed` turned about its line `axis_entity` by
    `angle` degrees (a parameter)."""
    region = f"regions({sketch}, ({fmt(seed[0])}, {fmt(seed[1])}))"
    call = f'revolve({region}, axis={sketch}.axis("{axis_entity}"), revolution_arc={{name}}_angle'
    if operation != "ADD":
        call += f", mode=Mode.{operation}"
    prefix = {"ADD": "revolve", "SUBTRACT": "cut", "INTERSECT": "common"}[operation]
    return FeatureSpec(prefix, (("angle", float(angle)),), call + ")")


def line_entities(sketch):
    """Names of the entities of `sketch` (display dict) that are one straight segment: revolve axes."""
    return [name for name, curves in sketch["curves"].items() if len(curves) == 1 and len(curves[0]) == 2]


def distance_to_segment(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    length2 = ax * ax + ay * ay
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / length2))
    return math.hypot(p[0] - a[0] - t * ax, p[1] - a[1] - t * ay)


def entity_at(sketch, p, radius, names=None):
    """The entity of `sketch` whose curves pass within `radius` of `p` (the nearest), or None."""
    best, found = radius, None
    for name, curves in sketch["curves"].items():
        if names is not None and name not in names:
            continue
        for curve in curves:
            for a, b in zip(curve, curve[1:]):
                d = distance_to_segment(p, a, b)
                if d <= best:
                    best, found = d, name
    return found
