# Display mesh of flat faces with holes: topology without slivers

- **Date:** 2026-09-28
- **Question:** a flat BRep face with holes (e.g. a box face with two circular holes or bosses near one edge) is
  meshed as a triangulation merged into convex polygons (Hertel–Mehlhorn, `tessellate._merge_convex`, ADR 0008).
  The result is long fans of slivers from the face's outer corners to every hole vertex (sample: 65 polygons,
  min angle 0.38°). The maintainer finds it ugly. Can the topology be better, under ADR 0008's constraints?
- **Constraints:** boundary vertices are fixed and shared with the neighbour faces (no vertex may be added on
  a BRep edge); the mesh stays welded and closed; it must work with Bevel (by weight, *Clamp Overlap* on by
  default), Subdivision Surface, Solidify, Weighted Normal; a later "convert to quads" feature is planned.
- **Method:** product documentation and author posts (Rhino, MoI, Plasticity, Parasolid, FreeCAD, Gmsh), the
  Plasticity Blender bridge source, Blender's Bevel source (`bmesh_bevel.cc`, main branch), literature.
  Legend: **[inference]** = my reading, **[estimate]** = back-of-envelope number, not measured.

---

## 0. Summary

1. **The slivers are inherent to "convex pieces, no Steiner points".** Seen from the plate, every vertex of a
   curved hole is reflex, so a convex piece holds at most one hole edge: a hole with N vertices needs ≥ N
   pieces, and with no interior vertices each of them must reach the outer boundary — on a box face, its 4
   corners. The angle at a corner is ≈ chord / distance (0.75 mm / 100 mm ≈ 0.4°). No choice of triangulation
   or merge order fixes this. **[inference, elementary geometry]**
2. **CAD products don't solve it either**: Rhino ("simple planes") fills planar faces with a minimal triangle
   fan, MoI outputs one n-gon cut "right through the hole" (concave), Parasolid/Plasticity output convex
   (default) or concave n-gons. Clean hole topology exists only where a remesher or a person makes it.
