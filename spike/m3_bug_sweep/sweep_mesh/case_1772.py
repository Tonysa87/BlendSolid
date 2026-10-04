with BuildPart() as part:
    Box(4000.000000, 3000.000000, 1000.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-1400.000000, -900.000000), (-15.991937, -900.000000), arc_to((-15.991937, -82.648345)), (-758.586984, -82.648345), (-758.586984, -1025.460787), (523.871330, -1025.460787), arc_to((1136.193926, -413.138191)), (1136.193926, 869.787106), (1700.000000, 869.787106), arc_to((1700.000000, 1741.004959)))
    groove(sketch_1.path_1, width=275.252605, depth=206.508081, profile="round", corners="mitre", mode=Mode.ADD)  # feature: groove_1
    chamfer(part.faces().sort_by(Axis.Z)[-1].edges(), length=49.789571)  # feature: blend_1
result = part.part
