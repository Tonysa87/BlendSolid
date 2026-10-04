"""2D sketches in part scripts, and the extrude/revolve of their regions (milestone 3a).

A sketch is a feature of its own: a plane and named build123d objects drawn in that plane's local XY
(millimetres). It adds no solid; its closed areas (regions) are what extrude() and revolve() take:

    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.rect_1 = Pos(12.0, 8.0) * Rectangle(sketch_1_rect_1_width, sketch_1_rect_1_height)
        sketch_1.circle_1 = Pos(30.0, 8.0) * Circle(sketch_1_circle_1_radius)
    extrude(regions(sketch_1, (12.0, 8.0)), amount=extrude_1_amount)  # feature: extrude_1

- `on_face(face(...))` is a flat face's exact plane with its origin at the part's origin projected onto it and
  its X axis by Draw Solid's rule (ADR 0006), so the sketch follows the face when an upstream change moves it,
  and sketch coordinates don't shift when the face grows (build123d's Plane(face) is centred on the face).
- `regions(sketch, (u, v), ...)` are the areas bounded by all the sketch's curves (overlaps split them, as in
  Fusion, Onshape and Plasticity) that contain the seed points, placed on the sketch's plane. A seed in no
  region is an error; a seed on a region's boundary a warning. The tools write each seed as
  `area((u, v), inside="rect_1", left="line_1", ...)`: the point and the curves bounding the area it picked, with
  the area's side of each (Onshape identifies a region by its bounding curves). When an upstream change moves
  the area under the point, the side of a curve that flipped (or no curve in common) is an error, other
  changes to the bounding curves a warning: a region is never re-bound silently (ADR 0009).
- extrude() and revolve() of regions are BlendSolid's own (other inputs go to build123d's): taper is a straight
  extrusion drafted with the sketch plane as neutral plane (only planes and cones, never build123d's lofted
  B-spline sides), and the faces they bring in get roles by what made them: "start" and "end" for the caps,
  the name of the sketch entity for each side (face("extrude_1", "rect_1")).
"""
import math

HOOK_FEATURE = "__bs_sketch__"
ON_EDGE_MM = 1e-4       # a seed this close to a region's boundary is doubtful (warning)
ON_FACE_MM = 1e-4       # a sketch edge this close to a solid's face swept it
AXIS_SNAP = 1e-4        # a face normal this close to a part axis is that axis (drawing.plane_on_part_face)
MIN_MM = 1e-6          # the smallest extrude distance (OCCT's prism fails at 1e-7)
FUZZY_MM = 1e-5         # curve ends this close meet (scripts write 6 decimals: ends snapped to a rounded corner)
FACE = "face"           # area(): the sketch face's own boundary, among the entity names (reserved)
SIDES = ("inside", "outside", "left", "right")
CURVE_DEG = 5.0         # display: one polyline segment per this many degrees of arc
MAX_SEGMENTS = 256


class SketchError(ValueError):
    """A sketch or region that can't be built; reported on the script line."""


def _vec(v):
    return tuple(float(c) + 0.0 for c in v)


def plane_frame(normal, d_mm):
    """(origin, x, y, z) of the sketch plane on a flat face with unit outward `normal` and n . p = d_mm: the
    part's origin projected onto it, X by Draw Solid's rule. Must match drawing.plane_on_part_face (Blender)."""
    n = [float(c) for c in normal]
    length = math.sqrt(sum(c * c for c in n))
    n = [c / length for c in n]
    for i in range(3):
        if abs(abs(n[i]) - 1.0) < AXIS_SNAP:
            sign = math.copysign(1.0, n[i])
            n = [0.0, 0.0, 0.0]
            n[i] = sign
    x = [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0]
    dot = sum(x[i] * n[i] for i in range(3))
    x = [x[i] - n[i] * dot for i in range(3)]
    length = math.sqrt(sum(c * c for c in x))
    x = [c / length for c in x]
    y = [n[1] * x[2] - n[2] * x[1], n[2] * x[0] - n[0] * x[2], n[0] * x[1] - n[1] * x[0]]
    return (_vec(c * d_mm for c in n), _vec(x), _vec(y), _vec(n))


def on_face(faces):
    """The sketch plane on one flat face (a face() result): see the module docstring."""
    from build123d import Plane
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    import tessellate
    items = list(faces) if isinstance(faces, (list, tuple)) else [faces]
    if len(items) != 1:
        name = getattr(faces, "_bs_name", "the face")
        raise SketchError(f"a sketch goes on one flat face, and {name} is {len(items)} faces")
    face = items[0].wrapped
    if BRepAdaptor_Surface(face).GetType() != GeomAbs_Plane:
        raise SketchError("a sketch goes on a flat face")
    n, o = tessellate.plane_normal(face)
    origin, x, _, z = plane_frame(n, float(n @ o))
    plane = Plane(origin=origin, x_dir=x, z_dir=z)
    plane._bs_face = items[0]  # its edges bound the sketch's regions too (a line across the face splits it)
    return plane


def _entity_edges(shape):
    """The edges of one sketch entity: a face contributes its boundary, a curve its edges."""
    return list(shape.edges())


