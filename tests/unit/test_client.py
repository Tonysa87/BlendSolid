import time

import pytest

from blendsolid import paths
from blendsolid.client import WorkerClient

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
    assert r["verts"].shape[1] == 3 and len(r["tri_face"]) == len(r["tris"])
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
