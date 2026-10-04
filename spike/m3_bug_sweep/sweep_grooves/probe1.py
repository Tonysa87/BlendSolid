import sys
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import sketches
from build123d import *
from OCP.BRepCheck import BRepCheck_Analyzer
plane = Plane(origin=(0, -10, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
w = sketches.path((9.701073, 3.73751), (10.88196, 6.526477), (12.863058, 11.20535), (8.23183, 7.192943))
wire = plane.location * w
n = plane.z_dir
width, depth = 3.615984, 2.107803
def profile_at(point, tangent):
    return sketches._profile_wire("rect", width, depth, 0.5, sketches._Place(point, n.cross(tangent).normalized(), n, tangent))
runs, sharp = sketches._runs(wire)
print("runs", len(runs), [len(r.edges()) for r in runs], "sharp", len(sharp))
pieces = [sketches._pipe(r, profile_at(r.position_at(0), r.tangent_at(0)), n, "mitre") for r in runs]
for p in pieces: print("run piece vol", p.volume, BRepCheck_Analyzer(p.wrapped).IsValid())
solid = sketches._sweep(wire, profile_at, n, "mitre")
print("sweep vol", solid.volume, len(solid.faces()))
box = Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
cut = box - solid
print("cut vol", cut.volume, BRepCheck_Analyzer(cut.wrapped).IsValid(), "inter", (box & solid).volume)
from OCP.BRepCheck import BRepCheck_Analyzer
fused = pieces[0].fuse(*pieces[1:])
cornerless = None
print("fused (no clean) faces", len(fused.faces()), "vol", fused.volume)
# pieces incl corner
import math
allp = list(pieces)
point, before, after = sharp[0]
box2 = profile_at(runs[0].position_at(0), runs[0].tangent_at(0)).bounding_box(); reach = (box2.max - box2.min).length
turn = math.radians(before.get_angle(after)); length = 2 * reach / math.cos(turn / 2) + 1.0
ahead = Solid.extrude(Face(profile_at(point, before)), before * length)
behind = Solid.extrude(Face(profile_at(point, after)), after * -length)
corner = Solid(ahead.intersect(behind).solids()[0].wrapped)
f2 = pieces[0].fuse(pieces[1], corner)
print("fuse3 noclean vol", f2.volume, "faces", len(f2.faces()), "cut", (box - f2).volume)
f3 = f2.clean()
print("fuse3 clean vol", f3.volume, "faces", len(f3.faces()), "cut", (box - f3).volume)
print("run0 cut alone", (box - pieces[0]).volume, "run1", (box - pieces[1]).volume, "corner", (box - corner).volume)
for f in solid.faces(): print(f.geom_type, round(f.area, 4))
