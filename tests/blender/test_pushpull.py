"""Milestone 2 phase D: Push/Pull a clicked flat face (a new feature extruding it out, or cutting it in)."""
import math

import bpy
import pytest

from blendsolid import part, script_model
from conftest import mm3, up_to_date, wait_for


@pytest.fixture
def default_part(clean):
    obj = part.new_part(bpy.context)  # box 40 x 30 x 20 mm from the origin, boss r6 h25 at (20, 15), fillet r5
    wait_for(lambda: up_to_date(obj))
    return obj


def push(obj, reference, amount):
    return bpy.ops.blendsolid.push_pull(target=obj.name, reference=reference, amount=amount)


def test_pull_a_face_out_and_follow_an_upstream_change(default_part):
    v0 = mm3(default_part)
    assert push(default_part, 'face("box_1", "+X")', 10.0) == {"FINISHED"}
    source = part.source_of(default_part)
    assert 'extrude(face("box_1", "+X"), amount=push_1_amount, mode=Mode.ADD)' in source
    assert script_model.features(source)[-1].name == "push_1"
    wait_for(lambda: up_to_date(default_part))
    assert mm3(default_part) - v0 == pytest.approx(30 * 20 * 10, rel=1e-3)
    part.set_param(default_part, "box_1_height", 30.0)  # the face grows: so does the pulled block
    wait_for(lambda: up_to_date(default_part))
    assert default_part.blendsolid_error == ""
    # the box grows by 10 mm (its filleted corner too), the boss (25 mm high) is now inside it, and the pulled
    # block is 30 x 30 x 10
    grown = 40 * 30 * 10 - (25 - 25 * math.pi / 4) * 10 - math.pi * 36 * 5 + 30 * 30 * 10
    assert mm3(default_part) - v0 == pytest.approx(grown, rel=5e-3)


def test_push_a_face_in_cuts(default_part):
    v0 = mm3(default_part)
    assert push(default_part, 'face("box_1", "-Z")', -5.0) == {"FINISHED"}
    assert 'amount=-push_1_amount, mode=Mode.SUBTRACT' in part.source_of(default_part)
    wait_for(lambda: up_to_date(default_part))
    bottom = 40 * 30 - (25 - 25 * math.pi / 4)  # the bottom face, its corner rounded by the template's fillet
    assert v0 - mm3(default_part) == pytest.approx(bottom * 5, rel=1e-3)


def test_curved_faces_and_zero_are_refused(default_part):
    with pytest.raises(RuntimeError, match="flat"):
        push(default_part, 'face("boss_1", "side")', 5.0)
    with pytest.raises(RuntimeError):
        push(default_part, 'face("box_1", "+X")', 0.0)
