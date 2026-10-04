import sys, json, glob
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import sketches, runner, provenance
from build123d import *
from OCP.BRepCheck import BRepCheck_Analyzer
V = lambda s: BRepCheck_Analyzer(s.wrapped).IsValid()
orig = sketches._prism
def spy(face, direction, sk, taper):
    s = orig(face, direction, sk, taper)
    print("prism valid", V(s), "vol", s.volume, "faces", len(s.faces()), "area", face.area, "dir", direction)
    return s
sketches._prism = spy
for fn in glob.glob("fuzz_p2_*.json"):
    d = json.load(open(fn)); c = {x["id"]: x for x in d["phase2"]}
    if sys.argv[1] in c: src = c[sys.argv[1]]["src"]
tr = provenance.Tracker()
shape = runner._build(src, runner.SCRIPT_NAME, [], runner.ShapeCache(), tracker=tr)
print("result", shape.volume, V(shape))
