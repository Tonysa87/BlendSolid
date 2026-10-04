import json, math, sys
from drive import run_cases
BOX = '    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
SK = '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
def S(body, params=""):
    return f"{params}\nwith BuildPart() as part:\n{body}result = part.part\n"
pi = math.pi
cases = []
def add(id, body, vol=None, expect="ok", note=""):
    cases.append(dict(id=id, src=S(body), vol=vol, expect=expect, note=note))

# dangling line attached to an inner circle (hole) -> hole dropped?
add("hole_with_tail", BOX + SK + "        sketch_1.r = Rectangle(20.0, 10.0)\n        sketch_1.c = Circle(2.0)\n"
    "        sketch_1.l = Line((2.0, 0.0), (5.0, 0.0))\n"
    "    extrude(regions(sketch_1, (7.0, 3.0)), amount=5.0)  # feature: extrude_1\n", 24000 + (200 - 4*pi)*5)
add("outer_with_tail_in", BOX + SK + "        sketch_1.r = Rectangle(20.0, 10.0)\n"
    "        sketch_1.l = Line((10.0, 0.0), (5.0, 0.0))\n"
    "    extrude(regions(sketch_1, (0.0, 3.0)), amount=5.0)  # feature: extrude_1\n", 24000 + 200*5)
add("outer_with_tail_out", BOX + SK + "        sketch_1.r = Rectangle(20.0, 10.0)\n"
    "        sketch_1.l = Line((10.0, 0.0), (15.0, 0.0))\n"
    "    extrude(regions(sketch_1, (0.0, 3.0)), amount=5.0)  # feature: extrude_1\n", 24000 + 200*5)
