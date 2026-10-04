with BuildPart() as part:
    Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-15.0, 0.0), (15.0, 0.0))
    groove(sketch_1.path_1, width=4.0, depth=4.0, profile="round", mode=Mode.SUBTRACT)  # feature: groove_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_2:  # feature: sketch_2
        sketch_2.path_1 = path((0.0, -12.0), (0.0, 12.0))
    groove(sketch_2.path_1, width=4.0, depth=4.0, profile="round", mode=Mode.SUBTRACT)  # feature: groove_2
result = part.part
