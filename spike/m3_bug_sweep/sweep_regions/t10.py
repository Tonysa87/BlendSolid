from drive import run_cases
def S(b): return "with BuildPart() as part:\n" + b + "result = part.part\n"
REV = ("    with sketch(Plane.XZ) as sketch_1:  # feature: sketch_1\n        sketch_1.r = Polygon((0.0, 0.0), (5.0, 2.0), (5.0, -2.0), align=None)\n"
       "        sketch_1.ax = Line((0.0, 20.0), (0.0, 30.0))\n    revolve(regions(sketch_1, (3.0, 0.0)), axis=sketch_1.axis(\"ax\"), revolution_arc=360)  # feature: revolve_1\n")
L = ("    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n"
     "    with sketch(on_face(face(\"box_1\", \"+Z\"))) as sketch_1:  # feature: sketch_1\n"
     "        sketch_1.r = Rectangle(20.0, 10.0)\n        sketch_1.l = Line((0.0, -5.0), (0.0, 5.0))\n"
     "    extrude(regions(sketch_1, (5.0, 0.0), (-5.0, 0.0)), amount=5.0, taper=10.0)  # feature: extrude_1\n")
cases = [dict(id="rev_apex", src=S(REV)),
         dict(id="rev_apex_fillet", src=S(REV + '    fillet(edge_between(face("revolve_1", "r"), face("revolve_1", "r"), near=(-5.0, 0.0, 2.0)), radius=0.2)  # feature: fillet_1\n')),
         dict(id="same_label", src=S(L)),
         dict(id="same_label_fillet", src=S(L + '    fillet(edge_between(face("extrude_1", "l"), face("extrude_1", "l")), radius=0.2)  # feature: fillet_1\n'))]
r = run_cases(cases)
for c in cases:
    x = r[c["id"]]; print(c["id"], x["ok"], x["error"][:200], x.get("line"), x.get("volume"), x.get("warnings"))
