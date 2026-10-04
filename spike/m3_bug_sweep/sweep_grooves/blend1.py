import sys
sys.path.insert(0, sys.argv[1])
from harness import *
base = dict(face="+Z", start=(-10.0, 0.0), segs=[("L", (0.0, 0.0)), ("L", (0.0, 5.0))], closed=False)
out = []
for prof, cor in [("round", "round"), ("circle", "round"), ("v", "round"), ("rect", "round"), ("round", "mitre"), ("v", "mitre")]:
    c = dict(base, grooves=[dict(width=2.0, depth=2.0, profile=prof, corners=cor, rib=False)])
    r = run_many([script(c)], jobs=1)[0]
    refs = [t for t in r["edge_refs"] if "groove_1" in t]
    cases = []
    for ref in refs:
        for op, kw in [("fillet", "radius"), ("chamfer", "length")]:
            cases.append(dict(c, extra=[f"    {op}({ref}, {kw}=0.2)  # feature: {op}_1"]))
    res = run_many([script(x) for x in cases], jobs=2)
    for x, rr in zip(cases, res):
        if not rr["ok"]:
            print(prof, cor, "|", x["extra"][0].strip()[:150], "|", rr["error"][:100])
