"""Where the add-on finds the worker's interpreter, entry point, libraries and bytecode cache."""
import os
import sys
import tempfile

PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def python_executable():
    """Blender's bundled Python (in Blender 5.2 `sys.executable` is the python binary, not blender)."""
    return sys.executable


def server_script():
    return os.path.join(PKG_DIR, "worker", "server.py")


def worker_libs():
    """Private library folder of the worker: env override, bundled folder, then the dev checkout's .dev/."""
    env = os.environ.get("BLENDSOLID_WORKER_LIBS")
    if env:
        return env
    for candidate in (os.path.join(PKG_DIR, "worker_libs"),
                      os.path.join(os.path.dirname(PKG_DIR), ".dev", "worker_libs")):
        if os.path.isdir(candidate):
            return candidate
    raise FileNotFoundError(
        "BlendSolid worker libraries not found: run tools/setup_dev.sh or set BLENDSOLID_WORKER_LIBS")


def pycache_dir(package):
    """Writable bytecode cache for the worker (the extension folder may be read-only)."""
    try:
        import bpy
        return bpy.utils.extension_path_user(package, path="pycache", create=True)
    except Exception:  # not running as an installed extension (dev checkout, unit tests)
        d = os.path.join(tempfile.gettempdir(), "blendsolid-pycache")
        os.makedirs(d, exist_ok=True)
        return d
