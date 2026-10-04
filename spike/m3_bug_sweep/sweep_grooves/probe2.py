import sys, math
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import sketches
from build123d import *
from OCP.BRepCheck import BRepCheck_Analyzer
def valid(s): return BRepCheck_Analyzer(s.wrapped).IsValid()
def probe(pts_args, profile, corners, width, depth, rib=False, plane=Plane.XY, over=0.5, closed=False):
    w = sketches.path(*pts_args, closed=closed)
    wire = plane.location * w
    n = plane.z_dir
    up = n if not rib else -n
    def profile_at(point, tangent):
        return sketches._profile_wire(profile, width, depth, over, sketches._Place(point, n.cross(tangent).normalized(), up, tangent))
    runs, sharp = sketches._runs(wire)
    print("runs", [len(r.edges()) for r in runs], "sharp turns", [round(b.get_angle(a), 4) for _, b, a in sharp])
    for r in runs:
        try:
            p = sketches._pipe(r, profile_at(r.position_at(0), r.tangent_at(0)), n, corners)
            print("  run ok vol", round(p.volume, 4), [e.geom_type.name for e in r.edges()])
        except Exception as e:
            print("  run FAIL", type(e).__name__, str(e)[:80], [(e.geom_type.name, round(e.length, 4)) for e in r.edges()])
    try:
        s = sketches._sweep(wire, profile_at, n, corners)
        print("  sweep ok vol", s.volume)
    except Exception as e:
        import traceback; tb = traceback.extract_tb(e.__traceback__)[-1]
        print("  sweep FAIL", type(e).__name__, str(e)[:80], "at line", tb.lineno)
args = sys.argv[1:]
