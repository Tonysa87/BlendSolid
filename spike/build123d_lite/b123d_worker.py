"""OCCT worker that runs build123d history scripts in its own interpreter (build123d decision research).

The worker builds its own sys.path (private libs dir first), installs the stub finder and imports build123d.
None of this touches Blender's interpreter: Blender only exchanges messages with this process.

Usage: python b123d_worker.py <libs_dir> <ocp_site_dir>
Request:  {"op": "run", "name": str, "script": str}   the script must assign the final shape to `result`
Response: {"ok": True, "volume", "valid", "faces", "verts", "tris", "tri_face", "timing", "stubs_used"}
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SPIKE = os.path.dirname(HERE)


def main():
    t0 = time.perf_counter()
    libs, ocp_site = sys.argv[1], sys.argv[2]
    # private path order: our libs (incl. typing_extensions >= 4.16) win over the interpreter's site-packages
    sys.path[:0] = [libs, HERE, SPIKE, ocp_site]
    import lite_shim
    lite_shim.install()
    import build123d
    import typing_extensions
    from importlib.metadata import version

    import occ_model
    from worker import read_msg, write_msg
    t_import = time.perf_counter() - t0

    inp, out = sys.stdin.buffer, sys.stdout.buffer
    write_msg(out, {"ready": True, "import": t_import, "build123d": build123d.__version__,
                    "typing_extensions": version("typing_extensions"),
                    "typing_extensions_file": typing_extensions.__file__})
    while True:
        req = read_msg(inp)
        if req is None or req.get("op") == "quit":
            return
        try:
            ns = {}
            exec("from build123d import *\n", ns)
            n_used = len(lite_shim.used)
            t1 = time.perf_counter()
            exec(compile(req["script"], req.get("name", "<history>"), "exec"), ns)
            t2 = time.perf_counter()
            shape = ns["result"]
            info = occ_model.check(shape.wrapped)
            verts, tris, tri_face = occ_model.tessellate(shape.wrapped)
            t3 = time.perf_counter()
            resp = {"ok": True, "volume": info["volume"], "valid": info["valid"], "faces": info["faces"],
                    "verts": verts.tobytes(), "tris": tris.tobytes(), "tri_face": tri_face.tobytes(),
                    "timing": {"script": t2 - t1, "tessellate": t3 - t2},
                    "stubs_used": lite_shim.used[n_used:]}
        except Exception as e:
            resp = {"ok": False, "error": f"{type(e).__name__}: {e}", "stubs_used": lite_shim.used[-3:]}
        write_msg(out, resp)


if __name__ == "__main__":
    main()