class Sketch:
    """A plane and named entities in its local XY (see the module docstring). Used as a context manager, the
    body runs outside the part's builder (build123d objects there don't join the part), and each attribute
    assigned on the sketch is one entity: `sketch_1.rect_1 = Rectangle(...)`."""

    _OWN = ("plane", "name", "used", "entities", "shapes", "_regions", "_token", "_loops", "_face_local")

    def __init__(self, plane):
        from build123d import Plane
        if not isinstance(plane, Plane):
            raise SketchError(f"a sketch needs a Plane (or on_face(...)), not {type(plane).__name__}")
        self.plane = plane
        self.entities = {}    # name -> its edges (local XY)
        self.shapes = {}      # name -> the object as written
        self.name = None      # the feature name, set by the hook after the statement
        self.used = False     # regions() was called on it
        self._regions = None
        self._token = None
        self._loops = {}      # name -> its closed wires, or None for an open entity (cached)
        self._face_local = None

    def __setattr__(self, name, value):
        if name in Sketch._OWN:
            object.__setattr__(self, name, value)
            return
        if name.startswith("_"):
            raise SketchError(f"sketch entity names can't start with '_' ({name})")
        if name == FACE:
            raise SketchError(f"'{FACE}' names the sketch face's boundary in area(): pick another entity name")
        if not hasattr(value, "edges"):
            raise SketchError(f"sketch entity {name} is a {type(value).__name__}, not a build123d shape")
        edges = _entity_edges(value)
        if not edges:
            raise SketchError(f"sketch entity {name} has no curves")
        for e in edges:
            box = e.bounding_box()
            if abs(box.min.Z) > 1e-9 or abs(box.max.Z) > 1e-9:
                raise SketchError(f"sketch entity {name} leaves the sketch plane (z != 0)")
        self.entities[name] = edges
        self.shapes[name] = value
        self._loops.pop(name, None)
        try:
            value._bs_sketch, value._bs_entity = self, name  # groove(sketch_1.path_1) finds its sketch
        except AttributeError:
            pass
        self._regions = None

    def __getattr__(self, name):
        shapes = self.__dict__.get("shapes", {})
        if name in shapes:
            return shapes[name]
        raise AttributeError(f"the sketch has no entity '{name}'")

    def __enter__(self):
        from build123d import build_common
        self._token = build_common._build_scope.set(None)  # entities are plain objects, not part of the part
        return self

    def __exit__(self, *exc):
        from build123d import build_common
        build_common._build_scope.reset(self._token)
        self._token = None
        return False

    # -- regions ---------------------------------------------------------------------------------------------------

    def regions_local(self):
        """The bounded areas of the sketch's curves, as faces in local XY (cached)."""
        if self._regions is None:
            edges = [e for edges in self.entities.values() for e in edges]
            face = self.face_local()
            if face is not None and edges:
                edges += list(face.edges())
            self._regions = _split(edges)
        return self._regions

    def region_index(self, uv, warn=None, what="the region"):
        """Index of the region containing local point `uv` (mm), or None."""
        from build123d import Vertex
        point = Vertex(float(uv[0]), float(uv[1]), 0.0)
        for i, face in enumerate(self.regions_local()):
            if face.is_inside((float(uv[0]), float(uv[1]), 0.0), ON_EDGE_MM / 10):
                if warn is not None:
                    gap = min(e.distance_to(point) for e in face.edges())
                    if gap < ON_EDGE_MM:
                        warn(f"{what}: the point {_uv(uv)} is on a boundary of the sketch {self.name}; "
                             f"check that the right area is used")
                return i
        return None

    def face_local(self):
        """The sketch face in local XY, or None for a sketch on a plane (cached)."""
        face = getattr(self.plane, "_bs_face", None)
        if face is not None and self._face_local is None:
            self._face_local = self.plane.to_local_coords(face)
        return self._face_local

    def bounds_of(self, region):
        """What bounds the local region `region`: {entity name: set of sides}. Closed entities (and FACE, the
        sketch face's boundary) have the region "inside" or "outside" them; open curves have it on their "left"
        or "right" along their own direction (a self-crossing path can have both)."""
        from build123d import Vector
        inside = Vector(*_inside_point(region), 0.0)
        out = {}
        for e in region.edges():
            name = self.entity_of(e)
            if name is None:
                if self.face_local() is None:
                    continue
                name = FACE
            if name == FACE or self._closed(name) is not None:
                if name not in out:
                    out[name] = {"inside" if self._contains(name, inside) else "outside"}
                continue
            side = self._side(name, e, region)
            if side is not None:
                out.setdefault(name, set()).add(side)
        return out

    def _closed(self, name):
        """The closed wires of entity `name`, or None if it is an open curve (FACE: None)."""
        if name == FACE:
            return None
        if name not in self._loops:
            from build123d import Face, Wire
            loops = None
            try:
                wires = Wire.combine(self.entities[name])
                if wires and all(w.is_closed for w in wires):
                    loops = [Face(w) for w in wires]
            except Exception:  # a self-crossing closed path: its sides are left/right
                loops = None
            self._loops[name] = loops
        return self._loops[name]

    def _contains(self, name, point):
        if name == FACE:
            return self.face_local().is_inside(point)
        return sum(1 for f in self._loops[name] if f.is_inside(point)) % 2 == 1

    def _side(self, name, edge, region):
        """"left" or "right": the side of open entity `name` (along its direction) where `region` lies next to its
        boundary edge `edge`; None if neither side tells (a region thinner than the probe)."""
        from build123d import Vector
        m = edge.position_at(0.5)
        nearest = min(self.entities[name], key=lambda e: e.distance_to(m))
        t = nearest.tangent_at(nearest.param_at_point(m))
        step = min(1e-3, edge.length / 20)
        normal = Vector(-t.Y, t.X, 0.0)
        left, right = region.is_inside(m + normal * step), region.is_inside(m - normal * step)
        if left == right:
            return None
        return "left" if left else "right"

    def entity_of(self, edge_local):
        """The name of the entity a (split) region edge comes from, or None."""
        from build123d import Vertex
        mid = Vertex(*edge_local.position_at(0.5))
        best, name = ON_FACE_MM, None
        for key, edges in self.entities.items():
            for e in edges:
                d = e.distance_to(mid)
                if d < best:
                    best, name = d, key
        return name

    def placed(self, shape):
        return self.plane.location * shape

    def axis(self, name):
        """The axis along the straight entity `name` (a Line), in the part's frame: for revolve()."""
        from build123d import Axis, GeomType
        edges = self.entities.get(name)
        if not edges:
            raise SketchError(f"the sketch {self.name} has no entity '{name}'")
        if len(edges) != 1 or edges[0].geom_type != GeomType.LINE:
            raise SketchError(f"sketch entity {name} is not a straight line: it can't be an axis")
        edge = self.placed(edges[0])
        start, end = edge.position_at(0), edge.position_at(1)
        return Axis(start, end - start)

    # -- display ---------------------------------------------------------------------------------------------------

    def display(self):
        """What Blender draws and picks: the plane (part frame, mm), each entity as polylines and each region as
        loops, in plane coordinates (mm), with a point inside each region (its seed when it is clicked)."""
        o, x, z = self.plane.origin, self.plane.x_dir, self.plane.z_dir
        y = z.cross(x)
        curves = {name: [_polyline(e) for e in edges] for name, edges in self.entities.items()}
        regions = []
        for face in self.regions_local():
            loops = [_polyline(w, closed=True) for w in [face.outer_wire(), *face.inner_wires()]]
            bounds = {name: sorted(sides) for name, sides in sorted(self.bounds_of(face).items())}
            regions.append({"loops": loops, "area": face.area, "inside": _inside_point(face), "bounds": bounds})
        return {"name": self.name, "used": self.used, "plane": [list(_vec(v)) for v in (o, x, y, z)],
                "curves": curves, "regions": regions, "points": _snap_points(self.entities)}


