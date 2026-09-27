"""BlendSolid geometry worker: runs history scripts with build123d in its own Python process.

Started by blendsolid.client with Blender's Python in isolated mode:
    python -I server.py <port> <libs_dir> <pycache_dir> <parent_pid>     (env: BLENDSOLID_WORKER_TOKEN)
It connects back to Blender on 127.0.0.1:<port>, proves the token, imports build123d, reports "ready",
then answers one request at a time. This process, not Blender, owns sys.path and the heavy imports.

It never outlives Blender: a watchdog thread exits the process as soon as the parent is gone, even while a
script is stuck in an endless loop (Blender doesn't call add-ons' unregister() on quit, and may crash).
"""
import os
import socket
import sys
import threading
import time
from multiprocessing.connection import Connection

WATCH_INTERVAL = 0.25


def _exit_with_parent_posix(parent_pid):
    """Linux also gets PR_SET_PDEATHSIG, which works even while a C extension holds the GIL; the polling
    thread below covers every POSIX system (the parent's death re-parents us: getppid() changes)."""
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            import signal
            ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL)  # 1 = PR_SET_PDEATHSIG
        except Exception:
            pass
    initial_ppid = os.getppid()

    def parent_alive():
        if os.getppid() != initial_ppid:
            return False
        if parent_pid == initial_ppid:
            return True
        try:  # started through some intermediate process: also watch the PID Blender passed explicitly
            os.kill(parent_pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            pass
        return True

    def watch():
        while parent_alive():
            time.sleep(WATCH_INTERVAL)
        os._exit(0)

    if not parent_alive():
        os._exit(0)
    threading.Thread(target=watch, name="blendsolid-parent-watchdog", daemon=True).start()


def _exit_with_parent_windows(parent_pid):
    import ctypes
    from ctypes import wintypes
    synchronize, infinite, error_invalid_parameter = 0x00100000, 0xFFFFFFFF, 87
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    handle = kernel32.OpenProcess(synchronize, False, parent_pid)  # opened now, while the parent is alive
    if not handle:
        if ctypes.get_last_error() == error_invalid_parameter:
            os._exit(0)  # no such process: the parent is already gone
        return  # can't watch it (should not happen for our own parent): run unwatched rather than not at all

    def watch():
        kernel32.WaitForSingleObject(handle, infinite)
        os._exit(0)

    threading.Thread(target=watch, name="blendsolid-parent-watchdog", daemon=True).start()


def exit_with_parent(parent_pid):
    if sys.platform == "win32":
        _exit_with_parent_windows(parent_pid)
    else:
        _exit_with_parent_posix(parent_pid)


def main():
    port, libs = int(sys.argv[1]), sys.argv[2]
    parent_pid = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else os.getppid()
    exit_with_parent(parent_pid)
    if len(sys.argv) > 3 and sys.argv[3]:
        sys.pycache_prefix = sys.argv[3]
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path[:0] = [libs, here]  # -I doesn't add the script folder; our libraries win over Blender's

    import protocol

    conn = Connection(socket.create_connection(("127.0.0.1", port)).detach())
    conn.send_bytes(os.environ["BLENDSOLID_WORKER_TOKEN"].encode("ascii"))
    t0 = time.perf_counter()
    try:
        import build123d
        import runner
    except Exception as e:
        protocol.send_message(conn, {"type": "fatal", "error": f"cannot load build123d: {type(e).__name__}: {e}"})
        return 1
    protocol.send_message(conn, {"type": "ready", "build123d": build123d.__version__,
                                 "import_s": time.perf_counter() - t0})
    while True:
        try:
            header, _ = protocol.recv_message(conn)
        except EOFError:
            return 0
        kind = header["type"]
        if kind == "quit":
            return 0
        try:
            if kind == "ping":
                protocol.send_message(conn, {"type": "pong"})
            elif kind == "run":
                r = runner.run_script(header["source"], header.get("lin_defl", 0.1), header.get("ang_defl", 0.3),
                                      deps=header.get("deps") or (), tag=header["tag"])
                reply = {"type": "result", "job": header["job"], "key": header["key"], "tag": header["tag"],
                         "ok": r.ok, "error": r.error, "line": r.line, "volume": r.volume, "faces": r.faces,
                         "timing": r.timing, "face_refs": r.face_refs, "edge_refs": r.edge_refs}
                arrays = ({"verts": r.verts, "loops": r.loops, "poly_sizes": r.poly_sizes, "poly_face": r.poly_face,
                           "planes": r.planes,
                           "corner_normals": r.corner_normals, "edges": r.edges, "edge_ids": r.edge_ids,
                           "edge_sharp": r.edge_sharp} if r.ok else None)
                protocol.send_message(conn, reply, arrays)
            else:
                protocol.send_message(conn, {"type": "error", "error": f"unknown request {kind!r}"})
        except Exception as e:
            # runner.run_script never raises; this guards against a bug while building/sending the reply
            # itself, so a single malformed request can't take the whole worker process down with it. A
            # failed "run" is answered as a `result` (ok=False) so the client leaves "busy" immediately;
            # `error` is reserved for requests of an unknown type.
            if kind == "run":
                reply = {"type": "result", "job": header.get("job"), "key": header.get("key"),
                         "tag": header.get("tag"), "ok": False, "error": f"{type(e).__name__}: {e}",
                         "line": None, "volume": 0.0, "faces": 0, "timing": {}}
                try:
                    protocol.send_message(conn, reply)
                except Exception:
                    return 1
            else:
                try:
                    protocol.send_message(conn, {"type": "error", "error": f"{type(e).__name__}: {e}"})
                except Exception:
                    return 1


if __name__ == "__main__":
    sys.exit(main())
