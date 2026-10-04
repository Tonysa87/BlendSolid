with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-14.000000, -9.000000), (-9.449773, -9.000000), (-9.449773, 5.553965))
    groove(sketch_1.path_1, width=2.856721, depth=3.861729, profile="rect", corners="mitre", mode=Mode.ADD)  # feature: groove_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_2:  # feature: sketch_2
        sketch_2.path_1 = path((-7.307223, 7.833736), (-3.692371, -4.195349))
    groove(sketch_2.path_1, width=2.856721, depth=0.000000, profile="circle", corners="round", mode=Mode.ADD)  # feature: groove_2
result = part.part
