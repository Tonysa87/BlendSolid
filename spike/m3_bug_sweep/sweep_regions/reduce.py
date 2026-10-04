import sys, json, glob, re
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import sketches, runner, provenance
from OCP.BRepCheck import BRepCheck_Analyzer
flag = {}
orig = sketches._prism
def spy(face, direction, sk, taper):
    s = orig(face, direction, sk, taper)
    flag["bad"] = not BRepCheck_Analyzer(s.wrapped).IsValid()
    flag["area"] = face.area
    flag["edges"] = [(e.geom_type.name, round(e.length, 6)) for e in face.edges()]
    return s
sketches._prism = spy
def bad(src):
    flag.clear()
    try:
        runner._build(src, runner.SCRIPT_NAME, [], runner.ShapeCache(), tracker=provenance.Tracker())
    except Exception as e:
        return False
    return flag.get("bad", False)
for fn in glob.glob("fuzz_p2_*.json"):
    d = json.load(open(fn)); c = {x["id"]: x for x in d["phase2"]}
    if sys.argv[1] in c: src = c[sys.argv[1]]["src"]
lines = src.splitlines()
assert bad(src)
i = 0
while i < len(lines):
    if lines[i].startswith("        sketch_1."):
        trial = lines[:i] + lines[i+1:]
        if bad("\n".join(trial) + "\n"):
            lines = trial; continue
    i += 1
print("\n".join(lines)); bad("\n".join(lines) + "\n"); print(flag)
