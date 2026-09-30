"""The interactive Add's sizes (ADR 0015): proportions and round numbers."""
import pytest

from blendsolid import primitives


@pytest.mark.parametrize("kind", sorted(primitives.PRIMITIVES))
def test_proportions_cover_every_parameter_and_make_the_size_the_largest_extent(kind):
    prim = primitives.PRIMITIVES[kind]
    assert set(primitives.PROPORTIONS[kind]) == {s for s, _, _ in prim.params}
    values = primitives.sized_values(kind, 1000.0)
    assert max(prim.extents(values)) == pytest.approx(1000.0)


def test_box_is_a_cube():
    assert primitives.sized_values("box", 1000.0) == {"length": 1000.0, "width": 1000.0, "height": 1000.0}


def test_nice_sizes():
    assert primitives.nice_size(870.0) == 1000.0
    assert primitives.nice_size(130.0) == 100.0
    assert primitives.nice_size(0.034) == 0.05
    assert primitives.nice_size(3400.0) == 5000.0
    assert primitives.nice_size(330.0, primitives.DRAG_STEPS) == 300.0
    assert primitives.nice_size(7300.0, primitives.DRAG_STEPS) == 8000.0
