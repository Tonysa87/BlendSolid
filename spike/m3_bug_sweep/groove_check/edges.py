import sys, os
W = sys.argv[1]
sys.path[:0] = [os.path.join(W, "blendsolid", "worker"), "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import sketches
w = sketches.path((4.053926, 1.141709), (3.914217, 0.888261), (2.75228, -1.219645), (2.753019, -1.220319), sketches.arc_to((5.203252, 0.383503)), closed=True)
for e in w.edges():
    print(os.path.basename(W), e.geom_type.name, [round(c, 9) for c in e.position_at(0)], [round(c, 9) for c in e.position_at(1)])
w = sketches.path((-11.005622, -6.050002), (-11.037672, -5.98361), (-10.97514, -5.953424), sketches.arc_to((-9.911976, -5.440201)))
for e in w.edges():
    print(os.path.basename(W), "R1", e.geom_type.name, [round(c, 9) for c in e.position_at(0)], [round(c, 9) for c in e.position_at(1)])
