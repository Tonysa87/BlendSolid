import pytest

from blendsolid import params

SCRIPT = '''"""A bracket."""
from math import pi

length = 40.0
count = 4
offset = -2.5
width = 30.0  # mm

with BuildPart() as p:
    Box(length, width, 10)
depth = 3.0
result = p.part
'''


def test_parse_leading_numeric_assignments():
    ps = params.parse_params(SCRIPT)
    assert [(p.name, p.value, p.is_int) for p in ps] == [
        ("length", 40.0, False), ("count", 4.0, True), ("offset", -2.5, False), ("width", 30.0, False)]


def test_assignments_after_code_are_not_parameters():
    assert "depth" not in [p.name for p in params.parse_params(SCRIPT)]


def test_set_float_param_keeps_the_rest_of_the_line():
    out = params.set_param(SCRIPT, "width", 12.0)
    assert "width = 12.0  # mm\n" in out
    assert out.replace("width = 12.0", "width = 30.0") == SCRIPT


def test_set_param_rounds_float32_noise():
    out = params.set_param(SCRIPT, "length", 12.300000190734863)  # a Blender FloatProperty value
    assert "length = 12.3\n" in out


def test_set_int_param_stays_int():
    assert "count = 6\n" in params.set_param(SCRIPT, "count", 5.7)


def test_set_negative_param():
    assert "offset = -3.0\n" in params.set_param(SCRIPT, "offset", -3)


def test_unknown_param():
    with pytest.raises(params.ParamError):
        params.set_param(SCRIPT, "height", 1.0)


def test_duplicate_param():
    with pytest.raises(params.ParamError):
        params.parse_params("a = 1.0\na = 2.0\n")


def test_non_ascii_before_the_value():
    src = "città = 1.5  # Unicode names are valid Python\nresult = None\n"
    assert "città = 2.5  #" in params.set_param(src, "città", 2.5)


def test_invalid_python_raises_syntax_error():
    with pytest.raises(SyntaxError):
        params.parse_params("length = \n")
