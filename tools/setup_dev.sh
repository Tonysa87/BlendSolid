#!/usr/bin/env bash
# Creates .dev/worker_libs (build123d + all dependencies, for the worker) and .dev/pytest,
# using the Python bundled with the Blender in $BL.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BL="${BL:-$HOME/blender/blender-5.2.2-linux-x64/blender}"
PY="$(dirname "$BL")/5.2/python/bin/python3.13"
"$PY" -m pip install --upgrade --target "$ROOT/.dev/worker_libs" -r "$ROOT/tools/worker-requirements.txt"
"$PY" -m pip install --upgrade --target "$ROOT/.dev/pytest" pytest
echo "dev environment ready in $ROOT/.dev"
