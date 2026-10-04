with BuildPart() as part:
    Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-7.307223, 7.833736), (-3.692371, -4.195349))
    groove(sketch_1.path_1, width=2.856721, depth=0.0, profile="circle", corners="round", mode=Mode.ADD)  # feature: rib_1
result = part.part
