import sys, json, glob
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import runner
key = sys.argv[2]
for fn in glob.glob("fuzz_p2_*.json"):
    d = json.load(open(fn)); c = {x["id"]: x for x in d["phase2"]}
    if sys.argv[1] in c: src = c[sys.argv[1]]["src"]
def bad(s):
    r = runner.run_script(s); return (not r.ok) and key in r.error
lines = src.splitlines(); assert bad(src)
i = 0
while i < len(lines):
    if lines[i].startswith("        sketch_1."):
        trial = lines[:i] + lines[i+1:]
        if bad("\n".join(trial) + "\n"): lines = trial; continue
    i += 1
print("\n".join(lines))
