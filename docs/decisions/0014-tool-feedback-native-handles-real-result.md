# ADR 0014: Fillet and Push/Pull feedback — the real result as the only preview, Blender's native handle

- **Status:** accepted (2026-09-30, decided by the maintainer); point 4 partly built on 2026-09-30 (addendum
  below); the rest not built yet (UI pass, plan `docs/superpowers/plans/2026-09-30-ui-pass.md`)
- **Date:** 2026-09-30
- **Research:** `docs/research/2026-09-30-fillet-handle-and-preview.md`
- **Design:** `docs/superpowers/specs/2026-09-30-fillet-feedback-design.md`

## Context

The maintainer: the fillet preview looks right from the side where it is made, but "the lines on the faces
opposite to the view look wrong". The overlay (`preview_lines`, every segment of every selected edge) is drawn with
the depth test off (`ops_draw._draw_segments`), so lines on the far side show through the solid; lag, failures
that silently keep the last mesh, and tangent chains add to it. The tools' yellow wire arrows are hand-drawn.

## Decision

1. **Blender's native gizmos only.** Fillet and Push/Pull get the handle Blender's own Bevel and Push/Pull tools
   use (`VIEW3D_GGT_tool_generic_handle_normal`, `view3d_gizmo_tool_generic.cc`), rebuilt from Python with the
   same gizmo type (`GIZMO_GT_button_2d`: backdrop, help line, outline) in the theme's Gizmo Primary / Highlight
   colours: at the selected edge's midpoint along the faces' bisector (Fillet), at the pressed face's centre along
   its normal (Push/Pull). The hand-drawn arrows go; parameter arrows keep `GIZMO_GT_arrow_3d` with theme colours.
2. **The real result is the only preview**: the drawn stand-in (`drawing.fillet_preview`) goes; the part's own
   mesh, recomputed on every move, is the preview (as Fusion, Onshape, Shapr3D, Rhino, Blender's Bevel).
3. **Selection highlights drawn with depth** (`LESS_EQUAL`): nothing drawn through the part. Draw Solid's grid,
   ticks and labels keep depth off.
4. **State shown, never hidden:** pending result → the selected edges in a busy tint; a radius that can't be
   built → the handle in the error colour with the largest working radius (the worker's bisection) and the part
   visibly on its last good result.
5. **Drag out of the solid = fillet, into it = chamfer** (Shapr3D, Plasticity; approved 2026-09-30); C stays a
   shortcut.
6. Last: the tangent chain OCCT will round shown in a lighter tint before dragging.

## Consequences

- Built in the same UI pass as ADR 0013. Order: depth highlights and removing the stand-in preview first (the
  maintainer's complaint), then the handle and state, then the tangent chain.
- Typed values while dragging (`NumInput`) stay a later follow-up.

## Addendum (2026-09-30, the maintainer's test6.blend): a failing feature is shown and stops new features

The maintainer found "problems with all the fillets": one fillet (50 mm on all 14 edges of a grooved top face; the
largest that works is 19.995 mm) failed, the part kept showing its last good mesh, the error was only in the
sidebar, and the eight fillets and the extrusion added after it were never built — they were even picked on the
stale mesh (four fillets on an edge already rounded). Built:
- **In the viewport:** a part whose current script fails shows, next to it, "<part>: <feature> fails", the
  worker's message and "(the part shows its last good result)", in the theme's error colour (`ui.error_label`).
- **No feature is added to a failing part** (every tool and operator that appends one: Fillet, Push/Pull, Draw
  Solid union/cut, booleans, Sketch, Extrude, Revolve, Groove): the message names the failing feature and asks to
  change or undo it (`part.blocking_error`). Errors of a drag's live preview don't count (their tag is not the
  current script's).
- **The Fillet drag stops at the largest size that works:** when the worker answers "too large … the largest that
  works is X mm" during the drag, the radius is held at X (header and label say so), so a release never leaves a
  fillet that can't be built (gui_check step 25).
- The parameter arrows of the selected part hide while any BlendSolid editing tool is active (they took the
  Fillet tool's click on the top face's centre).
