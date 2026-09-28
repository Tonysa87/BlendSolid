"""Milestone 2 spike 1 (throwaway): face/edge provenance from build123d's per-operation history.

Question: can the worker label every face and edge of a part's result with (feature, role) by instrumenting the
feature boundaries of a canonical script (no build123d patch), using the ShapeHistory record BuildPart already
keeps for Select.LAST/NEW? And do the labels stay the same when upstream parameters change?

Run with Blender's Python and the worker libraries:
    PYTHONPATH=.dev/worker_libs "$PY" spike/m2_s01_provenance.py
"""
import ast
import math
import time
from collections import Counter

from build123d import *  # noqa: F401,F403 (the scripts' namespace)
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.TopExp import TopExp
from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedDataMapOfShapeListOfShape
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as IMap
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_Torus
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

import build123d

SURF = {GeomAbs_Plane: "plane", GeomAbs_Cylinder: "cyl", GeomAbs_Cone: "cone", GeomAbs_Sphere: "sphere",
        GeomAbs_Torus: "torus"}


def mapped(shape, kind):
    m = IMap()
    TopExp.MapShapes_s(shape, kind, m)
    cast = TopoDS.Face if kind == TopAbs_FACE else TopoDS.Edge
    return [cast(m(i + 1)) for i in range(m.Extent())]


def role_of(face, feature_frame_inv=None):
    """Role of a face of a freshly brought-in primitive: surface type + outward normal direction (primitive axes)."""
    face = TopoDS.Face(face)
    s = BRepAdaptor_Surface(face)
    kind = SURF.get(s.GetType(), "other")
    if kind == "plane":
        n = s.Plane().Axis().Direction()
        if face.Orientation() == 1:  # TopAbs_REVERSED
            n = n.Reversed()
        v = [n.X(), n.Y(), n.Z()]
        axis = max(range(3), key=lambda i: abs(v[i]))
        if abs(abs(v[axis]) - 1) < 1e-9:
            return ("+" if v[axis] > 0 else "-") + "XYZ"[axis]
        return "plane(%.2f,%.2f,%.2f)" % tuple(v)
    return kind


class Provenance:
    """Labels of the current part's faces: face -> (feature, role)."""

    def __init__(self):
        self.labels = []  # list of (TopoDS_Face, label)
        self.log = []

    def label_of(self, shape):
        for f, lab in self.labels:
            if f.IsSame(shape):
                return lab
        return None

    def step(self, feature, part_obj):
        rec = getattr(part_obj, "_history", None)
        faces = mapped(part_obj.wrapped, TopAbs_FACE)
        new_labels = []
        if rec is None:
            self.log.append((feature, "NO RECORD"))
            for f in faces:
                new_labels.append((f, (feature, "?")))
        else:
            before_trace, brought_trace = rec._from()
            brought_faces = [f for b in rec.brought for f in mapped(b, TopAbs_FACE)]
            for f in faces:
                lab = None
                if before_trace.untouched.Contains(f):
                    lab = self.label_of(f)
                elif before_trace.modified_from.IsBound(f):
                    lab = self.label_of(before_trace.modified_from.Find(f))
                elif brought_trace.untouched.Contains(f):
                    lab = (feature, role_of(f))
                elif brought_trace.modified_from.IsBound(f):
                    lab = (feature, role_of(brought_trace.modified_from.Find(f)))
                elif before_trace.generated_from.IsBound(f):
                    src = before_trace.generated_from.Find(f)
                    lab = (feature, "from:" + str(self.edge_label(src)))
                elif brought_trace.generated_from.IsBound(f):
                    lab = (feature, "gen-brought")
                new_labels.append((f, lab if lab is not None else (feature, "UNKNOWN")))
        self.labels = new_labels
        self.shape = part_obj.wrapped

    def edge_label(self, edge):
        """An edge named by its two adjacent faces' labels (edge_between)."""
        if not hasattr(self, "shape"):
            return None
        m = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(self.shape, TopAbs_EDGE, TopAbs_FACE, m)
        if not m.Contains(edge):
            return ("vertex-or-unknown",)
        faces = list(m.FindFromKey(edge))
        return tuple(sorted(str(self.label_of(f)) for f in faces))


