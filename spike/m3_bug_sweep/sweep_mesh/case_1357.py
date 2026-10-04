with BuildPart() as part:
    with sketch(Plane.XZ) as sketch_1:  # feature: sketch_1
        sketch_1.r = Pos(1429.786159, 0.0) * Circle(138.951595)
        sketch_1.axis = Line((0.0, -4000.000000), (0.0, 4000.000000))
    revolve(regions(sketch_1, (1429.786159, 0.000000)), axis=sketch_1.axis("axis"), revolution_arc=77.561992)  # feature: revolve_1
result = part.part
