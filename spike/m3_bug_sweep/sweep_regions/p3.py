import sys, time
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import sketches
from build123d import *
from OCP.BRepCheck import BRepCheck_Analyzer
V = lambda s: BRepCheck_Analyzer(s.wrapped).IsValid()
if sys.argv[1] == "tangent":
    sk = sketches.Sketch(Plane.XY)
    sk.a = Pos(-5,0)*Circle(5); sk.b = Pos(5,0)*Circle(5)
    regs = sk.regions_local()
    sols = [sketches._prism(f, Vector(0,0,5), sk, -5.0) for f in regs]
    fused = sols.pop().fuse(*sols)
    print(type(fused), V(fused), fused.volume)
    s2 = list(fused.solids()); print([V(s) for s in s2])
    c = [s.clean() for s in s2]; print([V(s) for s in c], [s.volume for s in c])
    with BuildPart() as p:
        add(c)
    print("part", V(p.part), p.part.volume)
else:
    i = int(sys.argv[2])
    sk = sketches.Sketch(Plane.XY)
    sk.a = Pos(-4,0)*Circle(5); sk.b = Pos(4,0)*Circle(5)
    regs = sk.regions_local()
    f = regs[i]
    print(i, f.area, [e.geom_type for e in f.edges()], flush=True)
    t = time.time()
    s = sketches._prism(f, Vector(0,0,5), sk, float(sys.argv[3]))
    print("piece", V(s), s.volume, time.time()-t, flush=True)
