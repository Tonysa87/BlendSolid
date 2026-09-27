import math
import os

import numpy as np

import runner  # worker module, imported as the worker does

MODEL = """
length = 40.0
with BuildPart() as p:
    Box(length, 30, 20, align=Align.MIN)
    with Locations((20, 15, 0)):
        Cylinder(6, 25, align=(Align.CENTER, Align.CENTER, Align.MIN))
    fillet(p.edges().filter_by(Axis.Z).sort_by_distance((0, 0, 0))[0], radius=5)
result = p.part
"""
EXPECTED = 40 * 30 * 20 + math.pi * 36 * 5 - (1 - math.pi / 4) * 25 * 20


def mesh_volume(v, loops, sizes):
    v, total, start = v.astype(np.float64), 0.0, 0
    for n in sizes:  # fan-triangulate each polygon
        p = v[loops[start:start + n]]
        total += np.einsum("ij,ij->i", np.repeat(p[:1], n - 2, 0), np.cross(p[1:-1], p[2:])).sum()
        start += n
    return total / 6


def test_spike_model_volume_and_mesh():
    r = runner.run_script(MODEL)
    assert r.ok, r.error
    assert abs(r.volume - EXPECTED) < 1e-6
    assert r.verts.dtype == np.float32 and r.loops.dtype == np.int32 and r.poly_face.dtype == np.int32
    assert set(np.unique(r.poly_face)) == set(range(r.faces)) and r.poly_sizes.sum() == len(r.loops)
    assert abs(mesh_volume(r.verts, r.loops, r.poly_sizes) - EXPECTED) / EXPECTED < 0.01


def test_builder_is_accepted_as_result():
    r = runner.run_script("with BuildPart() as p:\n    Box(1, 2, 3)\nresult = p\n")
    assert r.ok and abs(r.volume - 6.0) < 1e-9


def test_syntax_error_reports_line():
    r = runner.run_script("length = 1.0\nresult = Box(length,\n")
    assert not r.ok and r.error.startswith("SyntaxError") and r.line == 2


def test_runtime_error_reports_script_line():
    r = runner.run_script("a = 1.0\nb = 2.0\nresult = Box(a, b, undefined_name)\n")
    assert not r.ok and "NameError" in r.error and r.line == 3


def test_missing_result():
    r = runner.run_script("x = Box(1, 1, 1)\n")
    assert not r.ok and "`result`" in r.error


def test_result_must_be_a_shape():
    r = runner.run_script("result = 42\n")
    assert not r.ok and "build123d shape" in r.error


def test_result_without_solid():
    r = runner.run_script("result = Rectangle(10, 10)\n")
    assert not r.ok and "no solid" in r.error


def test_sys_exit_in_script_is_an_error_not_an_exit():
    r = runner.run_script("import sys\nsys.exit(3)\n")
    assert not r.ok and "sys.exit" in r.error


def test_tessellation_failure_is_reported_not_raised(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(runner.tessellate, "tessellate_with_normals", boom)
    r = runner.run_script("with BuildPart() as p:\n    Box(1, 2, 3)\nresult = p\n")
    assert not r.ok and "RuntimeError: boom" in r.error and r.line is None


def test_a_broken_reference_is_reported_on_its_line():
    template = open(os.path.join(os.path.dirname(__file__), "..", "..", "blendsolid", "templates",
                                 "default_part.py")).read()
    line = '    fillet(edges_of(face("box_1", "+Q")), radius=1)  # feature: fillet_2'
    broken = template.replace("\nresult = part.part", line + "\n\nresult = part.part")
    r = runner.run_script(broken)
    assert not r.ok and "box_1 has no face '+Q'" in r.error
    assert r.line == broken.splitlines().index(line) + 1
    assert runner.run_script(MODEL).ok  # a script without feature markers runs as before
