import hmac
import os
import secrets
import socket
import subprocess
import time
from multiprocessing.connection import Connection

import pytest

import protocol  # imported as the worker does (blendsolid/worker on sys.path); used to talk to a raw worker
from blendsolid import paths
from blendsolid.client import WorkerClient, WorkerStartError

BOX = "size = 10.0\nresult = Box(size, size, size)\n"


@pytest.fixture
def client():
    c = WorkerClient(paths.python_executable(), paths.server_script(), paths.worker_libs(),
                     paths.pycache_dir("blendsolid"), job_timeout=60.0)
    yield c
    c.stop()


def collect(c, n_results, timeout=120.0):
    """Poll until n result/crashed events arrived; returns every event seen."""
    events, end = [], time.monotonic() + timeout
    while time.monotonic() < end:
        events += c.poll()
        if sum(e["type"] in ("result", "crashed") for e in events) >= n_results:
            return events
        time.sleep(0.01)
    raise AssertionError(f"timed out; events: {[e['type'] for e in events]}")


def results(events):
    return [e for e in events if e["type"] in ("result", "crashed")]


def test_ready_then_result(client):
    client.submit("A", BOX, "t1")
    events = collect(client, 1)
    assert events[0]["type"] == "ready" and events[0]["build123d"] == "0.13.0"
    (r,) = results(events)
    assert r["ok"] and r["key"] == "A" and r["tag"] == "t1" and abs(r["volume"] - 1000.0) < 1e-9
    assert r["verts"].shape[1] == 3 and len(r["poly_face"]) == len(r["poly_sizes"])
    assert client.state == "idle"


def test_script_error_is_a_result_not_a_crash(client):
    client.submit("A", "result = Box(1, 1,\n", "bad")
    (r,) = results(collect(client, 1))
    assert r["type"] == "result" and not r["ok"] and r["line"] == 1


def test_crash_is_reported_and_worker_restarts(client):
    client.submit("A", "import os\nos._exit(3)\n", "crash")
    (r,) = results(collect(client, 1))
    assert r["type"] == "crashed" and r["key"] == "A" and r["tag"] == "crash"
    assert client.state == "stopped"
    client.submit("A", BOX, "ok")
    (r,) = results(collect(client, 1))
    assert r["ok"] and r["tag"] == "ok"


def test_crash_before_ready_drops_queued_requests(tmp_path):
    c = WorkerClient(paths.python_executable(), paths.server_script(), str(tmp_path),  # no build123d there
                     paths.pycache_dir("blendsolid"))
    try:
        c.submit("A", BOX, "a")
        c.submit("B", BOX, "b")
        (r,) = results(collect(c, 1, timeout=60))
        assert r["type"] == "crashed" and r["key"] is None and "build123d" in r["error"]
        assert sorted(r["dropped"]) == [["A", "a"], ["B", "b"]]
    finally:
        c.stop()


def test_timeout_kills_the_worker():
    c = WorkerClient(paths.python_executable(), paths.server_script(), paths.worker_libs(),
                     paths.pycache_dir("blendsolid"), job_timeout=1.0)
    try:
        c.submit("A", "import time\ntime.sleep(30)\nresult = Box(1, 1, 1)\n", "slow")
        # the first job also pays the worker's cold start: allow for it before the 1 s job timeout applies
        (r,) = results(collect(c, 1, timeout=60))
        assert r["type"] == "crashed" and "timed out" in r["error"]
    finally:
        c.stop()


def test_timeout_names_what_the_worker_said_it_was_doing():
    # M13: a fillet search hanging in OCCT only said "timed out"; the worker's last progress note names it
    c = WorkerClient(paths.python_executable(), paths.server_script(), paths.worker_libs(),
                     paths.pycache_dir("blendsolid"), job_timeout=1.0)
    try:
        c.submit("A", "import time, progress\nprogress.note('testing a hang')\ntime.sleep(30)\n"
                      "result = Box(1, 1, 1)\n", "slow")
        (r,) = results(collect(c, 1, timeout=60))
        assert r["type"] == "crashed" and "timed out after 1 s while testing a hang" in r["error"]
        assert r["line"] == 2
    finally:
        c.stop()


def test_a_finished_step_no_longer_names_a_timeout():
    c = WorkerClient(paths.python_executable(), paths.server_script(), paths.worker_libs(),
                     paths.pycache_dir("blendsolid"), job_timeout=1.0)
    try:
        c.submit("A", "import time, progress\nprogress.note('testing a step')\nprogress.clear()\ntime.sleep(30)\n"
                      "result = Box(1, 1, 1)\n", "slow")
        (r,) = results(collect(c, 1, timeout=60))
        assert r["type"] == "crashed" and "while" not in r["error"] and r["line"] is None
    finally:
        c.stop()


def test_coalescing_per_key(client):
    client.submit("A", "import time\ntime.sleep(1.5)\nresult = Box(1, 1, 1)\n", "a1")
    collect_until_busy(client)
    client.submit("A", BOX, "a2")
    client.submit("B", BOX, "b1")
    client.submit("A", BOX, "a3")  # replaces a2, still queued behind B
    tags = [r["tag"] for r in results(collect(client, 3))]
    assert tags == ["a1", "b1", "a3"]


def collect_until_busy(c, timeout=60.0):
    end = time.monotonic() + timeout
    while c.state != "busy" and time.monotonic() < end:
        c.poll()
        time.sleep(0.01)
    assert c.state == "busy"


