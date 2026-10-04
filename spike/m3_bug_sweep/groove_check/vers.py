import sys, os
W = sys.argv[1]
sys.path[:0] = [os.path.join(W, "blendsolid", "worker"), "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import runner
r = runner.run_script(open(sys.argv[2]).read())
print(os.path.basename(W), r.ok, round(r.volume, 4), r.error[:70])
