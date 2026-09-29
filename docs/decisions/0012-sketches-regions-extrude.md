# ADR 0012 — Sketches, regions and their extrude/revolve in part scripts

- **Status:** accepted (to be checked by the maintainer in the GUI)
- **Date:** 2026-09-29
- **Context from:** research `docs/research/2026-09-29-milestone-3a-sketch-extrude-io.md`, milestone 3a

## Context

Milestone 3a adds 2D sketches on a face or plane and the extrude/revolve of their closed areas. The history is a
build123d script (ADR 0009 references); build123d's own sketch objects join the current builder (a `Rectangle`
inside `with BuildPart()` raises), `BuildSketch` fuses overlapping shapes (their inner areas are lost), and
`Plane(face)` is centred on the face (sketch coordinates drift when an upstream change resizes it).

## Decision

1. **Grammar.** A sketch is a feature written as a `with` block whose attributes are its entities:
   ```python
   with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1
       sketch_1.rect_1 = Pos(5.0, 0.0) * Rectangle(sketch_1_rect_1_width, sketch_1_rect_1_height)
       sketch_1.line_1 = Line((0.0, -20.0), (0.0, 20.0))
   extrude(regions(sketch_1, (5.0, 0.0)), amount=extrude_1_amount, taper=extrude_1_taper)  # feature: extrude_1
   ```
   The block runs outside the part's builder (the sketch clears build123d's build scope), so entities are plain
   build123d objects in the plane's XY; attribute names name them. Sizes are parameters, positions literals
   (6 decimals), as for primitives.
2. **Planes.** `on_face(face(...))`: the face's exact plane, origin = the part's origin projected, X by Draw
   Solid's rule (ADR 0006) — identical to Blender's `drawing.plane_on_part_face`, so the tools' plane coordinates
   are the script's. On the 3D cursor's plane a sketch makes a new part placed there, on `Plane.XY`. A part may be
   only sketches (empty mesh, no error).
3. **Regions** are the areas bounded by all the sketch's curves (General Fuse with a 1e-5 mm fuzzy value, dangling
   edges dropped), picked by a seed point: `regions(sketch_1, (u, v), ...)` (Onshape's `qContainsPoint`). A seed in
   no region is a `BrokenReference` on its line; a seed on a boundary a warning (ADR 0009 policy).
4. **extrude()/revolve() of regions are BlendSolid's** (other inputs still go to build123d's, e.g. Push/Pull's
   faces): taper = straight prism + `draft` (planes and cones, never lofted B-splines); up to next/last is
   computed by the boolean's meaning (a join fills the empty space ahead up to where material starts; a cut
   takes the first stretch of material, or all of it for last), and finding nothing to stop at is an error —
   build123d's `extrude_until` stopped at the face the sketch lies on. Direction against the normal is written
   `dir=-sketch_1.plane.z_dir` (with `until`) or a negative amount.
5. **Roles** of the faces they bring in: `start`, `end`, and each side face by the name of the entity that swept
   it (`face("extrude_1", "rect_1", near=...)`), stable under taper and parameter changes (ADR 0009 addendum).
6. **Display.** The worker returns each sketch's plane, curves, regions and snap points; the part keeps them on
   its mesh (`bs_sketches`, JSON). An overlay draws sketches not extruded yet, and all of them while a sketch tool
   is active. Constraints are not in 3a (Plasticity/MoI model: snaps + parameters).

## Consequences

- Tools: Sketch (rectangle, circle, line; ends snap to sketch points, Ctrl to the grid; a drag on a face adds to
  the unused sketch on that plane, else starts one; on the cursor plane, to the unused sketch on it), Extrude
  Sketch (drag a region: out joins, in cuts; operation, up to next/last, symmetric, taper in Adjust Last
  Operation), Revolve Sketch (region, then a sketch line).
- Up to a picked face, New Part/Cutter operations, editing entities (move, delete) from the viewport, arcs,
  polygons and slots are not built yet.
- Sketches drawn across adjacent faces: one sketch per plane (every product does so); projecting/wrapping across
  faces is 3c.

## Addendum (2026-09-29, session 11): paths and grooves

The maintainer's first try: rectangles and circles duplicate Draw Solid and a single line did nothing. Research
`docs/research/2026-09-29-sketch-drawing-ux.md` (CAD products, BoxCutter, Hard Ops): the sketch's value is the
open path, which splits faces and carries a profile. So:
- **Paths**: `sketch_1.path_1 = path((u, v), (u, v), arc_to((u, v)), ..., closed=True)` — lines and arcs tangent
  to the path so far. The Sketch tool's default shape: click points, press-drag (or A) for an arc, click the first
  point to close, Enter/right-click/double-click to end, Backspace removes the last point.
- **A sketch on a face splits the face**: the face's edges bound its regions too (Onshape imprint, SketchUp), so a
  line across a face gives two pieces for Extrude Sketch.
- **Grooves and ribs**: `groove(sketch_1.path_1, width=, depth=, profile="rect"|"round"|"v"|"circle",
  corners="mitre"|"round", mode=Mode.SUBTRACT|Mode.ADD)` sweeps the profile along any sketch curve, kept square to
  the sketch plane (`MakePipeShell` binormal mode; RightCorner/RoundCorner transitions — build123d's default
  Transformed gives invalid solids at sharp corners). A groove's profile reaches 0.5 mm above the face (no
  coplanar boolean faces); a rib on a face sinks 0.5 mm into it. The Groove tool: press on a curve and drag into
  the part (groove) or out (rib). Its faces all get the role `wall` for now (references need `near=`).
