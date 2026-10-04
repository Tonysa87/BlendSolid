from drive import run_cases
src = '''with BuildPart() as part:
    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.line_1 = Line((-30.0, 0.0), (30.0, 0.0))
    extrude(regions(sketch_1, (0.0, 5.0)), amount=5.0)  # feature: extrude_1
result = part.part
'''
print(run_cases([dict(id="a", src=src)]))
