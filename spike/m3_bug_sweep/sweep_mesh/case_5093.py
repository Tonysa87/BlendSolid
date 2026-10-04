with BuildPart() as part:
    Box(4000.000000, 3000.000000, 1000.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-1400.000000, -900.000000), (-275.639812, -900.000000), arc_to((432.073538, -192.286650)), (432.073538, 1083.138184), arc_to((-293.111636, 1808.323358)), (-1272.218243, 1275.000000), arc_to((-1614.455925, 932.762319)), (-1614.455925, -364.866131), arc_to((-889.079443, -1090.242612)), (-207.140496, -1090.242612), arc_to((150.462508, -732.639608)))
    groove(sketch_1.path_1, width=300.093846, depth=446.337563, profile="round", corners="round", mode=Mode.ADD)  # feature: groove_1
    fillet(part.faces().sort_by(Axis.Z)[-1].edges(), radius=94.613002)  # feature: blend_1
result = part.part
