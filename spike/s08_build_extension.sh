#!/usr/bin/env bash
# Objective 8: package the spike extension with --split-platforms.
# Stage: spike/extension (manifest + __init__) + spike modules + wheels from ./wheels → dist/stage
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BL="${BL:-$HOME/blender/blender-5.2.2-linux-x64/blender}"
STAGE="$ROOT/dist/stage/blendsolid"
rm -rf "$ROOT/dist" && mkdir -p "$STAGE/wheels"
cp "$ROOT/spike/extension/"{blender_manifest.toml,__init__.py} "$STAGE/"
cp "$ROOT/spike/"{occ_model.py,bl_bridge.py} "$STAGE/"
cp "$ROOT"/wheels/*.whl "$STAGE/wheels/"
"$BL" --command extension validate "$STAGE"
"$BL" --command extension build --split-platforms --source-dir "$STAGE" --output-dir "$ROOT/dist"
ls -l "$ROOT/dist"/*.zip
