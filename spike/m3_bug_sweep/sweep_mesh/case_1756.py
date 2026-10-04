with BuildPart() as part:
    Box(5000.000000, 3750.000000, 1250.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "-Y"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((451.194817, -259.744473), (1718.249350, -88.430303), (-604.269853, -199.903726), (-1921.721140, -495.324134), (1718.765978, -178.126209))
    groove(sketch_1.path_1, width=389.326762, depth=499.312800, profile="v", corners="round", mode=Mode.ADD)  # feature: groove_1
    with sketch(on_face(face("box_1", "-Y"))) as sketch_2:  # feature: sketch_2
        sketch_2.c = Pos(-601.188571, -132.858305) * Circle(809.291068)
    extrude(regions(sketch_2, (-601.188571, -132.858305)), dir=-sketch_2.plane.z_dir, until=Until.LAST, mode=Mode.SUBTRACT)  # feature: hole_1
result = part.part