def test_stop_is_idempotent(client):
    client.stop()
    client.stop()
    assert client.state == "stopped"


# -- fix round 1: start() must never block past start_timeout, and must clean up properly ------------------

def test_start_with_bad_python_raises_quickly():
    c = WorkerClient("/nonexistent/blendsolid-test-python", paths.server_script(), paths.worker_libs(),
                     paths.pycache_dir("blendsolid"), start_timeout=10.0)
    t0 = time.monotonic()
    with pytest.raises(WorkerStartError):
        c.start()
    assert time.monotonic() - t0 < 5.0
    assert c.state == "stopped"


def test_start_with_exiting_server_script_raises_before_timeout(tmp_path):
    bad_server = tmp_path / "bad_server.py"
    bad_server.write_text("import sys\nsys.exit(2)\n")
    c = WorkerClient(paths.python_executable(), str(bad_server), paths.worker_libs(),
                     paths.pycache_dir("blendsolid"), start_timeout=10.0)
    t0 = time.monotonic()
    with pytest.raises(WorkerStartError) as exc_info:
        c.start()
    assert time.monotonic() - t0 < 5.0
    assert "2" in str(exc_info.value)
    assert c.state == "stopped"


def test_dispatch_puts_request_back_when_send_fails(client, monkeypatch):
    """If sending a request fails (the worker died between becoming idle and us sending), the request
    must not be lost and _dispatch() must not raise into submit()'s caller."""
    client.submit("A", BOX, "t1")
    collect(client, 1)
    assert client.state == "idle"

    from blendsolid import client as client_module
    real_send = client_module.protocol.send_message

    def boom(conn, header, arrays=None):
        if header.get("type") == "run" and header.get("key") == "B":
            raise OSError("simulated broken pipe")
        return real_send(conn, header, arrays)

    monkeypatch.setattr(client_module.protocol, "send_message", boom)
    client.submit("B", BOX, "t2")  # must not raise
    assert client.state == "idle"
    assert client._pending["B"]["tag"] == "t2" and "job" not in client._pending["B"]

    monkeypatch.undo()
    client._dispatch()  # now succeeds against the real (still-alive) worker
    (r,) = results(collect(client, 1))
    assert r["ok"] and r["tag"] == "t2"


def test_server_run_failure_is_a_result_not_a_crash():
    """A malformed 'run' request (missing job/key/tag) makes server.py raise while building the reply;
    it must still answer with a `result` (ok=False), not crash the worker or send an `error` message."""
    token = secrets.token_hex(16)
    listener = socket.create_server(("127.0.0.1", 0))
    listener.settimeout(30)
    env = dict(os.environ, BLENDSOLID_WORKER_TOKEN=token)
    proc = subprocess.Popen(
        [paths.python_executable(), "-I", paths.server_script(), str(listener.getsockname()[1]),
         paths.worker_libs(), paths.pycache_dir("blendsolid")],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        sock, _ = listener.accept()
        conn = Connection(sock.detach())
        assert hmac.compare_digest(conn.recv_bytes(), token.encode("ascii"))
        header, _ = protocol.recv_message(conn)
        assert header["type"] == "ready"

        protocol.send_message(conn, {"type": "run", "source": BOX})  # no job/key/tag
        header, arrays = protocol.recv_message(conn)

        assert header["type"] == "result"
        assert header["ok"] is False
        assert header["job"] is None and header["key"] is None and header["tag"] is None
        assert "KeyError" in header["error"]
        assert header["line"] is None and header["volume"] == 0.0 and header["faces"] == 0
        assert header["timing"] == {}
        conn.close()
    finally:
        listener.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()


# -- final review: the ready phase has its own, longer timeout -------------------------------------------------------

def test_default_timeouts():
    c = WorkerClient("python", "server.py", "libs")
    assert c.start_timeout == 30.0   # connect + handshake: fails fast on a broken interpreter or script
    assert c.ready_timeout == 120.0  # importing build123d on a cold disk can take a long time


def test_not_ready_uses_the_ready_timeout(tmp_path):
    silent = tmp_path / "silent_server.py"
    silent.write_text(
        "import os, socket, sys, time\n"
        "from multiprocessing.connection import Connection\n"
        "c = Connection(socket.create_connection(('127.0.0.1', int(sys.argv[1]))).detach())\n"
        "c.send_bytes(os.environ['BLENDSOLID_WORKER_TOKEN'].encode('ascii'))\n"
        "time.sleep(60)\n")
    c = WorkerClient(paths.python_executable(), str(silent), paths.worker_libs(), start_timeout=10.0,
                     ready_timeout=1.0)
    try:
        c.submit("A", BOX, "t")
        assert c.state == "starting"
        (r,) = results(collect(c, 1, timeout=20))
        assert r["type"] == "crashed" and "not ready after 1 s" in r["error"]
    finally:
        c.stop()


def test_submit_with_dependencies(client):
    target = "with BuildPart() as p:\n    Box(10, 10, 10)\n    insert(ref('c'), mode=Mode.SUBTRACT)\nresult = p\n"
    cutter = "result = Box(2, 2, 20)\n"
    deps = [{"id": "c", "tag": "c1", "source": cutter, "matrices": [[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]],
             "deps": []}]
    client.submit("A", target, "t", deps=deps)
    (r,) = results(collect(client, 1))
    assert r["ok"], r["error"]
    assert abs(r["volume"] - (1000.0 - 2 * 2 * 10)) < 1e-9