def _snap_points(entities):
    """Points a click snaps to, in plane coordinates: every curve's ends and every arc's or circle's centre."""
    from build123d import GeomType
    out = []
    for edges in entities.values():
        for e in edges:
            points = [e.position_at(0), e.position_at(1)]
            if e.geom_type == GeomType.CIRCLE:
                points.append(e.arc_center)
            for p in points:
                q = [round(p.X, 9) + 0.0, round(p.Y, 9) + 0.0]  # 5.000000000000001 -> 5.0
                if all(abs(q[0] - r[0]) + abs(q[1] - r[1]) > 1e-9 for r in out):
                    out.append(q)
    return out


def _uv(uv):
    return "(" + ", ".join(repr(round(float(c), 6) + 0.0) for c in uv) + ")"


def _split(edges):
    """The faces bounded by `edges` (local XY): General Fuse of a big face by all the edges, keeping the pieces
    that don't reach the big face's border, without the dangling edges left inside them."""
    from build123d import Compound, Face, ShapeList
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from OCP.collections import List_TopoDS_Shape
    if not edges:
        return []
    boxes = [e.bounding_box() for e in edges]
    lo = min(min(b.min.X, b.min.Y) for b in boxes)
    hi = max(max(b.max.X, b.max.Y) for b in boxes)
    size = 4 * max(hi - lo, 1.0)
    centre = ((lo + hi) / 2,) * 2
    from build123d import Location
    big = Location((centre[0], centre[1], 0)) * Face.make_rect(size, size)
    args, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
    args.Append(big.wrapped)
    for e in edges:
        tools.Append(e.wrapped)
    splitter = BRepAlgoAPI_Splitter()
    splitter.SetArguments(args)
    splitter.SetTools(tools)
    splitter.SetFuzzyValue(FUZZY_MM)
    splitter.Build()
    if not splitter.IsDone():
        raise SketchError("the sketch's curves could not be split into areas")
    limit = size / 2 * 0.999
    out = []
    for face in Compound(splitter.Shape()).faces():
        box = face.bounding_box()
        if max(abs(box.min.X - centre[0]), abs(box.max.X - centre[0]),
               abs(box.min.Y - centre[1]), abs(box.max.Y - centre[1])) >= limit:
            continue  # the outside
        inner = [w for w in face.inner_wires() if w.edges() and w.is_closed]
        out.append(Face(face.outer_wire(), inner))
    # biggest first: a stable order for display (seeds, not indices, name regions in scripts)
    return ShapeList(sorted(out, key=lambda f: -f.area))


def _polyline(curve, closed=False):
    """Points (u, v) along an edge or wire in local XY: every edge's start (a wire's corners stay exact; sampling
    the whole wire by length cut them off), straight edges as one segment, curved ones every CURVE_DEG.
    A closed polyline doesn't repeat its first point."""
    from build123d import GeomType
    edges = curve.edges()  # a wire's edges in order, each oriented along the wire
    pts = []
    for e in edges:
        n = 1
        if e.geom_type != GeomType.LINE:
            try:
                turn = e.length / e.radius
            except Exception:
                turn = math.pi
            n = max(4, min(MAX_SEGMENTS, math.ceil(math.degrees(turn) / CURVE_DEG)))
        pts += [e.position_at(i / n) for i in range(n)]
    if not closed:
        pts.append(edges[-1].position_at(1))
    return [[p.X + 0.0, p.Y + 0.0] for p in pts]


def _inside_point(face):
    """A point (u, v) inside a local face: its centre if inside, else a point next to its biggest edge's middle."""
    c = face.center()
    if face.is_inside(c):
        return [c.X + 0.0, c.Y + 0.0]
    from build123d import Vector
    for e in sorted(face.edges(), key=lambda e: -e.length):
        p, t = e.position_at(0.5), e.tangent_at(0.5)
        for side in (1, -1):
            q = p + Vector(-t.Y, t.X, 0) * (side * min(0.01, e.length / 10))
            if face.is_inside(q):
                return [q.X + 0.0, q.Y + 0.0]
    return [c.X + 0.0, c.Y + 0.0]


# -- roles of the faces an extrude or revolve of regions brings in ----------------------------------------------------

BORDER = "border"  # the role of a side face swept by an edge of the face a sketch lies on


def _side_roles(solid, sketch, region_faces, roles, axis=None):
    """Name each face of `solid` swept by a region edge after the sketch entity it comes from (BORDER: an edge of
    the sketch's face). Edges on a revolve's `axis` sweep nothing (their midpoint lies on the end cap too)."""
    from build123d import Vertex
    points = []
    for face in region_faces:
        for e in face.edges():
            name = sketch.entity_of(e)
            if name is None and sketch.face_local() is not None:
                name = BORDER
            placed = sketch.placed(e)
            if axis is not None and all(_off_axis(placed.position_at(t), axis) < ON_FACE_MM for t in (0, 0.5, 1)):
                continue
            if name is not None:
                points.append((Vertex(*placed.position_at(0.5)), name))
    for f in solid.faces():
        if f.wrapped in roles:
            continue
        for p, name in points:
            if f.distance_to(p) < ON_FACE_MM:
                roles[f.wrapped] = name
                break


def _crosses_axis(face, axis, normal):
    """Does the (placed) area lie on both sides of `axis`, in its plane of normal `normal`? An axis out of the
    plane: no answer (False)."""
    if abs(axis.direction.dot(normal)) > 1e-9:
        return False
    side = axis.direction.cross(normal)
    if abs((face.center() - axis.position).dot(normal)) > ON_FACE_MM:
        return False
    signs = set()
    for e in face.edges():
        for i in range(17):
            d = (e.position_at(i / 16) - axis.position).dot(side)
            if abs(d) > ON_FACE_MM:
                signs.add(d > 0)
    return len(signs) > 1


def _off_axis(point, axis):
    d = point - axis.position
    return (d - axis.direction * d.dot(axis.direction)).length


def _cap_roles(solid, sketch, direction, roles):
    """Planar faces parallel to the sketch plane: "start" on the sketch plane or behind it, else "end"."""
    from build123d import GeomType
    n = sketch.plane.z_dir
    o = sketch.plane.origin
    sign = 1.0 if n.dot(direction) >= 0 else -1.0
    for f in solid.faces():
        if f.geom_type != GeomType.PLANE:
            continue
        normal = f.normal_at()
        if abs(abs(normal.dot(n)) - 1.0) > 1e-9:
            continue
        offset = (f.center() - o).dot(n) * sign
        roles[f.wrapped] = "start" if offset <= ON_FACE_MM else "end"


