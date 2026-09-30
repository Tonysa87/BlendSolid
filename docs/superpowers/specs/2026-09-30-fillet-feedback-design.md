# Design: Fillet tool feedback — the real result as the only preview, a native handle

- **Status:** decided by the maintainer on 2026-09-30 (points 1–2 below); the rest is the proposal that follows
  from them, to confirm when planned
- **Date:** 2026-09-30
- **Research:** `docs/research/2026-09-30-fillet-handle-and-preview.md`

## What the maintainer sees (2026-09-30)

"From the viewpoint where the fillet is made the preview looks right; then the preview follows the whole face,
and the lines on the faces opposite to the view look wrong from the viewport." This matches the code: the
immediate overlay (`preview_lines` for every segment of every selected edge) is drawn with the depth test off
(`ops_draw._draw_segments`: `depth_test_set("NONE")`), so the preview lines of edges on the far side of the part
are drawn over the solid. The other causes in the research note (lag, failures keeping the last mesh, curved
faces, corners, tangent chains) add to it.

## Decisions (maintainer)

1. **Blender's native gizmos, no reinvented handles.** The yellow wire arrow goes.
2. The preview problem is to be fixed (the drawn-through lines above).

## Proposal that follows

1. **The real result is the only preview.** Remove the approximate overlay (`preview_lines` /
   `drawing.fillet_preview` while dragging). The part's own mesh, recomputed on every move (59 ms on the test
   part), is the preview, as in Fusion, Onshape, Shapr3D, Rhino and Blender's Bevel.
2. **The radius handle is a native arrow gizmo** (`GIZMO_GT_arrow_3d`), in the same style and colour as the
   parameter arrows (ADR 0011), in a gizmo group with `bl_options` `{"3D", "DEPTH_3D", …}` ("Supports culled
   depth by other objects in the view", `rna_wm_gizmo.cc` [verified, source]) so it hides behind the part like
   the geometry, and `use_draw_value` ("Show an indicator for the current value while dragging" [verified,
   source]). The arrow is bound to the drag radius with `target_set_handler`, the way the parameter arrows are.
   Placement stays the edge's midpoint along the faces' bisector (`drawing.fillet_handle`).
3. **Fillet out, chamfer in** (Shapr3D, Plasticity): dragging the arrow into the solid makes a chamfer, out of
   it a fillet. The C key stays as a shortcut. **Approved by the maintainer (2026-09-30).**
4. **State is shown, never hidden:**
   - while a result for the current radius is pending, the selected edges in a "busy" tint;
   - when the radius can't be built, the arrow turns red (the gizmo's `color`) and the value shows the largest
     radius that works, which the worker already finds by bisection (`worker/blends.py`), plus the header
     message as today. The part keeps its last good mesh, but now visibly so.
5. **Selection highlights with depth**: hovered and selected edges drawn with the depth test on; edges behind
   the part not drawn (or faint). This alone removes the maintainer's "wrong from the viewport" effect.
6. **Tangent chain before dragging**: the edges OCCT will round together with the clicked one, in a lighter tint
   of the selection colour (OCCT can't limit the chain, so the tool shows it).
7. Later, not in this pass: typed numbers while dragging (Blender's `NumInput`, milestone 2 follow-up); the
   same treatment for Push/Pull's handle.

## Native gizmos for the tools (maintainer: "use Blender's native gizmos for these tools too")

Read in Blender's source (main branch, GitHub mirror; the API and manual pages returned only navigation to the
fetch tool) [verified, source]:

- **Gizmo types registered by Blender** (`space_api/spacetypes.cc`): `GIZMO_GT_button_2d`, `dial_3d`, `move_3d`,
  `arrow_3d`, `preselect_3d`, `primitive_3d`, `blank_3d`, `cage_2d`, `cage_3d`, `snap_3d`. `arrow_3d` draw styles
  NORMAL/CROSS/BOX/CONE/PLANE, options STEM/ORIGIN, transform INVERT/CONSTRAIN; gizmo `use_draw_value` shows
  the value while dragging; gizmo groups can be `DEPTH_3D`.
- **What Blender's own tools use** (`scripts/startup/bl_ui/space_toolsystem_toolbar.py`): **Bevel**, **Push/Pull**,
  Shrink/Fatten, Edge Slide and the Extrude-along-normals tools use `VIEW3D_GGT_tool_generic_handle_normal`;
  Inset, Rip, Vertex Slide use `…_handle_free`; Extrude uses `VIEW3D_GGT_xform_extrude`; the Add Cube/Cylinder/…
  tools (draw a base, then the height — Draw Solid's native cousin) use `VIEW3D_GGT_placement`.
- **The generic handle** (`space_view3d/view3d_gizmo_tool_generic.cc`) is a `GIZMO_GT_button_2d` circle with
  backdrop, help line and outline, in the theme's **Gizmo Primary / Gizmo Highlight** colours, placed at the
  centre of Blender's *edit-mesh selection* along its normal; dragging it runs the tool's keymap operator. It can't
  be reused as it is for BlendSolid (our selection is BRep edges and faces in Object Mode, not an edit-mesh
  selection), but its **look and behaviour can be rebuilt with the same gizmo type** from Python.

So, per tool:

| Tool | Native model in Blender | Proposal |
| --- | --- | --- |
| Fillet | Bevel tool's generic handle | `GIZMO_GT_button_2d` handle (backdrop + help line + outline, theme gizmo colours) at the selected edge's midpoint, offset out along the faces' bisector; dragging it runs the fillet drag |
| Push/Pull | Push/Pull tool's generic handle | the same handle on the pressed face's centre, along its normal |
| Parameters | (already) `GIZMO_GT_arrow_3d` | keep; switch hardcoded colours to the theme's gizmo colours |
| Draw Solid | Add Cube tool (`VIEW3D_GGT_placement`) | study it for 3a's placement feedback; the snap marker could become `GIZMO_GT_snap_3d` (to check from Python) |

With the handle as `button_2d` (a screen-space circle, like Blender's), point 2 above (arrow gizmo in a
`DEPTH_3D` group) is replaced; the value label while dragging stays (header + `use_draw_value` where the type
supports it, else the existing label). Colours everywhere from `preferences.themes[0].user_interface`
(`gizmo_primary`, `gizmo_hi`, …) instead of the hardcoded yellow, orange and blue.

## Handoff to the evening session

- Merge this branch's docs; the decision goes into the same ADR as the pie menus or its own (Claude Code's call).
- Plan it with the pie-menu work as one "UI pass" before the 3a usage checkpoint (both are the tools' interface,
  not modeling features). Order suggested: points 5 and 1 first (the maintainer's complaint, small), then 2–4,
  then 6.
- Criterion: no preview line drawn through the part (a headless test on the draw lists: only real-result mesh
  while dragging); the handle is a native arrow gizmo in a `DEPTH_3D` group; a too-large radius turns the handle
  red with the largest working radius shown; `gui_check.py` step for a drag on a box edge from a view where the
  opposite edges are hidden.
- Check first in a GUI session: whether `GIZMO_GT_arrow_3d` in a `DEPTH_3D` group stays visible enough on the
  part's own edge (it sits on the surface), and whether negative values (chamfer) draw well with the arrow's
  range.
