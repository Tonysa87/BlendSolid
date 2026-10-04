with BuildPart() as part:
    Box(4000.000000, 3000.000000, 1000.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+X"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-1050.000000, -300.000000), (-866.215596, -300.000000), (-866.215596, 152.089707))
    groove(sketch_1.path_1, width=131.649531, depth=0.000000, profile="circle", corners="round", mode=Mode.ADD)  # feature: groove_1
result = part.part
