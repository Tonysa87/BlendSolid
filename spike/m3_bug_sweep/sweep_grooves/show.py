import sys, json
cats = json.load(open("cats.json"))
pref = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 2
for k, v in cats.items():
    if not k.startswith(pref): continue
    v = sorted(v, key=lambda o: (len(o["case"]["segs"]), len(o["src"])))
    print("=====", k, len(v))
    for o in v[:n]:
        g = o["case"]["grooves"][0]
        print("--", o["case"]["face"], g, "tags", o["case"].get("tags"), "feat", o.get("feat"))
        print("   err:", o["res"].get("error", "")[:300], "| vol", o["res"].get("volume"), "exp", o.get("exp"), "lip", o.get("lip"), "diff", o.get("diff"), "t", round(o["res"]["time"],2))
        print("   " + [l for l in o["src"].splitlines() if "path(" in l][0].strip())
