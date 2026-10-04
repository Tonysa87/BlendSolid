from drive import run_cases
def S(params, b): return params + "\nwith BuildPart() as part:\n" + b + "result = part.part\n"
BOX = '    Box(box_1_length, 30.0, 20.0, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n'
SK = '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
cases = []
for w in (10.0, 4.0, 2.0):
    cases.append(dict(id=f"seed_rebind_w{w}", src=S(f"box_1_length = 40.0\nsketch_1_rect_1_width = {w}", BOX + SK +
        "        sketch_1.rect_1 = Pos(3.0, 0.0) * Rectangle(sketch_1_rect_1_width, 6.0)\n"
        "    extrude(regions(sketch_1, (6.0, 0.0)), amount=5.0)  # feature: extrude_1\n")))
for L in (40.0, 20.0, 10.0):
    cases.append(dict(id=f"seed_face_shrink_L{L}", src=S(f"box_1_length = {L}", BOX + SK +
        "        sketch_1.c = Circle(2.0)\n"
        "    extrude(regions(sketch_1, (15.0, 0.0)), amount=-5.0, mode=Mode.SUBTRACT)  # feature: extrude_1\n")))
for a in (5.0, 9.0, 12.0):
    cases.append(dict(id=f"second_sketch_on_end_a{a}", src=S(f"box_1_length = 40.0\nextrude_0_amount = {a}", BOX + SK +
        "        sketch_1.r = Rectangle(20.0, 10.0)\n"
        "    extrude(regions(sketch_1, (0.0, 0.0)), amount=extrude_0_amount)  # feature: extrude_0\n"
        '    with sketch(on_face(face("extrude_0", "end"))) as sketch_2:  # feature: sketch_2\n'
        "        sketch_2.c = Pos(5.0, 0.0) * Circle(2.0)\n"
        "    extrude(regions(sketch_2, (5.0, 0.0)), dir=-sketch_2.plane.z_dir, until=Until.LAST, mode=Mode.SUBTRACT)  # feature: hole_1\n"
        '    fillet(edge_between(face("hole_1", "c"), face("extrude_0", "end")), radius=0.5)  # feature: fillet_1\n')))
for sw in (4.0, 50.0):
    cases.append(dict(id=f"sketch_on_split_face_{sw}", src=S(f"box_1_length = 40.0\nslot_w = {sw}", BOX +
        "    with Locations(Location((0.0, 0.0, 20.0), (0.0, 0.0, 0.0))):  # feature: slot_1\n"
        "        Box(4.0, slot_w, 6.0, mode=Mode.SUBTRACT)\n" + SK +
        "        sketch_1.c = Pos(10.0, 0.0) * Circle(2.0)\n"
        "    extrude(regions(sketch_1, (10.0, 0.0)), amount=5.0)  # feature: extrude_1\n")))
for rr in (0.0, 30.0):
    cases.append(dict(id=f"sketch_sides_ref_rot{rr}", src=S(f"box_1_length = 40.0\nrr = {rr}", BOX + SK +
        "        sketch_1.r = Rot(0, 0, rr) * Rectangle(10.0, 6.0)\n"
        "    extrude(regions(sketch_1, (0.0, 0.0)), amount=5.0)  # feature: extrude_1\n"
        '    fillet(edge_between(face("extrude_1", "end"), face("extrude_1", "r", near=(0.0, 3.0, 22.5))), radius=1.0)  # feature: fillet_1\n')))
r = run_cases(cases)
for c in cases:
    x = r[c["id"]]; print(f'{c["id"]:30s}', x["ok"], x.get("error","")[:140], round(x.get("volume") or 0, 3), x.get("line"), x.get("regions"), x.get("warnings"))
