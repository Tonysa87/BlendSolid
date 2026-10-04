import sys, json
sys.path.insert(0, sys.argv[1])
from harness import *
ns = {}; exec(open(sys.argv[2]).read(), ns); cases = ns["cs"]
res = run_many([script(c) for c in cases], jobs=1)
for c, r in zip(cases, res):
    e = expected(c)
    print(c.get("name", ""), "| ok", r["ok"], r.get("error", "")[:120], "| vol %.4f" % r.get("volume", 0), "exp", e, "diff", (r["volume"] - e[0]) if r["ok"] and e[0] is not None else None, "solids", r.get("solids"), "t %.2f" % r["time"])