add("face_rest_with_tail", BOX + SK + "        sketch_1.r = Rectangle(20.0, 10.0)\n"
    "        sketch_1.l = Line((10.0, 0.0), (15.0, 0.0))\n"
    "    extrude(regions(sketch_1, (17.0, 12.0)), amount=-5.0, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 24000 - (1200-200)*5)
add("face_rest_with_inner_tail_hole", BOX + SK + "        sketch_1.c = Circle(3.0)\n"
    "        sketch_1.l = Line((3.0, 0.0), (8.0, 0.0))\n"
    "    extrude(regions(sketch_1, (15.0, 10.0)), amount=-5.0, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 24000 - (1200-9*pi)*5)
# island in hole
add("island_in_hole", BOX + SK + "        sketch_1.a = Circle(10.0)\n        sketch_1.b = Circle(6.0)\n        sketch_1.c = Circle(3.0)\n"
    "    extrude(regions(sketch_1, (8.0, 0.0), (0.0, 0.0)), amount=5.0)  # feature: extrude_1\n", 24000 + (100-36+9)*pi*5)
# taper across face-edge-bounded region: roles
add("taper_face_bounded_roles", BOX + SK + "        sketch_1.l = Line((0.0, -20.0), (0.0, 20.0))\n"
    "    extrude(regions(sketch_1, (10.0, 0.0)), amount=5.0, taper=5.0)  # feature: extrude_1\n", None)
# adjacent regions tapered together
add("taper_two_adjacent", BOX + SK + "        sketch_1.r = Rectangle(20.0, 10.0)\n        sketch_1.l = Line((0.0, -5.0), (0.0, 5.0))\n"
    "    extrude(regions(sketch_1, (5.0, 0.0), (-5.0, 0.0)), amount=5.0, taper=10.0)  # feature: extrude_1\n", None)
add("taper_one_rect", BOX + SK + "        sketch_1.r = Rectangle(20.0, 10.0)\n"
    "    extrude(regions(sketch_1, (5.0, 0.0)), amount=5.0, taper=10.0)  # feature: extrude_1\n", None)
# taper too large: section collapses
add("taper_collapse", BOX + SK + "        sketch_1.r = Rectangle(10.0, 6.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), amount=8.0, taper=30.0)  # feature: extrude_1\n", None, expect="error")
add("taper_collapse_circle", BOX + SK + "        sketch_1.r = Circle(3.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), amount=8.0, taper=30.0)  # feature: extrude_1\n", None, expect="error")
add("taper_hole_negative", BOX + SK + "        sketch_1.a = Circle(10.0)\n        sketch_1.b = Circle(2.0)\n"
    "    extrude(regions(sketch_1, (5.0, 0.0)), amount=8.0, taper=-10.0)  # feature: extrude_1\n", None)
add("taper_hole_positive_closes", BOX + SK + "        sketch_1.a = Circle(10.0)\n        sketch_1.b = Circle(2.0)\n"
    "    extrude(regions(sketch_1, (5.0, 0.0)), amount=8.0, taper=-30.0)  # feature: extrude_1\n", None, expect="error")
add("taper_89", BOX + SK + "        sketch_1.r = Rectangle(10.0, 6.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), amount=8.0, taper=89.0)  # feature: extrude_1\n", None, expect="error")
add("taper_90", BOX + SK + "        sketch_1.r = Rectangle(10.0, 6.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), amount=8.0, taper=90.0)  # feature: extrude_1\n", None, expect="error")
# revolve crossing axis
REV = '    with sketch(Plane.XZ) as sketch_1:  # feature: sketch_1\n'
add("revolve_cross_axis", REV + "        sketch_1.r = Pos(1.0, 5.0) * Rectangle(4.0, 10.0)\n        sketch_1.axis = Line((-5.0, -20.0), (-5.0, -15.0))\n        sketch_1.ax2 = Line((0.0, 20.0), (0.0, 30.0))\n"
    "    revolve(regions(sketch_1, (2.0, 5.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=360)  # feature: revolve_1\n", None, expect="error")
add("revolve_cross_axis_partial", REV + "        sketch_1.r = Pos(1.0, 5.0) * Rectangle(4.0, 10.0)\n        sketch_1.ax2 = Line((0.0, 20.0), (0.0, 30.0))\n"
    "    revolve(regions(sketch_1, (2.0, 5.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=90)  # feature: revolve_1\n", None, expect="error")
add("revolve_touch_axis", REV + "        sketch_1.r = Pos(2.0, 5.0) * Rectangle(4.0, 10.0)\n        sketch_1.ax2 = Line((0.0, 20.0), (0.0, 30.0))\n"
    "    revolve(regions(sketch_1, (2.0, 5.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=360)  # feature: revolve_1\n", pi*4*10)
add("revolve_touch_axis_partial", REV + "        sketch_1.r = Pos(2.0, 5.0) * Rectangle(4.0, 10.0)\n        sketch_1.ax2 = Line((0.0, 20.0), (0.0, 30.0))\n"
    "    revolve(regions(sketch_1, (2.0, 5.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=90)  # feature: revolve_1\n", pi*4*10/4)
add("revolve_point_touch_axis", REV + "        sketch_1.r = Polygon((0.0, 0.0), (5.0, 2.0), (5.0, -2.0), align=None)\n        sketch_1.ax2 = Line((0.0, 20.0), (0.0, 30.0))\n"
    "    revolve(regions(sketch_1, (3.0, 0.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=360)  # feature: revolve_1\n", None)
add("revolve_zero", REV + "        sketch_1.r = Pos(17.0, 5.0) * Rectangle(4.0, 10.0)\n        sketch_1.ax2 = Line((0.0, 20.0), (0.0, 30.0))\n"
    "    revolve(regions(sketch_1, (17.0, 5.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=0)  # feature: revolve_1\n", None, expect="error")
add("revolve_axis_in_sketch_plane_perp", REV + "        sketch_1.r = Pos(17.0, 5.0) * Rectangle(4.0, 10.0)\n        sketch_1.ax2 = Line((0.0, -20.0), (30.0, -20.0))\n"
    "    revolve(regions(sketch_1, (17.0, 5.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=360)  # feature: revolve_1\n", 40*2*pi*25)
add("revolve_axis_circle_region", REV + "        sketch_1.c = Pos(10.0, 0.0) * Circle(3.0)\n        sketch_1.ax2 = Line((0.0, -20.0), (0.0, 20.0))\n"
    "    revolve(regions(sketch_1, (10.0, 0.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=360)  # feature: revolve_1\n", 9*pi*2*pi*10)
add("revolve_axis_crosses_circle", REV + "        sketch_1.c = Pos(2.0, 0.0) * Circle(3.0)\n        sketch_1.ax2 = Line((0.0, 20.0), (0.0, 30.0))\n"
    "    revolve(regions(sketch_1, (2.0, 0.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=360)  # feature: revolve_1\n", None, expect="error")
add("revolve_axis_line_splits_region", REV + "        sketch_1.c = Pos(2.0, 0.0) * Circle(3.0)\n        sketch_1.ax2 = Line((0.0, -20.0), (0.0, 20.0))\n"
    "    revolve(regions(sketch_1, (3.0, 0.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=360)  # feature: revolve_1\n", None)
add("revolve_on_box_face", BOX + SK + "        sketch_1.c = Pos(10.0, 0.0) * Circle(3.0)\n        sketch_1.ax2 = Line((0.0, -5.0), (0.0, 5.0))\n"
    "    revolve(regions(sketch_1, (10.0, 0.0)), axis=sketch_1.axis(\"ax2\"), revolution_arc=360)  # feature: revolve_1\n", None)
add("revolve_axis_not_a_line", REV + "        sketch_1.c = Pos(10.0, 0.0) * Circle(3.0)\n"
    "    revolve(regions(sketch_1, (10.0, 0.0)), axis=sketch_1.axis(\"c\"), revolution_arc=360)  # feature: revolve_1\n", None, expect="error")
# until variants
add("until_next_add_up_nothing", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), until=Until.NEXT)  # feature: extrude_1\n", None, expect="error")
add("until_next_add_down_inside", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), dir=-sketch_1.plane.z_dir, until=Until.NEXT)  # feature: extrude_1\n", None, expect="error")
add("until_last_add_down_inside", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), dir=-sketch_1.plane.z_dir, until=Until.LAST)  # feature: extrude_1\n", None, expect="?")
add("until_next_cut_up_nothing", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), until=Until.NEXT, mode=Mode.SUBTRACT)  # feature: extrude_1\n", None, expect="error")
add("until_last_cut_partly_off", BOX + SK + "        sketch_1.r = Pos(20.0, 0.0) * Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (17.0, 0.0)), dir=-sketch_1.plane.z_dir, until=Until.LAST, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 24000-50*20)
add("until_last_cut_face_rest", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (17.0, 0.0)), dir=-sketch_1.plane.z_dir, until=Until.LAST, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 100*20)
add("until_next_intersect", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), dir=-sketch_1.plane.z_dir, until=Until.NEXT, mode=Mode.INTERSECT)  # feature: extrude_1\n", 100*20)
add("until_plane_no_part", '    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n        sketch_1.r = Rectangle(10.0, 10.0)\n'
    "    extrude(regions(sketch_1, (0.0, 0.0)), until=Until.NEXT)  # feature: extrude_1\n", None, expect="error")
