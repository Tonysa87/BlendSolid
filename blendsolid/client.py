"""Blender-side handle on the geometry worker. bpy-free: every call returns immediately except start(),
which waits only for the worker process to connect (not for build123d to load).

Requests are coalesced per key (a part): a newer request for the same key replaces a queued one.
"""
import hmac
import os
import secrets
import socket
import subprocess
import tempfile
import time
from collections import OrderedDict
from multiprocessing.connection import Connection

from .worker import protocol


class WorkerStartError(RuntimeError):
    pass


class WorkerClient:
    def __init__(self, python, server, libs, pycache_dir="", start_timeout=30.0, job_timeout=120.0,
                 ready_timeout=120.0):
        """start_timeout: to connect and pass the handshake (short: a broken interpreter or server script
        fails fast). ready_timeout: from then on, to import build123d and report "ready" (long: a cold
        start on a slow disk or a busy machine can take a minute)."""
        self.python, self.server, self.libs, self.pycache_dir = python, server, libs, pycache_dir
        self.start_timeout, self.job_timeout, self.ready_timeout = start_timeout, job_timeout, ready_timeout
        self.state = "stopped"
        self.info = {}
        self.submitted = 0
        self._proc = self._conn = self._stderr = None
        self._pending = OrderedDict()  # key -> request header
        self._running = None           # (job, key, tag, started_at)
        self._ready_at = None
        self._next_job = 1

    # -- lifecycle ---------------------------------------------------------------------------------------

    def start(self):
        if self.state != "stopped":
            return
        token = secrets.token_hex(16)
        listener = socket.create_server(("127.0.0.1", 0))
        self._stderr = tempfile.TemporaryFile()
        env = dict(os.environ, BLENDSOLID_WORKER_TOKEN=token)
        deadline = time.monotonic() + self.start_timeout
        try:
            try:
                self._proc = subprocess.Popen(
                    [self.python, "-I", self.server, str(listener.getsockname()[1]), self.libs, self.pycache_dir,
                     str(os.getpid())],  # the worker exits by itself when this process is gone
                    env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=self._stderr,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError as e:
                self._fail(f"could not start the worker process: {e}")
            sock = self._accept(listener, deadline)
        finally:
            listener.close()

        conn = Connection(sock.detach())
        remaining = max(0.0, deadline - time.monotonic())
        try:
            token_ok = (conn.poll(remaining)
                        and hmac.compare_digest(conn.recv_bytes(maxlength=64), token.encode("ascii")))
        except (OSError, EOFError):
            token_ok = False
        if not token_ok:
            conn.close()
            self._fail("the worker failed the handshake")

        self._conn = conn
        self.state = "starting"
        self._ready_at = time.monotonic()

    def _accept(self, listener, deadline):
        """Accept in short slices against a single deadline, so a worker that exits before connecting (a
        bad interpreter path, a bad server script) is reported almost immediately rather than after the
        full start_timeout."""
        while True:
            if self._proc.poll() is not None:
                self._fail(f"the worker exited with code {self._proc.returncode} before connecting")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._fail(f"the worker did not connect within {self.start_timeout:.0f} s")
            listener.settimeout(min(0.1, remaining))
            try:
                sock, _ = listener.accept()
                return sock
            except OSError:
                continue

    def _fail(self, message):
        """Read the worker's stderr tail before _kill() discards it, then raise WorkerStartError."""
        tail = self._stderr_tail()
        self._kill()
        raise WorkerStartError(message + (f"\n{tail}" if tail else ""))

    def stop(self):
        if self._conn is not None and self._proc is not None and self._proc.poll() is None:
            try:
                protocol.send_message(self._conn, {"type": "quit"})
                self._proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self._kill()

    def kill(self):
        """Kill the worker right away (e.g. at interpreter exit), without asking it to quit first."""
        self._kill()

    def _kill(self):
        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait()
        if self._conn is not None:
            self._conn.close()
        if self._stderr is not None:
            try:
                self._stderr.close()
            except OSError:
                pass
        self._proc = self._conn = self._stderr = None
        self._running = None
        self.state = "stopped"

    # -- requests ----------------------------------------------------------------------------------------

    def submit(self, key, source, tag, lin_defl=0.1, ang_defl=0.3):
        self._pending[key] = {"type": "run", "key": key, "tag": tag, "source": source,
                              "lin_defl": lin_defl, "ang_defl": ang_defl}
        self._pending.move_to_end(key)
        if self.state == "stopped":
            self.start()
        self._dispatch()

    def _dispatch(self):
        if self.state != "idle" or not self._pending:
            return
        key, req = self._pending.popitem(last=False)
        job = self._next_job
        self._next_job += 1
        req["job"] = job
        try:
            protocol.send_message(self._conn, req)
        except OSError:
            # the worker died between becoming idle and us sending: keep the request (the next poll()
            # will detect the dead process and report it, via `dropped` or as the running job) and don't
            # raise into submit()'s caller.
            del req["job"]
            self._pending[key] = req
            self._pending.move_to_end(key, last=False)
            return
        self.submitted += 1
        self._running = (job, key, req["tag"], time.monotonic())
        self.state = "busy"

    # -- events ------------------------------------------------------------------------------------------

    def poll(self):
        events = []
        if self.state == "stopped":
            return events
        try:
            while self._conn.poll(0):
                header, arrays = protocol.recv_message(self._conn)
                kind = header["type"]
                if kind == "ready":
                    self.info = header
                    self.state = "idle"
                elif kind == "result":
                    header.update(arrays)
                    self._running = None
                    self.state = "idle"
                elif kind == "fatal":
                    events.append(self._crash(header["error"]))
                    return events
                events.append(header)
                self._dispatch()
        except (EOFError, OSError, protocol.ProtocolError) as e:
            events.append(self._crash(f"lost the connection to the worker ({type(e).__name__})"))
            return events
        now = time.monotonic()
        if self._proc.poll() is not None:
            events.append(self._crash(f"the worker exited with code {self._proc.returncode}"))
        elif self._running and now - self._running[3] > self.job_timeout:
            events.append(self._crash(f"the recompute timed out after {self.job_timeout:.0f} s"))
        elif self.state == "starting" and now - self._ready_at > self.ready_timeout:
            events.append(self._crash(f"the worker was not ready after {self.ready_timeout:.0f} s"))
        return events

    def _crash(self, reason):
        job, key, tag = (self._running or (None, None, None, None))[:3]
        dropped = [[k, req["tag"]] for k, req in self._pending.items()]
        self._pending.clear()  # the caller decides what to resubmit; never restart in a loop by ourselves
        tail = self._stderr_tail()
        self._kill()
        return {"type": "crashed", "job": job, "key": key, "tag": tag, "dropped": dropped,
                "error": reason + (f"\n{tail}" if tail else "")}

    def _stderr_tail(self, limit=2000):
        if self._stderr is None:
            return ""
        try:
            self._stderr.seek(0)
            return self._stderr.read().decode("utf-8", "replace")[-limit:].strip()
        except OSError:
            return ""
