with BuildPart() as part:
    Box(4.000000, 3.000000, 1.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "-Y"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-1.400000, -0.300000), (-1.026518, -0.300000), (-1.168934, -0.058064), (-1.305147, -0.138246))
    groove(sketch_1.path_1, width=0.289591, depth=0.322862, profile="rect", corners="round", mode=Mode.ADD)  # feature: groove_1
    with sketch(on_face(face("box_1", "-Y"))) as sketch_2:  # feature: sketch_2
        sketch_2.path_1 = path((0.462030, 0.230717), (-0.348792, -0.180597), (1.177862, 0.105026), (-0.435150, 0.241305), (0.416574, -0.279684), (0.214863, -0.078713), (-0.712585, -0.362872))
    groove(sketch_2.path_1, width=0.289591, depth=0.000000, profile="circle", corners="mitre", mode=Mode.ADD)  # feature: groove_2
result = part.part
