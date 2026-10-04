with BuildPart() as part:
    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-6.959651, -2.821778), (-5.800949, -4.970833), (-9.00161, 1.614851), (-1.165306, 5.423318))
    groove(sketch_1.path_1, width=2.147519, depth=1.566852, profile="round", corners="round")  # feature: groove_1
result = part.part
