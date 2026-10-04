with BuildPart() as part:
    Box(400.000000, 300.000000, 100.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "-Y"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-140.000000, -30.000000), (-109.342870, -30.000000), (-109.342870, -11.104208), (-151.525474, -11.104208))
    groove(sketch_1.path_1, width=34.727489, depth=21.707760, profile="rect", corners="round", mode=Mode.SUBTRACT)  # feature: groove_1
    with sketch(on_face(face("box_1", "-Y"))) as sketch_2:  # feature: sketch_2
        sketch_2.path_1 = path((130.772821, 30.325183), (16.131290, 18.291062), arc_to((-63.112737, 26.623619)), (12.236319, -37.169874), (-80.166033, -2.798104), (123.238040, -32.528484), arc_to((3.008758, -12.700997)))
    groove(sketch_2.path_1, width=34.727489, depth=21.707760, profile="v", corners="round", mode=Mode.SUBTRACT)  # feature: groove_2
result = part.part
