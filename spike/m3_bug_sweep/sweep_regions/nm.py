import sys
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import runner, provenance, tessellate
from OCP.TopExp import TopExp
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as M
src = '''with BuildPart() as part:
    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.c = Pos(20.0, 0.0) * Circle(5.0)
    extrude(regions(sketch_1, (23.0, 0.0)), amount=5.0)  # feature: extrude_1
result = part.part
'''
shape = runner._build(src, runner.SCRIPT_NAME, [], runner.ShapeCache(), tracker=provenance.Tracker())
m = M(); TopExp.MapShapesAndAncestors_s(shape.wrapped, TopAbs_EDGE, TopAbs_FACE, m)
print("solids", len(shape.solids()), "edges with >2 faces", sum(1 for i in range(1, m.Extent()+1) if m.FindFromIndex(i).Size() > 2))
r = runner.run_script(src); print(r.ok, r.volume, r.edge_refs)
