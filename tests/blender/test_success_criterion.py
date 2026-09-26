"""Milestone 1.5's success criterion (docs/spec.md), headless: with operators only (no hand-written script), build
the milestone 1 default part and a bracket with 3 holes from parametric primitives (Shift+A), Draw Solid (on a
face; union/cut by direction) and booleans between parts with live cutters; every step is one undo step and one
script edit. Draw Solid runs through execute(), with the properties its modal would set (see test_draw_tool.py
for the modal itself)."""
import math

import bpy
from mathutils import Euler

from blendsolid import part, runtime, script_model
from conftest import mm3, select, up_to_date, wait_for

M1_DEFAULT = 40 * 30 * 20 + math.pi * 36 * 5 - (1 - math.pi / 4) * 25 * 20
BRACKET = 60 * 40 * 5 + 5 * 40 * 35 - 2 * math.pi * 9 * 5 - math.pi * 16 * 5


def scripts():
    return {o.name: part.source_of(o) for o in bpy.data.objects if o.blendsolid_script is not None}


def n_features(source):
    return len(script_model.features(source))


def one_step(operator, **props):
    """Run `operator` as Blender runs a user's action (with an undo push) and check it was one script edit
    (one new single-feature part, or one more feature in one part) and one undo step. A `runtime.tick()`
    right after the operator submits the "after" script to the worker, so its recompute is genuinely in
    flight when we undo below (background mode never does this on its own: no timer drives the reconcile
    loop) - checked directly against `runtime._inflight`, or there would be nothing for the guard below to
    discard and this test would pass the same way whether or not that guard exists. `runtime._inflight` is
    plain Python state, not part of Blender's undo stack, so that job is still in flight once the undo
    reverts the script; whatever mesh its result would have produced must never reach the part once
    reverted (`runtime._handle`'s stale-result guard: same technique as
    test_parts.py::test_stale_result_is_discarded, recording every tag `part.apply_result` is called with).
    A follow-up reconcile tick harmlessly resubmits and re-applies the correct ("before") result on its own,
    which is why this can't be told apart from a missing guard by the converged end state alone (`up_to_date`
    would pass either way) - the recording is what actually exercises the guard. Returns the name of the
    part it made or edited."""
    before = scripts()
    assert operator("EXEC_DEFAULT", True, **props) == {"FINISHED"}
    after = scripts()
    added = set(after) - set(before)
    changed = [n for n in before if after.get(n) != before[n]]
    if added:
        assert len(added) == 1 and not changed, (added, changed)
        (name,) = added
        assert n_features(after[name]) == 1
    else:
        assert len(changed) == 1, changed
        (name,) = changed
        assert n_features(after[name]) == n_features(before[name]) + 1
    after_tag = part.current_tag(bpy.data.objects[name])
    applied_tags = []
    orig_apply_result = part.apply_result

    def recording_apply_result(obj, event, factor):
        applied_tags.append(event["tag"])
        orig_apply_result(obj, event, factor)

    part.apply_result = recording_apply_result
    try:
        runtime.tick()  # submit the "after" script now, before it is undone below
        assert runtime._inflight.get(name) == after_tag, (
            "the worker must have a pending job for the 'after' script at undo time, or there is nothing "
            "for the stale-result guard below to discard")
        bpy.ops.ed.undo()
        assert scripts() == before, "one undo must restore the state before the step"
        wait_for(all_up_to_date)  # meshes converge on the restored ("before") scripts; the "after" result,
                                  # once in flight above, must never be applied along the way (checked below)
    finally:
        part.apply_result = orig_apply_result
    assert after_tag not in applied_tags, "the in-flight 'after' result must be discarded as stale, not applied"
    bpy.ops.ed.redo()
    assert scripts() == after
    return name


def all_up_to_date():
    return all(up_to_date(o) or o.blendsolid_error for o in bpy.data.objects if o.blendsolid_script is not None)


