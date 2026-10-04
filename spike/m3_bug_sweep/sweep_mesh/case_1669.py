with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-14.000000, -9.000000), (-4.806577, -9.000000), arc_to((-4.806577, 5.517763)), (-13.713055, 5.517763), arc_to((-20.627567, -1.396749)), (-17.000000, -12.577268), (-11.793875, -12.577268), arc_to((-9.011671, -9.795063)))
    groove(sketch_1.path_1, width=0.744056, depth=0.946975, profile="round", corners="mitre", mode=Mode.ADD)  # feature: groove_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_2:  # feature: sketch_2
        sketch_2.path_1 = path((5.765546, -7.411650), (-0.256466, -3.056210), (-5.834916, -10.116764), arc_to((3.250790, 10.209057)), arc_to((-0.202193, 3.400132)))
    groove(sketch_2.path_1, width=0.744056, depth=0.946975, profile="round", corners="round", mode=Mode.ADD)  # feature: groove_2
result = part.part
