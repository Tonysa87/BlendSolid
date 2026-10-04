with BuildPart() as part:
    Box(4000.000000, 3000.000000, 1000.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-1400.000000, -900.000000), (-652.958550, -900.000000), arc_to((-652.958550, 553.142547)), (-1485.692851, 553.142547), arc_to((-1485.692851, -815.634507)))
    groove(sketch_1.path_1, width=192.537460, depth=125.556271, profile="round", corners="mitre", mode=Mode.ADD)  # feature: groove_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_2:  # feature: sketch_2
        sketch_2.path_1 = path((-1599.132095, 1013.802504), (-288.473567, 400.043466), arc_to((1301.008320, -690.812193)), (-1585.044040, -683.002270), arc_to((253.732248, 747.771876)), (-522.738148, 757.539464), (311.897741, 1081.489409))
    groove(sketch_2.path_1, width=192.537460, depth=0.000000, profile="circle", corners="round", mode=Mode.ADD)  # feature: groove_2
result = part.part
