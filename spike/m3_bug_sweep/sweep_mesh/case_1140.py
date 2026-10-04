with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-5.287279, -10.590732), (4.465934, -7.227565), (11.255022, -3.768143), arc_to((1.658038, -7.152250)), (6.214241, -5.792007))
    groove(sketch_1.path_1, width=0.828899, depth=0.664371, profile="v", corners="round", mode=Mode.ADD)  # feature: groove_1
    fillet(part.faces().sort_by(Axis.Z)[-1].edges(), radius=0.117286)  # feature: blend_1
result = part.part
