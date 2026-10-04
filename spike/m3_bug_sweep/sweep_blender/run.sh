#!/bin/bash
# run.sh scenario.py -> log next to it
D=/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender
BL=~/blender/blender-5.2.2-linux-x64/blender
s=$1
timeout 600 $BL -b --factory-startup --python-use-system-env --python "$D/$s" > "$D/${s%.py}.log" 2>&1
grep -v "^Read prefs\|^Blender quit\|^$" "$D/${s%.py}.log" | tail -n ${2:-80}