class _Roles:
    """Faces (by TShape and location, like OCCT's shape maps) -> role."""

    def __init__(self):
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
        self._map, self._roles = ShapeMap(), []

    def __contains__(self, face):
        return self._map.Contains(face)

    def __setitem__(self, face, role):
        i = self._map.FindIndex(face)
        if i > 0:
            self._roles[i - 1] = role
        else:
            self._map.Add(face)
            self._roles.append(role)

    def get(self, face):
        i = self._map.FindIndex(face)
        return self._roles[i - 1] if i > 0 else None


# -- paths: polylines with tangent arcs, drawn in the sketch plane ---------------------------------------------------

class ArcTo:
    """A path segment: a circular arc tangent to the path so far, ending at `end` (plane coordinates, mm)."""

    def __init__(self, end):
        self.end = (float(end[0]), float(end[1]))


def arc_to(end):
    return ArcTo(end)


CLOSE_MM = 1e-6  # a closed path's last point this near its start ends there
STRAIGHT = 1e-6  # sin of the angle between an arc's tangent and its chord below which it is a line (radius > 5e5 x chord)
KINK = 1e-6  # radians: a line leaving the path's tangent by less goes along it (its end moves by up to 1e-6 x its length;
# more moved a point before a 0.001 mm segment enough to turn the arc after it: bug sweep rerun, 2026-10-04)


def path(start, *segments, closed=False):
    """A wire in the sketch plane from `start` through `segments`: points (straight lines to them) and
    arc_to(point) (arcs tangent to the previous segment); `closed` adds a line back to the start (or ends there when
    the last segment already does)."""
    from build123d import Edge, Vector, Wire
    here = Vector(float(start[0]), float(start[1]), 0.0)
    first = here
    ends = [Vector(*seg.end, 0.0) if isinstance(seg, ArcTo) else Vector(float(seg[0]), float(seg[1]), 0.0)
            for seg in segments]
    if closed and ends and (ends[-1] - first).length <= CLOSE_MM:
        ends[-1] = first  # 6-decimal points miss the start by up to 5e-7 mm: a gap would leave the wire open
    edges = []
    for seg, end in zip(segments, ends):
        if (end - here).length < 1e-9:
            continue  # a double click, or an arc to where the path already is
        if isinstance(seg, ArcTo):
            if not edges:
                raise SketchError("a path can't start with an arc: its tangent comes from the segment before it")
            tangent = edges[-1].tangent_at(1)
            chord = end - here
            if abs(tangent.cross(chord).Z) <= STRAIGHT * chord.length:  # the arc is a line (as the preview draws it)
                if chord.dot(tangent) > 0:  # exactly along its tangent: a hair off it is a corner OCCT can't sweep
                    end = here + tangent * chord.dot(tangent)
                edge = Edge.make_line(here, end)  # straight back: a 180° turn, which a groove refuses clearly
            else:
                edge = Edge.make_tangent_arc(here, tangent, end)
        else:
            if edges:  # leaving the path's tangent by a rounding-level kink: along the tangent (a kink that small
                tangent = edges[-1].tangent_at(1)  # makes OCCT's sweeps and booleans fail; bug sweep 2026-10-04)
                along = (end - here).dot(tangent)
                if along > 0 and abs(tangent.cross(end - here).Z) <= KINK * along:
                    end = here + tangent * along
                    if (ends[-1] - end).length <= CLOSE_MM:
                        ends[-1] = end  # a closing point moved with it
            edge = Edge.make_line(here, end)
        edges.append(edge)
        here = end
    if closed and (here - first).length > CLOSE_MM:
        edges.append(Edge.make_line(here, first))
    if not edges:
        raise SketchError("a path needs at least two different points")
    return Wire(edges)


PROFILES = ("rect", "round", "v", "circle")
CORNERS = ("mitre", "round")
OVERSHOOT = 0.5  # mm a groove's profile reaches above the face it cuts (no coplanar faces in the boolean)


def _profile_points(profile, width, depth, over):
    """The groove/rib profile as (lateral, up) points: `up` is along the sketch's normal, 0 on the plane; the solid
    reaches `depth` below the plane (and `over` above it). For a rib the caller flips `up`."""
    w = width / 2
    if profile == "rect":
        return [(-w, -depth), (w, -depth), (w, over), (-w, over)]
    if profile == "v":
        k = w / depth  # the V's half width per mm of depth, from the apex up to the plane
        return [(0.0, -depth), (w + k * over, over), (-w - k * over, over)]
    raise SketchError(f"unknown profile '{profile}' (one of {', '.join(PROFILES)})")


def _profile_wire(profile, width, depth, over, place):
    """The profile as a wire placed by `place` (lateral, up) -> 3D point."""
    from build123d import Edge, Wire
    if profile == "circle":
        return Wire([Edge.make_circle(width / 2, place.plane)])
    if profile == "round":
        r = width / 2
        if depth < r:
            raise SketchError(f"a round groove's depth ({depth:g} mm) must be at least half its width ({r:g} mm)")
        arc = Edge.make_three_point_arc(place((-r, -depth + r)), place((0.0, -depth)), place((r, -depth + r)))
        top = Edge.make_line(place((r, over)), place((-r, over)))
        if over == depth - r:  # a half disc: no straight sides
            return Wire([arc, top])
        return Wire([Edge.make_line(place((-r, over)), place((-r, -depth + r))), arc,
                     Edge.make_line(place((r, -depth + r)), place((r, over))), top])
    return Wire.make_polygon([place(p) for p in _profile_points(profile, width, depth, over)], close=True)


class _Place:
    """(lateral, up) in the plane normal to a path at its start -> 3D points."""

    def __init__(self, origin, lateral, up, tangent):
        from build123d import Plane
        self.origin, self.lateral, self.up = origin, lateral, up
        self.plane = Plane(origin=origin, x_dir=lateral, z_dir=tangent)

    def __call__(self, p):
        return self.origin + self.lateral * p[0] + self.up * p[1]


