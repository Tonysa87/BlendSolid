"""Delta-minimize failing cases: drop segments / start, keep the failure category."""
import sys, json, math
sys.path.insert(0, sys.argv[1])
from harness import *

def classify(case, r):
    if r["ok"]:
        if r.get("solids") != 1:
            return "multisolid"
        exp, lip = expected(case)
        if exp is None:
            return "ok-noref"
        g = case["grooves"][0]
        gv = abs(exp - (8000.0 if case["face"] != "XY" else 0.0))
        diff = r["volume"] - exp
        tol = 2e-4 * gv + 0.05 * g["width"] ** 2 * 3 + 1e-3
        if abs(diff) <= tol:
            return "pass"
        if isinstance(lip, float) and lip > 0 and abs(diff - lip) <= tol:
            return "lip"
        return "volume"
    e = r.get("error", "")
    if e.startswith("SketchError"):
        return "refusal"
    return "err:" + e.split(":")[0][:40]

def variants(c):
    segs = c["segs"]
    out = []
    # drop the start (next point becomes start) if next is a line
    if len(segs) > 1 and segs[0][0] == "L":
        out.append(dict(c, start=segs[0][1], segs=segs[1:]))
    for i in range(len(segs)):
        s2 = segs[:i] + segs[i + 1:]
        if not s2 or (s2[0][0] == "A" and i == 0):
            continue
        out.append(dict(c, segs=s2))
    for i in range(len(segs)):
        if segs[i][0] == "A":
            out.append(dict(c, segs=segs[:i] + [("L", segs[i][1])] + segs[i + 1:]))
    if c["closed"]:
        out.append(dict(c, closed=False))
    return out

def run1(c):
    return run_many([script(c)], timeout=60, jobs=1)[0]

rows = [json.loads(l) for l in open(sys.argv[2])]
for row in rows:
    c = row["case"]
    target = classify(c, run1(c))
    print("START", target, script(c).splitlines()[2].strip(), c["grooves"][0], flush=True)
    changed = True
    while changed:
        changed = False
        for v in variants(c):
            if classify(v, run1(v)) == target:
                c = v; changed = True
                break
    r = run1(c)
    exp = expected(c) if r["ok"] else None
    print("MIN", target, "| err", r.get("error"), "| vol", r.get("volume"), "exp", exp, flush=True)
    print(script(c), flush=True)