def instrument(source):
    """Insert __bs_done__("<feature>") after each feature statement of the with-BuildPart body (line numbers kept)."""
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.With) and any(isinstance(i.context_expr, ast.Call) and
                                              getattr(i.context_expr.func, "id", "") == "BuildPart"
                                              for i in node.items):
            body = []
            for stmt in node.body:
                body.append(stmt)
                marker = lines[stmt.lineno - 1].split("# feature:")
                name = marker[1].strip() if len(marker) > 1 else f"line{stmt.lineno}"
                call = ast.parse(f"__bs_done__({name!r}, part)").body[0]
                ast.copy_location(call, stmt)
                ast.fix_missing_locations(call)
                body.append(call)
            node.body = body
    return compile(tree, "<part>", "exec")


def run(source):
    prov = Provenance()
    ns = {}
    exec("from build123d import *", ns)
    ns["__bs_done__"] = lambda name, part: prov.step(name, part.part)
    t0 = time.perf_counter()
    exec(instrument(source), ns)
    dt = time.perf_counter() - t0
    shape = ns["result"].wrapped
    edges = mapped(shape, TopAbs_EDGE)
    edge_labels = [prov.edge_label(e) for e in edges]
    return prov, edge_labels, dt


def centroid(face):
    face = TopoDS.Face(face)
    p = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, p)
    c = p.CentreOfMass()
    return round(c.X(), 3), round(c.Y(), 3), round(c.Z(), 3)


def report(title, source):
    prov, edge_labels, dt = run(source)
    fl = Counter(lab for _, lab in prov.labels)
    el = Counter(edge_labels)
    print(f"\n== {title}: {len(prov.labels)} faces, {len(edge_labels)} edges, {dt*1000:.0f} ms, log {prov.log}")
    for f, lab in prov.labels:
        print("  ", lab, centroid(f), "" if fl[lab] == 1 else f"  <-- {fl[lab]} faces share this label")
    unique_f = sum(1 for _, lab in prov.labels if fl[lab] == 1 and "UNKNOWN" not in str(lab))
    unique_e = sum(1 for lab in edge_labels if el[lab] == 1)
    print(f"  unique face labels {unique_f}/{len(prov.labels)}, unique edge labels (face pair) "
          f"{unique_e}/{len(edge_labels)}")
    return prov, edge_labels


DEFAULT = open("blendsolid/templates/default_part.py").read()

BRACKET = """
box_1_length = 80.0
box_1_width = 40.0
box_1_height = 10.0
cut_1_radius = 4.0
cut_2_radius = 4.0
cut_3_radius = 4.0
wall_1_height = 30.0

with BuildPart() as part:
    Box(box_1_length, box_1_width, box_1_height, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with Locations(Location((-40.0, 0.0, 10.0), (0.0, 0.0, 0.0))):  # feature: wall_1
        Box(10.0, box_1_width, wall_1_height, align=(Align.MIN, Align.CENTER, Align.MIN))
    with Locations(Location((-10.0, 0.0, 10.0), (0.0, 0.0, 0.0))):  # feature: cut_1
        Cylinder(cut_1_radius, 10.0, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((10.0, 0.0, 10.0), (0.0, 0.0, 0.0))):  # feature: cut_2
        Cylinder(cut_2_radius, 10.0, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((30.0, 0.0, 10.0), (0.0, 0.0, 0.0))):  # feature: cut_3
        Cylinder(cut_3_radius, 10.0, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    fillet(part.edges().filter_by(Axis.Y).group_by(Axis.Z)[-1], radius=2)  # feature: fillet_1

result = part.part
"""

SPLIT = """
with BuildPart() as part:
    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with Locations(Location((0.0, 0.0, 20.0), (0.0, 0.0, 0.0))):  # feature: slot_1
        Box(8, 40, 5, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)

result = part.part
"""

if __name__ == "__main__":
    print("build123d", build123d.__version__)
    report("default part", DEFAULT)
    report("default part, box_1_length 40 -> 55", DEFAULT.replace("box_1_length = 40.0", "box_1_length = 55.0"))
    report("bracket with 3 holes + fillet", BRACKET)
    report("bracket, cut_2 radius 4 -> 6, wall 30 -> 45", BRACKET.replace("cut_2_radius = 4.0", "cut_2_radius = 6.0")
           .replace("wall_1_height = 30.0", "wall_1_height = 45.0"))
    report("slot splitting the top face", SPLIT)
