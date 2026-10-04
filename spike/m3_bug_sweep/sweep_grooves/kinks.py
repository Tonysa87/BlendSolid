import sys, json, collections
sys.path.insert(0, sys.argv[1])
from harness import *
cats = json.load(open("cats.json"))
tab = collections.Counter(); clean_fail = collections.defaultdict(list)
for k, v in cats.items():
    for o in v:
        c = o["case"]
        g, _ = path_coords(c)
        if g is None:
            tab[(k[:60], "nopath")] += 1; continue
        kink = any(t < 1e-3 for _, _, _, t, _ in g.corners)
        huge = any(r > 1e4 for r in g.radii)
        tiny_seg = False
        key = "kink" if kink else "huge-r" if huge else "clean"
        tab[(k[:60], key)] += 1
        if key == "clean" and not k.startswith("pass") and not k.startswith("d-a corner") and not k.startswith("d-a round") and k != "b-lip" and k != "ok-noref":
            clean_fail[k].append(o)
for (k, key), n in sorted(tab.items()):
    print(f"{n:5d} {key:7s} {k}")
json.dump(clean_fail, open("clean_fail.json", "w"), default=str)
