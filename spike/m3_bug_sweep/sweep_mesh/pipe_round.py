with BuildPart() as part:
    Box(4000, 3000, 1000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-1000.0, -300.0), (-800.0, -300.0), (-800.0, 150.0))
    groove(sketch_1.path_1, width=130.0, depth=0.0, profile="circle", corners="round", mode=Mode.ADD)  # feature: rib_1
result = part.part
