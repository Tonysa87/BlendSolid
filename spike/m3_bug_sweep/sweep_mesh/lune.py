with BuildPart() as part:
    Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+X"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-10.0, -3.0), (-8.0, -3.0), (-8.0, 2.0))
    groove(sketch_1.path_1, width=4.0, depth=0.0, profile="circle", corners="round", mode=Mode.ADD)  # feature: rib_1
result = part.part
