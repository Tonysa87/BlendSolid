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
- Review findings fixed (2026-09-27): a solid that is non-manifold where two of its parts touch along an edge
  (Draw Solid with corner snapping) still gets its mesh — those edges carry no id; mirrored solids' planes (an
  indirect frame) point outward (`tessellate.plane_normal`) and their holed faces merge; the on-plane check is
  skipped without modifiers and scales with the distance from the origin (float32: 4e-3 mm at 50 m); an edge is
  sharp where either end is angled.
- Known: a Boolean modifier's operand polygons get `brep_face_id` 0; the on-plane check keeps them from using
  face 0's exact plane unless they lie on it.

## Addendum (2026-09-28, session 8): collars around curved holes

The maintainer found the fans of slivers of flat faces with holes ugly (research:
`docs/research/2026-09-28-planar-faces-with-holes.md`). Changes (`worker/tessellate.py`):

1. **Collars.** A hole of ≥ 8 nodes, star-shaped from its centroid, gets a rectangle around it at 35% of its
   clearance to the other loops (`_COLLAR_SHARE`), with one radial piece per hole node (`_collar`). The region
   outside the collars is triangulated and merged as before (`_collared`).
2. **No thin Catmull–Clark children** (`_thin_children`, `_FACE_POINT_ANGLE` = 20°). A merge is refused when the
   merged polygon has a straight corner (a run of collinear collar nodes, turn < 1°) that sees the polygon's
   vertex average within 20° of its sides. Subdivision Surface puts the face point at the vertex average: a
   collar side of 9 nodes inside one trapezoid had its face point far along the side, and the children there
   folded. Before this rule the collars folded 1–38 children per test part in one Catmull–Clark step; milestone
   2's fans folded too (plate with a small hole 72, bolt circle 36, two bosses 17), which the default-part-only
   test had missed.
3. **BRep vertices keep a corner** (`keep` in `_merge_convex`): where a bevelled edge ends in a tangent arc, a
   merge may not make the vertex a nearly straight corner.

Measured (unit test `test_subdivision_folds_nothing_around_holes`, simulation `spike/m2_flat_faces/cc_folds.py`,
Blender tests): no folded child on the six test parts; Bevel 2 mm by weight on the default part removes the same
volume with Clamp Overlap on and off (a hole, a boss likewise at 0.5–2 mm); fuzz 7 × 60–80 random parts: no
fallback, closed, ≤ 0.33 s. Smallest polygon corner on holed faces: bolt circle 1.2° → 38°, slot 0.9° → 15°,
washer 5.4° → 45°, plate with a small hole 0.13° → 45°.

Tuning found by measurement: a collar at 45% of the clearance left a low strip between its side and the face's
edge, whose wedges to the face's corners were 2° slivers that Bevel 2 mm + Subdivision folded; at 25–35% there
is room for fat pieces. A stricter rule (≥ 23°) split the fillet arc of the default part between two polygons,
and Blender's clamp (`geometry_collide_offset`: an un-bevelled edge at angle θ to a bevelled chord adds cot θ to
the chord's "collapse" sum) then limited a 2 mm bevel to 1.5 mm through the arc's 0.7 mm chords.

Known limit: a hole close to a straight edge (e.g. bosses 4 mm from it) leaves a thin strip between its collar
and that edge; with no vertex allowed on a BRep edge, the strip can only be fans to the edge's two ends (min
corner 0.3° on the two-bosses face, 0.02° for a hole 0.3 mm from an edge). They don't fold under Subdivision.
Collars are aligned with the outer loop's longest segment, so on round faces (washer, bolt circle) they are
tilted; cosmetic.

Revised the same day after the maintainer's GUI review (`/mnt/e/bs_debug/test2.blend`): the wedges the rule adds
from the face's corners to the collars' sides look worse than the 4 diagonals of plain trapezoids, and
Subdivision belongs on "convert to quads", not on the display mesh (maintainer). Subdivision fold tests are gone.
The rule itself stays, weaker (10°): without it, or below ~10°, one polygon holding the default part's whole
fillet arc and a collar side folds under Bevel 2 mm (limiting the rule to polygons with arc nodes split the arc
instead and made it worse). On test2's three holed flat faces, polygons with a corner under 10°: 18/21/49 at
20°, 11/7/38 at 10°. What remains is fans from arc notches in the outer loop (a boss or hole cutting a corner or
an edge) and thin strips next to edges: next step, partial collars for arcs of the outer loop.
