with BuildPart() as part:
    Box(4.000000, 3.000000, 1.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+X"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-1.050000, -0.300000), (-0.692698, -0.300000), (-0.692698, -0.425000), arc_to((-0.494416, -0.623282)), (-0.272442, -0.425000), arc_to((-0.272442, 0.048513)), (-0.566818, 0.048513), arc_to((-0.735710, -0.120379)), (-0.735710, -0.425000))
    groove(sketch_1.path_1, width=0.335017, depth=0.335017, profile="round", corners="round", mode=Mode.ADD)  # feature: groove_1
    with sketch(on_face(face("box_1", "+X"))) as sketch_2:  # feature: sketch_2
        sketch_2.c = Pos(-0.470701, 0.121408) * Circle(0.857123)
    extrude(regions(sketch_2, (-0.470701, 0.121408)), dir=-sketch_2.plane.z_dir, until=Until.LAST, mode=Mode.SUBTRACT)  # feature: hole_1
result = part.part
