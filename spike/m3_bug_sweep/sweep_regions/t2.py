import json
from drive import run_cases
d = json.load(open("targeted_out.json"))
cases = [dict(c, resolve=True) for c in d["cases"] if d["results"][c["id"]]["ok"]]
r = run_cases(cases)
n = 0
for c in cases:
    x = r[c["id"]]
    u = x.get("unresolved")
    if u: n += 1; print(c["id"], u[:4])
print(len(cases), "cases,", n, "with unresolved refs")
