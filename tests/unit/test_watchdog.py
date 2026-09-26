"""The worker must not outlive Blender: when its parent process dies, it exits by itself, even while a script
is stuck in an infinite loop (server.py's parent watchdog)."""
import os
import select
import signal
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The "Blender" of this test: a plain Python process that starts a worker through WorkerClient, submits an
# endless script, prints the worker's PID once the worker is running it, then waits to be killed.
PARENT = r"""
import time
from blendsolid import paths
from blendsolid.client import WorkerClient
c = WorkerClient(paths.python_executable(), paths.server_script(), paths.worker_libs(),
                 paths.pycache_dir("blendsolid"), job_timeout=600.0)
c.submit("A", "while True:\n    pass\n", "loop")
while c.state != "busy":
    c.poll()
    time.sleep(0.01)
print(c._proc.pid, flush=True)
time.sleep(600)
"""


def alive(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"  # a zombie has already exited
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="uses /proc")
def test_worker_exits_when_parent_is_killed():
    env = dict(os.environ, PYTHONPATH=ROOT)
    parent = subprocess.Popen([sys.executable, "-c", PARENT], env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
    worker_pid = None
    try:
        ready, _, _ = select.select([parent.stdout], [], [], 90)
        assert ready, "the worker never started running the script"
        worker_pid = int(parent.stdout.readline())
        time.sleep(0.5)  # well inside `while True: pass` now
        assert alive(worker_pid)
        parent.kill()    # SIGKILL: no atexit, no cleanup of any kind in the parent
        parent.wait()
        end = time.monotonic() + 5
        while alive(worker_pid) and time.monotonic() < end:
            time.sleep(0.05)
        assert not alive(worker_pid), "the worker outlived its parent"
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
        if worker_pid is not None and alive(worker_pid):
            os.kill(worker_pid, signal.SIGKILL)
