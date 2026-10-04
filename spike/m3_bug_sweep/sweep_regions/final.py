from drive import run_cases
def S(b): return "with BuildPart() as part:\n" + b + "result = part.part\n"
BOX = '    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
SK = '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
cases = [
 dict(id="F1_moon_taper_hang", src=S("    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n        sketch_1.a = Pos(-4.0, 0.0) * Circle(5.0)\n        sketch_1.b = Pos(4.0, 0.0) * Circle(5.0)\n    extrude(regions(sketch_1, (-6.0, 0.0)), amount=5.0, taper=5.0)  # feature: extrude_1\n")),
 dict(id="F2_invalid_draft_cut_noop", src=S("    Box(53.7, 27.1, 23.1, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n    with sketch(on_face(face(\"box_1\", \"+X\"))) as sketch_1:  # feature: sketch_1\n        sketch_1.c = Pos(-2.397918, 1.740731) * Circle(2.531821)\n    extrude(regions(sketch_1, (0.182725, 11.764405)), amount=-32.901, taper=-3.0, mode=Mode.SUBTRACT)  # feature: extrude_1\n")),
 dict(id="F2_invalid_draft_join", src=S("    Box(53.7, 27.1, 23.1, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n    with sketch(on_face(face(\"box_1\", \"+X\"))) as sketch_1:  # feature: sketch_1\n        sketch_1.c = Pos(-2.397918, 1.740731) * Circle(2.531821)\n    extrude(regions(sketch_1, (0.182725, 11.764405)), amount=32.901, taper=-3.0)  # feature: extrude_1\n")),
 dict(id="F10_sketch_on_end_after_taper", src=S(BOX+SK+"        sketch_1.l = Line((0.0, -20.0), (0.0, 20.0))\n    extrude(regions(sketch_1, (10.0, 0.0)), amount=5.0, taper=5.0)  # feature: extrude_1\n    with sketch(on_face(face(\"extrude_1\", \"end\"))) as sketch_2:  # feature: sketch_2\n        sketch_2.c = Pos(10.0, 0.0) * Circle(2.0)\n")),
 dict(id="F11_partial_revolve_end", src=S("    with sketch(Plane.XZ) as sketch_1:  # feature: sketch_1\n        sketch_1.r = Pos(2.0, 5.0) * Rectangle(4.0, 10.0)\n        sketch_1.axis = Line((0.0, 20.0), (0.0, 30.0))\n    revolve(regions(sketch_1, (2.0, 5.0)), axis=sketch_1.axis(\"axis\"), revolution_arc=90.0)  # feature: revolve_1\n    fillet(edges_of(face(\"revolve_1\", \"end\")), radius=0.5)  # feature: fillet_1\n")),
]
r = run_cases(cases, timeout=60)
for c in cases:
    x = r[c["id"]]; print(f'{c["id"]:32s}', x["ok"], x.get("error","")[:160], x.get("volume"), x.get("line"), x.get("t"))
