"""Run cases (list of dicts id/src) through child.py processes with per-case timeout."""
import json, subprocess, sys, select, time
PY = "/home/tony/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13"
def run_cases(cases, timeout=60):
    results = {}
    i = 0
    while i < len(cases):
        p = subprocess.Popen(["taskset", "-c", "0,1", PY, "child.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                             cwd="/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_regions")
        first = True
        while i < len(cases):
            c = cases[i]
            p.stdin.write(json.dumps(c) + "\n"); p.stdin.flush()
            lim = timeout + (30 if first else 0)
            r, _, _ = select.select([p.stdout], [], [], lim)
            if not r:
                p.kill(); results[c["id"]] = dict(id=c["id"], ok=False, error="HANG", hang=True)
                i += 1; break
            line = p.stdout.readline()
            if not line:
                results[c["id"]] = dict(id=c["id"], ok=False, error="CHILD DIED rc=%s" % p.wait(), crash=True)
                i += 1; break
            results[c["id"]] = json.loads(line); first = False
            i += 1
        else:
            p.stdin.close(); p.wait()
    return results
