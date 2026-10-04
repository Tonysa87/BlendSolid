"""Notes the worker sends Blender before a step that may hang inside OCCT holding the GIL (no watchdog in the
worker can stop it: the client kills the worker after its job timeout). The client keeps the last note of the
running job, so that timeout names what hung and on which script line (bug sweep M13), instead of only
"timed out". Without a connection (tests, scripts) a note does nothing."""
import sys

SCRIPT_NAME = "<history>"  # runner.SCRIPT_NAME (runner imports the modules that send notes)
send = None  # set by the server while it runs a job: send(what, line)


def note(what):
    """Tell the client what comes next (`what`: "looking for ...", read after "timed out ... while")."""
    if send is None:
        return
    line, frame = None, sys._getframe(1)
    while frame is not None:
        if frame.f_code.co_filename == SCRIPT_NAME:
            line = frame.f_lineno
            break
        frame = frame.f_back
    try:
        send(what, line)
    except Exception:  # a note must never fail the job
        pass