def cursor_at(mm, rotation_deg=(0, 0, 0)):
    c = bpy.context.scene.cursor
    c.location = [v * part.unit_factor() for v in mm]
    c.rotation_euler = Euler([math.radians(a) for a in rotation_deg])


def test_build_the_default_part_and_a_bracket_with_three_holes(clean):
    ops = bpy.ops.blendsolid
    bpy.ops.ed.undo_push(message="start")  # background mode: the undo stack starts with an explicit push

    # -- the milestone 1 default part: box, boss (Draw Solid union), vertical fillet (a live cutter) -----------------
    cursor_at((0, 0, 0))
    body = one_step(ops.add_box, length=40, width=30, height=20)            # x -20..20, y -15..15, z 0..20
    one_step(ops.draw_solid, shape="CYLINDER", mode="UNION", target=body, location=(0, 0, 20),
             rotation=(0, 0, 0), radius=6, height=5)                          # the boss, on the top face
    cursor_at((-20, -15, -5))
    corner = one_step(ops.add_box, length=10, width=10, height=30)          # around the corner edge
    one_step(ops.draw_solid, shape="CYLINDER", mode="CUT", target=corner, location=(5, 5, 30),
             rotation=(0, 0, 0), radius=5, height=30)                         # leaves the fillet's waste
    select(bpy.data.objects[body], bpy.data.objects[corner])
    one_step(ops.boolean, operation="DIFFERENCE")

    # -- the bracket: base plate, flange (Draw Solid union), 2 holes (Draw Solid cut), 1 hole (cutter part) --------
    cursor_at((100, 0, 0))
    bracket = one_step(ops.add_box, length=60, width=40, height=5)         # x 70..130 in the world
    one_step(ops.draw_solid, shape="BOX", mode="UNION", target=bracket, location=(-27.5, 0, 5),
             rotation=(0, 0, 0), length=5, width=40, height=35)               # the upright flange
    for y in (-10, 10):
        one_step(ops.draw_solid, shape="CYLINDER", mode="CUT", target=bracket, location=(10, y, 5),
                 rotation=(0, 0, 0), radius=3, height=5)
    cursor_at((60, 0, 25), rotation_deg=(0, 90, 0))                          # a pin along +X through the flange
    pin = one_step(ops.add_cylinder, radius=4, height=20)
    select(bpy.data.objects[bracket], bpy.data.objects[pin])
    one_step(ops.boolean, operation="DIFFERENCE")

    body, corner, bracket, pin = (bpy.data.objects[n] for n in (body, corner, bracket, pin))
    wait_for(lambda: all(up_to_date(o) and not o.blendsolid_error for o in (body, corner, bracket, pin)))
    assert [f.name for f in script_model.features(part.source_of(body))] == ["box_1", "cylinder_1", "bool_1"]
    assert abs(mm3(body) - M1_DEFAULT) / M1_DEFAULT < 0.005
    assert [f.name for f in script_model.features(part.source_of(bracket))] == [
        "box_1", "box_2", "cut_1", "cut_2", "bool_1"]
    assert abs(mm3(bracket) - BRACKET) / BRACKET < 0.005
    assert corner.display_type == "WIRE" and pin.display_type == "WIRE"

    # the same volume as New Part's default part (milestone 1), built by the worker from its template
    bpy.ops.blendsolid.new_part()
    reference = bpy.context.view_layer.objects.active
    wait_for(lambda: up_to_date(reference))
    assert abs(mm3(body) - mm3(reference)) / M1_DEFAULT < 0.005

    # live cutter: moving the pin out of the flange closes the third hole, moving it back reopens it
    pin.location.z += 0.1
    bpy.context.view_layer.update()
    wait_for(lambda: up_to_date(bracket))
    assert abs(mm3(bracket) - (BRACKET + math.pi * 16 * 5)) / BRACKET < 0.005
    pin.location.z -= 0.1
    bpy.context.view_layer.update()
    wait_for(lambda: up_to_date(bracket))
    assert abs(mm3(bracket) - BRACKET) / BRACKET < 0.005
