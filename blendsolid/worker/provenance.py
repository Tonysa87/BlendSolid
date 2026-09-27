"""Face and edge provenance of a part script, and the references scripts use to name faces and edges.

A canonical part script (`with BuildPart() as part:` whose statements carry `# feature: <name>` markers) is
compiled with a hook call after each feature statement (instrument()); the script text is not changed and
errors keep the user's line numbers. After each feature the hook relabels the part's faces from the record
build123d keeps of the operation (`ShapeHistory`, the OCCT BRepTools_History of the boolean/fillet, with the
inputs that were there before and the ones the operation brought in):

- a face untouched or modified from one that was there before keeps that face's label;
- a face untouched or modified from one the feature brought in is `(feature, role on the feature)`;
- a face generated from an edge that was there before (a fillet or chamfer face) is `(feature, "blend")`;
- anything else is `(feature, "new")`.

Roles are computed on the brought-in face in the feature's frame (the rotation of its literal `Location`): a
planar face whose normal is a frame axis is "+X".."-Z", another planar face "slope", a cylinder or cone "side", a
sphere or torus "surface", any other surface type its GeomType name. Edges are named by the labels of their two
faces.
"""
import ast

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import (GeomAbs_BezierSurface, GeomAbs_BSplineSurface, GeomAbs_Cone, GeomAbs_Cylinder,
                         GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus)
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS
from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as AncestorMap
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap

HOOK = "__bs_feature__"
_AXIS_TOL = 1e-9
_OTHER_SURFACES = {GeomAbs_BSplineSurface: "bspline", GeomAbs_BezierSurface: "bezier"}


def _faces(shape):
    m = ShapeMap()
    TopExp.MapShapes_s(shape, TopAbs_FACE, m)
    return [TopoDS.Face(m.FindKey(i)) for i in range(1, m.Extent() + 1)]


def _rotation_of(stmt):
    """The rotation (degrees) of a feature statement `with Locations(Location((x, y, z), (a, b, c))):`, or None."""
    if not (isinstance(stmt, ast.With) and len(stmt.items) == 1):
        return None
    call = stmt.items[0].context_expr
    if not (isinstance(call, ast.Call) and getattr(call.func, "id", "") == "Locations" and len(call.args) == 1):
        return None
    loc = call.args[0]
    if not (isinstance(loc, ast.Call) and getattr(loc.func, "id", "") == "Location" and len(loc.args) == 2):
        return None
    try:
        rot = ast.literal_eval(loc.args[1])
    except ValueError:
        return None
    return tuple(float(a) for a in rot) if isinstance(rot, tuple) and len(rot) == 3 else None


def _feature_name(lines, stmt):
    text = lines[stmt.lineno - 1]
    if "# feature:" not in text:
        return None
    return text.split("# feature:", 1)[1].strip() or None


def instrument(source, filename):
    """`source` compiled with a hook call after each feature statement of its `with BuildPart() as <name>:`
    block, or None when there is no such block with feature markers (the script then runs as it is)."""
    tree = ast.parse(source, filename)
    lines = source.splitlines()
    found = False
    for node in tree.body:
        if not (isinstance(node, ast.With) and len(node.items) == 1):
            continue
        item = node.items[0]
        if not (isinstance(item.context_expr, ast.Call) and getattr(item.context_expr.func, "id", "") == "BuildPart"
                and isinstance(item.optional_vars, ast.Name)):
            continue
        builder = item.optional_vars.id
        body = []
        for stmt in node.body:
            body.append(stmt)
            name = _feature_name(lines, stmt)
            if name is None:
                continue
            found = True
            call = ast.parse(f"{HOOK}({name!r}, {builder}, {_rotation_of(stmt)!r})").body[0]
            for sub in ast.walk(call):  # errors inside the hook point at the feature's own line
                ast.copy_location(sub, stmt)
                sub.end_lineno, sub.end_col_offset = stmt.lineno, stmt.col_offset
            body.append(call)
        node.body = body
    return compile(tree, filename, "exec") if found else None


def _role(face, rotation):
    """Role of a brought-in face (its orientation as in the feature's own solid) in the feature's frame."""
    surf = BRepAdaptor_Surface(face)
    kind = surf.GetType()
    if kind in (GeomAbs_Cylinder, GeomAbs_Cone):
        return "side"
    if kind in (GeomAbs_Sphere, GeomAbs_Torus):
        return "surface"
    if kind != GeomAbs_Plane:
        return _OTHER_SURFACES.get(kind, "surface")
    d = surf.Plane().Axis().Direction()
    if face.Orientation() == TopAbs_REVERSED:
        d = d.Reversed()
    if rotation is not None and any(rotation):
        from build123d import Location
        d = d.Transformed(Location((0, 0, 0), rotation).wrapped.Transformation().Inverted())
    v = (d.X(), d.Y(), d.Z())
    for axis in range(3):
        if abs(abs(v[axis]) - 1.0) < _AXIS_TOL:
            return ("+" if v[axis] > 0 else "-") + "XYZ"[axis]
    return "slope"


