with BuildPart() as part:
    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "-Y"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((4.053926, 1.141709), (3.914217, 0.888261), (2.75228, -1.219645), (2.753019, -1.220319), arc_to((5.203252, 0.383503)), closed=True)
    groove(sketch_1.path_1, width=1.803477, depth=2.110572, profile="circle", corners="round", mode=Mode.ADD)  # feature: rib_1
result = part.part
