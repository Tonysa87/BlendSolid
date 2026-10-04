with BuildPart() as part:
    Box(5000.000000, 3750.000000, 1250.000000, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-1750.000000, -1125.000000), (-191.201832, -1125.000000), arc_to((471.473487, -462.324682)), (471.473487, 543.420067), arc_to((-416.823073, 543.420067)), (-416.823073, -227.706127), (-1958.366781, -227.706127))
    groove(sketch_1.path_1, width=367.860620, depth=486.891576, profile="rect", corners="mitre", mode=Mode.ADD)  # feature: groove_1
    with sketch(on_face(face("box_1", "+Z"))) as sketch_2:  # feature: sketch_2
        sketch_2.path_1 = path((-171.416419, -1002.811064), (1065.882240, 405.717608), (-875.238974, -1115.951821), arc_to((-1648.393945, 905.972066)), arc_to((1544.884233, 734.102846)), arc_to((1423.890553, 1194.127419)))
    groove(sketch_2.path_1, width=367.860620, depth=0.000000, profile="circle", corners="round", mode=Mode.ADD)  # feature: groove_2
result = part.part
