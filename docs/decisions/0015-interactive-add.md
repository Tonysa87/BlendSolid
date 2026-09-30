# ADR 0015: Adding a primitive: placed where the pie was opened, sized by the mouse

- **Status:** accepted (2026-09-30, the maintainer's request; design agreed in the chat before building)
- **Date:** 2026-09-30

## Context

E > Add > Box made a 40 × 30 × 20 mm box at the 3D cursor: tiny next to a 500 mm part, and far from where the
user was looking. The maintainer asked for an approximate, usable size at once (e.g. 1000 × 1000 × 1000) that
the mouse can scale before confirming, with the exact numbers afterwards.

Other software: Plasticity, Shapr3D, MoI and Blender's own Add Cube tool draw a primitive (click, drag the base,
then the height) — BlendSolid already has that as Draw Solid. Blender's Shift+A puts a fixed-size object at the 3D
cursor and offers the numbers in Adjust Last Operation. Scaling around a pivot by the mouse distance is Blender's S.

## Decision

Invoked from the viewport (the pie or Shift+A; scripts and `EXEC_DEFAULT` calls keep the old behaviour):

1. **Where:** the point where the pie was opened (the pie remembers it for 30 s, per area): on the face under
   it (as Draw Solid picks: exact plane of a part's flat face, tangent plane of a curved one) or on the 3D
   cursor's plane. Always a new part, never joined. From Shift+A (no pie point): the 3D cursor, as Blender does.
2. **Starting size from the view, not fixed:** about a fifth of the viewport's height at that point, rounded to
   1-2-5 × 10ⁿ mm. Even proportions (`primitives.PROPORTIONS`): a cube, a cylinder as wide as tall, a sphere, a
   cone 2:1 radii, a torus 4:1 radii, a wedge with a quarter-length top; the size is the largest extent.
3. **Scaling like S:** size = start × (mouse distance from the point) / (starting distance), snapped to
   1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8 × 10ⁿ mm; Ctrl snaps to the grid step; digits type the size.
   While scaling only the object's scale changes (instant, no worker round trip); the confirmed size is written into
   the script and the scale reset to 1 (parts keep scale 1).
4. Click / Enter / Space confirms (one undo step); Esc / right-click removes the preview part and its script.
   Adjust Last Operation then shows the exact dimensions and re-runs at the same placement (hidden `matrix`).

## Consequences

- The E key opens the pie through `blendsolid.call_pie` (records the point), the right-drag through
  `blendsolid.pie_or_menu`.
- Tests: `tests/unit/test_primitives_sizes.py`; gui_check step 24 (E > Add > Box, scale, confirm; Esc leaves
  nothing).
