import json, os, subprocess, glob
from concurrent.futures import ThreadPoolExecutor
S = os.path.dirname(os.path.abspath(__file__))
PY = os.path.expanduser("~/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13")
ch = {c["id"]: c for c in json.load(open(f"{S}/changed.json"))}
wrong = ["s1_5_r1_tapercut", "s2_16_r0_tapercut", "s2_28_r1_taper", "s3_36_r0_tapercut", "s4_0_r4_tapercut", "s4_5_r0_taper", "s5_3_r5_taper", "s5_33_r2_tapercut"]
right = ["s1_0_r0_tapercut", "s3_13_r0_tapercut"]
unknown = [i for i in ch if i not in wrong + right and "RUNNER" not in ch[i]["new"]["error"]]
# plus 25 cases that passed both before and now (drafts believed right)
D = "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_regions"
ok = []
for p in sorted(glob.glob(f"{D}/fuzz_p2_*.json")):
    d = json.load(open(p))
    for c in d["phase2"]:
        if "taper=" in c["src"] and d["r2"].get(c["id"], {}).get("ok") and c["id"] not in ch:
            ok.append(c)
ok = ok[::30][:25]
items = [("WRONG", ch[i]) for i in wrong] + [("RIGHT", ch[i]) for i in right] + [("OK", c) for c in ok] + [("?", ch[i]) for i in unknown]
def run(item):
    tag, c = item
    try:
        o = subprocess.run(["nice", "-n", "10", PY, f"{S}/selfint_child.py"], input=c["src"], capture_output=True, text=True, timeout=90)
        return tag, c["id"], json.loads(o.stdout.strip().splitlines()[-1])
    except Exception as e:
        return tag, c["id"], {"err": type(e).__name__}
with ThreadPoolExecutor(2) as pool:
    for tag, i, r in pool.map(run, items):
        print(f"{tag:6s} {i:22s} {r}", flush=True)
