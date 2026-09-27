# ADR 0010 — Edge-first, grid-based tessellation of trimmed faces

- **Status:** accepted (2026-09-28, after the maintainer's review of the ADR 0005 addendum in the GUI)
- **Date:** 2026-09-28
- **Supersedes:** ADR 0005's addendum (trimmed curved faces re-triangulated by a Delaunay lattice)
- **Research:** `docs/research/2026-09-28-cad-display-tessellation-products.md`,
  `docs/research/2026-09-28-trimmed-face-tessellation-algorithms.md`

## Context

The maintainer opened `fillet.blend` (a box corner cut by a big cylinder, every edge of the cut filleted) and,
with a bigger box, found the topology "pessima". Measured on `tests/unit/data/maintainer_fillet_part.py` at 1 mm:

- the fillet band along the big cylinder (a trimmed torus, 695 triangles) is an irregular mosaic: 35% of its
  triangles under 15°, vertices with 11 triangles. ADR 0005's addendum re-triangulates it with Delaunay on a
  lattice: a rectangular lattice is co-circular, so Delaunay picks every cell's diagonal by round-off, and the
  band between the lattice and the boundary is free Delaunay;
- the quarter cylinder under it (29 triangles, one row 400 mm tall) fans irregularly: its top edge (shared with
  the fillet) and its bottom edge were discretized independently by BRepMesh, with different node counts;
- narrow fillet strips are dense slivers for the same reason.

What the products whose wireframes users call clean do (research): **Rhino, MoI and ACIS** lay a grid on each
surface's (u, v), trim it by the face's boundary, and triangulate only what the trim cuts ("every poly edge is
either along a trim boundary edge, or running along a surface's UV directions" — MoI's author). **Each edge is
discretized once**, its points shared by both faces (ACIS: spaced like the finer of the two faces' grids;
Parasolid's topology matching; OCCT does the same for its edges). A size cap and an aspect-ratio cap bound the
cells (Rhino suggests 6). SALOME's quadrangle mapping and Gmsh's transfinite surfaces mesh 4-sided faces as
structured grids from their boundary nodes, after making opposite sides carry the same node count. BRepMesh
itself can't be changed from Python: OCP doesn't expose the classes a custom face mesher needs.

The maintainer set the scope: **the display mesh follows CAD conventions (triangles, as Rhino/Plasticity/MoI show
them)**; converting a part to quads will be a separate, later button (for CAD parts and NURBS surfaces alike).

## Decision

BlendSolid tessellates every face itself from one shared discretization of the edges
(`blendsolid/worker/meshing.py`); BRepMesh is no longer used for display.

1. **Edge-first discretization.** Every BRep edge gets one list of curve parameters and its 3D points (edge
   ends: the exact vertex points), computed once per recompute; each face takes its boundary nodes from these
   lists (3D points shared, (u, v) from the face's pcurve at the same parameters), so neighbouring faces weld
   exactly by construction. The count of an edge is the largest of: its own chord deflection and angle (the
   tolerance), and the grid step of each curved face it bounds, in the edge's direction. Nodes are spaced
   evenly along the edge, checked against the tolerance at the midpoints. The angular limit per segment is half
   the scene's angular deflection (0.15 rad): the density BRepMesh gave curves under ADR 0005 (a 10 mm circle
   had 42 segments), which the maintainer checked; interpolated normals on a one-row cone side stay within 1.4°.
2. **Matched opposite sides.** A curved face with four corners (the four sharpest turns of its boundary, as
   SALOME picks them; smooth joints between edges aren't corners) wants opposite sides with the same node count.
   Counts are raised, never lowered, until every such face's opposite sides match (iterated over the shared
   edges, which propagates along chains of fillets and trimmed cylinders); the faces a cap stops keep the
   general mesher. A cylinder or cone between two circles pairs its circles the same way.
3. **Four-sided curved faces: structured grids.** Transfinite (Coons) interpolation of the four sides in (u, v)
   (SALOME's `calcUV`), rows × columns from the side counts, each cell split by its shorter 3D diagonal (a fixed
   diagonal when both are equal within 1%). A straight direction (a cylinder's generatrix) is one row, as on full
   faces of revolution (ADR 0005). Fillet bands become regular rows, trimmed cylinders aligned columns.
4. **Other curved faces: a trimmed grid.** A tensor grid in (u, v), scaled per direction by the curvature (chord
   sag and angle within the tolerance, at most 4:1 between directions, a straight direction at most 6 times
   the other step), keeps the nodes inside the face and at least half a cell from its boundary. Cells whose four
   corners are kept and that the boundary doesn't cross are split by one diagonal; the band between them and
   the boundary is a constrained Delaunay triangulation (scipy's Delaunay, missing boundary segments recovered
   by edge flips).
5. **Flat faces** are triangulated from their boundary nodes the same way (no interior nodes): they become one
   polygon, or convex polygons around holes, as before (ADR 0008).
6. **Full faces of revolution** keep ADR 0005's grids; their boundary circles come from the shared edge lists.
   Full spheres and tori (no edges shared) are unchanged.
7. **Failure is loud.** If a face can't be meshed from its boundary (an invalid trim loop), the worker reports
   the face and falls back to BRepMesh for that face only; the mesh is then open along its edges (visible), never
   silently wrong.

## Consequences

- Wireframes follow the surfaces' (u, v) directions and trims, as in Rhino and MoI; the fans and mosaics are gone.
  The criterion is numeric: `tests/unit/test_tessellate.py` measures, per face, the minimum angles, the valence,
  the share of grid-regular vertices, the deviation from the exact surface, the welding and the volume.
- Straight directions stay one row (long thin triangles on cylinders, as Blender's own cylinder): shading is exact
  (ADR 0005 point 3). If the maintainer wants them split, it is the aspect cap of point 4 applied to point 3.
- Matching opposite sides can add nodes to a neighbour (a plane's edge, a small fillet): meshes get somewhat
  denser along fillet chains.
- Measured on `maintainer_fillet_part.py` at 1 mm: fillet bands with 100% valence-6 interior vertices, the quarter
  cylinder as one row of aligned columns, closed mesh, 12,966 triangles in 0.07 s (0.14 s before, BRepMesh plus
  the addendum's remesh). The band's 4:1 cells set the columns of the cylinder next to it (about 3 mm on a
  400 mm face): regular but dense; the scene tolerance makes it coarser.
- `MESH_FORMAT` is bumped: saved meshes are recomputed.
- Quads: out of scope here (the future conversion button); the structured grids of point 3 are its easiest input.
