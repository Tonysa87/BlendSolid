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
  region is an error; a seed on a region's boundary a warning.
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
    return Plane(origin=origin, x_dir=x, z_dir=z)


def _entity_edges(shape):
    """The edges of one sketch entity: a face contributes its boundary, a curve its edges."""
    return list(shape.edges())


class Sketch:
    """A plane and named entities in its local XY (see the module docstring). Used as a context manager, the
    body runs outside the part's builder (build123d objects there don't join the part), and each attribute
    assigned on the sketch is one entity: `sketch_1.rect_1 = Rectangle(...)`."""

    _OWN = ("plane", "name", "used", "entities", "shapes", "_regions", "_token")

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

    def __setattr__(self, name, value):
        if name in Sketch._OWN:
            object.__setattr__(self, name, value)
            return
        if name.startswith("_"):
            raise SketchError(f"sketch entity names can't start with '_' ({name})")
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
            self._regions = _split([e for edges in self.entities.values() for e in edges])
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
            regions.append({"loops": loops, "area": face.area, "inside": _inside_point(face)})
        return {"name": self.name, "used": self.used,
                "plane": [list(_vec(v)) for v in (o, x, y, z)], "curves": curves, "regions": regions}


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
    """Points (u, v) along an edge or wire in local XY."""
    from build123d import GeomType
    edges = curve.edges() if hasattr(curve, "edges") else [curve]
    if all(e.geom_type == GeomType.LINE for e in edges) and not closed:
        pts = [curve.position_at(0)] + [e.position_at(1) for e in edges]
        return [[p.X + 0.0, p.Y + 0.0] for p in pts]
    turn = 0.0
    for e in edges:
        if e.geom_type != GeomType.LINE:
            try:
                turn += e.length / e.radius
            except Exception:
                turn += math.pi
    n = int(min(MAX_SEGMENTS, max(len(edges), math.degrees(turn) / CURVE_DEG + 4 * len(edges))))
    if closed:
        pts = [curve.position_at(i / n) for i in range(n)]
    else:
        pts = [curve.position_at(i / n) for i in range(n + 1)]
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

def _side_roles(solid, sketch, region_faces, roles):
    """Name each face of `solid` swept by a region edge after the sketch entity it comes from."""
    from build123d import Vertex
    points = []
    for face in region_faces:
        for e in face.edges():
            name = sketch.entity_of(e)
            if name is not None:
                points.append((Vertex(*sketch.placed(e).position_at(0.5)), name))
    for f in solid.faces():
        if f.wrapped in roles:
            continue
        for p, name in points:
            if f.distance_to(p) < ON_FACE_MM:
                roles[f.wrapped] = name
                break


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


# -- the script helpers -------------------------------------------------------------------------------------------

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
        for uv in points:
            i = sk.region_index(uv, tracker.warn, f"the area of {sk.name} at {_uv(uv)}")
            if i is None:
                from provenance import BrokenReference
                raise BrokenReference(f"no closed area of the sketch {sk.name} contains the point {_uv(uv)}")
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
            context._add_to_context(*solids, clean=clean, mode=mode)
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
            if amount is not None and amount < 0:
                n = -n
            if target is None:
                context = bd.BuildPart._get_context("extrude")
                target = context.part_local if context is not None else None
            if target is None:
                raise SketchError("up to next/last needs a solid to reach: there is none before this line")
            solids = [bd.Solid.extrude_until(f, target=target, direction=n, until=until) for f in to_extrude]
            direction = n
        else:
            if amount is None or amount == 0:
                raise SketchError("the extrude has no distance")
            direction = n * amount
            parts = [(f, direction) for f in to_extrude]
            if both:
                parts += [(f, -direction) for f in to_extrude]
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
        return _add(solids, clean, mode)

    def revolve(profiles=None, axis=bd.Axis.Z, revolution_arc=360.0, clean=True, mode=bd.Mode.ADD):
        sk = getattr(profiles, "_bs_sketch", None)
        if sk is None:
            return bd.revolve(profiles, axis=axis, revolution_arc=revolution_arc, clean=clean, mode=mode)
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
            _side_roles(s, sk, [local], roles)
            for f in s.faces():
                if f.wrapped not in roles:
                    roles[f.wrapped] = "end"
        return _add(solids, clean, mode)

    return {"sketch": sketch, "on_face": on_face, "regions": regions, "extrude": extrude, "revolve": revolve}


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
    try:
        return solid.draft(sides, neutral, taper)
    except Exception as e:
        raise SketchError(f"the taper of {taper:g}° failed ({type(e).__name__}): try a smaller angle") from None
