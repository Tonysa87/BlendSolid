"""Run cases in a child process, one at a time, killing a case past TIMEOUT s (then restarting after it).
usage: drive.py cases.json out.jsonl"""
import json
import os
import select
import subprocess
import sys
import time

PY = os.path.expanduser("~/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13")
HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 60

CHILD = r'''
import json, sys, traceback
sys.path.insert(0, HERE)
from check import run_case
cases = json.load(open(sys.argv[1]))
start = int(sys.argv[2])
for i in range(start, len(cases)):
    print("START", i, flush=True)
    c = cases[i]
    try:
        res = run_case(c["src"], c["meta"]["tol"])
    except Exception as e:
        res = {"ok": False, "error": "HARNESS " + traceback.format_exc()[-800:]}
    res["meta"] = c["meta"]
    print("RESULT " + json.dumps(res, default=float), flush=True)
'''.replace("HERE", repr(HERE))


def main(cases_path, out_path):
    cases = json.load(open(cases_path))
    out = open(out_path, "a")
    done = set()
    if os.path.exists(out_path):
        for line in open(out_path):
            try:
                done.add(json.loads(line)["meta"]["seed"])
            except Exception:
                pass
    i = 0
    while i < len(cases):
        if cases[i]["meta"]["seed"] in done:
            i += 1
            continue
        i_before = i
        p = subprocess.Popen([PY, "-c", CHILD, cases_path, str(i)], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, bufsize=0)
        current, t0 = None, time.time()
        buf = b""
        while True:
            r, _, _ = select.select([p.stdout], [], [], 1.0)
            lines = []
            if r:
                chunk = os.read(p.stdout.fileno(), 1 << 20)
                if not chunk:
                    p.wait()
                    r = []
                buf += chunk
                while b"\n" in buf:
                    ln, buf = buf.split(b"\n", 1)
                    lines.append(ln.decode() + "\n")
            for line in lines:
                if line.startswith("START"):
                    current, t0 = int(line.split()[1]), time.time()
                elif line.startswith("RESULT"):
                    res = json.loads(line[7:])
                    out.write(json.dumps(res) + "\n")
                    out.flush()
                    i = current + 1
                    current = None
            if current is not None and time.time() - t0 > TIMEOUT:
                p.kill()
                p.wait()
                out.write(json.dumps({"ok": False, "error": "HANG", "hang": True, "meta": cases[current]["meta"]}) + "\n")
                out.flush()
                i = current + 1
                break
            if p.poll() is not None and not r:
                if current is not None:  # crashed mid case
                    out.write(json.dumps({"ok": False, "error": f"CRASH rc={p.returncode}", "crash": True,
                                          "meta": cases[current]["meta"]}) + "\n")
                    out.flush()
                    i = current + 1
                else:
                    i = len(cases) if i >= len(cases) else i
                break
        if p.poll() is None:
            p.kill()
        if i == i_before:
            raise SystemExit('child made no progress')
        if current is None and i < len(cases) and p.returncode == 0:
            pass


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
