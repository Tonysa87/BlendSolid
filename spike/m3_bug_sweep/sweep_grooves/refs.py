import sys
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import runner
src = '''with BuildPart() as part:
    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-15.0, -5.0), (5.0, -5.0), arc_to((5.0, 5.0)), (-15.0, 5.0), (-15.0, -2.0))
    groove(sketch_1.path_1, width=2.0, depth=2.0, profile="rect", corners="mitre")  # feature: groove_1
result = part.part
'''
r = runner.run_script(src)
print([t for t in r.edge_refs if "groove_1" in t][:40])
