"""Representative build123d history scripts covering the MVP feature catalog.

Each script assigns the final shape to `result`. Run by b123d_blender_test.py (lite worker inside Blender)
and by b123d_reference.py (full build123d install) so volumes can be compared.
"""
import os
import tempfile

STEP_PATH = os.path.join(tempfile.gettempdir(), "blendsolid_b123d_roundtrip.step")
# same TTF file on both platforms (Windows reads it from the WSL share), to separate font effects from lite effects
FONT = (r"\\wsl.localhost\Ubuntu-24.04\usr\share\fonts\truetype\dejavu\DejaVuSans.ttf" if os.name == "nt"
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

SCRIPTS = {
    # the milestone-0 model, with a click-like selector for the filleted edge
    "spike_model": """
with BuildPart() as p:
    Box(40, 30, 20, align=Align.MIN)
    with Locations((20, 15, 0)):
        Cylinder(6, 25, align=(Align.CENTER, Align.CENTER, Align.MIN))
    edge = p.edges().filter_by(Axis.Z).sort_by_distance((0, 0, 0))[0]
    fillet(edge, radius=5)
result = p.part
""",
    "sketch_extrude_holes_chamfer": """
with BuildPart() as p:
    with BuildSketch():
        RectangleRounded(80, 50, 8)
        with GridLocations(60, 30, 2, 2):
            Circle(4, mode=Mode.SUBTRACT)
        SlotCenterToCenter(30, 8, mode=Mode.SUBTRACT)
    extrude(amount=10)
    chamfer(p.edges().group_by(Axis.Z)[-1], length=1)
result = p.part
""",
    "revolve": """
with BuildPart() as p:
    with BuildSketch(Plane.XZ):
        with BuildLine():
            Polyline((0, 0), (20, 0), (20, 5), (8, 10), (8, 40), (0, 40), close=True)
        make_face()
    revolve(axis=Axis.Z)
result = p.part
""",
    "loft": """
with BuildPart() as p:
    with BuildSketch():
        Rectangle(30, 30)
    with BuildSketch(Plane.XY.offset(40)):
        Circle(10)
    loft()
result = p.part
""",
    "shell": """
with BuildPart() as p:
    Box(40, 30, 20)
    offset(amount=-2, openings=p.faces().sort_by(Axis.Z)[-1])
result = p.part
""",
    "sweep": """
with BuildPart() as p:
    with BuildLine() as path:
        Spline((0, 0, 0), (20, 10, 10), (40, 0, 30), tangents=((1, 0, 0), (0, 0, 1)))
    with BuildSketch(Plane(origin=path.line @ 0, z_dir=path.line % 0)):
        Circle(3)
    sweep()
result = p.part
""",
    "mirror_boolean": """
with BuildPart() as p:
    Box(20, 20, 10, align=(Align.MIN, Align.CENTER, Align.MIN))
    Cylinder(5, 10, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    mirror(about=Plane.YZ)
result = p.part
""",
    "text_engrave": """
with BuildPart() as p:
    Box(60, 20, 5)
    with BuildSketch(p.faces().sort_by(Axis.Z)[-1]):
        Text("CAD", font_size=10)
    extrude(amount=-1, mode=Mode.SUBTRACT)
result = p.part
""",
    "text_engrave_fixed_font": f"""
with BuildPart() as p:
    Box(60, 20, 5)
    with BuildSketch(p.faces().sort_by(Axis.Z)[-1]):
        Text("CAD", font_size=10, font_path=r"{FONT}")
    extrude(amount=-1, mode=Mode.SUBTRACT)
result = p.part
""",
    "step_roundtrip": f"""
part = Box(10, 20, 30) - Cylinder(4, 30)
export_step(part, r"{STEP_PATH}")
result = import_step(r"{STEP_PATH}")
""",
    "param_at_point": """
e = Edge.make_spline([(0, 0, 0), (10, 5, 0), (20, 0, 5)])
u = e.param_at_point(e @ 0.37)
assert abs(u - 0.37) < 1e-3, u
result = Box(1, 1, 1)
""",
}
