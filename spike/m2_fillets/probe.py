"""What OCCT 8 / build123d 0.13 does on typical fillet edge cases: ok / exception / invalid solid, volume.
$PY spike/m2_fillets/probe.py"""
import sys, time, traceback; sys.path[:0] = ["blendsolid/worker", ".dev/worker_libs"]
from build123d import *
from OCP.BRepCheck import BRepCheck_Analyzer

def box(): return Box(40, 30, 20)
def corner_edges(p):  # the 3 edges at the (+,+,+) corner
    v = p.vertices().sort_by(Axis.X)[-1:] and max(p.vertices(), key=lambda v: v.X + v.Y + v.Z)
    return [e for e in p.edges() if any((e.position_at(t) - Vector(v)).length < 1e-6 for t in (0, 1))]

CASES = {
 "one edge r5": lambda: fillet(box().edges().filter_by(Axis.Z)[0], 5),
 "radius = half width (15) on vertical edges": lambda: fillet(box().edges().filter_by(Axis.Z), 15),
 "radius > half width (16) on vertical edges": lambda: fillet(box().edges().filter_by(Axis.Z), 16),
 "radius 10 = half height on top edges": lambda: fillet(box().edges().group_by(Axis.Z)[-1], 10),
 "radius 12 > half height on top edges": lambda: fillet(box().edges().group_by(Axis.Z)[-1], 12),
 "3 edges at a corner r5": lambda: fillet(corner_edges(box()), 5),
 "all 12 edges r5": lambda: fillet(box().edges(), 5),
 "all 12 edges r10 (=half height)": lambda: fillet(box().edges(), 10),
 "2 of 3 corner edges r5 (mixed)": lambda: fillet(corner_edges(box())[:2], 5),
 "fillet next to fillet (r5 then r3 on adjacent)": lambda: fillet(fillet(box().edges().filter_by(Axis.Z).sort_by(Axis.X)[-1], 5).edges().group_by(Axis.Z)[-1], 3),
 "concave edge of a boss r2": lambda: fillet((box() + Pos(0, 0, 10) * Cylinder(5, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))).edges().filter_by(GeomType.CIRCLE).group_by(Axis.Z)[1], 2),
 "concave boss edge r10 (too big)": lambda: fillet((box() + Pos(0, 0, 10) * Cylinder(5, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))).edges().filter_by(GeomType.CIRCLE).group_by(Axis.Z)[1], 10),
 "hole edge r2": lambda: fillet((box() - Cylinder(5, 40)).edges().filter_by(GeomType.CIRCLE).group_by(Axis.Z)[-1], 2),
 "hole edge r6 (> hole radius)": lambda: fillet((box() - Cylinder(5, 40)).edges().filter_by(GeomType.CIRCLE).group_by(Axis.Z)[-1], 6),
 "hole near edge, top edges r3 (runs into hole)": lambda: fillet((box() - Pos(17, 0, 0) * Cylinder(2, 40)).edges().group_by(Axis.Z)[-1], 3),
 "cylinder seam top edge r2": lambda: fillet(Cylinder(10, 20).edges().group_by(Axis.Z)[-1], 2),
 "cylinder top edge r10 (= radius)": lambda: fillet(Cylinder(10, 20).edges().group_by(Axis.Z)[-1], 10),
 "tiny edge after boolean r1": lambda: fillet((box() - Pos(20, 15, 10) * Box(10, 10.001, 10)).edges().filter_by(Axis.Z), 1),
 "sphere-cut edge r2": lambda: fillet((box() - Pos(20, 15, 10) * Sphere(8)).edges().filter_by(GeomType.LINE, reverse=True), 2),
 "chamfer 5 on vertical": lambda: chamfer(box().edges().filter_by(Axis.Z), 5),
 "chamfer 16 (> half width)": lambda: chamfer(box().edges().filter_by(Axis.Z), 16),
 "asymmetric chamfer 3/6": lambda: chamfer(box().edges().filter_by(Axis.Z)[0], 3, 6),
 "chamfer corner 3 edges": lambda: chamfer(corner_edges(box()), 4),
 "wedge slanted edge r5": lambda: fillet(Wedge(40, 20, 30, 10, 10, 30, 30).edges(), 3),
 "torus-cut edge r1": lambda: fillet((box() - Pos(0, 0, 20) * Torus(10, 3)).edges().filter_by(GeomType.LINE, reverse=True).group_by(Axis.Z)[-1], 1),
}
for name, make in CASES.items():
    t = time.perf_counter()
    try:
        p = make(); ok = BRepCheck_Analyzer(p.wrapped).IsValid()
        res = f"{'VALID' if ok else 'INVALID'} vol {p.volume:.1f} faces {len(p.faces())}"
    except Exception as e:
        res = f"RAISE {type(e).__name__}: {str(e)[:90]}"
    print(f"{name:48s} {time.perf_counter() - t:5.2f}s  {res}", flush=True)
