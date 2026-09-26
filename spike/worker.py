"""OCCT worker in a process separate from Blender (objective 7).

Protocol over stdin/stdout: length-prefixed pickle messages (8 bytes, little endian).
Request:   {"op": "build", "params": {...}, "lin_defl": 0.1}
Response:  {"ok": True, "verts": bytes, "tris": bytes, "tri_face": bytes, "n": (nv, nt), "timing": {...}}
stdout is reserved for the protocol: logs go to stderr.
pickle is acceptable here only because the pipe is private between Blender and a child Blender itself spawns;
for milestone 1 prefer a format that does not execute code (JSON header + raw numpy buffers).
"""
import os
import pickle
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def read_exact(stream, n):
    """Pipes can return partial reads: read exactly n bytes (or None on EOF)."""
    buf = bytearray()
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return bytes(buf)


def read_msg(stream):
    head = read_exact(stream, 8)
    if head is None:
        return None
    (n,) = struct.unpack("<Q", head)
    return pickle.loads(read_exact(stream, n))


def write_msg(stream, obj):
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(struct.pack("<Q", len(data)))
    stream.write(data)
    stream.flush()


def main():
    t0 = time.perf_counter()
    sys.path.insert(0, sys.argv[1])  # directory containing OCP
    import occ_model
    t_import = time.perf_counter() - t0
    inp, out = sys.stdin.buffer, sys.stdout.buffer
    write_msg(out, {"ready": True, "import": t_import})
    while True:
        req = read_msg(inp)
        if req is None or req.get("op") == "quit":
            return
        try:
            _, (verts, tris, tri_face), tm = occ_model.build_and_tessellate(
                req.get("params"), req.get("lin_defl", 0.1), req.get("ang_defl", 0.3))
            t = time.perf_counter()
            resp = {"ok": True, "verts": verts.tobytes(), "tris": tris.tobytes(),
                    "tri_face": tri_face.tobytes(), "n": (len(verts), len(tris)), "timing": tm}
            resp["timing"]["pack"] = time.perf_counter() - t
        except Exception as e:
            resp = {"ok": False, "error": repr(e)}
        write_msg(out, resp)


if __name__ == "__main__":
    main()
