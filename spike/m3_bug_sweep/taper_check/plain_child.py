import sys, os, json
ROOT = "/home/tony/Projects/BlendSolid"
sys.path[:0] = [os.path.join(ROOT, "blendsolid", "worker"), os.path.join(ROOT, ".dev", "worker_libs")]
import faulthandler; faulthandler.enable()
import runner
r = runner.run_script(sys.stdin.read())
print(json.dumps({"ok": r.ok, "error": r.error, "volume": r.volume}))
