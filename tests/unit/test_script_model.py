import re

import pytest

from blendsolid import params, script_model as sm

BOX = sm.FeatureSpec("box", (("length", 40.0), ("width", 30.0), ("height", 20.0)),
                     "Box({name}_length, {name}_width, {name}_height, align=(Align.CENTER, Align.CENTER, Align.MIN))")
CUT = sm.FeatureSpec("cut", (("radius", 3.0), ("height", 5.0)),
                     "Cylinder({name}_radius, {name}_height, align=(Align.CENTER, Align.CENTER, Align.MAX), "
                     "mode=Mode.SUBTRACT)",
                     location=(12.0, -8.5, 20.0), rotation=(0.0, 90.0, 0.0))
BOOL = sm.FeatureSpec("bool", (), 'insert(ref("0123abcd"), mode=Mode.SUBTRACT)')


def test_new_script_layout():
    source, name = sm.new_script(BOX)
    assert name == "box_1"
    assert source == (
        "# BlendSolid part. The numbers below are its parameters (millimetres).\n"
        "box_1_length = 40.0\n"
        "box_1_width = 30.0\n"
        "box_1_height = 20.0\n"
        "\n"
        "with BuildPart() as part:\n"
        "    Box(box_1_length, box_1_width, box_1_height, align=(Align.CENTER, Align.CENTER, Align.MIN))"
        "  # feature: box_1\n"
        "\n"
        "result = part.part\n")
    assert sm.is_canonical(source)


def test_features_of_new_script():
    source, _ = sm.new_script(BOX)
    (f,) = sm.features(source)
    assert (f.name, f.kind, f.mode, f.align) == ("box_1", "box", "ADD", ("CENTER", "CENTER", "MIN"))
    assert f.location == (0.0, 0.0, 0.0) and f.rotation == (0.0, 0.0, 0.0) and f.refs == ()
    assert f.lineno == f.end_lineno == 7


def test_append_placed_feature():
    source, _ = sm.new_script(BOX)
    source, name = sm.append_feature(source, CUT)
    assert name == "cut_1"
    assert [p.name for p in params.parse_params(source)] == [
        "box_1_length", "box_1_width", "box_1_height", "cut_1_radius", "cut_1_height"]
    assert ("    with Locations(Location((12.0, -8.5, 20.0), (0.0, 90.0, 0.0))):  # feature: cut_1\n"
            "        Cylinder(cut_1_radius, cut_1_height, align=(Align.CENTER, Align.CENTER, Align.MAX), "
            "mode=Mode.SUBTRACT)\n\nresult = part.part\n") in source
    f = sm.features(source)[1]
    assert (f.name, f.kind, f.mode, f.align) == ("cut_1", "cylinder", "SUBTRACT", ("CENTER", "CENTER", "MAX"))
    assert f.location == (12.0, -8.5, 20.0) and f.rotation == (0.0, 90.0, 0.0)
    assert (f.lineno, f.end_lineno) == (10, 11)


def test_append_feature_without_params_and_names_are_unique():
    source, _ = sm.new_script(BOX)
    source, first = sm.append_feature(source, BOOL)
    source, second = sm.append_feature(source, BOOL)
    assert (first, second) == ("bool_1", "bool_2")
    assert [f.name for f in sm.features(source)] == ["box_1", "bool_1", "bool_2"]
    assert sm.features(source)[1].kind == "insert" and sm.features(source)[1].refs == ("0123abcd",)
    assert sm.references(source) == ["0123abcd"]


def test_next_name_continues_after_the_highest():
    assert sm.next_name(["box_1", "box_3", "cut_1", "box_3_length"], "box") == "box_4"
    assert sm.next_name([], "cut") == "cut_1"


def test_parameter_values_are_rounded_and_never_negative_zero():
    spec = sm.FeatureSpec("box", (("length", 12.300000190734863),), "Box({name}_length, 1, 1)",
                          location=(-0.0, 1e-9, -2.0))
    source, _ = sm.new_script(spec)
    assert "box_1_length = 12.3\n" in source
    assert "Location((0.0, 0.0, -2.0), (0.0, 0.0, 0.0))" in source


def test_numbers_can_still_be_edited_by_params():
    source, _ = sm.new_script(BOX)
    source = params.set_param(source, "box_1_width", 31.5)
    assert "box_1_width = 31.5\n" in source and sm.is_canonical(source)


@pytest.mark.parametrize("source, reason", [
    ("length = 1.0\nresult = Box(length, 1, 1)\n", "feature layout"),
    ("with BuildPart() as part:\n    Box(1, 1, 1)\nresult = part.part\n", "no `# feature: <name>` marker"),
    ("with BuildPart() as part:\n    Box(1, 1, 1)  # feature: a\n    Box(2, 2, 2)  # feature: a\n"
     "result = part.part\n", "two features are named 'a'"),
    ("with BuildPart() as p:\n    Box(1, 1, 1)  # feature: a\nresult = p.part\n", "feature layout"),
    ("with BuildPart() as part:\n    Box(1, 1, 1)  # feature: a\nresult = part.part\nx = 1\n", "feature layout"),
    ("with BuildPart() as part:\n    Box(1, 1,\n", "syntax error"),
])
def test_not_canonical_explains_why(source, reason):
    with pytest.raises(sm.NotCanonical, match=re.escape(reason)):
        sm.features(source)
    assert not sm.is_canonical(source)
    with pytest.raises(sm.NotCanonical):
        sm.append_feature(source, BOOL)


def test_append_refuses_an_existing_parameter_name():
    source, _ = sm.new_script(BOX)
    source = source.replace("box_1_height = 20.0\n", "box_1_height = 20.0\ncut_1_radius = 1.0\n")
    with pytest.raises(sm.NotCanonical, match="cut_1_radius"):
        sm.append_feature(source, CUT)


def test_docstring_imports_and_other_features_are_allowed():
    source = ('"""My part."""\nimport math\n\nsize = 10.0\n\nwith BuildPart() as part:\n'
              '    Box(size, size, size)  # feature: base\n'
              '    with Locations((size / 2, 0, 0)):  # feature: boss\n'
              '        Cylinder(2, 4)\n'
              '    fillet(part.edges(), radius=1)  # feature: round\n\nresult = part.part\n')
    fs = sm.features(source)
    assert [(f.name, f.kind) for f in fs] == [("base", "box"), ("boss", "cylinder"), ("round", "other")]
    assert fs[1].location is None and fs[1].rotation is None  # placed, but not with literal numbers
    source, name = sm.append_feature(source, CUT)
    assert name == "cut_1" and "size = 10.0\ncut_1_radius = 3.0\ncut_1_height = 5.0\n" in source


def test_append_to_a_script_without_parameters():
    source = "with BuildPart() as part:\n    Box(1, 1, 1)  # feature: a\n\nresult = part.part\n"
    source, _ = sm.append_feature(source, CUT)
    assert source.startswith("cut_1_radius = 3.0\ncut_1_height = 5.0\n\nwith BuildPart() as part:\n")
    assert sm.is_canonical(source)


def test_references_tolerates_broken_scripts():
    assert sm.references("insert(ref('a')\n") == []
    assert sm.references("x = ref('a')\ny = ref('b')\nz = ref('a')\nw = ref(name)\n") == ["a", "b"]
