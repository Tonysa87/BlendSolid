with BuildPart() as part:
    Box(38.1, 23.1, 22.5, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "-X"))) as sketch_1:  # feature: sketch_1
        sketch_1.rect_1 = Pos(-0.932747, -15.615814) * Rectangle(17.963384, 7.66076)
        sketch_1.circle_2 = Pos(0.919655, 2.789569) * Circle(0.967168)
        sketch_1.poly_3 = Polygon((-17.89497, -11.491267), (-18.901631, -11.504522), (-20.846851, -12.375423), (-20.906814, -12.426856), (-14.717284, -16.733582), align=None)
        sketch_1.line_4 = Line((7.570226, -2.722236), (-10.306787, -28.529583))
        sketch_1.axis = Line((-25.95687, -62.5), (-25.95687, -57.5))
    extrude(regions(sketch_1, (0.919655, 2.789569)), amount=14.399, taper=3.0)  # feature: extrude_1
result = part.part
