with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-14.000000, -9.000000), (-3.756960, -9.000000), (-3.756960, 1.730749), arc_to((-10.643163, 1.730749)))
    groove(sketch_1.path_1, width=1.824987, depth=0.851466, profile="v", corners="round", mode=Mode.SUBTRACT)  # feature: groove_1
    fillet(part.edges().filter_by(GeomType.LINE, reverse=True), 0.506868)  # feature: blend_1
result = part.part
