import json, os, subprocess
from concurrent.futures import ThreadPoolExecutor
S = os.path.dirname(os.path.abspath(__file__))
PY = os.path.expanduser("~/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13")
ch = [c for c in json.load(open(f"{S}/changed.json")) if "exactly" in c["new"]["error"] or "closes" in c["new"]["error"]]
def run(c):
    try:
        o = subprocess.run(["nice", "-n", "10", PY, f"{S}/truth_child.py"], input=c["src"], capture_output=True, text=True, timeout=60)
        return c, json.loads(o.stdout.strip().splitlines()[-1])
    except Exception as e:
        return c, {"err": type(e).__name__}
agree = disagree = other = 0
with ThreadPoolExecutor(2) as pool:
    for c, r in pool.map(run, ch):
        t, d = r.get("truth"), r.get("draft")
        if isinstance(t, float) and isinstance(d, float):
            rel = abs(t - d) / max(abs(t), 1e-9)
            tag = "DRAFT RIGHT" if rel < 1e-3 else "draft wrong"
            agree += rel < 1e-3; disagree += rel >= 1e-3
            print(f"{c['id']:22s} {tag:12s} truth {t:.4f} draft {d:.4f} rel {rel:.1e}")
        else:
            other += 1
            print(f"{c['id']:22s} ?? {r}")
print("draft right (false refusals):", agree, "draft wrong (refusal right):", disagree, "other:", other)
