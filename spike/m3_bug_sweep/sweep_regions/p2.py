import sys, time
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import runner, sketches
from build123d import *
from OCP.BRepCheck import BRepCheck_Analyzer
which = sys.argv[1]
if which == "tangent":
    sk = sketches.Sketch(Plane.XY)
    sk.a = Pos(-5,0)*Circle(5); sk.b = Pos(5,0)*Circle(5)
    regs = sk.regions_local()
    sols = [sketches._prism(f, Vector(0,0,5), sk, -5.0) for f in regs]
    for s in sols: print("piece valid", BRepCheck_Analyzer(s.wrapped).IsValid(), s.volume)
    fused = sols[0].fuse(sols[1])
    print("fused valid", BRepCheck_Analyzer(fused.wrapped).IsValid(), fused.volume, len(fused.solids()))
    c = fused.clean()
    print("clean valid", BRepCheck_Analyzer(c.wrapped).IsValid(), c.volume, len(c.solids()))
else:
    sk = sketches.Sketch(Plane.XY)
    sk.a = Pos(-4,0)*Circle(5); sk.b = Pos(4,0)*Circle(5)
    regs = sk.regions_local()
    print([round(f.area,3) for f in regs])
    sols = []
    for f in regs:
        t = time.time()
        s = sketches._prism(f, Vector(0,0,5), sk, 5.0)
        print("piece", round(f.area,3), BRepCheck_Analyzer(s.wrapped).IsValid(), s.volume, time.time()-t, flush=True)
        sols.append(s)
    t = time.time()
    fused = sols.pop().fuse(*sols)
    print("fused", time.time()-t, BRepCheck_Analyzer(fused.wrapped).IsValid(), fused.volume, flush=True)
    t = time.time()
    c = fused.clean()
    print("clean", time.time()-t, flush=True)