3. **Hard-surface modelers use interior vertices**: a ring of radial quads around the hole ("circle in a
   square", grid fill), vertex counts in multiples of 4, the square's straight sides joined to the rest.
4. **Blender's Clamp Overlap limits the bevel to the distance of the nearest un-bevelled polygon neighbour**
   (source below). Any interior vertex at distance d from the boundary clamps the whole part's bevel to ≈ d.
   Quality meshers (Triangle, paving, Gmsh) put interior vertices at ≈ one chord from the boundary → the
   0.22 mm³ regime of ADR 0008. Interior vertices are acceptable only far from the boundary.
5. **Recommendation:** a *rectangular collar* per curved hole, placed half-way to the nearest other boundary
   (medial position): N radial quads between the hole and the collar, then Hertel–Mehlhorn on the face minus the
   collars, whose straight sides make a few convex trapezoids. Section 5.

---

## 1. CAD display/export meshers

**Rhino.** Render/export mesh setting *Simple planes*: "all planar surfaces are meshed by meshing the surface
edges and then filling the area bounded by the edges with triangles … a minimum polygon count on planar
surfaces"; all other settings (max edge length, aspect ratio) are then ignored on planes. Without it the
planar face gets the quad-grid-then-trim mesher. Rhino states its mesher "does not support watertight meshes
made only of quadrangles unless you are meshing a single untrimmed surface". Clean quads come only from
*QuadRemesh*, a separate destructive command (target count, *Detect Hard Edges*); users report it struggles
with trimmed surfaces and holes.
<https://docs.mcneel.com/rhino/8/help/en-us/information/polygonmeshsettings.htm>,
<https://wiki.mcneel.com/rhino/meshfaqdetails>, <https://docs.mcneel.com/rhino/8/help/en-us/commands/quadremesh.htm>,
<https://discourse.mcneel.com/t/quad-remesh-issues/105426>

**MoI3D.** Output *N-gons / Quads & Triangles / Triangles*; *Divide larger than* by default applies "only to
curved surfaces leaving planar surfaces unaffected" (can be switched to planes); *Avoid smaller than*, *Aspect
ratio limit*. A planar face is one n-gon; with a hole, the author: "when MoI encounters this type of situation
where it ends up with an n-gon with an interior hole it will divide the n-gon in half right through the hole"
(two concave n-gons). Quads/triangles are obtained by triangulating those n-gons. The author says a mesher for
sub-d use would need "a substantially different meshing process" that "tries to build polygons that radiate
out from trim edges" (never built).
<https://moi3d.com/4.0/docs/moi_command_reference11.htm>, <https://moi3d.com/forum/lmessages.php?webtag=MOI&msg=9388.1>,
<http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=3196.1>, <http://moi3d.com/forum/lmessages.php?msg=162.44&webtag=MOI>

**Parasolid** (Plasticity, Onshape, SolidWorks, NX). Facet `shape`: `convex` (default: "all interior angles
are convex and none of the facets contain interior holes"), `cut` (concave allowed), `any` (holes allowed);
`max_facet_sides` (default 3); min/max facet width; optional `quality improved` ("only … for purposes other
than visualisation"). <http://www.q-solid.com/Parasolid_Docs_V35/chapters/fd_chap.108.html>

**Plasticity.** OBJ export *Tris / Quads* ("quadrangular and triangular polygons") */ Ngons*, *Convex Ngons
Only* ("cleaner topology", more n-gons), min/max width. Its Blender bridge refaceting sends Parasolid
`max_sides = 128` for n-gons and `shape = CUT` (concave n-gons).
<https://doc.plasticity.xyz/plasticity-essentials/export-obj>,
<https://github.com/nkallen/plasticity-blender-addon> (`ui.py`, `client.py`)

**FreeCAD / others.** Mesh from shape: Standard (BRepMesh), Mefisto (max edge length), Netgen (with a *Quad
dominated* option), Gmsh. Fusion 360, Onshape, SolidWorks STL/OBJ export is triangles.
<https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Mesh_FromPartShape.md>

**Takeaway:** every CAD mesher either leaves the fan (triangles, convex n-gons) or hides it in big concave
n-gons. BlendSolid's current output equals Parasolid's default `convex` n-gons. **[inference]**

## 2. Hard-surface Blender practice

- **Circle in a square / radial quads.** Loop-cut the plate, inset the faces where the hole goes, LoopTools
  *Circle* on the inset ring, delete the centre: all quads, with radial edges from each hole vertex to a square
  ring. <https://www.3dsecrets.com/secrets/blender-secrets-modeling-holes>,
  <https://blender-secrets-school.teachable.com/courses/2096727/lectures/47203963>
- **Segment counts** are chosen as multiples of 4 (8/16/32) so the circle maps onto a square's sides and the
  grid around it; reductions (32 → 16 → 8) use 2:1 or 3:1 quad transitions further out.
  <https://polycount.com/discussion/81038/sub-d-tip-perfect-8-sided-cylinders-from-quads>,
  <http://wiki.polycount.com/wiki/Subdivision_Surface_Modeling>
- **Support loops**: a second loop next to a detail loop keeps it crisp under Subdivision
  (<https://blog.cgcookie.com/posts/the-art-of-good-topology-blender/>). BlendSolid doesn't need them for
  display (the part isn't subdivided by default); they belong to "convert to quads".
- **Boolean / bevel / weighted-normal workflow** (HardOps, BoxCutter): n-gons on flat areas are tolerated because
  a flat face shades flat with Weighted Normal; triangulation is applied only to n-gons when needed.
  <https://hardops-manual.readthedocs.io/en/latest/subdivision/>,
  <https://hardops-manual.readthedocs.io/en/latest/tips_boolean/>
- **Remeshers** (Quad Remesher/Exoside, Rhino QuadRemesh, Instant Meshes) are destructive and don't keep the
  boundary vertices shared with neighbour faces: tools for "convert to quads", not for the display mesh.

**Why concave n-gons are not an option for us [inference].** Catmull–Clark places the face point at the
average of the face's vertices (<https://en.wikipedia.org/wiki/Catmull%E2%80%93Clark_subdivision_surface>).
A MoI-style piece "outer side + 90° hole arc of 11 vertices" has its vertex average near the arc, i.e. inside
the hole: Subdivision Surface then builds folded (flipped) faces on a flat face. Convex pieces always contain
their vertex average. Concave pieces also have short bridge edges next to bevelled edges (section 4) — likely
why ADR 0008 measured 25 mm³ for "fewest concave polygons" **[unverified guess]**.

## 3. Algorithms

- **Quality constrained Delaunay without boundary Steiner points.** Shewchuk's Triangle: `-q` (min angle,
  default 20°), `-Y` "prohibits the insertion of Steiner points on the mesh boundary". Quality refinement puts
  interior points at ≈ local edge length from the boundary (≈ 0.75 mm next to a 10 mm hole at our density), and
  Triangle's licence forbids inclusion in commercial products without a licence (not GPL-compatible
  **[inference]**). <https://www.cs.cmu.edu/~quake/triangle.switch.html>, <https://www.cs.cmu.edu/~quake/triangle.html>,
  <https://people.eecs.berkeley.edu/~jrs/meshpapers/delnotes.pdf>
- **Quad-dominant meshing.** Gmsh: *Frontal-Delaunay for Quads* (right triangles aligned to a cross field) +
  *Blossom* recombination (minimum-cost perfect matching) → all-quad meshes; paving (advancing front of quads
  from the boundary). Both need boundary splitting for parity and put the first row at one edge length.
  <https://gmsh.info/doc/texinfo/gmsh.html>, <https://gmsh.info/doc/preprints/gmsh_quad_preprint.pdf>,
  <https://gmsh.info/doc/preprints/gmsh_quad2_preprint.pdf>, <https://www.robertschneiders.de/papers/vki.pdf>
- **Medial-axis decomposition** (Tam & Armstrong 1991): split the domain along its medial axis into simple
  sub-regions, then mesh each with a template (rings around holes). The medial axis is where a vertex is
  equally far from the two boundaries it separates — the bevel-optimal place (section 4).
  <https://www.sciencedirect.com/science/article/abs/pii/0961355291900353>
- **Convex decomposition.** Hertel–Mehlhorn is within 4× of the minimum number of convex pieces; the exact
  minimum is polynomial for simple polygons (Keil) and NP-hard with holes (Lingas). None of them helps with
  slivers: the lower bound is N pieces per curved hole (section 0.1).
  <https://en.wikipedia.org/wiki/Polygon_partition>
- **Ring reduction.** An N-vertex ring can become a coarser outer polygon with 2:1/3:1 quad transitions, or
  — the cheap trick — by mapping the ring onto a polygon with few *corners* whose sides carry the other
  vertices *collinearly*: the collinear vertices are 180° (not reflex), so the outer region sees a convex hole
  with 4 corners. This is the circle-in-a-square pattern. **[inference]**

## 4. Bevel Clamp Overlap: what actually limits the bevel

`bevel_limit_offset` (Blender `source/blender/bmesh/tools/bmesh_bevel.cc`, main) takes the **minimum over all
bevelled edge halves** of `geometry_collide_offset` and scales every offset by it — one tight spot clamps the
whole modifier. For a bevelled edge B = (b, c) in polygon P with previous edge A = (a, b), next C = (c, d):
- if A and C are bevelled: the offset where the offset copies of A, B, C meet (depends on |B| and the angles);
- if A is **not** bevelled: `A_side_slide = |A| · sin(π − θ_abc)` (walking on while collinear), i.e. the
  **distance from a to the line of B**; likewise for C. The limit is that distance (for weight 1).

Consequences for a flat face (all sharp CAD edges have bevel weight 1, ADR 0008):
- **Triangle ears along an arc**: the third edge is an un-bevelled chord whose far vertex is a hole vertex a
  fraction of a millimetre from B's line → the 0.22 mm³ result.
- **Current convex fans**: the un-bevelled neighbour edges run to far vertices (corners, other hole vertices);
  the limit is the true clearance c between the hole and the outer edge. Note: with both features bevelled the
  non-overlapping limit is c/2, which this check doesn't see (the source says "This is not perfect").
- **Any interior vertex** at distance d from a bevelled edge's line limits the bevel to d: quality meshes
  (d ≈ chord), support loops, radial rings. Blender modelers see the same when bevelling after adding loops.
- **Collar at the medial position** (d = c/2 on both sides): limit c/2 — the correct non-overlap limit when
  both the hole and the outer edge are bevelled (the default Bevel-by-weight case), half the current one when
  only one side is bevelled. **[inference from the source; to be measured]**

## 5. Recommendation for BlendSolid

### Display mesh now: rectangular collars + Hertel–Mehlhorn outside

For each flat face with holes (in `_polygons`, before `_merge_convex`):
1. **Pick the holes.** An inner loop gets a collar if it has ≥ 8 vertices, reflex from the face side, and is
   star-shaped from its vertex centroid (angles around the centroid strictly monotonic). Polygonal holes
   (rectangular pockets, slots with few vertices) keep today's path: their decomposition is already good.
2. **Frame.** In the face plane, axes along the outer loop's longest straight segment (or its minimum-area
   bounding rectangle).
3. **Clearance.** c = distance from the hole polygon to every other loop (outer, other holes); O(N·M) point–segment
   distances, cheap.
4. **Collar.** The hole's bounding rectangle in that frame grown by m = c/2 (optionally capped at a few hole
   radii on large plates — to be chosen by measurement). Collar vertices: each hole vertex projected along the ray
   from the hole centroid onto the rectangle (valence-3 vertices, radial quads); the 4 rectangle corners added
   where no ray hits them (the two quads there become convex pentagons).
5. **Validity** (else fall back to today's HM for that face): collar strictly inside the outer loop, collars
   pairwise disjoint and not touching other holes, every radial quad convex and positively oriented.
6. **Outer region.** Outer loop with the collars as holes (their collinear vertices included): triangulate
   (ear clipping with hole bridging, ~150 lines of numpy/Python, or OCCT on a planar face built from those
   polygons with a vertex at every collar point) and run the existing `_merge_convex` — `_convex_at` already
   accepts 180°. Typical result: 4 convex trapezoids per collar, plus a few pieces between collars.

What this gives on the sample (2 holes ≈ 42 vertices near one edge) **[estimate]**: 2 × 42 radial quads with
angles ≥ ≈ 45° (the worst at the collar corners), ≈ 8–12 outer convex n-gons — about 95 polygons instead of
65, min angle ≈ 30–45° instead of 0.38°. The polygon count per curved hole cannot go below N for convex
pieces (section 0.1); the collar makes those N pieces short and regular instead of long slivers.

Properties: boundary untouched (weld, closed mesh, edge ids and face map unchanged; new edges are interior,
`brep_edge_id = -1`); all pieces convex (Subdivision Surface, Solidify, Triangulate safe; Weighted Normal trivially
flat); bevel limit becomes min(c/2) over the collared holes (section 4).

Optional, cheap, and useful for both displays and quads: round the segment count of **full circles** up to a
multiple of 4 in the edge discretization (ADR 0010), so the collar corners fall on hole vertices (pure quads, no
pentagons). Neighbour faces share the edge nodes, so this stays conforming.

### Leave to "convert to quads"

- Quads in the outer region: subdividing straight CAD edges (new boundary vertices, propagated to the
  neighbour faces), transfinite grids on the trapezoids, 2:1/3:1 transitions from collar counts to the outer
  grid, or Blossom-Quad recombination of a Frontal-Delaunay-for-quads triangulation (Gmsh-style).
- Support/holding loops for Subdivision, segment-count reduction (32 → 16 → 8), hole groups (bolt circles)
  with a shared collar, non-star-shaped holes (field-aligned remeshing: Instant Meshes / QuadWild-class).

### Cost and risks

- **Cost [estimate]:** 200–300 lines in `worker/tessellate.py` (collar builder, clearance, validity, ear
  clipping or OCCT planar-face triangulation) plus tests; runtime O(N·M) per face, negligible next to meshing.
- **Bevel clamp changes.** ADR 0008's "clamp on = clamp off on every probed part" holds only for bevels ≤ c/2.
  A hole close to an edge now clamps the whole part to c/2 instead of c (it is the non-overlap limit when both are
  bevelled, which is the default). Must be re-measured in `tests/blender/test_modifiers.py` (1 mm bevel on the
  default part, box with hole, box with boss; clamp on vs off) and noted in an ADR 0008 addendum.
- **Crowded holes** (bolt circles, holes near outer concave corners, a hole in a narrow web): collars overlap or
  get tiny → fallback to HM for that face (today's look). Measure how often the fallback fires on the fuzz parts.
- **Large plates, small holes:** m = c/2 gives long radial quads (angles fine, aspect high); a cap trades that
  against the bevel limit — decide by measurement.
- **Verification (project rules):** per face: every polygon convex and planar, min angle, polygon count, face area
  equal to the BRep face area, mesh closed, volume unchanged; after a Subdivision Surface modifier, no polygon of
  the flat face flipped (normal · plane normal > 0); bevel volumes with clamp on/off.

## 6. Sources

Rhino mesh settings <https://docs.mcneel.com/rhino/8/help/en-us/information/polygonmeshsettings.htm> ·
Rhino mesh FAQ <https://wiki.mcneel.com/rhino/meshfaqdetails> · QuadReMesh
<https://docs.mcneel.com/rhino/8/help/en-us/commands/quadremesh.htm> · MoI export
<https://moi3d.com/4.0/docs/moi_command_reference11.htm> · MoI holes
<https://moi3d.com/forum/lmessages.php?webtag=MOI&msg=9388.1> · MoI mesher design
<http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=3196.1> · Parasolid faceting
<http://www.q-solid.com/Parasolid_Docs_V35/chapters/fd_chap.108.html> · Plasticity OBJ export
<https://doc.plasticity.xyz/plasticity-essentials/export-obj> · Plasticity Blender bridge
<https://github.com/nkallen/plasticity-blender-addon> · FreeCAD Mesh_FromPartShape
<https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Mesh_FromPartShape.md> · Holes with quad topology
<https://www.3dsecrets.com/secrets/blender-secrets-modeling-holes> · 8-sided cylinders
<https://polycount.com/discussion/81038/sub-d-tip-perfect-8-sided-cylinders-from-quads> · Polycount sub-d wiki
<http://wiki.polycount.com/wiki/Subdivision_Surface_Modeling> · CG Cookie topology
<https://blog.cgcookie.com/posts/the-art-of-good-topology-blender/> · HardOps
<https://hardops-manual.readthedocs.io/en/latest/subdivision/> · Blender Bevel source
<https://github.com/blender/blender/blob/main/source/blender/bmesh/tools/bmesh_bevel.cc> · Clamp regression
<https://projects.blender.org/blender/blender/issues/139664> · Catmull–Clark
<https://en.wikipedia.org/wiki/Catmull%E2%80%93Clark_subdivision_surface> · Triangle switches / licence
<https://www.cs.cmu.edu/~quake/triangle.switch.html>, <https://www.cs.cmu.edu/~quake/triangle.html> · Gmsh manual
<https://gmsh.info/doc/texinfo/gmsh.html> · Blossom-Quad <https://gmsh.info/doc/preprints/gmsh_quad_preprint.pdf> ·
Frontal-Delaunay quads <https://gmsh.info/doc/preprints/gmsh_quad2_preprint.pdf> · Schneiders survey
<https://www.robertschneiders.de/papers/vki.pdf> · Tam & Armstrong
<https://www.sciencedirect.com/science/article/abs/pii/0961355291900353> · Polygon partition
<https://en.wikipedia.org/wiki/Polygon_partition>
