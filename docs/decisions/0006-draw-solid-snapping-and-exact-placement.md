# ADR 0006 — Draw Solid: snapping, and exact placements on faces

- **Status:** accepted (2026-09-27, maintainer's requests and bugs found in the milestone 1.5 manual GUI test);
  amended the same day (placement decimals, snap guides)
- **Date:** 2026-09-27
- **Context from:** manual GUI test, steps 6–8; research on BoxCutter, HardOps, Plasticity, Blender's Add Cube

## Context

Draw Solid snapped only to 1 mm (0.1 mm with Shift) and only dimensions and the base centre. Solids drawn on a
part's face were placed from the float32 mesh hit point and `matrix_world`, converted with `mathutils` (float32,
π → 180.000005°) and stored in float32 operator properties: a cut from a bottom face started 3e-05 mm above it
(a skin closed the pocket) and side cuts were rotated 90.000003°, so OCCT booleans left skins and slivers. A drag
started exactly on a part's corner missed the part (ray casts aren't watertight) and made a new part. On a
curved face the drawing plane is the tangent plane, which touches the face along a line: booleans left slivers.

## Decision

1. **Snapping (Blender/BoxCutter convention):** Ctrl snaps, Shift+Ctrl uses a tenth of the step. The step is a
   scene setting on a ladder 0.1 mm – 10 m, changed with Ctrl+Wheel before the first click (tool keymap) or
   while drawing (modal); the wheel alone still zooms. Snapping is absolute: both corners of a box (a cylinder's
   centre) go to grid nodes, radius and height to multiples of the step. The grid is the 3D cursor's plane, or
   on a part's face the part's own origin projected on it. A cross marks the node under the mouse: orange over
   a part (union/cut), white over the cursor plane (new part). Shape and step are shown in the tool header and
   in the BlendSolid sidebar, whose button activates the tool. A part's parameter arrows hide while the tool is
   active (they took the click).
2. **Exact placements on flat faces:** the worker sends each flat face's plane in float64 (`face_planes`,
   stored on the mesh); Draw Solid builds the drawing plane from it in the part's own coordinates
   (`drawing.LocalPlane`, float64 Euler angles) and keeps the exact placement through the float32 redo
   properties (a hidden `exact` property, used while the visible values still match it).
3. **Edge picking:** when the ray under the mouse misses, rays 3 px around it are tried; on an edge the face
   most facing the view wins.
4. **Curved faces:** a solid drawn on a face without an exact plane reaches past it — a cut starts outside,
   a union inside the part — by the footprint's half-diagonal, capped at half the free space in front of the
   face (or the part's thickness behind it).
   The plane on a curved face is tangent to the surface (2026-09-27, after the maintainer saw the grid spin
   about the snap cross on a cone's side): its normal is the worker's exact vertex normals interpolated across
   the triangle hit (the triangle's own normal jumped ~12° from triangle to triangle and was up to 6° off; the
   interpolated one is within 1.4° on the default cone), its X the horizontal tangent (part Z × normal) and Y
   up the surface. The flat-face rule (part X projected, part Y past |n.x| = 0.9) switched axis mid-surface:
   on a tilted tangent plane the two projections differ, and the grid turned by up to ~180° under the mouse.
   Flat faces keep their rule, so scripts written on them are unchanged. The exact surface normal at the point
   (from the worker) would remove the remaining 1–2° tilt of a solid drawn on a curved face.
5. **Snap guides (added at the end of the manual GUI test, maintainer's request):** the node marker is a cross
   along the drawing plane plus a stub along its normal, each arm in its world axis colour (Blender's theme
   X/Y/Z colours, mixed by the squared components of the direction on tilted planes), 20 px scaled with the
   interface; a ring in the old colours (orange: a part, white: the cursor plane). Around it, a local grid of
   the current step fading out over 8 steps (every 5th line major); cells under 8 px on screen fall back to the
   major lines, or no grid. While dragging with Ctrl the grid follows the dragged corner; in the height stage
   ticks mark every step along the normal. Labels next to the solid give the base size or the height and the
   snap step. World axes (not the part's) match the navigation gizmo the user always sees. A local, fading
   grid rather than one over the whole face: on large faces with small steps a full grid is a wall of lines
   (not compared in detail with BoxCutter's or CAD sketch grids yet).

## Consequences

- Scripts written on flat faces carry exact numbers (0, 130, 90°); the maintainer's parts rebuild with the
  expected face counts and volumes (e.g. 738000 mm³, 26 faces instead of slivers).
- On curved faces the numbers are not round (tessellated hit point, tangent plane) and the tool is a little
  longer than drawn by the clearance, visible in the redo panel.
- Blender gives no modifier state outside a modal operator, so the snap cross can't depend on Ctrl being held:
  it is always shown while the tool is active.
- **Placements on exact planes are written with 10 decimals** (added after the manual GUI test, step 13): a face
  can sit off the scripts' 6-decimal grid (a pocket wall at y = -93.652651 + 53.694279 / 2 = -66.8055115 mm), and
  the rounded placement started a cut 5e-07 mm inside the material, past OCCT's 1e-07 mm tolerance: a skin
  closed the pocket. Only the component that must lie on the face gets the extra digits; the base centre in
  the plane is rounded to 6 decimals like the parameters (mouse positions are float32), so freehand scripts
  stay readable (`Location((0.0, 15.0000015, 10.0), ...)`).
- The snap guides can't be tested headless (no GPU in background mode): their geometry is
  (`drawing.axis_color`, `marker_lines`, `grid_segments`, `visible_grid_step`, `height_ticks`, `labels`), and
  `tools/gui_check.py` draws the preview with Ctrl held in a real window.
- Tests: `tests/blender/test_draw_tool.py`, `test_draw_solid.py` (exactness, picking, clearance, snapping).
