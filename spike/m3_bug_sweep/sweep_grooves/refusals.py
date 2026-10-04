import sys, json, collections
sys.path.insert(0, sys.argv[1])
from harness import *
cats = json.load(open("cats.json"))
sus = []
cnt = collections.Counter()
for k, v in cats.items():
    if not (k.startswith("d-the profile")): continue
    for o in v:
        c = o["case"]; g, _ = path_coords(c)
        hw = c["grooves"][0]["width"] / 2
        kink = any(t < 1e-3 for _, _, _, t, _ in g.corners)
        if kink or any(r > 1e4 for r in g.radii): cnt["kink/huge"] += 1; continue
        if g.radii and min(g.radii) < hw * 1.05: cnt["r<hw"] += 1; continue
        if not o["feat"].get("simple", True): cnt["selfcross"] += 1; continue
        cnt["suspicious"] += 1
        sus.append(o)
print(cnt)
sus.sort(key=lambda o: len(o["case"]["segs"]))
for o in sus[:25]:
    c = o["case"]; print(c["face"], c["grooves"][0], o["feat"].get("max_turn"), o["res"]["error"][:50]); print("   ", [l for l in o["src"].splitlines() if "path(" in l][0].strip())
json.dump(sus, open("sus.json", "w"))
