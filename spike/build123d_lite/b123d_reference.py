"""Run scripts.SCRIPTS with a *full* build123d install (all dependencies), to get reference volumes.

Usage: PYTHONPATH=<full_site> python b123d_reference.py > reference.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scripts import SCRIPTS  # noqa: E402

out = {}
for name, code in SCRIPTS.items():
    ns = {}
    exec("from build123d import *\n" + code, ns)
    out[name] = ns["result"].volume
print(json.dumps(out, indent=1))
