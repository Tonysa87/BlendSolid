with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+X"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-9.672919, -1.073993), (-11.581086, 2.814646), (1.751010, 2.675622), (-10.897977, -3.034718), (0.140977, 1.372897), arc_to((1.718385, 1.249130)))
    groove(sketch_1.path_1, width=2.036106, depth=0.000000, profile="circle", corners="round", mode=Mode.ADD)  # feature: groove_1
    chamfer(part.edges().filter_by(GeomType.LINE, reverse=True), 0.368401)  # feature: blend_1
result = part.part
