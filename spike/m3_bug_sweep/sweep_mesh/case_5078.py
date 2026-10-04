with BuildPart() as part:
    Box(5000.000000, 3750.000000, 1250.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-1750.000000, -1125.000000), (-903.210993, -1125.000000), arc_to((-485.015505, -706.804512)), (-485.015505, 876.528078), (-1580.862129, 876.528078), arc_to((-1892.867954, 564.522253)), (-1892.867954, -476.244931), arc_to((-188.251492, -476.244931)))
    groove(sketch_1.path_1, width=291.032914, depth=131.665300, profile="v", corners="mitre", mode=Mode.SUBTRACT)  # feature: groove_1
    chamfer(part.edges().filter_by(GeomType.LINE, reverse=True), 26.316577)  # feature: blend_1
result = part.part