class Tracker:
    """The labels of the current part's faces, updated after each feature (see the module docstring)."""

    def __init__(self):
        self._labels = []   # [(TopoDS_Face, (feature, role))]
        self._shape = None
        self.features = []  # feature names in script order, up to the current one
        self.history = {}   # feature name -> labels right after it

    def labels(self):
        return list(self._labels)

    def label_of(self, face):
        for f, label in self._labels:
            if f.IsSame(face):
                return label
        return None

    def step(self, feature, builder, rotation):
        part = builder.part
        if self._shape is not None and part.wrapped.IsSame(self._shape):  # the statement didn't change the part
            self.features.append(feature)
            self.history[feature] = self._labels
            return
        record = getattr(part, "_history", None)
        faces = _faces(part.wrapped)
        new = []
        if record is None:
            new = [(f, (feature, "new")) for f in faces]
        else:
            before, brought = record._from()
            for f in faces:
                new.append((f, self._label(feature, f, before, brought, rotation)))
        self._labels, self._shape = new, part.wrapped
        self.features.append(feature)
        self.history[feature] = new

    def _label(self, feature, f, before, brought, rotation):
        if before.untouched.Contains(f):
            return self.label_of(f) or (feature, "new")
        if before.modified_from.IsBound(f):
            return self.label_of(before.modified_from.Find(f)) or (feature, "new")
        if brought.untouched.Contains(f):
            return feature, _role(f, rotation)
        if brought.modified_from.IsBound(f):
            return feature, _role(TopoDS.Face(brought.modified_from.Find(f)), rotation)
        if before.generated_from.IsBound(f):
            return feature, "blend"
        return feature, "new"

    def edge_label(self, edge, shape=None):
        """The sorted pair of labels of `edge`'s two faces in `shape` (default: the current part), or None."""
        shape = self._shape if shape is None else shape
        if shape is None:
            return None
        ancestors = AncestorMap()
        TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, ancestors)
        if not ancestors.Contains(edge):
            return None
        faces = list(ancestors.FindFromKey(edge))
        found = [self.label_of(f) for f in faces]
        if len(faces) != 2 or None in found:
            return None
        return tuple(sorted(found))


class BrokenReference(Exception):
    """A face/edge reference of a part script that no longer names anything (reported on the script's line)."""


def _name(faces):
    return getattr(faces, "_bs_name", "these faces")


def _distance(shape, point):
    from build123d import Vector, Vertex
    return shape.distance_to(Vertex(*Vector(point)))


def _nearest(items, point):
    return min(items, key=lambda s: _distance(s, point))


def _edges(face):
    m = ShapeMap()
    TopExp.MapShapes_s(face, TopAbs_EDGE, m)
    return [TopoDS.Edge(m.FindKey(i)) for i in range(1, m.Extent() + 1)]


def _helpers(tracker):
    """The reference helpers of a part script, resolved against `tracker`'s current labels."""
    from build123d import Edge, Face, ShapeList

    def face(feature, role=None, near=None):
        """The faces of the current part made by `feature` (with `role`, e.g. "+Z", "side", "blend"); with
        `near` (a point, mm, part frame) only the one closest to it."""
        if feature not in tracker.features:
            raise BrokenReference(f"no feature '{feature}' before this line")
        found = [Face(f) for f, (feat, r) in tracker.labels() if feat == feature and (role is None or r == role)]
        what = feature if role is None else f"{feature} {role}"
        if not found:
            raise BrokenReference(f"{feature} has no face '{role}'" if role is not None
                                  else f"no face of {feature} is left")
        if near is not None:
            found = [_nearest(found, near)]
        out = ShapeList(found)
        out._bs_name = what
        return out

    def edge_between(a, b, near=None):
        """The edges shared by a face of `a` and a face of `b` (results of face()); with `near`, the closest."""
        second = ShapeMap()
        for f in b:
            for e in _edges(f.wrapped):
                second.Add(e)
        shared, seen = [], ShapeMap()
        for f in a:
            for e in _edges(f.wrapped):
                if second.Contains(e) and not seen.Contains(e):
                    seen.Add(e)
                    shared.append(Edge(e))
        if not shared:
            raise BrokenReference(f"no edge between {_name(a)} and {_name(b)}")
        if near is not None:
            shared = [_nearest(shared, near)]
        return ShapeList(shared)

    def edges_of(faces):
        """Every edge of `faces` (a result of face())."""
        seen, out = ShapeMap(), []
        for f in faces:
            for e in _edges(f.wrapped):
                if not seen.Contains(e):
                    seen.Add(e)
                    out.append(Edge(e))
        return ShapeList(out)

    def _shape(shape):
        if shape is not None:
            return shape
        if tracker._shape is None:
            raise BrokenReference("nearest_face()/nearest_edge() need the shape to look in outside a part's features")
        return _wrap(tracker._shape)

    def nearest_face(point, shape=None):
        """The face of `shape` (default: the current part) closest to `point` (mm)."""
        return _nearest(_shape(shape).faces(), point)

    def nearest_edge(point, shape=None):
        """The edge of `shape` (default: the current part) closest to `point` (mm)."""
        return _nearest(_shape(shape).edges(), point)

    return {"face": face, "edge_between": edge_between, "edges_of": edges_of, "nearest_face": nearest_face,
            "nearest_edge": nearest_edge}


def _wrap(topods):
    from build123d import Compound
    return Compound(topods)


def namespace(tracker):
    """A part script's globals: build123d, the feature hook and the reference helpers."""
    ns = {"__name__": "__blendsolid_history__"}
    exec("from build123d import *", ns)
    ns[HOOK] = tracker.step
    ns.update(_helpers(tracker))
    return ns
