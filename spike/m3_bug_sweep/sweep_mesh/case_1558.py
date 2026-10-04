with BuildPart() as part:
    Box(0.400000, 0.300000, 0.100000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+X"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-0.105000, -0.030000), (-0.064162, -0.030000), arc_to((-0.050121, -0.015958)), (-0.050121, 0.025958), (-0.068776, 0.042500), (-0.076636, -0.000849))
    groove(sketch_1.path_1, width=0.012537, depth=0.008688, profile="rect", corners="round", mode=Mode.ADD)  # feature: groove_1
    fillet(part.faces().sort_by(Axis.Z)[-1].edges(), radius=0.004532)  # feature: blend_1
result = part.part
