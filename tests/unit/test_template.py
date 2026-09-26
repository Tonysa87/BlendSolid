"""The default part (New Part, milestone 1) is a canonical script, so the tools can add features to it."""
import math
import os

import runner  # worker module, imported as the worker does
from blendsolid import params, script_model as sm

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "blendsolid", "templates", "default_part.py")
EXPECTED = 40 * 30 * 20 + math.pi * 36 * 5 - (1 - math.pi / 4) * 25 * 20


def template():
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def test_default_template_is_canonical():
    source = template()
    assert source.startswith(sm.HEADER + "\n")
    assert [(f.name, f.kind) for f in sm.features(source)] == [
        ("box_1", "box"), ("boss_1", "cylinder"), ("fillet_1", "other")]
    assert [p.name for p in params.parse_params(source)] == [
        "box_1_length", "box_1_width", "box_1_height", "boss_1_radius", "boss_1_height", "fillet_1_radius"]


def test_default_template_volume_is_unchanged():
    r = runner.run_script(template())
    assert r.ok, r.error
    assert abs(r.volume - EXPECTED) < 1e-6
