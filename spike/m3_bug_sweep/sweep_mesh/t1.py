import json, sys
from check import run_case
SRC = '''with BuildPart() as part:
    Box(5000.0, 5000.0, 5000.0, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with sketch(on_face(face("box_1", "+X"))) as sketch_1:  # feature: sketch_1
        sketch_1.path_1 = path((-2000.0, 4500.0), (-2000.0, 3000.0), (-1000.0, 3000.0), arc_to((-1000.0, 4000.0)), (-1000.0, 4500.0), (500.0, 4500.0), arc_to((500.0, 3000.0)), (500.0, 2000.0), (-1000.0, 2000.0), (-1000.0, 1000.0), arc_to((0.0, 1000.0)))
    groove(sketch_1.path_1, width=150.0, depth=150.0, profile="PROF", corners="CORN", mode=Mode.ADD)  # feature: rib_1
result = part.part
'''
for prof in ["rect","round","v","circle"]:
  for corn in ["mitre","round"]:
    for tol in [1.0, 0.1]:
        r = run_case(SRC.replace("PROF",prof).replace("CORN",corn), tol)
        r.pop("stderr",None)
        print(prof, corn, tol, json.dumps({k:r.get(k) for k in ["ok","error","wall","fallbacks","polys","open_edges","dup_directed","zero_area_polys","dvol_over_area_tol","curved_min_angle","curved_lt1","plane_lt1","normal_back","dev_over_tol","dev_face","sliver_faces"]}), flush=True)
