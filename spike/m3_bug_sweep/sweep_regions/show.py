import json, sys, glob
ids = sys.argv[1:]
for fn in glob.glob("fuzz_p2_*.json"):
    d = json.load(open(fn)); c = {x["id"]: x for x in d["phase2"]}
    for i in ids:
        if i in c:
            x = d["r2"][i]
            print("####", i, "A=", c[i]["A"], "vol=", c[i]["vol"], "extra=", c[i]["extra"], "->", x.get("ok"), x.get("volume"), x.get("error", "")[:200], x.get("warnings"))
            print(c[i]["src"])
