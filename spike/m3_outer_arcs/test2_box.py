# BlendSolid part. The numbers below are its parameters (millimetres).
box_1_length = 100.0
box_1_width = 60.575722
box_1_height = 20.0
cylinder_1_radius = 10.0
cylinder_1_height = 10.0
cylinder_2_radius = 10.0
cylinder_2_height = 10.0
cut_1_radius = 10.0
cut_1_height = 10.0
cut_2_radius = 5.286958
cut_2_height = 19.307123
cylinder_3_radius = 3.668386
cylinder_3_height = 5.41221
cut_3_radius = 4.320889
cut_3_height = 15.434737
cut_4_radius = 10.0
cut_4_height = 60.0
fillet_1_radius = 5.710001

with BuildPart() as part:
    Box(box_1_length, box_1_width, box_1_height, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with Locations(Location((20.0, 0.0, 20.0), (0.0, 0.0, 0.0))):  # feature: cylinder_1
        Cylinder(cylinder_1_radius, cylinder_1_height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(Location((-50.0, -30.0, 20.0), (0.0, 0.0, 0.0))):  # feature: cylinder_2
        Cylinder(cylinder_2_radius, cylinder_2_height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(Location((-20.0, 10.0, 20.0), (0.0, 0.0, 0.0))):  # feature: cut_1
        Cylinder(cut_1_radius, cut_1_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((-47.056299, 30.0, 9.548634), (-90.0, 0.0, 0.0))):  # feature: cut_2
        Cylinder(cut_2_radius, cut_2_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((-50.0, -9.346083, 10.639526), (-90.0, -90.0, 0.0))):  # feature: cylinder_3
        Cylinder(cylinder_3_radius, cylinder_3_height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(Location((18.999979, 30.0, 8.944545), (-90.0, 0.0, 0.0))):  # feature: cut_3
        Cylinder(cut_3_radius, cut_3_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((45.0, 25.0, 20.0), (0.0, 0.0, 0.0))):  # feature: cut_4
        Cylinder(cut_4_radius, cut_4_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    fillet(edge_between(face("box_1", "+Y"), face("box_1", "+Z")), radius=fillet_1_radius)  # feature: fillet_1

result = part.part

