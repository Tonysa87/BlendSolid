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

## Addendum (2026-10-04, session 15): area seeds carry their bounding curves (bug sweep R11)

A bare seed point silently picked another region after an upstream change (a rectangle narrowed past the point:
the extrude took the rest of the face instead). Research: Onshape identifies a sketch region by the sketch curves
bounding it ("at least one sketch id in the loop of edges around the region") and resolves a changed topology to
the patches next to those curves; Fusion stores the clicked profile and is known to switch profiles after sketch
edits (Autodesk forum, FUS-227038). Neither tells the user. So:
- The tools write each seed as `area((u, v), inside="rect_1", left="line_1", ...)`: the point stays the
  identifier (readable, editable), and each curve bounding the picked area is listed with the area's side of it —
  `inside`/`outside` for closed entities and for `"face"` (the sketch face's boundary, a reserved entity name),
  `left`/`right` for open curves along their own direction.
- The worker compares the area under the point with that description: a curve whose side flipped, or no curve in
  common, is a `BrokenReference` on the line ("pick the area again"); other changes (a curve added or gone, e.g.
  the rectangle now clipped by the face's edge) are a warning. Equal descriptions pass silently; a bare `(u, v)`
  seed is not checked (scripts written by hand or before this addendum).
- Two areas with the same description (a zigzag line crossing a rectangle) are still told apart by the point
  alone: the description is a check, not a full identity.
- After an independent review of the first version: `"face"` is always listed for a sketch on a face, bounding
  the area or not (the face narrowing past the area must show: it was only a warning); a closed entity named by
  the seed that no longer bounds the area is still checked for containment (a rectangle grown over the whole face
  is a warning, not an error); a closed path crossing itself has left/right sides (its `Face()` is invalid, its
  inside arbitrary); a face edge merely *near* a line never fails the sketch's display. Blender writes the
  region's own inside point instead of the click when the click lies within the display polygon's sagitta of
  the region's boundary (5° chords cut arcs short: the worker's exact test put the point in the next area).
- Known limits: reversing a line's direction flips its left/right (the tools never do); an entity deleted by
  hand and redrawn under the same name matches the old description; `bounds` cost ~0.5 s per recompute for a
  sketch of 30 entities and 200 regions (bounding-box prefilter; lazily computed bounds if that ever matters).

Roles, same session (bug sweep R8, R9): a side face swept by an edge of the face the sketch lies on (a region
bounded by the face's border, tapered) gets the role `border` (it was `end`, like the top cap); a region edge on
a revolve's axis sweeps nothing and names no face (its midpoint lay on the end cap, which took the entity's name).
