"""ref(): a part's script uses another part (a live cutter), placed by the matrix Blender sends."""
import math

import numpy as np

import runner  # worker module, imported as the worker does

PLATE = ("with BuildPart() as part:\n"
         "    Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n"
         "    insert(ref(\"pin\"), mode=Mode.SUBTRACT)  # feature: bool_1\n"
         "result = part.part\n")
PIN = "with BuildPart() as part:\n    Cylinder(3, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))\nresult = part.part\n"
IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]


def moved(x, y, z):
    return [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z]


def dep(part_id="pin", source=PIN, tag="pin-1", matrix=None, deps=(), matrices=None, name="Pin"):
    return {"id": part_id, "name": name, "source": source, "tag": tag,
            "matrices": [matrix or moved(5, 0, -5)] if matrices is None else matrices, "deps": list(deps)}


def test_ref_subtracts_the_cutter_in_the_target_frame():
    r = runner.run_script(PLATE, deps=[dep()], cache=runner.ShapeCache())
    assert r.ok, r.error
    assert abs(r.volume - (40 * 30 * 10 - math.pi * 9 * 10)) < 1e-6


def test_cutter_outside_the_part_cuts_nothing():
    r = runner.run_script(PLATE, deps=[dep(matrix=moved(100, 0, 0))], cache=runner.ShapeCache())
    assert r.ok, r.error
    assert abs(r.volume - 40 * 30 * 10) < 1e-6


def test_rotated_cutter():
    # rotated 90 degrees about Y, the pin's +Z axis becomes +X: it runs from x = -30 to x = -10 at z = 5,
    # so its last 10 mm (x = -20 to -10) are inside the plate
    rot_y = [0, 0, 1, -30, 0, 1, 0, 0, -1, 0, 0, 5]
    r = runner.run_script(PLATE, deps=[dep(matrix=rot_y)], cache=runner.ShapeCache())
    assert r.ok, r.error
    assert abs(r.volume - (40 * 30 * 10 - math.pi * 9 * 10)) < 1e-6


def test_float32_rounded_rotation_is_still_a_valid_solid():
    # Blender's matrix_world is float32: a "pure" rotation's determinant differs from 1 by ~1e-8 once widened
    # to float64 -- inside the orthonormality tolerance, but enough for gp_Trsf.SetValues to derive a
    # non-unit scale factor from it and fail BRepCheck unless the rotation is re-orthonormalized first.
    def rot_z(deg):
        t = np.float32(math.radians(deg))
        c, s = np.float32(np.cos(t)), np.float32(np.sin(t))
        return [float(c), float(-s), 0.0, 5.0, float(s), float(c), 0.0, 0.0, 0.0, 0.0, 1.0, -5.0]

    for deg in (30, 45):
        r = runner.run_script(PLATE, deps=[dep(matrix=rot_z(deg))], cache=runner.ShapeCache())
        assert r.ok, r.error
        assert abs(r.volume - (40 * 30 * 10 - math.pi * 9 * 10)) < 1e-6


def test_every_linked_duplicate_of_a_cutter_cuts():
    r = runner.run_script(PLATE, deps=[dep(matrices=[moved(-10, 0, -5), moved(10, 0, -5)])],
                          cache=runner.ShapeCache())
    assert r.ok, r.error
    assert abs(r.volume - (40 * 30 * 10 - 2 * math.pi * 9 * 10)) < 1e-6


def test_dependency_shapes_are_cached_by_tag():
    cache = runner.ShapeCache()
    assert runner.run_script(PLATE, deps=[dep()], cache=cache).ok
    assert len(cache) == 1
    # same tag, broken source: the cached shape is used, the source isn't run again
    r = runner.run_script(PLATE, deps=[dep(source="raise RuntimeError('not run')")], cache=cache)
    assert r.ok, r.error


def test_result_is_cached_under_its_own_tag():
    cache = runner.ShapeCache()
    assert runner.run_script(PIN, tag="pin-1", cache=cache).ok
    r = runner.run_script(PLATE, deps=[dep(source="raise RuntimeError('not run')")], cache=cache)
    assert r.ok, r.error


