import check
from OCP.TopExp import TopExp
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.BRep import BRep_Tool
from OCP.TopoDS import TopoDS
from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as DM
def brep_edge_faces(shape):
    m = DM(); TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, m)
    bad, free = 0, 0
    for i in range(1, m.Extent() + 1):
        e = TopoDS.Edge(m.FindKey(i))
        if BRep_Tool.Degenerated_s(e): continue
        faces = list(m.FindFromIndex(i))
        uniq = []
        for f in faces:
            if not any(f.IsSame(g) for g in uniq): uniq.append(f)
        n = len(faces)
        if len(uniq) > 2: bad += 1
        if len(faces) == 1: free += 1
    return bad, free
if __name__ == "__main__":
    import sys, runner
    r = runner.run_script(open(sys.argv[1]).read(), 1.0, 0.3, tag="x")
    print(brep_edge_faces(runner.SHAPES.get("x").wrapped))