add("until_next_cylinder_target", '    with Locations(Location((0.0, 0.0, 30.0), (0.0, 0.0, 0.0))):  # feature: cyl_1\n        Cylinder(20.0, 10.0)\n'
    '    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n        sketch_1.r = Rectangle(10.0, 10.0)\n'
    "    extrude(regions(sketch_1, (0.0, 0.0)), until=Until.NEXT)  # feature: extrude_1\n", pi*400*10 + 100*25)
add("until_next_sphere_target", '    with Locations(Location((0.0, 0.0, 30.0), (0.0, 0.0, 0.0))):  # feature: sph_1\n        Sphere(10.0)\n'
    '    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1\n        sketch_1.r = Circle(2.0)\n'
    "    extrude(regions(sketch_1, (0.0, 0.0)), until=Until.NEXT)  # feature: extrude_1\n", None)
add("until_last_sphere_through_cut", '    Sphere(10.0)  # feature: sph_1\n'
    '    with sketch(Plane.XY.offset(15)) as sketch_1:  # feature: sketch_1\n        sketch_1.r = Circle(2.0)\n'
    "    extrude(regions(sketch_1, (0.0, 0.0)), dir=(0,0,-1), until=Until.LAST, mode=Mode.SUBTRACT)  # feature: extrude_1\n", None)
