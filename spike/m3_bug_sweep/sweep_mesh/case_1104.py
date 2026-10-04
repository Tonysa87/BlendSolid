with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+X"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((2.248554, -3.925664), (-5.012185, 0.448471), (-10.573386, -1.636359))
    groove(sketch_1.path_1, width=3.472357, depth=1.984244, profile="rect", corners="round", mode=Mode.ADD)  # feature: groove_1
    with sketch(on_face(face("box_1", "+X"))) as sketch_2:  # feature: sketch_2
        sketch_2.c = Pos(-0.509092, -0.607555) * Circle(6.469870)
    extrude(regions(sketch_2, (-0.509092, -0.607555)), dir=-sketch_2.plane.z_dir, until=Until.LAST, mode=Mode.SUBTRACT)  # feature: hole_1
result = part.part
