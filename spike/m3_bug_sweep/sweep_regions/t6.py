from drive import run_cases
def S(b): return "with BuildPart() as part:\n" + b + "result = part.part\n"
BOX = '    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
cases = []
for role in ("+Z", "-Y", "+X"):
  SK = f'    with sketch(on_face(face("box_1", "{role}"))) as sketch_1:  # feature: sketch_1\n'
  for t in (3.0, -3.0):
    cases += [
     dict(id=f"face_minus_square_{role}_{t}", src=S(BOX+SK+"        sketch_1.r = Pos(0.0, 8.0) * Rectangle(4.0, 4.0)\n"+f"    extrude(regions(sketch_1, (0.0, 1.0)), amount=-5.0, taper={t}, mode=Mode.SUBTRACT)  # feature: extrude_1\n")),
     dict(id=f"face_minus_circle_{role}_{t}", src=S(BOX+SK+"        sketch_1.r = Pos(0.0, 8.0) * Circle(2.0)\n"+f"    extrude(regions(sketch_1, (0.0, 1.0)), amount=-5.0, taper={t}, mode=Mode.SUBTRACT)  # feature: extrude_1\n")),
     dict(id=f"rect_minus_square_{role}_{t}", src=S(BOX+SK+"        sketch_1.o = Pos(0.0, 8.0) * Rectangle(14.0, 10.0)\n        sketch_1.r = Pos(0.0, 8.0) * Rectangle(4.0, 4.0)\n"+f"    extrude(regions(sketch_1, (0.0, 4.0)), amount=-5.0, taper={t}, mode=Mode.SUBTRACT)  # feature: extrude_1\n")),
     dict(id=f"face_circle_cross_edge_{role}_{t}", src=S(BOX+SK+"        sketch_1.r = Circle(2.5)\n"+f"    extrude(regions(sketch_1, (5.0, 5.0)), amount=-5.0, taper={t}, mode=Mode.SUBTRACT)  # feature: extrude_1\n")),
    ]
r = run_cases(cases)
for c in cases:
    x = r[c["id"]]; print(f'{c["id"]:36s}', x["ok"], x.get("error","")[:120], round(x.get("volume") or 0, 3), x.get("line"))
