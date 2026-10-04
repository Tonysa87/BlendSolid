from drive import run_cases
def S(b): return "with BuildPart() as part:\n" + b + "result = part.part\n"
BOX = '    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
SK = '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
cases = []
for t in (-3.0, 3.0):
  for mode, amt in (("ADD", 5.0), ("SUBTRACT", -5.0)):
    cases += [
     dict(id=f"collinear_T_{t}_{mode}", src=S(BOX+SK+"        sketch_1.r = Rectangle(20.0, 10.0)\n        sketch_1.l = Line((0.0, 5.0), (0.0, 12.0))\n"+f"    extrude(regions(sketch_1, (0.0, 0.0)), amount={amt}, taper={t}, mode=Mode.{mode})  # feature: extrude_1\n")),
     dict(id=f"collinear_poly_{t}_{mode}", src=S(BOX+SK+"        sketch_1.p = Polygon((-10.0, -5.0), (0.0, -5.0), (10.0, -5.0), (10.0, 5.0), (-10.0, 5.0), align=None)\n"+f"    extrude(regions(sketch_1, (0.0, 0.0)), amount={amt}, taper={t}, mode=Mode.{mode})  # feature: extrude_1\n")),
     dict(id=f"facerest_T_{t}_{mode}", src=S(BOX+SK+"        sketch_1.l = Line((0.0, 15.0), (0.0, 5.0))\n        sketch_1.m = Line((-25.0, 5.0), (25.0, 5.0))\n"+f"    extrude(regions(sketch_1, (0.0, 0.0)), amount={amt}, taper={t}, mode=Mode.{mode})  # feature: extrude_1\n")),
    ]
r = run_cases(cases)
for c in cases:
    x = r[c["id"]]; print(f'{c["id"]:32s}', x["ok"], x.get("error","")[:120], x.get("volume"), x.get("line"))
