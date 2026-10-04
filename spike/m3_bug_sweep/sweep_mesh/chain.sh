#!/bin/bash
PY=~/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13
for k in "$@"; do $PY drive.py c_$k.json r_$k.jsonl; done