def _sweep(wire, profile_at, normal, corners):
    """The solid swept by the profile along `wire`, kept square to the plane of normal `normal`, sharp corners
    mitred or rounded. `profile_at(point, tangent)` is the profile wire placed square to the path there.
    OCCT sweeps a path without sharp corners in one go; at a sharp corner its transitions aren't reliable (a mitre
    right after an arc raises StdFail_NotDone, or gives a solid overlapping itself that BRepCheck accepts: the
    maintainer's GUI test, 2026-10-04), so a path with sharp corners is swept run by run (_sweep_by_runs)."""
    runs, sharp = _runs(wire)
    if not sharp:
        return _pipe(wire, profile_at(wire.position_at(0), wire.tangent_at(0)), normal, corners)
    return _sweep_by_runs(runs, sharp, profile_at, normal, corners)


def _pipe(wire, profile_wire, normal, corners):
    """OCCT's sweep of `profile_wire` along the whole `wire` (binormal mode: build123d's sweep(normal=) fixes the
    trihedron instead), sharp corners mitred or rounded (build123d's default Transformed transition gives invalid
    solids there)."""
    from build123d import Solid
    from OCP.BRepBuilderAPI import BRepBuilderAPI_TransitionMode as Mode
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
    from OCP.gp import gp_Dir
    maker = BRepOffsetAPI_MakePipeShell(wire.wrapped)
    maker.SetMode(gp_Dir(normal.X, normal.Y, normal.Z))
    maker.SetTransitionMode(Mode.BRepBuilderAPI_RoundCorner if corners == "round" else Mode.BRepBuilderAPI_RightCorner)
    maker.Add(profile_wire.wrapped, False, False)
    maker.Build()
    if not maker.IsDone():
        raise SketchError("the profile can't follow this path (a corner or an arc too tight for its width?)")
    maker.MakeSolid()
    if maker.Shape().IsNull():
        raise SketchError("the profile can't follow this path (a corner or an arc too tight for its width?)")
    return _valid_sweep(Solid(maker.Shape()))


def _valid_sweep(solid):
    from OCP.BRepCheck import BRepCheck_Analyzer
    if not BRepCheck_Analyzer(solid.wrapped).IsValid() or solid.volume <= 0:
        raise SketchError("the profile swept along this path isn't a valid solid (does the path cross itself, or "
                          "turn tighter than the profile is wide?)")
    return solid


SHARP = 1e-6  # radians between two edges' tangents at their common point: more is a sharp corner
MITRE_MAX_TURN = math.radians(170)  # a mitre's spike grows as 1 / cos(turn / 2): sharper turns need round corners


SMALL_TURN = math.radians(5)  # a mitre OCCT can't build at a corner turning less is built round instead


def _round_corner(profile_at, point, before, after, normal, turn, reach):
    """The round corner piece: the profile's half on the outside of the turn (inside, the runs overlap) turned
    about the corner point's normal."""
    from build123d import Axis, Face, Plane, Solid, Wire
    sign = 1.0 if before.cross(after).dot(normal) > 0 else -1.0
    outside = before.cross(normal) * sign  # a left turn's outside is on the path's right
    half = Plane(origin=point, x_dir=outside, z_dir=before)
    face = Face(profile_at(point, before)).intersect(
        Face(Wire.make_polygon([half.from_local_coords(p) for p in
                                ((0, -reach), (reach, -reach), (reach, reach), (0, reach))], close=True)))
    face = face.faces()[0] if not isinstance(face, Face) else face
    return _valid_sweep(Solid.revolve(face, sign * math.degrees(turn), Axis(point, normal)))


def _runs(wire):
    """The wire's runs (wires of edges joined tangentially) and its sharp corners (point, tangent before, tangent
    after); a closed wire whose ends join tangentially makes its last run go on into its first."""
    from build123d import Wire
    edges = wire.edges()
    runs, sharp = [[edges[0]]], []
    for e in edges[1:]:
        before, after = runs[-1][-1].tangent_at(1), e.tangent_at(0)
        if math.radians(before.get_angle(after)) > SHARP:
            runs.append([e])
            sharp.append((e.position_at(0), before, after))
        else:
            runs[-1].append(e)
    if wire.is_closed:
        before, after = edges[-1].tangent_at(1), edges[0].tangent_at(0)
        if math.radians(before.get_angle(after)) > SHARP:
            sharp.append((edges[0].position_at(0), before, after))
        elif len(runs) > 1:
            runs[0] = runs.pop() + runs[0]
    return [Wire(run) for run in runs], sharp


def _sweep_by_runs(runs, sharp, profile_at, normal, corners):
    """The sweep as the union of its runs (swept by OCCT, no sharp corner inside) and of a piece at each sharp
    corner: a mitre is where the two runs' straight extensions overlap (exact for profiles symmetric about the
    path, as every groove profile is), a round corner the profile turned about the corner point's normal."""
    from build123d import Face, Solid
    pieces = [_pipe(w, profile_at(w.position_at(0), w.tangent_at(0)), normal, corners) for w in runs]
    box = profile_at(runs[0].position_at(0), runs[0].tangent_at(0)).bounding_box()
    reach = (box.max - box.min).length  # more than the profile reaches from the path
    for point, before, after in sharp:
        turn = math.radians(before.get_angle(after))
        if corners == "round":
            pieces.append(_round_corner(profile_at, point, before, after, normal, turn, reach))
            continue
        if turn > MITRE_MAX_TURN:
            raise SketchError(f"a corner of the path turns {math.degrees(turn):.0f}°: too sharp to mitre, use round "
                              "corners")
        length = 2 * reach / math.cos(turn / 2) + 1.0
        ahead = Solid.extrude(Face(profile_at(point, before)), before * length)
        behind = Solid.extrude(Face(profile_at(point, after)), after * -length)
        try:
            common = ahead.intersect(behind)
            solids = common.solids() if common is not None else []
        except ValueError:  # "Null TopoDS_Shape object"
            solids = []
        if len(solids) == 1:
            pieces.append(_valid_sweep(solids[0]))
        elif turn < SMALL_TURN:  # nearly coaxial pipes: OCCT finds no common part; the round piece differs by ~turn^3
            pieces.append(_round_corner(profile_at, point, before, after, normal, turn, reach))
        else:
            raise SketchError("the profile can't be mitred at a corner of this path: try round corners")
    solid = pieces[0].fuse(*pieces[1:]).clean() if len(pieces) > 1 else pieces[0]
    solids = solid.solids()
    if len(solids) != 1:
        raise SketchError("the profile can't follow this path (a corner or an arc too tight for its width?)")
    return _valid_sweep(solids[0])


# -- the script helpers -------------------------------------------------------------------------------------------

