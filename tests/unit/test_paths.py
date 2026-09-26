import os
import sys

from blendsolid import paths


def test_server_script_exists():
    assert os.path.isfile(paths.server_script())


def test_python_executable_is_a_python():
    exe = os.path.basename(paths.python_executable()).lower()
    assert exe.startswith("python"), exe


def test_worker_libs_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("BLENDSOLID_WORKER_LIBS", str(tmp_path))
    assert paths.worker_libs() == str(tmp_path)


def test_worker_libs_finds_dev_folder(monkeypatch):
    monkeypatch.delenv("BLENDSOLID_WORKER_LIBS", raising=False)
    assert paths.worker_libs().endswith(os.path.join(".dev", "worker_libs"))


def test_pycache_dir_without_blender_falls_back_to_temp():
    d = paths.pycache_dir("blendsolid")
    assert os.path.isdir(d)
    assert "bpy" not in sys.modules
