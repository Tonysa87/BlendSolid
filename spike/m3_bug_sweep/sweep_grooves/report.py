import sys, json, collections
rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
cats = collections.defaultdict(list)
for o in rows:
    r, c, ft = o["res"], o["case"], o.get("feat", {})
    g = c["grooves"][0]
    err = r.get("error") or ""
    if r["ok"]:
        if r.get("solids") != 1:
            cats["b-multisolid"].append(o); continue
        exp = o.get("exp")
        if exp is None:
            cats["ok-noref"].append(o); continue
        gv = abs(exp - (8000.0 if c["face"] != "XY" else 0.0))
        diff = r["volume"] - exp
        lip = o.get("lip") or 0.0
        tol = 2e-4 * gv + 0.02 * g["width"] ** 2 * max(1, ft.get("nsharp", 1)) + 1e-3
        if abs(diff) <= tol:
            cats["pass" if r["time"] < 10 else "c-slow"].append(o)
        elif isinstance(lip, float) and lip > 0 and abs(diff - lip) <= tol:
            cats["b-lip"].append(o)
        else:
            o["diff"] = diff
            cats["b-volume"].append(o)
    else:
        if err.startswith("HANG") or err.startswith("CRASH"):
            cats["c-" + err.split()[0]].append(o)
        elif err.startswith("SketchError") or "BrokenReference" in err:
            cats["d-" + err.split(":", 1)[1].strip()[:60]].append(o)
        else:
            cats["a-" + err[:70]].append(o)
for k in sorted(cats, key=lambda k: (k[0], -len(cats[k]))):
    print(f"{len(cats[k]):5d}  {k}")
json.dump({k: v for k, v in cats.items()}, open("/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_grooves/cats.json", "w"), default=str)
