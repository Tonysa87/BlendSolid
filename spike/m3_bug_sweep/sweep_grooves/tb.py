import sys, traceback
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
import runner
src = open(sys.argv[1]).read()
try:
    runner._build(src, runner.SCRIPT_NAME, [], runner.SHAPES)
    print("built OK")
except Exception as e:
    for f in traceback.extract_tb(e.__traceback__)[-6:]:
        print(f"  {f.filename.split('/')[-1]}:{f.lineno} {f.name}: {f.line}")
    print(type(e).__name__, e)
