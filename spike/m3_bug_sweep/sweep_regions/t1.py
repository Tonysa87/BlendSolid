import sys
from drive import run_cases
BOX = '    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
SK = '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
def S(body): return f"\nwith BuildPart() as part:\n{body}result = part.part\n"
cases = [
 dict(id="ring_notail", src=S(BOX+SK+"        sketch_1.r = Rectangle(20.0, 10.0)\n        sketch_1.c = Circle(2.0)\n    extrude(regions(sketch_1, (7.0, 3.0)), amount=5.0)  # feature: extrude_1\n")),
 dict(id="ring_circles", src=S(BOX+SK+"        sketch_1.r = Circle(6.0)\n        sketch_1.c = Circle(2.0)\n    extrude(regions(sketch_1, (4.0, 0.0)), amount=5.0)  # feature: extrude_1\n")),
 dict(id="ring_box_part", src=S(BOX+"    with Locations(Location((0.0, 0.0, 20.0), (0.0, 0.0, 0.0))):  # feature: boss_1\n        Cylinder(6.0, 5.0, align=(Align.CENTER, Align.CENTER, Align.MIN))\n        Cylinder(2.0, 5.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)\n")),
 dict(id="tiny1e-6", src=S(BOX+SK+"        sketch_1.c = Circle(5.0)\n    extrude(regions(sketch_1, (0.0, 0.0)), amount=1e-6)  # feature: extrude_1\n")),
 dict(id="tiny1e-5", src=S(BOX+SK+"        sketch_1.c = Circle(5.0)\n    extrude(regions(sketch_1, (0.0, 0.0)), amount=1e-5)  # feature: extrude_1\n")),
 dict(id="tiny1e-7", src=S(BOX+SK+"        sketch_1.c = Circle(5.0)\n    extrude(regions(sketch_1, (0.0, 0.0)), amount=1e-7)  # feature: extrude_1\n")),
 dict(id="one_tangent_circle_taper", src=S(BOX+SK+"        sketch_1.a = Pos(-5.0, 0.0) * Circle(5.0)\n    extrude(regions(sketch_1, (-5.0, 0.0)), amount=5.0, taper=-5.0)  # feature: extrude_1\n")),
 dict(id="tangent_circles_taper_sep", src=S(BOX+SK+"        sketch_1.a = Pos(-5.0, 0.0) * Circle(5.0)\n        sketch_1.b = Pos(5.0, 0.0) * Circle(5.0)\n    extrude(regions(sketch_1, (-5.0, 0.0)), amount=5.0, taper=-5.0)  # feature: extrude_1\n    extrude(regions(sketch_1, (5.0, 0.0)), amount=5.0, taper=-5.0)  # feature: extrude_2\n")),
 dict(id="overlap_circles_taper_two", src=S(BOX+SK+"        sketch_1.a = Pos(-4.0, 0.0) * Circle(5.0)\n        sketch_1.b = Pos(4.0, 0.0) * Circle(5.0)\n    extrude(regions(sketch_1, (-6.0, 0.0), (6.0, 0.0), (0.0, 0.0)), amount=5.0, taper=5.0)  # feature: extrude_1\n")),
 dict(id="overlap_circles_two", src=S(BOX+SK+"        sketch_1.a = Pos(-4.0, 0.0) * Circle(5.0)\n        sketch_1.b = Pos(4.0, 0.0) * Circle(5.0)\n    extrude(regions(sketch_1, (-6.0, 0.0), (6.0, 0.0), (0.0, 0.0)), amount=5.0)  # feature: extrude_1\n")),
 dict(id="plane_tangent_circles_taper", src=S("    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n        sketch_1.a = Pos(-5.0, 0.0) * Circle(5.0)\n        sketch_1.b = Pos(5.0, 0.0) * Circle(5.0)\n    extrude(regions(sketch_1, (-5.0, 0.0), (5.0, 0.0)), amount=5.0, taper=-5.0)  # feature: extrude_1\n")),
 dict(id="plane_tangent_circles", src=S("    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n        sketch_1.a = Pos(-5.0, 0.0) * Circle(5.0)\n        sketch_1.b = Pos(5.0, 0.0) * Circle(5.0)\n    extrude(regions(sketch_1, (-5.0, 0.0), (5.0, 0.0)), amount=5.0)  # feature: extrude_1\n")),
]
r = run_cases(cases)
for c in cases:
    x = r[c["id"]]; print(c["id"], x["ok"], x.get("error","")[:200], x.get("volume"), x.get("faces"), x.get("face_refs"))
