with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-14.000000, -9.000000), (-8.813020, -9.000000), (-8.813020, -12.750000))
    groove(sketch_1.path_1, width=1.908656, depth=1.752957, profile="v", corners="round", mode=Mode.ADD)  # feature: groove_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_2:  # feature: sketch_2
        sketch_2.path_1 = path((5.313706, -5.923891), (-6.973150, -1.680337), arc_to((2.100781, -0.381663)), (-15.656575, 1.226397), (4.808057, -10.596919), arc_to((9.981319, -7.725527)))
    groove(sketch_2.path_1, width=1.908656, depth=1.752957, profile="v", corners="round", mode=Mode.ADD)  # feature: groove_2
result = part.part
