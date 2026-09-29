"""Catmull-Clark folds (cc_folds.py's rule) on the notch parts, test2 and the corpus:
$PY spike/m3_outer_arcs/folds.py"""
import sys, glob; sys.argv = sys.argv[:1]; sys.path[:0] = ["spike/m3_outer_arcs"]
exec(open("spike/m2_flat_faces/cc_folds.py").read().split("SHAPES = {")[0])
import measure, notch_parts


class Wrap:  # folds() takes a build123d shape
    def __init__(self, w): self.wrapped = w


total = 0
items = [(k, lambda k=k: notch_parts.PARTS[k]()) for k in notch_parts.PARTS] + [("test2", lambda: Wrap(measure.test2()[0]))]
for f in sorted(glob.glob(measure.CORPUS + "/*.step")):
    for i, s in enumerate(measure.step_solids(f)):
        items.append((f"{f.split('/')[-1][:24]}:{i}", lambda s=s: Wrap(s)))
for name, make in items:
    try:
        bad, amin, n = folds(make())
    except Exception as e:
        print(name, "ERR", type(e).__name__); continue
    total += len(bad)
    if bad or not name.count(":"):
        print(f"{name:30s} polys {n:5d} folded children {len(bad)}", bad[:2])
print("TOTAL folded", total)