def test_nested_references():
    holder = ("with BuildPart() as part:\n    insert(ref(\"pin\"))  # feature: bool_1\nresult = part.part\n")
    deps = [dep("holder", holder, "holder-1", moved(0, 0, 0), deps=[dep()])]
    r = runner.run_script(PLATE.replace('ref("pin")', 'ref("holder")'), deps=deps, cache=runner.ShapeCache())
    assert r.ok, r.error
    assert abs(r.volume - (40 * 30 * 10 - math.pi * 9 * 10)) < 1e-6


def test_unknown_reference_is_an_error_on_the_ref_line():
    r = runner.run_script(PLATE, deps=[], cache=runner.ShapeCache())
    assert not r.ok and "ref('pin')" in r.error and r.line == 3


def test_broken_dependency_is_reported_on_the_ref_line():
    # ADR 0002: the cutter is named as the user knows it (its object name), never by its part id
    r = runner.run_script(PLATE, deps=[dep(source="result = Box(1, 1,\n")], cache=runner.ShapeCache())
    assert not r.ok and "the cutter 'Pin' could not be built" in r.error and "SyntaxError" in r.error
    assert "ref(" not in r.error and r.line == 3
    r = runner.run_script(PLATE, deps=[dep(source="x = 1\n")], cache=runner.ShapeCache())
    assert not r.ok and "the cutter 'Pin'" in r.error and "`result`" in r.error and r.line == 3


def test_a_nested_failure_names_the_part_that_failed():
    holder = ("with BuildPart() as part:\n    insert(ref(\"pin\"))  # feature: bool_1\nresult = part.part\n")
    deps = [dep("holder", holder, "holder-1", moved(0, 0, 0), deps=[dep(source="raise ValueError('bad')\n")],
                name="Holder")]
    r = runner.run_script(PLATE.replace('ref("pin")', 'ref("holder")'), deps=deps, cache=runner.ShapeCache())
    assert not r.ok and "the cutter 'Pin' could not be built: ValueError: bad" in r.error and "ref(" not in r.error


def test_unplaced_dependency_is_named():
    r = runner.run_script(PLATE, deps=[dep(matrices=[])], cache=runner.ShapeCache())
    assert not r.ok and "the cutter 'Pin' is not placed anywhere" in r.error and r.line == 3


def test_scaled_placement_is_refused():
    r = runner.run_script(PLATE, deps=[dep(matrix=[2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0])],
                          cache=runner.ShapeCache())
    assert not r.ok and "the cutter 'Pin' is scaled" in r.error and r.line == 3


def test_cache_drops_the_least_recently_used():
    cache = runner.ShapeCache(size=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert cache.get("b") is None and cache.get("a") == 1 and cache.get("c") == 3


# -- warnings: references that still resolve, but doubtfully (milestone 2 phase E) --------------------------------

GROOVED = """groove_1_width = {w}
with BuildPart() as part:
    Box(40, 30, 20)  # feature: box_1
    with Locations((0, 0, 10)):  # feature: groove_1
        Box(groove_1_width, 40, 10, mode=Mode.SUBTRACT)
    {op}  # feature: fillet_1
result = part.part
"""


def test_a_split_face_warns_on_the_feature_line():
    r = runner.run_script(GROOVED.format(w=10, op='fillet(edges_of(face("box_1", "+Z")), radius=1)'))
    assert r.ok
    assert r.warnings == [(6, 'face box_1 +Z now names 2 faces (it was split by a change before it): the feature '
                              'uses all of them')]


def test_a_near_pick_that_no_longer_tells_faces_apart_warns():
    # picked at x = -12 when the groove was 20 mm wide off-centre; the groove is now centred and 38 mm wide
    op = 'fillet(edges_of(face("box_1", "+Z", near=(-0.5, 0, 10))), radius=0.5)'
    r = runner.run_script(GROOVED.format(w=10, op=op))
    assert r.ok and len(r.warnings) == 1 and "about as close to another one" in r.warnings[0][1]
    assert r.warnings[0][0] == 6
    op = 'fillet(edges_of(face("box_1", "+Z", near=(-12, 0, 10))), radius=0.5)'
    assert runner.run_script(GROOVED.format(w=10, op=op)).warnings == []  # clearly the left half


def test_no_warnings_on_a_plain_part():
    r = runner.run_script(GROOVED.format(w=10, op='fillet(edges_of(face("box_1", "-Z")), radius=1)'))
    assert r.ok and r.warnings == []
