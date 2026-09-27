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
    from OCP.gp import gp_Dir
    import tessellate
    n, _ = tessellate.plane_normal(face)
    d = gp_Dir(*map(float, n))
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
        self._index = ShapeMap()  # the current part's faces; _label_list[i - 1] is the label of index i
        self._label_list = []
        self._shape = None
        self._ancestors = None    # edge -> faces of the current part, built when first asked
        self.features = []        # feature names in script order, up to the current one
        self.history = {}         # feature name -> [(face, label)] right after it

    def labels(self):
        return [(TopoDS.Face(self._index.FindKey(i + 1)), label) for i, label in enumerate(self._label_list)]

    def label_of(self, face):
        i = self._index.FindIndex(face)
        return self._label_list[i - 1] if i > 0 else None

    def step(self, feature, builder, rotation):
        part = builder.part
        self.features.append(feature)
        if self._shape is not None and part.wrapped.IsSame(self._shape):  # the statement didn't change the part
            self.history[feature] = self.labels()
            return
        record = getattr(part, "_history", None)
        faces = _faces(part.wrapped)
        if record is None:
            labels = [(feature, "new")] * len(faces)
        else:
            before, brought = record._from()
            labels = [self._label(feature, f, before, brought, rotation) for f in faces]
        index = ShapeMap()
        for f in faces:
            index.Add(f)
        self._index, self._label_list, self._shape, self._ancestors = index, labels, part.wrapped, None
        self.history[feature] = self.labels()

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

    def edge_faces(self, edge):
        """The distinct faces of the current part around `edge` (one for a seam)."""
        if self._shape is None:
            return []
        if self._ancestors is None:
            self._ancestors = AncestorMap()
            TopExp.MapShapesAndAncestors_s(self._shape, TopAbs_EDGE, TopAbs_FACE, self._ancestors)
        if not self._ancestors.Contains(edge):
            return []
        out = []
        for f in self._ancestors.FindFromKey(edge):
            if not any(f.IsSame(g) for g in out):
                out.append(f)
        return out

    def edge_label(self, edge):
        """The sorted pair of labels of `edge`'s two faces in the current part, or None (a seam, or no labels)."""
        faces = self.edge_faces(edge)
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


def _centre(shape):
    c = shape.center()  # centre of mass (of the length for an edge, of the area for a face)
    return (c.X, c.Y, c.Z)


def _closest_centre(items, point):
    """The item whose centre is closest to `point` (the `near=` tie-break)."""
    return min(items, key=lambda s: sum((a - b) ** 2 for a, b in zip(_centre(s), point)))


def _edges(face):
    m = ShapeMap()
    TopExp.MapShapes_s(face, TopAbs_EDGE, m)
    return [TopoDS.Edge(m.FindKey(i)) for i in range(1, m.Extent() + 1)]


def _helpers(tracker):
    """The reference helpers of a part script, resolved against `tracker`'s current labels."""
    from build123d import Edge, Face, ShapeList

    def face(feature, role=None, near=None):
        """The faces of the current part made by `feature` (with `role`, e.g. "+Z", "side", "blend"); with
        `near` (a point, mm, part frame) only the one whose centre is closest to it."""
        if feature not in tracker.features:
            raise BrokenReference(f"no feature '{feature}' before this line")
        found = [Face(f) for f, (feat, r) in tracker.labels() if feat == feature and (role is None or r == role)]
        what = feature if role is None else f"{feature} {role}"
        if not found:
            raise BrokenReference(f"{feature} has no face '{role}'" if role is not None
                                  else f"no face of {feature} is left")
        if near is not None:
            found = [_closest_centre(found, near)]
        out = ShapeList(found)
        out._bs_name = what
        return out

    def edge_between(a, b, near=None):
        """The edges shared by a face of `a` and a face of `b` (results of face()); with `near`, the one whose
        centre is closest to it."""
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
            shared = [_closest_centre(shared, near)]
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


# -- reference texts: what a click on a face or an edge writes into the script -----------------------------------

