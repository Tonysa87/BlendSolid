# ADR 0008 — A display mesh Blender's modifiers can work on

- **Status:** accepted
- **Date:** 2026-09-27
- **Context from:** the maintainer's requirement (2026-09-27) that a user can mix CAD operations and Blender
  modifiers on a part; milestone 2 design, section A (`docs/superpowers/specs/2026-09-27-milestone-2-selectors-design.md`)

## Context

Until milestone 1.5 the worker sent every BRep face as its own island of triangles: vertices duplicated along
the CAD edges gave sharp shading and an unambiguous face map, but to Blender the part was a set of open patches.
Bevel had nothing to round, Weighted Normal, Solidify and Subdivision saw open borders, and the mesh couldn't be
used as the base of a modifier workflow. Milestone 2 also needs the CAD edges in the mesh, to click them.

## Decision

1. **Weld.** The worker merges the coincident boundary nodes of neighbouring faces (a 1e-6 mm grid, then a
   1e-5 mm pass over vertices of edges still open). Neighbouring faces are conforming — BRepMesh's edge nodes,
   and the structured grids of ADR 0005 take their rims from those nodes — so every part mesh is closed (tested
   on every tessellation test shape: each edge has two polygons).
2. **Polygons, not only triangles.** A flat face without holes is one polygon (its boundary loop), as in
   Blender's own primitives (box faces are quads, cylinder caps n-gons). A flat face with holes is split into
   convex polygons (Hertel–Mehlhorn: triangles merged across their shortest shared edges while both ends of the
   edge stay convex). Curved faces stay triangulated (ADR 0005's grids). Reason, measured: Bevel's *Clamp
   Overlap*, on by default, clamps the whole bevel to its tightest spot, and a triangulated cap or the ears of a
   triangulation along an arc have short chords. A 1 mm bevel on the default part removed 0.22 mm³ with
   triangles, 25 mm³ with the fewest simple (concave) polygons, 82 mm³ with convex polygons — the unclamped value.
   With convex polygons clamped and unclamped bevels are equal on every probed part (box, box with a hole, box
   with a boss, filleted box, one fillet, the default part).
3. **Edge data.** Every mesh edge lying on a BRep edge carries `brep_edge_id` (index in the result's edge map;
   -1 inside a face; seams and poles are inside a face). Where the two faces meet at an angle (their exact normals
   differ by more than 1e-3 rad) the edge is `sharp_edge` and has `bevel_weight_edge` = 1: Bevel with *Limit
   Method: Weight* rounds exactly the CAD edges, not a tessellation edge, and not the tangent edges between a
   fillet and its neighbours.
4. **Normals per corner.** The exact surface normals (ADR 0005) move from the POINT to the CORNER domain: a welded
   vertex on a sharp edge has one normal per face.
5. **Tools read the evaluated mesh.** Ray casts return polygon indices of the evaluated mesh (after modifiers):
   face ids and corner normals are read from `obj.evaluated_get(depsgraph).data`, which every tested modifier
   keeps `brep_face_id` on (new faces take the id of the face they come from). A face's exact plane is used only
   when the hit point lies on it (1e-3 mm): an Array copy or a mirrored copy of a face carries the face's id but
   not its position, and then the drawing plane goes through the hit, as on any mesh.
6. `part.MESH_FORMAT` 4: meshes saved by older versions are recomputed once.

## Consequences

- Measured (headless tests, `tests/blender/test_modifiers.py`): Bevel (weight; clamp on and off), Weighted Normal,
  Triangulate, Solidify, Array, Subdivision Surface keep the part's mesh closed; Edge Split splits exactly the
  sharp CAD edges; volumes are as expected; a ray on a CAD face still resolves to its BRep face.
- A drawing started on a face a modifier created from a CAD face (an Array copy) is placed in the part's frame at
  that position: the result is what the script says, which the modifier then repeats. This is how modifiers work
  on any Blender mesh and is not treated as an error.
- The worker sends polygons (`loops`, `poly_sizes`, `poly_face`) instead of triangles; `part.mesh_volume`
  fan-triangulates them. Welding and edge ids cost about 0.1 s on a 29 000-triangle part (profiled).
- Milestone 2's edge picking and references build on `brep_edge_id`.
