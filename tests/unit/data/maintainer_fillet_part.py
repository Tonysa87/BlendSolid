# BlendSolid part. The numbers below are its parameters (millimetres).
box_1_length = 500.0
box_1_width = 500.0
box_1_height = 500.0
push_1_amount = 100.0
cut_1_radius = 250.0
cut_1_height = 2000.0
cut_2_radius = 20.0
cut_2_height = 20.0
cut_3_radius = 20.0
cut_3_height = 20.0
cut_4_radius = 20.0
cut_4_height = 20.0
cut_5_radius = 20.0
cut_5_height = 20.0
fillet_1_radius = 5.0
fillet_2_radius = 5.0
fillet_3_radius = 5.0
fillet_4_radius = 5.0

with BuildPart() as part:
    Box(box_1_length, box_1_width, box_1_height, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    extrude(face("box_1", "+Z"), amount=-push_1_amount, mode=Mode.SUBTRACT)  # feature: push_1
    with Locations(Location((-250.0, 250.0, 400.0), (0.0, 0.0, 0.0))):  # feature: cut_1
        Cylinder(cut_1_radius, cut_1_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((-250.0, -200.0, 360.0), (-90.0, -90.0, 0.0))):  # feature: cut_2
        Cylinder(cut_2_radius, cut_2_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((-250.0, -60.0, 360.0), (-90.0, -90.0, 0.0))):  # feature: cut_3
        Cylinder(cut_3_radius, cut_3_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((-250.0, -200.0, 60.0), (-90.0, -90.0, 0.0))):  # feature: cut_4
        Cylinder(cut_4_radius, cut_4_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((-250.0, -40.0, 60.0), (-90.0, -90.0, 0.0))):  # feature: cut_5
        Cylinder(cut_5_radius, cut_5_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    fillet(edge_between(face("box_1", "-X"), face("cut_4", "side")), radius=fillet_1_radius)  # feature: fillet_1
    fillet(edge_between(face("box_1", "-X"), face("cut_2", "side")), radius=fillet_2_radius)  # feature: fillet_2
    fillet(edge_between(face("box_1", "-X"), face("cut_3", "side")), radius=fillet_3_radius)  # feature: fillet_3
    fillet(edges_of(face("cut_1", "side")), radius=fillet_4_radius)  # feature: fillet_4

result = part.part
