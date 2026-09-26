# BlendSolid part. The numbers below are its parameters: edit them here or in the BlendSolid panel.
# All lengths are in millimetres (BlendSolid converts them to the scene's units).
length = 40.0
width = 30.0
height = 20.0
boss_radius = 6.0
boss_height = 25.0
fillet_radius = 5.0

with BuildPart() as part:
    Box(length, width, height, align=Align.MIN)
    with Locations((length / 2, width / 2, 0)):
        Cylinder(boss_radius, boss_height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    fillet(part.edges().filter_by(Axis.Z).sort_by_distance((0, 0, 0))[0], radius=fillet_radius)

result = part.part
