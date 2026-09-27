import math

import numpy as np
import pytest

import runner  # worker module, imported as the worker does
from blendsolid import primitives as pr, script_model as sm

VOLUMES = {
    "box": lambda v: v["length"] * v["width"] * v["height"],
    "cylinder": lambda v: math.pi * v["radius"] ** 2 * v["height"],
    "sphere": lambda v: 4 / 3 * math.pi * v["radius"] ** 3,
    "cone": lambda v: math.pi * v["height"] / 3 * (v["bottom_radius"] ** 2 + v["bottom_radius"] * v["top_radius"]
                                                   + v["top_radius"] ** 2),
    "torus": lambda v: 2 * math.pi ** 2 * v["major_radius"] * v["minor_radius"] ** 2,
    "wedge": lambda v: (v["length"] + v["top_length"]) / 2 * v["height"] * v["width"],
}


def defaults(kind):
    return {suffix: default for suffix, _, default in pr.PRIMITIVES[kind].params}


def bbox(result):
    return result.verts.min(axis=0), result.verts.max(axis=0)


@pytest.mark.parametrize("kind", sorted(pr.PRIMITIVES))
def test_each_primitive_sits_on_its_plane_with_the_right_volume(kind):
    v = defaults(kind)
    source, name = sm.new_script(pr.feature_spec(kind, v))
    assert name == f"{kind}_1" and sm.is_canonical(source)
    (f,) = sm.features(source)
    assert f.kind == kind
    r = runner.run_script(source)
    assert r.ok, r.error
    assert abs(r.volume - VOLUMES[kind](v)) / VOLUMES[kind](v) < 1e-6
    lo, hi = bbox(r)
    ext = pr.PRIMITIVES[kind].extents(v)
    np.testing.assert_allclose(lo, [-ext[0] / 2, -ext[1] / 2, 0.0], atol=0.05)  # BASE: centred, on z = 0
    np.testing.assert_allclose(hi, [ext[0] / 2, ext[1] / 2, ext[2]], atol=0.05)


def test_cut_hangs_from_its_placement_and_subtracts():
    source, _ = sm.new_script(pr.feature_spec("box", {"length": 40, "width": 30, "height": 20}))
    cut = pr.feature_spec("cylinder", {"radius": 3, "height": 5}, mode="SUBTRACT", align=pr.TOP,
                          location=(10.0, 5.0, 20.0))
    assert cut.prefix == "cut"
    source, name = sm.append_feature(source, cut)
    assert name == "cut_1" and sm.features(source)[1].mode == "SUBTRACT"
    r = runner.run_script(source)
    assert r.ok, r.error
    assert abs(r.volume - (40 * 30 * 20 - math.pi * 9 * 5)) < 1e-6


def test_placement_rotation_follows_build123d_intrinsic_xyz():
    # a 10 x 2 x 2 bar rotated 90 degrees about Y lies along Z: union into a flat plate as a post
    source, _ = sm.new_script(pr.feature_spec("box", {"length": 40, "width": 40, "height": 2}))
    post = pr.feature_spec("box", {"length": 10, "width": 2, "height": 2}, location=(0.0, 0.0, 2.0),
                           rotation=(0.0, 90.0, 0.0), align=("MAX", "CENTER", "CENTER"))
    source, _ = sm.append_feature(source, post)
    r = runner.run_script(source)
    assert r.ok, r.error
    lo, hi = bbox(r)
    assert abs(hi[2] - 12.0) < 0.05  # the bar's -X end (align MAX) went up along +Z


def test_insert_spec():
    spec = pr.insert_spec("abc", "SUBTRACT")
    assert (spec.prefix, spec.params, spec.call) == ("bool", (), 'insert(ref("abc"), mode=Mode.SUBTRACT)')
    assert pr.insert_spec("abc", "ADD").prefix == "union" and pr.insert_spec("abc", "INTERSECT").prefix == "common"


def test_wedge_align_round_trip():
    for align in (pr.BASE, pr.TOP, ("MIN", "MAX", "CENTER")):
        assert pr.wedge_align_inverse(pr.wedge_align(align)) == align


def _arrows(kind, values=None, **spec_kwargs):
    v = values or defaults(kind)
    source, _ = sm.new_script(pr.feature_spec(kind, v, **spec_kwargs))
    (f,) = sm.features(source)
    full = {f"{f.name}_{k}": x for k, x in v.items()}
    return {a.param: a for a in pr.arrows(f, full)}


def test_box_arrows_end_on_the_faces():
    arrows = _arrows("box", {"length": 40, "width": 30, "height": 20})
    for name, face in (("box_1_length", (20, 0, 10)), ("box_1_width", (0, 15, 10)), ("box_1_height", (0, 0, 20))):
        a = arrows[name]
        value = {"box_1_length": 40, "box_1_width": 30, "box_1_height": 20}[name]
        tip = np.add(a.origin, np.multiply(a.direction, value * a.scale))
        np.testing.assert_allclose(tip, face)


def test_cut_height_arrow_points_down_from_the_face():
    arrows = _arrows("cylinder", {"radius": 3, "height": 5}, mode="SUBTRACT", align=pr.TOP)
    a = arrows["cut_1_height"]
    assert a.origin == (0.0, 0.0, 0.0) and a.direction == (0.0, 0.0, -1.0) and a.scale == 1.0
    r = arrows["cut_1_radius"]
    assert r.direction == (1.0, 0.0, 0.0) and r.scale == 1.0 and r.origin == (0.0, 0.0, -2.5)


def test_torus_minor_radius_arrow_sits_on_the_tube():
    a = _arrows("torus", {"major_radius": 20, "minor_radius": 5})["torus_1_minor_radius"]
    assert a.origin == (20.0, 0.0, 0.0) and a.direction == (0.0, 0.0, 1.0) and a.scale == 2.0


def test_cone_radius_arrows_on_their_levels():
    arrows = _arrows("cone", {"bottom_radius": 10, "top_radius": 5, "height": 20})
    assert arrows["cone_1_bottom_radius"].origin[2] == 0.0 and arrows["cone_1_top_radius"].origin[2] == 20.0


def test_wedge_arrows_use_part_axes():
    a = _arrows("wedge")["wedge_1_height"]
    assert a.direction == (0.0, 0.0, 1.0) and a.origin[2] == 0.0


def test_wedge_top_length_arrow_runs_along_the_top_edge():
    for align, lo_x in ((pr.BASE, -20.0), (("MIN", "CENTER", "MIN"), 0.0), (("MAX", "CENTER", "MIN"), -40.0)):
        a = _arrows("wedge", {"length": 40, "width": 30, "height": 20, "top_length": 10}, align=align)["wedge_1_top_length"]
        assert a.origin == (lo_x, 0.0, 20.0) and a.direction == (1.0, 0.0, 0.0) and a.scale == 1.0, align
    # A top longer than the base widens the bounding box the align centres.
    a = _arrows("wedge", {"length": 40, "width": 30, "height": 20, "top_length": 60})["wedge_1_top_length"]
    assert a.origin == (-30.0, 0.0, 20.0)


def test_no_arrows_for_unknown_or_non_literal_features():
    source = ("size = 10.0\n\nwith BuildPart() as part:\n    Box(size, size, size)  # feature: base\n"
              "    fillet(part.edges(), radius=1)  # feature: round\n\nresult = part.part\n")
    base, rnd = sm.features(source)
    assert pr.arrows(base, {"size": 10.0}) == []   # no align literal, and no base_* parameters
    assert pr.arrows(rnd, {}) == []
