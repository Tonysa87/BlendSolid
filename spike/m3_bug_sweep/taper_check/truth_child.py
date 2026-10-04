import sys, os, json, math
ROOT = "/home/tony/Projects/BlendSolid"
sys.path[:0] = [os.path.join(ROOT, "blendsolid", "worker"), os.path.join(ROOT, ".dev", "worker_libs")]
import runner, sketches
from build123d import Compound, Face, GeomType, Plane, Solid
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
from OCP.GeomAbs import GeomAbs_Intersection
out = {}
def area_at(face, inset):
    if abs(inset) < 1e-12:
        return face.area
    m = BRepOffsetAPI_MakeOffset(face.wrapped, GeomAbs_Intersection); m.Perform(-inset)
    if not m.IsDone() or m.Shape().IsNull():
        return None
    ws = Compound(m.Shape()).wires()
    if not ws:
        return 0.0
    faces = sorted((Face(w) for w in ws), key=lambda f: -f.area)
    return faces[0].area - sum(f.area for f in faces[1:])
def spy(face, plane, inset, taper, length):
    f = face
    n = 64
    areas = [area_at(f, inset * i / n) for i in range(n + 1)]
    if any(a is None for a in areas):
        out["truth"] = None
    else:
        out["truth"] = length / n / 3 * (areas[0] + areas[-1] + 4 * sum(areas[1:-1:2]) + 2 * sum(areas[2:-1:2]))
    d = (plane.z_dir * length)
    solid = Solid.extrude(face, d)
    sides = [x for x in solid.faces() if not (x.geom_type == GeomType.PLANE and abs(abs(x.normal_at().dot(plane.z_dir)) - 1) < 1e-9)]
    try:
        out["draft"] = solid.draft(sides, plane, taper).volume
    except Exception as e:
        out["draft"] = str(e)[:60]
    try:
        orig(face, plane, inset, taper, length); out["check"] = "pass"
    except Exception as e:
        out["check"] = str(e)[:50]
    raise SystemExit
orig = sketches._check_taper_section
sketches._check_taper_section = spy
try:
    rr = runner.run_script(sys.stdin.read()); out.setdefault("run", rr.error[:120])
except SystemExit:
    pass
print(json.dumps(out))
