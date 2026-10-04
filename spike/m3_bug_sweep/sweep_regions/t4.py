from drive import run_cases
def S(b): return "with BuildPart() as part:\n" + b + "result = part.part\n"
BOX = '    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
SK = '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
cases = []
for t in (-3.0, 3.0):
  cases += [
   dict(id=f"facerest_tapercut_{t}", src=S(BOX+SK+"        sketch_1.c = Circle(3.0)\n"+f"    extrude(regions(sketch_1, (10.0, 10.0)), amount=-5.0, taper={t}, mode=Mode.SUBTRACT)  # feature: extrude_1\n")),
   dict(id=f"half_tapercut_{t}", src=S(BOX+SK+"        sketch_1.l = Line((0.0, -20.0), (0.0, 20.0))\n"+f"    extrude(regions(sketch_1, (10.0, 0.0)), amount=-5.0, taper={t}, mode=Mode.SUBTRACT)  # feature: extrude_1\n")),
   dict(id=f"inner_tapercut_{t}", src=S(BOX+SK+"        sketch_1.c = Rectangle(10.0, 10.0)\n"+f"    extrude(regions(sketch_1, (0.0, 0.0)), amount=-5.0, taper={t}, mode=Mode.SUBTRACT)  # feature: extrude_1\n")),
   dict(id=f"facerest_taperjoin_{t}", src=S(BOX+SK+"        sketch_1.c = Circle(3.0)\n"+f"    extrude(regions(sketch_1, (10.0, 10.0)), amount=5.0, taper={t})  # feature: extrude_1\n")),
  ]
cases.append(dict(id="thin_ring_revolve", src=S("    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n        sketch_1.c = Pos(0.0, 50.0) * Circle(2.0)\n        sketch_1.axis = Line((-10.0, 0.0), (10.0, 0.0))\n    revolve(regions(sketch_1, (0.0, 50.0)), axis=sketch_1.axis(\"axis\"), revolution_arc=360.0)  # feature: revolve_1\n")))
cases.append(dict(id="thin_ring_revolve_rect", src=S("    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n        sketch_1.c = Pos(0.0, 50.0) * Rectangle(2.0, 2.0)\n        sketch_1.axis = Line((-10.0, 0.0), (10.0, 0.0))\n    revolve(regions(sketch_1, (0.0, 50.0)), axis=sketch_1.axis(\"axis\"), revolution_arc=360.0)  # feature: revolve_1\n")))
r = run_cases(cases)
for c in cases:
    x = r[c["id"]]; print(c["id"], x["ok"], x.get("error","")[:150], x.get("volume"), x.get("line"))
