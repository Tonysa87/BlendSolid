# ADR 0003 — Units of history scripts and meshes

- **Status:** accepted (2026-09-26, controller's ruling after the milestone 1 branch review)
- **Date:** 2026-09-26
- **Context from:** milestone 1 whole-branch review, finding 7

## Context

build123d has no unit system: its numbers are whatever the script's author means, and CAD users (and every
exchange format BlendSolid will meet: STEP, STL for printing) think in millimetres. Blender's scenes are in
metres by default (`scene.unit_settings.scale_length = 1.0`), and many CAD-minded users set up millimetre
scenes (`scale_length = 0.001`, lengths shown in mm). Milestone 1 copied the worker's vertices unchanged, so
the default 40 mm part was 40 m tall in a default scene.

## Decision

- **Scripts are in millimetres.** The default template says so in its header comment.
- **Meshes are in Blender units:** vertices are multiplied by
  `factor = 0.001 / scene.unit_settings.scale_length` when the result is applied (Blender side; the worker
  and its tessellation tolerances stay in millimetres). A 40 mm box is 0.04 units (0.04 m) in a default scene
  and 40 units (shown as 40 mm) in a scene with `scale_length = 0.001`.
- **The factor is part of the cache tag:** `tag = sha1(source + factor)`. Changing the scene's unit scale makes
  every part stale, so the reconcile loop recomputes it; reloading a file with an unchanged scale doesn't.
- The factor comes from the active scene (`context.scene`). Parts are not per-scene in milestone 1: a part
  shown in two scenes with different unit scales follows whichever scene is active.

## Consequences

- Volumes, dimensions and tolerances in the worker are always in mm; tests compare in mm
  (`mesh_volume / factor**3`) or check dimensions in Blender units explicitly.
- Files saved before this decision recompute once on load (their tag has no factor) — acceptable before the
  first release.
- A scene with a very small `scale_length` gives large Blender-unit coordinates; that is the user's choice of
  scene units, not something BlendSolid corrects.