class Area:
    """A region seed as the tools write it: `area((u, v), inside="rect_1", left=("line_1", "path_1"), ...)` — the
    point and, for each curve bounding the picked area, the area's side of it (module docstring)."""

    def __init__(self, uv, inside=(), outside=(), left=(), right=()):
        self.uv = uv
        self.bounds = {}
        for side, names in zip(SIDES, (inside, outside, left, right)):
            for name in (names,) if isinstance(names, str) else names:
                self.bounds.setdefault(name, set()).add(side)

    def __repr__(self):
        return f"area({_uv(self.uv)}{area_arguments(self.bounds)})"


def area_arguments(bounds):
    """The keyword part of an area() call for `bounds` ({name: sides}): ', inside="rect_1", left=("a", "b")'."""
    out = ""
    for side in SIDES:
        names = sorted(name for name, sides in bounds.items() if side in sides)
        if names:
            out += f", {side}=" + (f'"{names[0]}"' if len(names) == 1 else
                                   "(" + ", ".join(f'"{n}"' for n in names) + ")")
    return out


def _describe(bounds):
    words = {"inside": "inside {}", "outside": "outside {}", "left": "left of {}", "right": "right of {}"}
    parts = [words[side].format("the face" if name == FACE else name)
             for name in sorted(bounds) for side in sorted(bounds[name])]
    return ", ".join(parts) if parts else "bounded by nothing named"


def _check_area(sk, seed, found, warn):
    """ADR 0009 for regions: the area under the seed point must be the one the seed's curves describe."""
    expected = seed.bounds
    if not expected or found == expected:
        return
    common = expected.keys() & found.keys()
    flipped = [name for name in common if not expected[name] & found[name]]
    where = f"the area of {sk.name} at {_uv(seed.uv)}"
    if flipped or not common:
        from provenance import BrokenReference
        raise BrokenReference(f"{where} is now {_describe(found)}, but it was picked {_describe(expected)}: the "
                              f"sketch changed under it — pick the area again")
    warn(f"{where} is now {_describe(found)}; it was picked {_describe(expected)}: check that the right area "
         f"is used")


