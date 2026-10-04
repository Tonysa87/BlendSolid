with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "-Y"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-14.000000, -3.000000), (-9.235699, -3.000000), (-9.235699, -0.794736), (-13.014612, -2.050031), (-12.245341, -4.250000), (-14.496313, -4.250000), arc_to((-16.040207, -7.329820)), (-15.435331, -4.250000))
    groove(sketch_1.path_1, width=1.672625, depth=0.000000, profile="circle", corners="mitre", mode=Mode.ADD)  # feature: groove_1
    fillet(part.faces().sort_by(Axis.Z)[-1].edges(), radius=0.114068)  # feature: blend_1
result = part.part
