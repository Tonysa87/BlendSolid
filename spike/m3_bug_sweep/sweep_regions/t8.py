import math
from drive import run_cases
def S(b): return "with BuildPart() as part:\n" + b + "result = part.part\n"
cases = []
for (x0, w, h) in ((20.0, 2.0, 1.0), (10.0, 1.0, 1.0), (40.0, 5.0, 3.0), (100.0, 10.0, 2.0)):
    cases.append(dict(id=f"washer_{x0}_{w}_{h}", exp=2*math.pi*(x0+w/2)*w*h, src=S("    with sketch(Plane.XZ) as sketch_1:  # feature: sketch_1\n"
        f"        sketch_1.r = Pos({x0 + w/2}, {h/2}) * Rectangle({w}, {h})\n        sketch_1.axis = Line((0.0, -5.0), (0.0, 5.0))\n"
        f'    revolve(regions(sketch_1, ({x0 + w/2}, {h/2})), axis=sketch_1.axis("axis"), revolution_arc=360.0)  # feature: revolve_1\n')))
# lines ending on a circle at 6-decimal rounded points (chord splitting circle)
for ang in (37.0, 61.3, 123.7):
    a1, a2 = math.radians(ang), math.radians(ang + 150)
    p1 = (round(10*math.cos(a1), 6), round(10*math.sin(a1), 6)); p2 = (round(10*math.cos(a2), 6), round(10*math.sin(a2), 6))
    cases.append(dict(id=f"chord_{ang}", exp=None, src=S("    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n"
        "        sketch_1.c = Circle(10.0)\n" f"        sketch_1.l = Line({p1}, {p2})\n"
        f"    extrude(regions(sketch_1, (0.0, 0.0)), amount=3.0)  # feature: extrude_1\n")))
r = run_cases(cases)
for c in cases:
    x = r[c["id"]]; print(f'{c["id"]:24s}', x["ok"], x.get("error","")[:120], x.get("volume"), c["exp"], x.get("regions"))
