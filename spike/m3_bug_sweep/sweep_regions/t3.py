import json
from drive import run_cases
d = json.load(open("targeted_out.json"))
ids = ["hole_with_tail","island_in_hole","taper_hole_negative","taper_hole_positive_closes"]
cases = [dict(c, resolve=True) for c in d["cases"] if c["id"] in ids]
r = run_cases(cases)
for c in cases: print(c["id"], r[c["id"]].get("unresolved"))
