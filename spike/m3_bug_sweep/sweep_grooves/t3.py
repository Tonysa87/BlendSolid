with BuildPart() as part:
    Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-10.0, 0.0), (0.0, 0.0), (0.0, 5.0))
    groove(sketch_1.path_1, width=2.0, depth=2.0, profile="v", corners="mitre")  # feature: groove_1
    fillet(edge_between(face("groove_1", "wall"), face("groove_1", "wall"), near=(-5.0, 0.0, 8.0)), radius=0.2)  # feature: fillet_1
result = part.part
