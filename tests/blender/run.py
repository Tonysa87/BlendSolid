"""Runs the Blender test suite inside `blender -b` (see tools/test.sh)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, ".dev", "pytest")]  # test harness only, not the add-on

import pytest  # noqa: E402

extra = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
code = pytest.main([os.path.join(ROOT, "tests", "blender"), "-q", "-p", "no:cacheprovider", *extra])
if code:
    raise SystemExit(int(code))
