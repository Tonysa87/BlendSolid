import sys
import check
import runner, tessellate
from OCP.TopAbs import TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
src = open(sys.argv[1]).read()
r = runner.run_script(src, 1.0, 0.3, tag="x")
shape = runner.SHAPES.get("x").wrapped
print("type", shape.ShapeType(), tessellate.check(shape))
e = TopExp_Explorer(shape, TopAbs_SOLID)
while e.More():
    s = e.Current(); p = GProp_GProps(); BRepGProp.VolumeProperties_s(s, p)
    n = 0; ee = TopExp_Explorer(s, TopAbs_SHELL)
    while ee.More(): n += 1; ee.Next()
    nf = 0; ee = TopExp_Explorer(s, TopAbs_FACE)
    while ee.More(): nf += 1; ee.Next()
    print(" solid vol", p.Mass(), "shells", n, "faces", nf)
    e.Next()
