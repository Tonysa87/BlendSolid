import sys, math; sys.path[:0] = ["spike/m3_outer_arcs", "blendsolid/worker", ".dev/worker_libs"]
import numpy as np, build123d as bd, measure, tessellate
M = bd.Align.MIN; C = bd.Align.CENTER
def cyl(r, x, y): return bd.Pos(x, y, 0) * bd.Cylinder(r, 10, align=(C, C, M))
PARTS = {
 "corner_notch": lambda: bd.Box(60, 40, 10, align=(C, C, M)) - cyl(6, 0, 0) - cyl(10, 30, 20),
 "edge_notch": lambda: bd.Box(60, 40, 10, align=(C, C, M)) - cyl(6, 10, 0) - cyl(8, -10, -20),
 "corner_boss": lambda: bd.Box(60, 40, 10, align=(C, C, M)) - cyl(6, 0, 0) + bd.Pos(-30, 20, 10) * bd.Cylinder(8, 5, align=(C, C, M)),
 "fillet_inside": lambda: bd.fillet((bd.Box(60, 40, 10, align=(C, C, M)) - bd.Pos(20, 10, 0) * bd.Box(20, 20, 10, align=(M, M, M))).edges().filter_by(bd.Axis.Z).sort_by_distance((20, 10, 5))[0], 8) - cyl(5, -10, 0),
}
if __name__ == "__main__":
  for name in (sys.argv[1:] or PARTS):
    s = PARTS[name]().wrapped
    print(name, measure.face_stats(s))