# symmetric
add("sym_cut", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), amount=4.0, both=True, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 24000-400)
add("sym_join_taper", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), amount=4.0, both=True, taper=5.0)  # feature: extrude_1\n", None)
add("sym_neg_amount", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), amount=-4.0, both=True)  # feature: extrude_1\n", 24000+400)
# region outside face
add("region_outside_face_join", BOX + SK + "        sketch_1.c = Pos(20.0, 0.0) * Circle(5.0)\n"
    "    extrude(regions(sketch_1, (23.0, 0.0)), amount=5.0)  # feature: extrude_1\n", None, expect="?")
add("region_outside_face_cut", BOX + SK + "        sketch_1.c = Pos(20.0, 0.0) * Circle(5.0)\n"
    "    extrude(regions(sketch_1, (23.0, 0.0)), amount=-5.0, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 24000, expect="?")
add("region_fully_off_face_join", BOX + SK + "        sketch_1.c = Pos(40.0, 0.0) * Circle(5.0)\n"
    "    extrude(regions(sketch_1, (40.0, 0.0)), amount=5.0)  # feature: extrude_1\n", None, expect="?")
# all regions
add("all_regions_on_face", BOX + SK + "        sketch_1.c = Circle(5.0)\n"
    "    extrude(regions(sketch_1), amount=5.0)  # feature: extrude_1\n", None, expect="?")
# extrude amount 0
add("amount_zero", BOX + SK + "        sketch_1.c = Circle(5.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), amount=0.0)  # feature: extrude_1\n", None, expect="error")
add("amount_tiny", BOX + SK + "        sketch_1.c = Circle(5.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), amount=1e-9)  # feature: extrude_1\n", None, expect="?")
# seed on face boundary edge
add("seed_on_face_edge", BOX + SK + "        sketch_1.c = Circle(5.0)\n"
    "    extrude(regions(sketch_1, (20.0, 0.0)), amount=5.0)  # feature: extrude_1\n", None, expect="?")
# two identical entities
add("duplicate_rect", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n        sketch_1.r2 = Rectangle(10.0, 10.0)\n"
    "    extrude(regions(sketch_1, (0.0, 0.0)), amount=5.0)  # feature: extrude_1\n", 24000+500)
add("tangent_circles", BOX + SK + "        sketch_1.a = Pos(-5.0, 0.0) * Circle(5.0)\n        sketch_1.b = Pos(5.0, 0.0) * Circle(5.0)\n"
    "    extrude(regions(sketch_1, (-5.0, 0.0), (5.0, 0.0)), amount=5.0)  # feature: extrude_1\n", 24000+2*25*pi*5)
add("tangent_circles_taper", BOX + SK + "        sketch_1.a = Pos(-5.0, 0.0) * Circle(5.0)\n        sketch_1.b = Pos(5.0, 0.0) * Circle(5.0)\n"
    "    extrude(regions(sketch_1, (-5.0, 0.0), (5.0, 0.0)), amount=5.0, taper=-5.0)  # feature: extrude_1\n", None)
add("circle_tangent_face_edge", BOX + SK + "        sketch_1.a = Pos(15.0, 0.0) * Circle(5.0)\n"
    "    extrude(regions(sketch_1, (15.0, 0.0)), amount=5.0)  # feature: extrude_1\n", 24000+25*pi*5)
add("circle_tangent_face_edge_cut", BOX + SK + "        sketch_1.a = Pos(15.0, 0.0) * Circle(5.0)\n"
    "    extrude(regions(sketch_1, (15.0, 0.0)), amount=-5.0, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 24000-25*pi*5)
add("circle_tangent_face_edge_rest_cut", BOX + SK + "        sketch_1.a = Pos(15.0, 0.0) * Circle(5.0)\n"
    "    extrude(regions(sketch_1, (-15.0, 0.0)), amount=-5.0, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 24000-(1200-25*pi)*5)
add("circle_tangent_corner_rect", BOX + SK + "        sketch_1.r = Rectangle(10.0, 10.0)\n        sketch_1.a = Circle(5.0)\n"
    "    extrude(regions(sketch_1, (4.8, 4.8)), amount=5.0)  # feature: extrude_1\n", 24000+(25-25*pi/4)*5)
# lines ending short
for gap in (1e-7, 5e-7, 1e-6, 5e-6, 9e-6, 1.1e-5, 5e-5, 1e-4):
    add(f"line_short_{gap:g}", BOX + SK + f"        sketch_1.l = Line((0.0, {-15.0+gap!r}), (0.0, {15.0-gap!r}))\n"
        "    extrude(regions(sketch_1, (10.0, 0.0)), amount=5.0, taper=3.0)  # feature: extrude_1\n", None, expect="?")
    add(f"line_short_cut_{gap:g}", BOX + SK + f"        sketch_1.l = Line((0.0, {-15.0+gap!r}), (0.0, {15.0-gap!r}))\n"
        "    extrude(regions(sketch_1, (10.0, 0.0)), amount=-5.0, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 24000-600*5 if gap < 1e-5 else None, expect="?")
    add(f"tjunction_short_{gap:g}", BOX + SK + "        sketch_1.a = Line((-10.0, 0.0), (10.0, 0.0))\n"
        f"        sketch_1.b = Line((0.0, {gap!r}), (0.0, 10.0))\n        sketch_1.r = Rectangle(20.0, 20.0)\n"
        "    extrude(regions(sketch_1, (5.0, 5.0)), amount=-5.0, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 24000-50*5 if gap < 1e-5 else 24000-200*5, expect="?")
    add(f"over_{gap:g}", BOX + SK + f"        sketch_1.l = Line((0.0, {-15.0-gap!r}), (0.0, {15.0+gap!r}))\n"
        "    extrude(regions(sketch_1, (10.0, 0.0)), amount=-5.0, mode=Mode.SUBTRACT)  # feature: extrude_1\n", 24000-600*5, expect="?")
    add(f"near_parallel_{gap:g}", BOX + SK + "        sketch_1.a = Rectangle(10.0, 10.0)\n"
        f"        sketch_1.b = Pos(10.0, {gap!r}) * Rectangle(10.0, 10.0)\n"
        "    extrude(regions(sketch_1, (0.0, 0.0), (10.0, 0.0)), amount=5.0)  # feature: extrude_1\n", None, expect="?")
r = run_cases(cases)
json.dump(dict(cases=cases, results=r), open("targeted_out.json", "w"))
for c in cases:
    x = r[c["id"]]
    vol = x.get("volume")
    dv = None if c["vol"] is None or vol is None else vol - c["vol"]
    print(f'{c["id"]:38s} ok={x["ok"]!s:5} t={x.get("t",0):6.2f} vol={vol} dv={dv} faces={x.get("faces")} regions={[[round(a,4) for a in s] for s in x.get("regions") or []]}')
    if not x["ok"]: print("     ERR:", x["error"][:300], "line", x.get("line"))
    if x.get("warnings"): print("     WARN:", x["warnings"])
