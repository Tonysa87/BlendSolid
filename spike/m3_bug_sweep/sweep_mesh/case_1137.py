with BuildPart() as part:
    Box(40.000000, 30.000000, 10.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.r = Polygon((-5.738046, -3.012799), (5.738046, -3.012799), (5.738046, -0.666785), (-3.392032, -0.666785), (-3.392032, 3.012799), (-5.738046, 3.012799), align=None)
    extrude(regions(sketch_1, (-4.565039, -1.839792)), amount=5.332352, taper=-4.864463, mode=Mode.ADD)  # feature: extrude_1
    fillet(part.edges().filter_by(Axis.Z, reverse=True).group_by(Axis.Z)[-1], 0.899336)  # feature: blend_1
result = part.part