def helpers(tracker):
    """sketch(), on_face(), regions() and the extrude()/revolve() that understand regions, for a part script
    run with `tracker` (provenance.Tracker: warnings, roles of brought-in faces, the sketches to display)."""
    import build123d as bd

    def sketch(plane):
        """A sketch feature on `plane` (on_face(...) or a Plane); its entities are assigned in its with block."""
        sk = Sketch(plane)
        tracker.sketches.append(sk)
        return sk

    def regions(sk, *points):
        """The regions of sketch `sk` containing the seed points (u, v) in its plane (mm), placed on the plane;
        no point: every region."""
        if not isinstance(sk, Sketch):
            raise SketchError(f"regions() takes a sketch, not {type(sk).__name__}")
        local = sk.regions_local()
        if not local:
            raise SketchError(f"the sketch {sk.name} has no closed area")
        picked = []
        if not points:
            picked = list(range(len(local)))
        for seed in points:
            uv = seed.uv if isinstance(seed, Area) else seed
            i = sk.region_index(uv, tracker.warn, f"the area of {sk.name} at {_uv(uv)}")
            if i is None:
                from provenance import BrokenReference
                raise BrokenReference(f"no closed area of the sketch {sk.name} contains the point {_uv(uv)}")
            if isinstance(seed, Area):
                _check_area(sk, seed, sk.bounds_of(local[i]), tracker.warn)
            if i not in picked:
                picked.append(i)
        sk.used = True
        faces = bd.ShapeList(sk.placed(local[i]) for i in picked)
        faces._bs_sketch = sk
        faces._bs_local = [local[i] for i in picked]
        return faces

    def _add(solids, clean, mode):
        context = bd.BuildPart._get_context("extrude")
        if context is not None:
            before = context.part.volume if context.part is not None else 0.0
            pieces = len(context.part.solids()) if context.part is not None else 0
            try:
                context._add_to_context(*solids, clean=clean, mode=mode)
            except AssertionError:  # build123d's intersection with nothing in common (bug sweep B12)
                if mode != bd.Mode.INTERSECT:
                    raise
                raise SketchError("this intersection has nothing in common with the part") from None
            if before > 0 and (context.part is None or not context.part.solids()):  # bug sweep R16
                raise SketchError("this feature removes the whole part" if mode == bd.Mode.SUBTRACT else
                                  "this intersection has nothing in common with the part")
            _check_boolean(before, context.part.volume if context.part is not None else 0.0,
                           sum(s.volume for s in solids), mode, tracker)
            if mode == bd.Mode.ADD and pieces and len(context.part.solids()) > pieces:  # bug sweep R13
                tracker.warn(f"this feature doesn't merge with the part (it lies apart, or touches it only along an "
                             f"edge or at a point): the part is now {len(context.part.solids())} separate solids")
        return bd.Part(bd.Compound(solids).wrapped)

    def extrude(to_extrude=None, amount=None, dir=None, until=None, target=None, both=False, taper=0.0,
                clean=True, mode=bd.Mode.ADD):
        sk = getattr(to_extrude, "_bs_sketch", None)
        if sk is None:
            return bd.extrude(to_extrude, amount=amount, dir=dir, until=until, target=target, both=both,
                              taper=taper, clean=clean, mode=mode)
        n = sk.plane.z_dir if dir is None else bd.Vector(dir).normalized()
        if until is not None:
            if taper:
                raise SketchError("a taper angle can't be combined with up to next/last yet")
            if both:
                raise SketchError("a symmetric extrude can't go up to next/last")
            if target is None:
                context = bd.BuildPart._get_context("extrude")
                target = context.part_local if context is not None else None
            if target is None:
                raise SketchError("up to next/last needs a solid to reach: there is none before this line")
            if until not in (bd.Until.NEXT, bd.Until.LAST):
                raise SketchError("an extrude goes up to Until.NEXT or Until.LAST")
            solids = [s for f in to_extrude for s in _until(f, target, n, until, mode)]
            direction = n
        else:
            if amount is None or amount == 0:
                raise SketchError("the extrude has no distance")
            if abs(amount) < MIN_MM:  # OCCT's prism fails below its confusion tolerance (bug sweep R16)
                raise SketchError(f"the extrude distance ({amount:g} mm) is too small: at least {MIN_MM:g} mm")
            direction = n * amount
            faces = list(to_extrude)
            if taper and len(faces) > 1:  # drafted one by one, neighbours leave a V-groove between them
                faces = _merged(faces)
            parts = [(f, direction) for f in faces]
            if both:
                parts += [(f, -direction) for f in faces]
            solids = [_prism(f, d, sk, taper) for f, d in parts]
            if len(solids) > 1:
                fused = solids.pop().fuse(*solids)
                solids = fused if isinstance(fused, list) else list(fused.solids())
        if clean:
            solids = [s.clean() for s in solids]
        roles = tracker.roles
        for s in solids:
            _cap_roles(s, sk, direction, roles)
            _side_roles(s, sk, to_extrude._bs_local, roles)
            for f in s.faces():  # up to next/last: the faces on the target's surfaces
                if f.wrapped not in roles:
                    roles[f.wrapped] = "end"
        return _add(solids, clean, mode)

    def revolve(profiles=None, axis=bd.Axis.Z, revolution_arc=360.0, clean=True, mode=bd.Mode.ADD):
        sk = getattr(profiles, "_bs_sketch", None)
        if sk is None:
            return bd.revolve(profiles, axis=axis, revolution_arc=revolution_arc, clean=clean, mode=mode)
        if abs(revolution_arc) < 1e-9:  # it made a full turn (bug sweep R14)
            raise SketchError("the revolve has no angle")
        for f in profiles:
            if _crosses_axis(f, axis, sk.plane.z_dir):  # OCCT: raw StdFail_NotDone (bug sweep R6)
                raise SketchError("the area crosses the axis it turns about: the revolve would pass through itself "
                                  "(split the area along the axis)")
        sign = 1 if revolution_arc >= 0 else -1
        angle = revolution_arc % (sign * 360.0)
        angle = sign * 360.0 if angle == 0 else angle
        solids = [bd.Solid.revolve(f, angle, axis) for f in profiles]
        if clean:
            solids = [s.clean() for s in solids]
        roles = tracker.roles
        for s, local in zip(solids, profiles._bs_local):
            inside = bd.Vertex(*sk.placed(bd.Vertex(*_inside_point(local), 0)).center())
            for f in s.faces():
                if f.geom_type == bd.GeomType.PLANE and f.distance_to(inside) < ON_FACE_MM:
                    roles[f.wrapped] = "start"
            _side_roles(s, sk, [local], roles, axis)
            for f in s.faces():
                if f.wrapped not in roles:
                    roles[f.wrapped] = "end"
        return _add(solids, clean, mode)

    def groove(curve, width, depth, profile="rect", corners="mitre", mode=bd.Mode.SUBTRACT):
        """A profile swept along a sketch path (sketch_1.path_1): a groove cut `depth` mm into the part (mode
        SUBTRACT), or a rib standing `depth` mm out of the sketch plane (mode ADD). Profiles: "rect" (width x
        depth), "round" (U: its bottom a half circle of the width), "v" (width at the plane, apex at depth),
        "circle" (a pipe of diameter `width` centred on the path; depth unused). Corners "mitre" or "round"."""
        sk, name = _owner(curve)
        if profile not in PROFILES:
            raise SketchError(f"unknown profile '{profile}' (one of {', '.join(PROFILES)})")
        if corners not in CORNERS:
            raise SketchError(f"unknown corners '{corners}' (one of {', '.join(CORNERS)})")
        if width <= 0 or (profile != "circle" and depth <= 0):
            raise SketchError("a groove needs a width and a depth")
        edges = sk.entities[name]
        if _crosses_itself(edges):  # BRepCheck accepts the swept solid overlapping itself (bug sweep G4)
            raise SketchError(f"the path {name} crosses or touches itself: a groove along it would overlap itself")
        wire = sk.placed(bd.Wire(edges) if len(edges) > 1 else bd.Wire([edges[0]]))
        n = sk.plane.z_dir
        cut = mode != bd.Mode.ADD
        up = n if cut else -n  # a rib is a groove turned over: its "depth" goes out of the plane
        on_part = getattr(sk.plane, "_bs_face", None) is not None
        over = OVERSHOOT if (cut or on_part) else 0.0  # a rib on a face sinks a little into it to fuse

        def profile_at(point, tangent):
            return _profile_wire(profile, width, depth, over, _Place(point, n.cross(tangent).normalized(), up, tangent))
        solid = _sweep(wire, profile_at, n, corners)
        if not cut and over and profile != "circle":  # a pipe is centred on its path: its lower half is its own
            solid = _trim_sunk(solid, sk.plane, n, over)
        roles = tracker.roles
        for f in solid.faces():
            roles[f.wrapped] = "wall"
        return _add([solid], True, mode)

    return {"sketch": sketch, "on_face": on_face, "regions": regions, "area": Area, "extrude": extrude, "revolve": revolve,
            "path": path, "arc_to": arc_to, "groove": groove}


def _crosses_itself(edges):
    """Does a sketch curve cross or touch itself? General Fuse of its edges splits an edge where another meets
    it, and a touch at a vertex gives that vertex more than two edges."""
    from OCP.BOPAlgo import BOPAlgo_Builder
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as Ancestors
    if len(edges) < 2 and not edges[0].is_closed:
        return False
    builder = BOPAlgo_Builder()
    for e in edges:
        builder.AddArgument(e.wrapped)
    builder.SetFuzzyValue(FUZZY_MM)
    builder.Perform()
    if builder.HasErrors():
        return False  # let the sweep report what it can't do
    ancestors = Ancestors()
    TopExp.MapShapesAndAncestors_s(builder.Shape(), TopAbs_VERTEX, TopAbs_EDGE, ancestors)
    found = sum(ancestors.FindFromIndex(i).Size() for i in range(1, ancestors.Extent() + 1))
    if found != 2 * len(edges):  # each edge has two ends (a closed edge: one vertex listed twice)
        return True
    return any(ancestors.FindFromIndex(i).Size() > 2 for i in range(1, ancestors.Extent() + 1))


def _trim_sunk(rib, plane, n, over):
    """A rib on a face sinks `over` mm below the sketch plane to fuse; where its path runs past the part, that
    sunk strip would hang in the air below the plane: it is kept only inside the part (bug sweep G7)."""
    import build123d as bd
    context = bd.BuildPart._get_context("groove")
    part = context.part_local if context is not None else None
    if part is None:
        return rib
    frame = bd.Plane(origin=plane.origin, x_dir=plane.x_dir, z_dir=n)
    box = rib.bounding_box()
    size = 2 * box.diagonal + 1.0
    c = frame.to_local_coords(box.center())
    slab = frame.location * bd.Pos(c.X - size / 2, c.Y - size / 2, -2 * over) * bd.Solid.make_box(size, size, 2 * over)
    hanging = slab.cut(part)
    if not hanging.solids():
        return rib
    trimmed = rib.cut(hanging).solids()
    if len(trimmed) != 1:  # the sunk strip held the rib together: keep it whole rather than split it
        return rib
    return trimmed[0]


