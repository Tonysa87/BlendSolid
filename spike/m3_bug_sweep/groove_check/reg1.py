with BuildPart() as part:
    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-11.005622, -6.050002), (-11.037672, -5.98361), (-10.97514, -5.953424), arc_to((-9.911976, -5.440201)))
    groove(sketch_1.path_1, width=1.828698, depth=2.754514, profile="v", corners="round", mode=Mode.ADD)  # feature: rib_1
result = part.part
