# BlendSolid part. The numbers below are its parameters (millimetres).
box_1_length = 40.0
box_1_width = 30.0
box_1_height = 20.0
boss_1_radius = 6.0
boss_1_height = 25.0
fillet_1_radius = 5.0

with BuildPart() as part:
    Box(box_1_length, box_1_width, box_1_height, align=Align.MIN)  # feature: box_1
    with Locations((box_1_length / 2, box_1_width / 2, 0)):  # feature: boss_1
        Cylinder(boss_1_radius, boss_1_height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    fillet(part.edges().filter_by(Axis.Z).sort_by_distance((0, 0, 0))[0], radius=fillet_1_radius)  # feature: fillet_1

result = part.part
