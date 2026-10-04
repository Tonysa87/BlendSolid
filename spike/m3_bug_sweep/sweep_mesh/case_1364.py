with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "-Y"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-13.303955, -0.113343), (10.367347, 3.246071))
    groove(sketch_1.path_1, width=2.905572, depth=2.270790, profile="v", corners="round", mode=Mode.ADD)  # feature: groove_1
    with sketch(on_face(face("box_1", "-Y"))) as sketch_2:  # feature: sketch_2
        sketch_2.c = Pos(-8.159200, 1.429743) * Circle(7.205709)
    extrude(regions(sketch_2, (-8.159200, 1.429743)), dir=-sketch_2.plane.z_dir, until=Until.LAST, mode=Mode.SUBTRACT)  # feature: hole_1
result = part.part
