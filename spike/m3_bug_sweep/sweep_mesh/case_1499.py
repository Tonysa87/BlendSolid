with BuildPart() as part:
    Box(5000.000000, 3750.000000, 1250.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((1509.090406, -384.621699), (-39.855079, -420.494540), (1216.741132, -592.082559), (444.811838, 614.034949), (711.981302, 531.074988), (1913.019096, -1254.328039), (678.799724, 1463.394398))
    groove(sketch_1.path_1, width=359.704918, depth=555.116014, profile="v", corners="round", mode=Mode.SUBTRACT)  # feature: groove_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_2:  # feature: sketch_2
        sketch_2.c = Pos(1202.000447, 763.771251) * Circle(843.225217)
    extrude(regions(sketch_2, (1202.000447, 763.771251)), dir=-sketch_2.plane.z_dir, until=Until.LAST, mode=Mode.SUBTRACT)  # feature: hole_1
result = part.part
