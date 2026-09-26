#!/usr/bin/env bash
# Unit tests (Blender's Python, no bpy) then Blender tests (headless Blender).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BL="${BL:-$HOME/blender/blender-5.2.2-linux-x64/blender}"
PY="$(dirname "$BL")/5.2/python/bin/python3.13"
PYTHONPATH="$ROOT:$ROOT/.dev/pytest" "$PY" -m pytest "$ROOT/tests/unit" -q -p no:cacheprovider "$@"
"$BL" -b --factory-startup --python-exit-code 1 --python "$ROOT/tests/blender/run.py" -- "$@"
