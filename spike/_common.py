"""Helpers shared by the spike scripts (throwaway code)."""
import os
import sys
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent


def site_dir() -> str:
    """Directory where cadquery-ocp-novtk is installed for the current Blender."""
    if os.environ.get("BLENDSOLID_SITE"):
        return os.environ["BLENDSOLID_SITE"]
    exe_dir = Path(sys.executable).resolve().parent
    # sys.executable = <blender>/5.2/python/bin/python(.exe) or <blender>/blender(.exe)
    for p in [exe_dir, *exe_dir.parents]:
        if (p / "spike_site").is_dir():
            return str(p / "spike_site")
    raise RuntimeError("spike_site not found: set BLENDSOLID_SITE")


def add_ocp_path():
    s = site_dir()
    if s not in sys.path:
        sys.path.insert(0, s)
    return s


def loaded_modules():
    """Paths of the native modules loaded in the process (DLLs on Windows, .so on Linux)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD)]
        psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR,
                                               wintypes.DWORD]
        proc = kernel32.GetCurrentProcess()
        arr = (wintypes.HMODULE * 4096)()
        needed = wintypes.DWORD()
        psapi.EnumProcessModules(proc, arr, ctypes.sizeof(arr), ctypes.byref(needed))
        out = []
        buf = ctypes.create_unicode_buffer(1024)
        for i in range(needed.value // ctypes.sizeof(wintypes.HMODULE)):
            psapi.GetModuleFileNameExW(proc, arr[i], buf, 1024)
            out.append(buf.value)
        return out
    with open("/proc/self/maps") as f:
        return sorted({line.split()[-1] for line in f if line.rstrip().endswith((".so",)) or ".so." in line})
