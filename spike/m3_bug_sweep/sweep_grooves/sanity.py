import sys, math; sys.path.insert(0, sys.argv[1])
from harness import *
P = dict(start=(-15,-5), segs=[("L",(5,-5)),("A",(5,5)),("L",(-15,5)),("L",(-15,-2))], closed=False)
cases = []
for prof, cor in [("rect","mitre"),("rect","round"),("v","mitre"),("round","mitre"),("circle","round")]:
    cases.append(dict(face="+Z", grooves=[dict(width=2.0, depth=2.0, profile=prof, corners=cor, rib=False)], **P))
cases.append(dict(face="+Z", grooves=[dict(width=2.0, depth=2.0, profile="rect", corners="mitre", rib=True)], start=(-15,-5), segs=[("L",(5,-5)),("A",(5,5)),("L",(5,8))], closed=False))
cases.append(dict(face="+Z", grooves=[dict(width=2.0, depth=2.0, profile="rect", corners="mitre", rib=False)], start=(-10,-5), segs=[("L",(10,-5)),("L",(10,5)),("L",(-10,5))], closed=True))
srcs = [script(c) for c in cases]
res = run_many(srcs)
L = 47 + 5*math.pi
for c, r in zip(cases, res):
    e = expected(c)
    print(c["grooves"][0]["profile"], c["grooves"][0]["corners"], r["ok"], r.get("error"), "vol", r.get("volume"), "exp", e, "t %.2f" % r["time"], r.get("solids"))
print("test expectations: rect mitre", 8000-4*L, "rect round", 8000-2*(2*L-1+math.pi/4), "v", 8000-2*L)
