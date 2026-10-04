import sys, faulthandler
import check, runner
faulthandler.dump_traceback_later(float(sys.argv[3]), exit=True)
r = runner.run_script(open(sys.argv[1]).read(), float(sys.argv[2]), 0.3)
print("done", r.ok, r.error, r.timing)