def _fmt(value):
    return repr(round(float(value), 6) + 0.0)  # the scripts' 6 decimals, never "-0.0"


def _point(p):
    return "(" + ", ".join(_fmt(c) for c in p) + ")"


def _on_face(face):
    """A point on `face` (its centre of mass moved onto it: a curved face's centre may lie off it)."""
    from build123d import Face, Vertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    f = Face(face)
    c = f.center()
    dist = BRepExtrema_DistShapeShape(Vertex(c).wrapped, face)
    p = dist.PointOnShape2(1) if dist.IsDone() and dist.NbSolution() else None
    return (p.X(), p.Y(), p.Z()) if p is not None else tuple(c)


_SAME_CENTRE = 1e-6  # mm: two entities with centres this close can't be told apart by near=


def _pick_text(base, index, centres):
    """`base` if the entity is alone in its group (`centres`: the group's centres, the entity's at `index`), else
    `base` with near= its centre when that singles it out, else None."""
    if len(centres) == 1:
        return base
    mine = centres[index]
    for k, other in enumerate(centres):
        if k != index and sum((a - b) ** 2 for a, b in zip(mine, other)) < _SAME_CENTRE ** 2:
            return None
    return base[:-1] + f", near={_point(mine)})"


class _Groups:
    """Entities grouped by a key, with each member's position in its group and the group's centres (computed
    once: near= compares every member's centre)."""

    def __init__(self, entities, keys, wrap):
        self.members, self.slot = {}, []
        for e, key in zip(entities, keys):
            group = self.members.setdefault(key, [])
            self.slot.append(len(group))
            group.append(e)
        self._wrap, self._centres = wrap, {}

    def centres(self, key):
        if key not in self._centres:
            self._centres[key] = [_centre(self._wrap(e)) for e in self.members[key]]
        return self._centres[key]


def reference_texts(tracker, faces, edges):
    """For each face and edge of the final part (in `faces`/`edges` order: the ids the display mesh carries), the
    reference a click on it writes: `face("f", "role")`, with `near=` (its centre) when the label names several
    faces; `edge_between(face(A), face(B))`, with `near=` when the two labels share several edges; the
    nearest_*() form when there is no provenance or centres can't tell the entity apart. "" for an entity that
    can't be clicked (a seam, a degenerate edge at a pole) or one OCCT can't evaluate. None for scripts without
    features (the tools don't edit those). The texts mirror the helpers' rules; tests resolve them."""
    if not tracker.features:
        return None
    from build123d import Edge, Face
    from OCP.BRep import BRep_Tool
    face_labels = [tracker.label_of(f) for f in faces]
    face_groups = _Groups(faces, face_labels, Face)
    pairs = [_safe(tracker.edge_label, e) or None for e in edges]
    edge_groups = _Groups(edges, pairs, Edge)

    def face_text(i, f):
        label = face_labels[i]
        text = None
        if label is not None and label[1] != "new":
            text = _pick_text(f'face("{label[0]}", "{label[1]}")', face_groups.slot[i], face_groups.centres(label))
        return text or f"nearest_face({_point(_on_face(f))})"

    def edge_text(i, e):
        if BRep_Tool.Degenerated_s(e) or len(tracker.edge_faces(e)) < 2:
            return ""
        pair, text = pairs[i], None
        if pair is not None and "new" not in (pair[0][1], pair[1][1]):
            a, b = (f'face("{feat}", "{role}")' for feat, role in pair)
            text = _pick_text(f"edge_between({a}, {b})", edge_groups.slot[i], edge_groups.centres(pair))
        return text or f"nearest_edge({_point(Edge(e).position_at(0.5))})"

    return ([_safe(face_text, i, f) for i, f in enumerate(faces)],
            [_safe(edge_text, i, e) for i, e in enumerate(edges)])


def _safe(make, *args):
    try:
        return make(*args)
    except Exception:  # an OCCT failure on one entity must not fail the part
        return ""