def _check_boolean(before, after, tool, mode, tracker):
    """A union never loses material and a cut never adds any (OCCT's booleans sometimes return a wrong solid, valid
    to BRepCheck: a rib fused on a rib that touches it tangentially came back alone, the part gone); one that
    changes nothing is a warning (a groove off the part, a join inside the material)."""
    import build123d as bd
    tol = 1e-6 * max(before, tool, 1.0)
    if mode == bd.Mode.ADD:
        wrong, changed = not before - tol <= after <= before + tool + tol, after > before + tol
    elif mode == bd.Mode.SUBTRACT:
        wrong, changed = not before - tool - tol <= after <= before + tol, after < before - tol
    else:
        wrong, changed = after > min(before, tool) + tol, True
    if wrong:
        raise SketchError(f"OCCT's boolean went wrong here (the part's volume went from {before:.6g} to {after:.6g} "
                          "mm³): change a size a little")
    if not changed and before > 0:
        tracker.warn("this feature changes nothing: it doesn't reach the part" if mode == bd.Mode.SUBTRACT
                     else "this feature changes nothing: it lies inside the part")


def _owner(curve):
    """(sketch, entity name) of a sketch entity given as `sketch_1.path_1`."""
    sk = getattr(curve, "_bs_sketch", None)
    if sk is None:
        raise SketchError("groove() takes a sketch path, e.g. sketch_1.path_1")
    return sk, curve._bs_entity


def _until(face, target, n, until, mode):
    """The extrusion of `face` along unit `n` up to the next or last surface of `target`, exact on those
    surfaces (build123d's extrude_until stops at the face the sketch lies on). What "next" means depends on the
    boolean, as in other CAD: a union grows through the empty space in front of the profile up to where material
    starts; a cut or an intersection takes the first stretch of material (from the profile if it starts on the
    part, else the first one ahead). "Last" is the whole way through: a union up to the farthest surface, a cut
    every stretch of material. An extrusion that finds nothing to stop at is an error, never a partial solid."""
    from build123d import Mode, Solid, Vector
    box = target.bounding_box()
    far = (box.max - box.min).length + (face.center() - box.center()).length + 1.0
    prism = Solid.extrude(face, Vector(n) * far)
    end_cap = face.moved(_translation(Vector(n) * far))
    touch = ON_FACE_MM * 10

    def pieces(shape):
        return [] if shape is None else list(shape.solids())

    if mode == Mode.ADD:
        gaps = pieces(prism - target)
        if until == _until_next():
            found = [g for g in gaps if g.distance_to(face) < touch]
            if not found:
                raise SketchError("the area starts inside the part: up to next adds nothing (try the other "
                                  "direction, or a cut)")
            if any(g.distance_to(end_cap) < touch for g in found):
                raise SketchError("up to next: nothing ahead of the area to stop at")
            return found
        beyond = [g for g in gaps if g.distance_to(end_cap) < touch]
        if len(beyond) == len(gaps):
            if not pieces(prism & target):
                raise SketchError("up to last: nothing ahead of the area to stop at")
            raise SketchError("up to last: the way from the area to the last face is all inside the part, it adds "
                              "nothing (try the other direction, or a cut)")  # bug sweep R15
        return pieces(prism - beyond) if beyond else [prism]
    material = sorted(pieces(prism & target), key=lambda m: m.distance_to(face))
    if not material:
        raise SketchError("the area's extrusion doesn't meet the part")
    return material[:1] if until == _until_next() else material


def _until_next():
    from build123d import Until
    return Until.NEXT


def _translation(v):
    from build123d import Location
    return Location(v)


def _merged(faces):
    """Adjacent coplanar faces merged into one (their shared edges dropped): what a taper drafts as one outline."""
    from build123d import Face
    fused = faces[0].fuse(*faces[1:]).clean()
    return [Face(f.wrapped) for f in fused.faces()]


def _prism(face, direction, sk, taper):
    """The straight extrusion of `face` along `direction`, its sides drafted by `taper` degrees (positive: the
    section shrinks away from the sketch plane) about the sketch plane."""
    from build123d import GeomType, Plane, Solid
    solid = Solid.extrude(face, direction)
    if not taper:
        return solid
    n = direction.normalized()
    sides = [f for f in solid.faces() if not (f.geom_type == GeomType.PLANE and abs(abs(f.normal_at().dot(n)) - 1) < 1e-9)]
    bad = [f.geom_type.name for f in sides if f.geom_type not in (GeomType.PLANE, GeomType.CYLINDER, GeomType.CONE)]
    if bad:
        raise SketchError(f"a taper needs lines and arcs: this area has {bad[0].lower()} sides")
    neutral = Plane(origin=sk.plane.origin, x_dir=sk.plane.x_dir, z_dir=n)
    inset = direction.length * math.tan(math.radians(taper))
    _check_taper_section(face, neutral, inset, taper, direction.length)
    try:
        drafted = solid.draft(sides, neutral, taper)
    except Exception as e:
        raise SketchError(f"OCCT could not draft the sides by {taper:g}° on this area: try a smaller angle") from None
    from OCP.BRepCheck import BRepCheck_Analyzer
    if not BRepCheck_Analyzer(drafted.wrapped).IsValid() or drafted.volume <= 0:  # used as is, a cut removed nothing
        raise SketchError(f"the taper of {taper:g}° gives an invalid solid on this area: try a smaller angle")
    return drafted


def _check_taper_section(face, plane, inset, taper, length):
    """Refuse a taper whose section surely closes before the extrude's end (OCCT's draft goes on through it: an
    hourglass): an area vanishes once the inset reaches half its smaller extent in the plane (no wider disc fits in
    it), a hole (growing the other way) likewise."""
    local = plane.to_local_coords(face)
    for wire in [local.outer_wire()] if inset > 0 else local.inner_wires():
        size = wire.bounding_box().size
        if abs(inset) >= min(size.X, size.Y) / 2:
            raise SketchError(f"the taper of {taper:g}° closes the area before the end of the {length:g} mm extrude: "
                              "use a smaller angle or distance")

