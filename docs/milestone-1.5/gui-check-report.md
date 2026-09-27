# GUI check report — milestone 1.5 (automated stand-in for Task 14 Step 1)

Date: 2026-09-26. Branch `milestone-1.5`. Script: `tools/gui_check.py` (commit ecc5d31).

## Result

- **Linux (WSLg, software OpenGL, repository add-on): GUI CHECK PASS** — `spike/logs/gui-check-linux.log`
- **Windows portable Blender, installed extension (rebuilt 0.2.0 with the fix below, real GPU): GUI CHECK PASS** — `spike/logs/gui-check-windows.log`
- Windows with the *originally installed* 0.2.0 zip (before the fix): GUI CHECK FAIL at step 15 (the bug below; step 4 also failed there, a check-script issue since fixed: the wait didn't tag viewport redraws) — `spike/logs/gui-check-windows-installed-0.2.0.log`
- Linux without `--enable-event-simulate` (fallback: execute paths): PASS with steps 9, 10 SKIP and step 4 without the drag — `spike/logs/gui-check-linux-nosim.log`
- No worker process left after quitting on either platform; the portable `userpref.blend` was not written by the GUI runs (only by the extension reinstall).

## How it works

A persistent `bpy.app.timers` generator walks the scenario after the window is up. Operators run with a window/area/region `temp_override` and the undo flag (`"EXEC_DEFAULT", True`), so every action is a real undo step; selections made from Python get an explicit undo push, as a click would. Adjust Last Operation is exercised with `ed.undo_redo` after changing `wm.operators[-1]` (the same undo + re-execute the panel triggers). With `--enable-event-simulate`, `Window.event_simulate` feeds real mouse/keyboard events: the Draw Solid tool's own keymap invokes the modal, which ray casts from the real region; screen positions come from `location_3d_to_region_2d` on a scripted view. Instrumentation wraps (and calls) the gizmo group's `draw_prepare`, the panel's `draw`, the draw operator's `invoke/_header/_finish` and `ops_draw._draw_preview` to record what was drawn/set; nothing the add-on does is replaced. Finding: the first simulated press after a pause only focuses the window, so a throwaway press/Esc precedes each drawing.

## Per step

### 1. Covered

Box added with the Shift+A operator at the cursor, named Box, selected; redo panel content ("Dimensions (millimetres)", Length/Width/Height) checked through the operator's draw(); Length 60 applied through `ed.undo_redo` (what the Adjust Last Operation panel does) -> one part, 36000 mm³. Manual: the panel widget itself, first-start latency feel.

```
Linux:   STEP 1 OK Box 40x30x20 -> 24000 mm³ (first result 1.9 s), redo Length 60 -> 36000.0 mm³
Windows: STEP 1 OK Box 40x30x20 -> 24000 mm³ (first result 1.7 s), redo Length 60 -> 36000.0 mm³
```

### 2. Covered

Cursor rotated X 30°, cylinder matrix = cursor matrix, mesh z range 0..20 mm in the cursor frame, volume; cursor reset.

```
Linux:   STEP 2 OK cylinder on the 30° cursor plane: z 0.000..20.000 mm, 6259.8 mm³
Windows: STEP 2 OK cylinder on the 30° cursor plane: z 0.000..20.000 mm, 6259.8 mm³
```

### 3. Covered

Sphere/cone/torus/wedge added and moved aside with `transform.translate` (G), volumes (curved ones within 2 % of the exact value: tessellation); Shift+A menu and sidebar content (6 buttons, 'Cone 1 top radius') and the real sidebar panel drawn by a UI region (a check-only copy of the panel in the Item tab, since a script can't switch sidebar tabs). Manual: the look of the menu/panel.

```
Linux:   STEP 3 OK sphere 4127, cone 3631, torus 9807, wedge 15000 mm³; sidebar: 6 buttons, 'Cone 1 top radius'; real panel drawn: True
Windows: STEP 3 OK sphere 4127, cone 3631, torus 9807, wedge 15000 mm³; sidebar: 6 buttons, 'Cone 1 top radius'; real panel drawn: True
```

### 4. Covered (feel: manual)

draw_prepare in the real viewport builds 3 arrows whose matrices equal `arrow_matrices`, starting on the +X/+Y/top faces (not at the origin, so the Move gizmo stays free); the height arrow is found by hovering (gizmo `is_highlight`), dragged with simulated mouse events: the height grows monotonically during the drag (recomputes while dragging), ends at the released value, volume = 60·30·h, one `ed.undo` restores 20 mm. Manual: drag feel/latency, arrow colours, visual overlap with the Move gizmo.

```
Linux:   STEP 4 OK 3 arrows on the +X, +Y, top faces; drag -> height 36.441 mm (65593 mm³, heights while dragging [22.12, 24.22, 26.3, 28.36, 30.41, 32.43, 34.45, 36.44]); one undo -> 20 mm
Windows: STEP 4 OK 3 arrows on the +X, +Y, top faces; drag -> height 36.382 mm (65488 mm³, heights while dragging [22.11, 24.2, 26.27, 28.33, 30.37, 32.39, 34.39, 36.38]); one undo -> 20 mm
```

### 5. Covered

`transform.resize` 2 (S 2), panel warning 'This part is scaled', gizmo poll False and no draw_prepare over several redraws, undo -> scale 1 and arrows back.

```
Linux:   STEP 5 OK panel 'This part is scaled', gizmo poll False, no arrows drawn; undo -> scale 1, arrows back
Windows: STEP 5 OK panel 'This part is scaled', gizmo poll False, no arrows drawn; undo -> scale 1, arrows back
```

### 6. Covered

Tool activated with `wm.tool_set_by_id` (and its header Shape option set through the tool's operator properties); the real modal driven by simulated events on empty grid (drag base, release, move for height, click) -> new part, mode NEW, sizes ≈ 20×10×8 as aimed, volume = L·W·H of the operator; redo Height 15 via `ed.undo_redo`. The preview callback also drew with a synthetic drawn state in the real viewport (no exception). Manual: the outline colour/following the mouse, the header on screen.

```
Linux:   STEP 6 OK drawn with simulated mouse events; New Part Box.001 20.16 x 9.87 mm, redo Height 15 -> 2984.5 mm³; synthetic preview drew 13 frame(s)
Windows: STEP 6 OK drawn with simulated mouse events; New Part Box.001 19.96 x 10.05 mm, redo Height 15 -> 3010.8 mm³; synthetic preview drew 13 frame(s)
```

### 7. Covered (visual: manual)

Drag on Box's top face, height up: header text set 'union with Box', preview drawn in mode UNION (green), one more feature on Box, no new object, volume +L·W·H.

```
Linux:   STEP 7 OK simulated mouse; header 'union with Box', green preview mode; Box +989.6 mm³ -> 36989.6
Windows: STEP 7 OK simulated mouse; header 'union with Box', green preview mode; Box +1009.3 mm³ -> 37009.3
```

### 8. Covered (visual: manual)

Header Cylinder, circle on the top face, height down: header 'cut from Box', preview mode CUT (red), SUBTRACT feature, volume −πr²h; redo Mode Union -> boss (+πr²h), redo Radius 3 -> updated.

```
Linux:   STEP 8 OK simulated mouse; header 'cut from Box', red preview mode; hole r 4.10 h 5.98; redo Union -> boss; redo Radius 3 -> 37158.0 mm³
Windows: STEP 8 OK simulated mouse; header 'cut from Box', red preview mode; hole r 3.85 h 5.96; redo Union -> boss; redo Radius 3 -> 37177.1 mm³
```

### 9. Covered (feel: manual)

Ctrl held on every event: length/width/height whole mm and the header shows them; Shift+Ctrl: tenths.

```
Linux:   STEP 9 OK Ctrl 19 x 9 x 7; Shift+Ctrl 19.2 x 9.3 x 7.4 mm
Windows: STEP 9 OK Ctrl 19 x 10 x 7; Shift+Ctrl 19.1 x 9.5 x 7.5 mm
```

### 10. Covered

Esc during the base drag and right-click during the height: `_finish` ran, header cleared (header_text_set(None)), no part changed.

```
Linux:   STEP 10 OK Esc during the base and right-click during the height: nothing added, header cleared
Windows: STEP 10 OK Esc during the base and right-click during the height: nothing added, header cleared
```

### 11. Covered

Cylinder added through the box, click cylinder then box (box active), Ctrl+Numpad − as a simulated key -> bool_1 SUBTRACT, cutter WIRE + hide_render, hole π·25·20; G −10 mm -> half hole; R 90° + G -> hole across the box (π·25·30); cutter radius 3 through the parameter mirror (the sidebar field's path) -> π·9·30.

```
Linux:   STEP 11 OK Ctrl+Numpad - (simulated key): hole 845.1 mm³ (1570.8 through, then half out, across after R/G), radius 3 in the panel -> 36313.0 mm³; cutter wire, not rendered
Windows: STEP 11 OK Ctrl+Numpad - (simulated key): hole 845.1 mm³ (1570.8 through, then half out, across after R/G), radius 3 in the panel -> 36332.1 mm³; cutter wire, not rendered
```

### 12. Covered

Ctrl+Numpad + (union: 12000 + π·9·10) and Ctrl+Numpad * (intersect: π·9·10) as simulated keys; the BlendSolid Boolean submenu is in the Object menu and lists Difference/Union/Intersect. Note: Blender's default keymap also binds Ctrl+Numpad +/− in Object Mode to object.select_more/select_less; the add-on's items win (the simulated keys ran the boolean). Other add-ons (Bool Tool): manual.

```
Linux:   STEP 12 OK union 12281.7, intersect 281.7 mm³ (Ctrl+Numpad keys); Object menu entry present; other Ctrl+Numpad bindings: ['Object Mode: object.select_more', 'Object Mode: object.select_less']
Windows: STEP 12 OK union 12281.7, intersect 281.7 mm³ (Ctrl+Numpad keys); Object menu entry present; other Ctrl+Numpad bindings: ['Object Mode: object.select_more', 'Object Mode: object.select_less']
```

### 13. Covered

Viewed along a line that crosses the protruding wire cutter before Box's −Y face (beside the hole the cutter made): `scene.ray_cast` hits the cutter first; a simulated press with the Draw Solid tool picks Box and its −Y face plane at the aimed point, then Esc.

```
Linux:   STEP 13 OK simulated press: first ray hit is the wire cutter, the tool picked Box's -Y face (y = -15.000 mm)
Windows: STEP 13 OK simulated press: first ray hit is the wire cutter, the tool picked Box's -Y face (y = -15.000 mm)
```

### 14. Covered

`object.delete` on the cutter -> Box error 'This part uses a cutter part that no longer exists (deleted?)…', the panel shows 'The part could not be rebuilt'; `ed.undo` -> cutter back, error cleared on the next tick, hole volume back.

```
Linux:   STEP 14 OK error: "This part uses a cutter part that no longer exists (deleted?): undo the deletion (Ctrl+Z) or delete this part"; undo -> cutter back, no error, 36313.0 mm³
Windows: STEP 14 OK error: "This part uses a cutter part that no longer exists (deleted?): undo the deletion (Ctrl+Z) or delete this part"; undo -> cutter back, no error, 36332.1 mm³
```

### 15. Covered

`ed.undo` 36 times to the empty scene, then `ed.redo` 36 times; after every step all parts are up to date (or show their error) and their panel mirror equals their script; final scripts and volumes equal those before. This step found the bug below. Manual: nothing essential (keyboard Ctrl+Z vs ed.undo is the same operator).

```
Linux:   STEP 15 OK 36 undos to the empty scene and 36 redos back; every step matched its scripts
Windows: STEP 15 OK 36 undos to the empty scene and 36 redos back; every step matched its scripts
```

### 16. Covered (quitting by hand: manual)

Saved to a temp .blend, Auto Run turned off (in-session, restored and never saved), `wm.open_mainfile`: file untrusted, cached meshes identical (tags and volumes), panel says 'Scripts in this file are not trusted' with the Trust button, Recompute poll False; the cutter moved +20 mm: Box keeps its saved mesh for 2 s, nothing in flight; Trust Scripts in This File -> Box recomputes, hole gone (+π·9·30), Recompute enabled. After Blender quit, the worker process id printed by the run no longer exists (both platforms). Manual: restarting Blender with the preference off and reading the Recompute tooltip.

```
Linux:   STEP 16 OK reopened untrusted: cached meshes, Recompute off, no recompute on move; trusted -> 37158.0 mm³
Windows: STEP 16 OK reopened untrusted: cached meshes, Recompute off, no recompute on move; trusted -> 37177.1 mm³
```

## Needs the manual test (a person)

- Step 4: how a gizmo drag feels (latency, following the mouse), arrow colours, the arrows vs the Move gizmo visually.
- Steps 6–9: the preview outline's colour and look while drawing, the header text as displayed, Ctrl snapping feel.
- Steps 1, 6, 8: the Adjust Last Operation panel as a widget (F9, typing values) — its effect is covered via `ed.undo_redo`.
- Step 3/12: opening Shift+A and the Object menu by hand (their content is checked), key conflicts with other installed add-ons (e.g. Bool Tool).
- Step 11: wireframe look of the cutter (display_type/hide_render are checked).
- Step 16: quitting and restarting Blender with the preference off, the Recompute tooltip text, Task Manager (the worker pid check covers the process).
- Real hardware input: all mouse/keyboard input was simulated (`--enable-event-simulate`); a real mouse was never used.

## Bugs found and fixed

1. **Stale parameter panel after undo** (commit db1171e, `blendsolid/runtime.py`, test `tests/blender/test_reconcile.py::test_undo_to_a_step_pushed_before_the_mirror_synced_resyncs_it`). An operator pushes its undo step as soon as it has written the script, before the reconcile tick mirrors the new parameters into `blendsolid_params`; that step therefore stores a stale mirror. Undoing back to it restores the stale mirror together with a script whose tag `runtime._synced` already remembers, so the tick never re-mirrored it: after Ctrl+Z the sidebar showed only `box_1_*` while the script had `box_2_*` and `cylinder_1_*` (seen at undo 19 on both platforms). Fix: `undo_post`/`redo_post` handlers clear `_synced` (nothing else decided there), so the next tick mirrors every part again. The headless test failed before the fix; `tools/test.sh`: 105 unit + 133 Blender tests pass.
   - The Windows zip was rebuilt (still 0.2.0) with the fix and reinstalled in the portable Blender (`extension install-file`); `tools/smoke_installed.py`: SMOKE PASS.

No other add-on bug was found. Observations (not bugs): after undoing the cutter deletion the error clears on the next tick (≈50 ms), not in the undo itself; Blender's default Object Mode keymap also has Ctrl+Numpad +/− (select more/less), shadowed by the add-on's items.

## Screenshots

Linux (offscreen viewport renders: the WSLg software-GL screen reads back black): `/tmp/claude-1000/-home-tony-Projects-BlendSolid/692bc3f7-6034-41ef-af96-1255922a60a3/scratchpad/out/01-box.png` … `15-trusted.png`.
Windows (real screen captures, whole window): `/tmp/claude-1000/-home-tony-Projects-BlendSolid/692bc3f7-6034-41ef-af96-1255922a60a3/scratchpad/out-win/01-box.png` … `15-trusted.png`.
Names: 01-box, 02-primitives, 03-gizmo-drag, 04-scaled, 05-preview-synthetic, 06-draw-grid, 07-draw-union, 08-draw-cut, 09-live-cutter, 10-cutter-moved, 11-booleans, 12-through-cutter, 13-deleted-cutter, 14-reopened-untrusted, 15-trusted. (Scratch directory: not in the repository; they go away with the session.)

## Commands

```bash
# Linux, repository add-on
WAYLAND_DISPLAY= LIBGL_ALWAYS_SOFTWARE=1 PYTHONPATH=$PWD ~/blender/blender-5.2.2-linux-x64/blender --factory-startup \
  --gpu-backend opengl --python-use-system-env --addons blendsolid --enable-event-simulate \
  --python tools/gui_check.py -- --out <scratch dir> > spike/logs/gui-check-linux.log 2>&1
# Windows portable, installed extension (no --factory-startup)
/mnt/e/blender-5.2.2-windows-x64/blender.exe --enable-event-simulate --python "$(wslpath -w tools/gui_check.py)" \
  -- --out "$(wslpath -w <scratch dir>)" > spike/logs/gui-check-windows.log 2>&1
# rebuild + reinstall the Windows zip after the fix
"$PY" tools/build_extension.py --platform windows-x64 --blender "$BL"
/mnt/e/blender-5.2.2-windows-x64/blender.exe --command extension install-file -r user_default -e "$(wslpath -w dist/blendsolid-0.2.0-windows-x64.zip)"
/mnt/e/blender-5.2.2-windows-x64/blender.exe -b --python "$(wslpath -w tools/smoke_installed.py)"
# worker left? (pid printed as 'WORKER PID <n>')
ps -p <pid>   # Linux;   powershell.exe -Command "Get-Process -Id <pid>"   # Windows
```

The logs under `spike/logs/gui-check-*.log` are not committed.
