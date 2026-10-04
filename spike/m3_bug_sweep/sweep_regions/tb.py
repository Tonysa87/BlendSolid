import json, sys, glob, traceback
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import runner, tessellate, provenance
from OCP.BRepCheck import BRepCheck_Analyzer
src = None
for fn in glob.glob("fuzz_p2_*.json"):
    d = json.load(open(fn)); c = {x["id"]: x for x in d["phase2"]}
    if sys.argv[1] in c: src = c[sys.argv[1]]["src"]
if src is None: src = open(sys.argv[1]).read()
tr = provenance.Tracker()
try:
    shape = runner._build(src, runner.SCRIPT_NAME, [], runner.ShapeCache(), tracker=tr)
    w = shape.wrapped
    print("solids", len(shape.solids()), "valid", BRepCheck_Analyzer(w).IsValid(), "vol", shape.volume, "faces", len(shape.faces()))
    print(tessellate.check(w))
    m = tessellate.display_mesh(w, 0.1, 0.3)
    print("mesh ok", len(m.verts))
except Exception:
    traceback.print_exc()
