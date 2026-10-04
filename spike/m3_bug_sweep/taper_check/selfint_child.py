import sys, os, json, time
ROOT = "/home/tony/Projects/BlendSolid"
sys.path[:0] = [os.path.join(ROOT, "blendsolid", "worker"), os.path.join(ROOT, ".dev", "worker_libs")]
import runner, sketches
from build123d import GeomType, Solid
from OCP.BOPAlgo import BOPAlgo_ArgumentAnalyzer
out = {}
def spy(face, plane, inset, taper, length):
    solid = Solid.extrude(face, plane.z_dir * length)
    sides = [x for x in solid.faces() if not (x.geom_type == GeomType.PLANE and abs(abs(x.normal_at().dot(plane.z_dir)) - 1) < 1e-9)]
    t = time.perf_counter()
    try:
        d = solid.draft(sides, plane, taper)
    except Exception as e:
        out["draft"] = str(e)[:40]; raise SystemExit
    a = BOPAlgo_ArgumentAnalyzer()
    a.SetShape1(d.wrapped)
    a.SelfInterMode = True; a.ArgumentTypeMode = True
    a.Perform()
    out["faulty"] = a.HasFaulty()
    out["ms"] = round((time.perf_counter() - t) * 1000)
    raise SystemExit
sketches._check_taper_section = spy
rr = runner.run_script(sys.stdin.read())
out.setdefault("run", rr.error[:80])
print(json.dumps(out))
