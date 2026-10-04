import sys, json, random, copy
sys.path.insert(0, sys.argv[1])
from harness import *
rng = random.Random(7)
cats = json.load(open("cats.json"))
passes = cats["pass"]
rng.shuffle(passes)
# 1) groove after groove on the same path
cases = []
for o in passes[:150]:
    c = copy.deepcopy(o["case"])
    g1 = c["grooves"][0]
    g2 = dict(g1)
    g2["width"] = round(g1["width"] * rng.uniform(0.3, 0.95), 6)
    g2["depth"] = round(rng.choice([g1["depth"], rng.uniform(0.5, 5.0)]), 6)
    g2["profile"] = rng.choice([g1["profile"], rng.choice(["rect", "round", "v", "circle"])])
    g2["corners"] = rng.choice(["mitre", "round"])
    if g2["profile"] == "round": g2["depth"] = max(g2["depth"], g2["width"] / 2 + 0.01)
    c["grooves"] = [g1, g2]
    c["kind"] = "double"
    cases.append(c)
res = run_many([script(c) for c in cases], timeout=60, jobs=2)
with open("r_double.jsonl", "w") as f:
    for c, r in zip(cases, res):
        r.pop("edge_refs", None); r.pop("face_refs", None)
        f.write(json.dumps({"case": c, "src": script(c), "res": r}, default=str) + "\n")
# 2) fillet / chamfer after a groove
base = [copy.deepcopy(o["case"]) for o in passes[150:330] if o["case"]["face"] != "XY"]
res0 = run_many([script(c) for c in base], timeout=60, jobs=2)
cases2 = []
for c, r in zip(base, res0):
    if not r["ok"] or not r.get("edge_refs"): continue
    name = ("rib_1" if c["grooves"][0]["rib"] else "groove_1")
    refs = [t for t in r["edge_refs"] if name in t]
    if not refs: continue
    ref = rng.choice(refs)
    op = rng.choice(["fillet", "chamfer"])
    size = round(rng.choice([0.1, 0.2, 0.5, c["grooves"][0]["width"] / 3]), 6)
    c2 = dict(c, extra=[f"    {op}({ref}, {'radius' if op == 'fillet' else 'length'}={size})  # feature: {op}_1"])
    c2["kind"] = "blend"
    cases2.append(c2)
res2 = run_many([script(c) for c in cases2], timeout=60, jobs=2)
with open("r_blend.jsonl", "w") as f:
    for c, r in zip(cases2, res2):
        r.pop("edge_refs", None); r.pop("face_refs", None)
        f.write(json.dumps({"case": c, "src": script(c), "res": r}, default=str) + "\n")
print("double", len(cases), "blend", len(cases2))
