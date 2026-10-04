import sys
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import sketches
from build123d import *
from OCP.BRepCheck import BRepCheck_Analyzer
plane = Plane(origin=(0, 0, 10), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
w = plane.location * sketches.path((-8.638812, 5.067554), (-2.14985, -8.684893), (-1.257986, 7.264964), (-2.910998, 6.849436), closed=True)
n = plane.z_dir
def sweep(profile, width, depth, corners):
    def profile_at(point, tangent):
        return sketches._profile_wire(profile, width, depth, 0.5, sketches._Place(point, n.cross(tangent).normalized(), -n, tangent))
    return sketches._sweep(w, profile_at, n, corners)
box = Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
r1 = sweep("round", 2.275027, 2.579678, "round")
r2 = sweep("round", 0.713101, 2.579678, "mitre")
print("r1", r1.volume, "faces", len(r1.faces()), "r2", r2.volume, "faces", len(r2.faces()))
a = box.fuse(r1).clean()
print("box+r1", a.volume, len(a.solids()))
b = a.fuse(r2)
print("box+r1+r2 raw", b.volume, len(b.solids()), BRepCheck_Analyzer(b.wrapped).IsValid())
b2 = b.clean()
print("cleaned", b2.volume, len(b2.solids()), BRepCheck_Analyzer(b2.wrapped).IsValid())
c = r1.fuse(r2)
print("r1+r2", c.volume, len(c.solids()), "clean", c.clean().volume)
print("r2 inside r1? r2-r1 vol", (r2 - r1).volume)
def sweep_o(profile, width, depth, corners, over):
    def profile_at(point, tangent):
        return sketches._profile_wire(profile, width, depth, over, sketches._Place(point, n.cross(tangent).normalized(), -n, tangent))
    return sketches._sweep(w, profile_at, n, corners)
for over in (0.4, 0.5):
    r2b = sweep_o("round", 0.713101, 2.579678, "mitre", over)
    print("over", over, "box+r1+r2", a.fuse(r2b).volume)
r2c = sweep("round", 0.713101, 2.579678, "round")
print("r2 round corners: box+r1+r2", a.fuse(r2c).volume)
r2d = sweep("round", 0.713101, 2.0, "mitre")
print("r2 depth 2.0: box+r1+r2", a.fuse(r2d).volume)
