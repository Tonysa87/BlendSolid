with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-8.767072, -7.525241), (-5.075659, 2.677325), arc_to((9.778834, -11.274154)), (-2.340025, -4.375195))
    groove(sketch_1.path_1, width=2.214092, depth=1.678205, profile="v", corners="mitre", mode=Mode.SUBTRACT)  # feature: groove_1
    chamfer(part.edges().filter_by(GeomType.LINE, reverse=True), 0.348713)  # feature: blend_1
result = part.part
