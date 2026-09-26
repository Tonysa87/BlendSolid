"""BlendSolid geometry worker: runs history scripts with build123d in its own Python process.

Started by blendsolid.client with Blender's Python in isolated mode:
    python -I server.py <port> <libs_dir> <pycache_dir>     (env: BLENDSOLID_WORKER_TOKEN)
It connects back to Blender on 127.0.0.1:<port>, proves the token, imports build123d, reports "ready",
then answers one request at a time. This process, not Blender, owns sys.path and the heavy imports.
"""
import os
import socket
import sys
import time
from multiprocessing.connection import Connection


def main():
    port, libs = int(sys.argv[1]), sys.argv[2]
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
                r = runner.run_script(header["source"], header.get("lin_defl", 0.1), header.get("ang_defl", 0.3))
                reply = {"type": "result", "job": header["job"], "key": header["key"], "tag": header["tag"],
                         "ok": r.ok, "error": r.error, "line": r.line, "volume": r.volume, "faces": r.faces,
                         "timing": r.timing}
                arrays = {"verts": r.verts, "tris": r.tris, "tri_face": r.tri_face} if r.ok else None
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
