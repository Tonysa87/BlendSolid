from drive import run_cases
def S(b): return "with BuildPart() as part:\n" + b + "result = part.part\n"
B = "    Box(33.1, 24.5, 38.0, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n"
F = '    fillet(edge_between(face("box_1", "+Z"), face("box_1", "+X")), radius=1.5)  # feature: fillet_1\n'
SK = '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
C1 = "        sketch_1.circle_1 = Pos(-14.656093, -2.120785) * Circle(1.893907)\n"
C2 = "        sketch_1.circle_2 = Pos(-8.98696, 3.513518) * Circle(7.563044)\n"
cases = []
for fil in ("", F):
  for ents in (C1 + C2, C1, C2):
    for op in ("amount=18.653, both=True, mode=Mode.SUBTRACT", "amount=-18.653, mode=Mode.SUBTRACT"):
      cases.append(dict(id=f"{'fil' if fil else 'box'}_{'c1' if C1 in ents else ''}{'c2' if C2 in ents else ''}_{'sym' if 'both' in op else 'cut'}",
        src=S(B + fil + SK + ents + "    extrude(regions(sketch_1, (2.014013, -1.047611)), " + op + ")  # feature: extrude_1\n")))
r = run_cases(cases)
for c in cases:
    x = r[c["id"]]; reg = x.get("regions")[0]
    print(f'{c["id"]:20s}', x["ok"], x.get("volume"), reg)
