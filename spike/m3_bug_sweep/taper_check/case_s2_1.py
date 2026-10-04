with BuildPart() as part:
    Box(16.8, 35.5, 59.9, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Y"))) as sketch_1:  # feature: sketch_1
        sketch_1.linex_1 = Line((-13.399999, 3.708741), (13.4, -12.174795))
        sketch_1.path_2 = path((6.413305, -19.10933), (-0.268426, -0.220252), arc_to((0.022608, -6.749916)))
        sketch_1.line_3 = Line((0.022608, -6.749916), (-0.359962, -49.417665))
        sketch_1.path_4 = path((9.00551, -3.588802), (7.337811, -31.365965), (-5.287384, -9.007864), (1.671632, -29.435179))
    extrude(regions(sketch_1, (-1.105392, -12.795344)), amount=5.876, taper=-8.0)  # feature: extrude_1
result = part.part
