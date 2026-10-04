"""Rerun the bug sweep's cases against the current worker, 2 processes at a time (the maintainer's PC must stay
usable). `rerun.py grooves`: the groove sweep's 3000 cases (category, independent volume `exp`, volume at the
sweep); `rerun.py tapers`: the 895 region-sweep tapers that passed at the sweep. Prints what changed."""
import gzip, json, os, subprocess, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PY = os.path.expanduser("~/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13")
CHILD = f'''
import sys, os, json
sys.path[:0] = [os.path.join({ROOT!r}, "blendsolid", "worker"), os.path.join({ROOT!r}, ".dev", "worker_libs")]
import runner
r = runner.run_script(sys.stdin.read())
print(json.dumps({{"ok": r.ok, "error": r.error, "volume": r.volume, "warnings": [w for _, w in r.warnings]}}))
'''
kind = sys.argv[1] if len(sys.argv) > 1 else "grooves"
cases = json.load(gzip.open(os.path.join(HERE, f"{'groove' if kind == 'grooves' else 'taper'}_cases.json.gz"), "rt"))


# one thread per child, all pinned to 2 cores: OCCT and numpy otherwise took ~9 cores each at peaks (session 15)
ENV = {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
       "TBB_NUM_THREADS": "1"}


def run(c):
    try:
        o = subprocess.run(["taskset", "-c", "2,3", "nice", "-n", "10", PY, "-c", CHILD], input=c["src"], capture_output=True, text=True,
                           timeout=90, env=ENV)
        return c, json.loads(o.stdout.strip().splitlines()[-1])
    except Exception as e:  # no output: a crash (segfault) or a hang
        return c, {"ok": False, "error": f"RUNNER {type(e).__name__}", "volume": 0.0, "warnings": []}


summary, changed = Counter(), []
with ThreadPoolExecutor(2) as pool:
    for c, r in pool.map(run, cases):
        before = c.get("cat", "ok")
        same = r["ok"] and c.get("old") is not None and abs(r["volume"] - c["old"]) <= 1e-6 * max(1.0, abs(c["old"]))
        exact = r["ok"] and c.get("exp") is not None and abs(r["volume"] - c["exp"]) <= 2e-3
        now = "same volume" if same else "exact" if exact else (r["error"][:60] if not r["ok"] else "other volume")
        summary[f"{before[:45]} -> {now}"] += 1
        if not same:
            changed.append({**c, "now": r})
json.dump(changed, open(os.path.join(HERE, f"changed_{kind}.json"), "w"), indent=1)
for line, n in summary.most_common():
    print(n, line)
