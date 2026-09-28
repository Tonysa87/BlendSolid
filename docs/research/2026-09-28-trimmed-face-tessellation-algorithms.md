# Tessellating trimmed CAD faces for display: algorithms and implementations

- **Date:** 2026-09-28 (research done 2026-09-27)
- **Question:** BlendSolid's display tessellation (ADR 0005) gives an irregular mosaic on trimmed curved faces:
  fillet bands (torus / BSpline rolling-ball surfaces whose (u, v) domain is almost a rectangle bounded by
  BSpline pcurves), cylinders trimmed by fillets (one row of long triangles, opposite sides with different node
  counts → fans), narrow fillet strips full of slivers. Which algorithms give regular, grid-like, conforming
  (welded) meshes within a chord tolerance (default 1 mm) and an angular tolerance, fast enough for
  interactive use (whole part ≲ 100 ms)?
- **Scope update (maintainer, during the research):** the display mesh follows CAD conventions (Rhino,
  Plasticity/Parasolid, MoI's triangle output): a **regular, conforming triangle mesh** is the goal. Quad
  output is a later, separate "convert to quads" feature; quad techniques are listed briefly (section 6) as
  input for it.
- **Method:** OCCT 8 documentation and source (GitHub `Open-Cascade-SAS/OCCT` master), Gmsh 4.15 reference
  manual (downloaded and grepped), SALOME SMESH source (`StdMeshers_Quadrangle_2D.cxx`, GitHub mirror
  `SalomePlatform/smesh`) and docs, Rhino / MoI / Parasolid documentation and the MoI author's forum posts,
  paper abstracts (full texts on ScienceDirect were not reachable: HTTP 403). OCP bindings were probed with the
  project's own worker libraries (`.dev/worker_libs`, OCP 8.0.1) in Blender's Python.
- **Tags:** **[verified]** = checked by running code here; **[inferred]** = my reading/derivation;
  **[unverified]** = could not check (e.g., closed-source internals, paywalled papers).

---

## 0. Summary

1. The CAD programs the maintainer names all use the same recipe for display meshes of trimmed surfaces:
   **start from a grid in the surface's (u, v) parameter space, refine it against the chord/angle criteria,
   then cut it with the trim boundary**; only the pieces along the trim boundary become irregular. Rhino
   documents exactly these three steps; MoI's author describes grid quads trimmed into n-gons and triangulated at
   the end, with every polygon edge either on a trim edge or along a u/v iso-direction (section 3).
2. The "mosaic" of our current Delaunay lattice has a specific cause: **Delaunay on a rectangular lattice is
   degenerate** (the four corners of every cell are co-circular), so the diagonal of each cell is chosen by
   round-off. A grid should emit its own triangles (one consistent diagonal per cell), not be re-Delaunayed
   **[inferred]**.
3. OCCT's BRepMesh already builds interior nodes on (u, v) grids (per-surface `*RangeSplitter` classes) but
   inserts them into a Delaunay triangulation; custom face meshers (`BRepMesh_CustomBaseMeshAlgo`,
   `IMeshTools_MeshAlgoFactory`) are C++-only: **OCP 8 cannot subclass them from Python** **[verified]**.
   What we *can* use from Python: BRepMesh's edge discretization (`Poly_PolygonOnTriangulation` with edge
   parameters **[verified]**), or our own edge discretization.
4. Conformity is simple if **edge nodes are decided once per edge** (by parameter on the 3D curve) and every
   face uses them; the face mesher then must not add points on its boundary — or the points it wants there
   (iso-line crossings) must be put into the edge's node list **before** either neighbour is meshed (MoI's
   "matching vertex on the adjacent face").
5. Recommendation (section 7): **(A) trimmed parametric grid ("MoI/Rhino recipe") with a two-pass edge
   discretization**, with **(B) transfinite/structured strips for 4-sided faces (fillet bands, trimmed
   cylinders)** as a special case of (A) or a fast path, and **(C) BRepMesh + clean-up** kept as a fallback.

---

## 1. OCCT BRepMesh: internals, options, extension points

### 1.1 Pipeline

The OCCT mesh user guide describes six stages: model builder → edge discretization → model healer →
preprocessor → face discretization → postprocessor; `IMeshTools_Context` (default `BRepMesh_Context`) holds the
tool of each stage, and face discretization picks an algorithm per face through an `IMeshTools_MeshAlgoFactory`
(default `BRepMesh_MeshAlgoFactory`, alternative `BRepMesh_DelabellaMeshAlgoFactory`). Example from the guide:

```cpp
occ::handle<IMeshTools_Context> aContext = new BRepMesh_Context();
aContext->SetFaceDiscret(new BRepMesh_FaceDiscret(new BRepMesh_DelabellaMeshAlgoFactory()));
BRepMesh_IncrementalMesh aMesher; aMesher.SetShape(aShape);
aMesher.ChangeParameters() = aMeshParams; aMesher.Perform(aContext);
```

Source: https://occt3d.com/dev/doc/overview/html/occt_user_guides__mesh.html

Third-party face algorithms plug in through three base classes: `BRepMesh_ConstrainedBaseMeshAlgo`,
`BRepMesh_CustomBaseMeshAlgo` (override `buildBaseTriangulation()`; the base class then restores the boundary
constraints with Delaunay edge flips, removes auxiliary elements and cleans free links) and
`BRepMesh_CustomDelaunayBaseMeshAlgo` (same URL; header:
https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/master/src/ModelingAlgorithms/TKMesh/BRepMesh/BRepMesh_CustomBaseMeshAlgo.hxx).

### 1.2 How interior nodes are placed

`BRepMesh_MeshAlgoFactory::GetAlgo` chooses, per surface type, a Delaunay algorithm templated on a
*range splitter* that generates interior (u, v) nodes: `BRepMesh_DefaultRangeSplitter` (plane),
`CylinderRangeSplitter`, `ConeRangeSplitter`, `SphereRangeSplitter`, `TorusRangeSplitter`,
`BoundaryParamsRangeSplitter` (surface of revolution), `ExtrusionRangeSplitter`, `NURBSRangeSplitter`
(Bezier/BSpline: "Initializes U and V parameters lists using CN continuity intervals", then filters "to avoid
too dense distribution"), `UndefinedRangeSplitter` (offset/other). Planes, cylinders, cones, spheres, tori use
`NodeInsertionMeshAlgo` (insert the splitter's grid nodes into the Delaunay mesh); BSpline, revolution,
extrusion and "other" use `DeflectionControlMeshAlgo` (insert, then keep adding nodes where triangles deviate
from the surface). Source:
https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/master/src/ModelingAlgorithms/TKMesh/BRepMesh/BRepMesh_MeshAlgoFactory.cxx
and `BRepMesh_NURBSRangeSplitter.hxx` in the same directory.

So BRepMesh's interior *is* a grid; the irregularity comes from (a) Delaunay's arbitrary diagonal on
co-circular grid cells, (b) Delaunay's treatment of the band between the grid and the boundary nodes, and (c)
deflection-control insertions **[inferred]**. This matches ADR 0005's observations (fans, slivers).

### 1.3 `IMeshTools_Parameters` (all fields, OCCT master)

| Field | Default | Meaning (header doc) |
|---|---|---|
| `MeshAlgo` | `DEFAULT` | 2D Delaunay algorithm factory (`DEFAULT` = Watson, or `Delabella`) |
| `Angle` / `Deflection` | 0.5 / 0.001 | angular / linear deflection of boundary edges |
| `AngleInterior` / `DeflectionInterior` | -1 / -1 | same for the face interior (-1 = use boundary values) |
| `MinSize` | -1 | minimum triangle edge size "to prevent sinking into amplification in case of distorted curves and surfaces" |
| `InParallel` | false | multi-threading |
| `Relative` | false | relative deflection |
| `InternalVerticesMode` | true | take internal face vertices into account |
| `ControlSurfaceDeflection` | true | check triangle-to-surface deviation of the interior |
| `EnableControlSurfaceDeflectionAllSurfaces` | false | apply that check to analytic surfaces too |
| `CleanModel` | true | drop the temporary data model when done |
| `AdjustMinSize` | false | local min-size adjustment from edge size |
| `ForceFaceDeflection` | false | use shape tolerances for face deflection |
| `AllowQualityDecrease` | false | allow a coarser mesh than the existing one |

Source: https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/master/src/ModelingAlgorithms/TKMesh/IMeshTools/IMeshTools_Parameters.hxx

None of these changes the *layout* of the triangles (grid vs Delaunay); they change density and checks
**[inferred]**. `IMeshTools_MeshAlgoType_Delabella` works from OCP (`p.MeshAlgo = ...Delabella`,
`BRepMesh_IncrementalMesh(shape, p)`) **[verified]**, but Delabella is also a Delaunay triangulator and will
not give grid-like output **[inferred]**.

### 1.4 What OCP 8.0.1 exposes (probed in Blender's Python) **[verified]**

- Exposed: `BRepMesh_DelabellaMeshAlgoFactory`, `BRepMesh_MeshAlgoFactory`, `BRepMesh_EdgeDiscret`,
  `BRepMesh_FaceDiscret`, `IMeshTools_Parameters` (all fields above), `IMeshTools_MeshAlgo`,
  `IMeshTools_MeshAlgoFactory`, `IMeshTools_CurveTessellator`, `IMeshTools_Context`.
- Not exposed: `BRepMesh_CustomBaseMeshAlgo`, `BRepMesh_Context`, `BRepMesh_IncrementalMesh.Perform(context)`
  is not usable without a context class.
- Subclassing `IMeshTools_MeshAlgo`, `IMeshTools_MeshAlgoFactory` or `IMeshTools_CurveTessellator` in Python
  fails: `TypeError: No constructor defined!` (no pybind11 trampolines). **A custom face mesher inside BRepMesh
  requires C++** (a compiled extension per platform) — not attractive for BlendSolid.
- After `BRepMesh_IncrementalMesh`, `BRep_Tool.PolygonOnTriangulation_s(edge, triangulation, loc)` returns the
  edge's node indices in the face triangulation **and their curve parameters** (`HasParameters() == True`,
  e.g. `[0.0, 20.0]` on a box edge). Since BRepMesh discretizes each edge once and shares it between faces, these
  parameters are a ready-made, conforming edge discretization we can feed to our own face mesher.

### 1.5 Per-edge discretization under our control

Two options, both pure Python/OCP **[inferred]**:

1. Run `BRepMesh_IncrementalMesh` (edges only matter), read each edge's parameters as above, evaluate points on
   the 3D curve and on each face's pcurve at those parameters.
2. Discretize edges ourselves (e.g., `GCPnts_TangentialDeflection` / `GCPnts_QuasiUniformDeflection` on
   `BRepAdaptor_Curve`, or our own sampling), store `edge → sorted parameters` once, and build each face from
   it. This is needed for the two-pass scheme of section 7 (inserting iso-line crossings).

Writing results back into OCCT (`Poly_PolygonOnTriangulation`, `BRep_Builder.UpdateFace`) is only needed if
OCCT must reuse our mesh; for Blender display it is not.

---

## 2. Gmsh (GPL-2.0-or-later, OCC-based CAD import)

From the Gmsh 4.15 reference manual, https://gmsh.info/doc/texinfo/gmsh.html :

- `Mesh.Algorithm`: "1: MeshAdapt, 2: Automatic, 3: Initial mesh only, 5: Delaunay, 6: Frontal-Delaunay,
  7: BAMG, 8: Frontal-Delaunay for Quads, 9: Packing of Parallelograms, 11: Quasi-structured Quad" (default 6).
- `Mesh.MeshSizeFromCurvature`: "Automatically compute mesh element sizes from curvature, using the value as the
  target number of elements per 2 * Pi radians".
- **Transfinite Surface**: "the expression-list on the right-hand-side should contain the tags of three or four
  points on the boundary of the surface that define the corners of the transfinite interpolation. If no tags are
  given, the transfinite algorithm will try to find the corners automatically. The optional argument
  [Left | Right | Alternate | AlternateRight | AlternateLeft] specifies the way the triangles are oriented when
  the mesh is not recombined." Opposite sides must carry matching node counts (set with `Transfinite Curve`).
  `Mesh.TransfiniteTri`: alternative arrangement for 3-sided surfaces.
- `gmsh.model.mesh.setTransfiniteAutomatic(dimTags=[], cornerAngle=2.35, recombine=True)`: "Transfinite meshing
  constraints are added to the curves of the quadrangular surfaces and to the faces of 6-sided volumes.
  Quadrangular faces with a corner angle superior to cornerAngle (in radians) are ignored. The number of points
  is automatically determined from the sizing constraints."
- Recombination: `Mesh.RecombinationAlgorithm` "0: simple, 1: blossom, 2: simple full-quad, 3: blossom full-quad"
  (default 1); Blossom = minimum-cost perfect matching (Remacle et al., "Blossom-Quad", IJNME 89, 2012);
  "Frontal-Delaunay for quads" = L∞-norm frontal Delaunay giving right triangles almost everywhere (Remacle et
  al., IJNME 94, 2013); `Mesh.RecombineOptimizeTopology` (default 5 passes); `Mesh.RecombineMinimumQuality`
  (default 0.01).
- Algorithm 11 (Quasi-structured quad): cross-field guided pipeline (Reberol, Georgiadis, Remacle,
  "Quasi-structured quadrilateral meshing in Gmsh — a robust pipeline for complex CAD models",
  https://arxiv.org/abs/2103.04652 ) **[unverified: paper not re-read for this note]**.

Relevance: Gmsh's *transfinite* surfaces are exactly the "structured strip" we want on fillets and trimmed
cylinders, and `Alternate` gives a symmetric diagonal pattern. Using Gmsh itself (the `gmsh` PyPI wheel bundles
its own OCC) is licence-compatible, but it would add a second OCCT, another ~50–100 MB per platform, and a
shape transfer (BRep string) per recompute; its speed for a whole part in < 100 ms is **[unverified]**. Better
to reimplement the few pieces we need (TFI, corner detection, sizing).

---

## 3. What Rhino, MoI and Parasolid do (the "CAD convention")

### 3.1 Rhino (documented)

Rhino's detailed mesh options page lists three creation steps: "The number of initial quads (estimated to
roughly meet the criteria)", "Refinement (subdivision to meet the criteria)", "Adjustment for trim
boundaries". Options: *Minimum initial grid quads* ("The number of quadrangles per surface in the initial mesh
grid"), *Maximum aspect ratio* ("The initial quad mesh is constructed so that on average, the maximum aspect
ratio of the quads is less than or equal to Maximum aspect ratio"), *Refine mesh* ("a recursive process to
refine the mesh until it meets the criteria defined by Maximum angle, Minimum edge length, Maximum edge length,
and Maximum distance, edge to surface"), *Maximum distance, edge to surface* ("Polygons divide until the
distance from a polygon edge midpoint to the NURBS surface is smaller than this value"), *Jagged seams* (faces
meshed independently, not stitched → cracks), *Simple planes* ("meshing the surface edges and then filling the
area bounded by the edges with triangles"). Source:
http://docs.mcneel.com/rhino/6mac/help/en-us/popup_moreinformation/polygon_mesh_detailed_options.htm

So: planes = boundary-only fill; curved surfaces = refined (u, v) quad grid, trimmed; seams stitched unless
*Jagged seams*.

### 3.2 MoI (author's own description)

Michael Gibson (MoI's author), MoI forum, "Michael's Plasticity rants":
"MOI does not make an initial triangular tessellation, it makes an initial UV quad mesh and then with trim
edges the quads are trimmed directly into n-gons." / "The only triangulation in MOI happens at the end if you
want triangles where the n-gons get triangulated." / "in MOI's n-gon output, every single poly edge in the
entire output is either along a trim boundary edge, or running along a surface's UV directions." He
contrasts this with Plasticity (Parasolid-based), whose output "will often generate edges that seem to be from
an initial triangular tessellation". Source:
http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=11865.65 . A search-engine summary of MoI forum posts
also attributes to him that every n-gon vertex has "a matching vertex on the adjacent face", i.e. watertight
output **[unverified: exact post not located]**. MoI's export options (*Angle*, *Divide larger than*, *Avoid
smaller than*, *Aspect ratio limit*, output n-gons / quads & triangles / triangles) are described in the MoI
forum, e.g. http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=630.2 .

**This is the most precise public description of the look the maintainer wants:** grid lines along u and v,
cut by the trim curves, n-gons triangulated at the end.

### 3.3 Parasolid (Plasticity's kernel)

The Parasolid facet documentation (v12, `PK_TOPOL_facet_mesh_o_t`) documents options, not the algorithm:
facet `shape` (`convex` default: "all interior angles are convex and none of the facets contain interior
holes"), `match` (`geom`: faces independent, small gaps; `topol` default: "boundary vertices on a facet mesh
always match with vertices on the boundaries of neighboring meshes (possibly splitting facets in the
neighboring facet mesh in order to meet this condition)"; `trimmed`: facets clipped to model edges, gaps/
overlaps within tolerance), maximum sides per facet, min/max facet width, curve tolerances (`curve_chord_tol`,
`curve_chord_max`, `curve_chord_ang`), surface tolerances (`surface_plane_tol`, `surface_plane_ang`), local
per-face tolerances. Source: http://www.q-solid.com/Parasolid_Docs/chapters/fd_chap.55.html .
Parasolid's facets can have more than 3 sides (convex polygons), consistent with a grid-cut-by-trims design,
but its internal algorithm is **[unverified]** (closed source). Note the `topol` match: conformity is achieved
by *splitting neighbour facets* at the other side's boundary vertices — the same idea as the two-pass edge
discretization in section 7.

### 3.4 Literature on trimmed-NURBS tessellation (standard recipe)

- Kumar & Manocha, "Efficient rendering of trimmed NURBS surfaces", Computer-Aided Design 27(7), 1995: convert
  to Bézier, "tight bounds for uniform tessellation of Bézier surfaces into cells", then "trim curve tracing,
  intersection computation with the cells, and triangulation of the cells"; "Polygonization anomalies like
  cracks and angularities are avoided". Sources: https://www.sciencedirect.com/science/article/abs/pii/001044859400003V ,
  http://gamma.cs.unc.edu/RENDER/abs.tech-8.html (abstract only).
- Rockwood, Heaton, Davis, "Real-time rendering of trimmed surfaces", SIGGRAPH 1989: uniform (u, v) grid per
  Bézier patch, trimmed region triangulated as monotone strips between trim curves and grid lines, with
  crack-free patch boundaries **[unverified: from memory, paper not re-read]**.
- Piegl & Tiller, "Geometry-based triangulation of trimmed NURBS surfaces", CAD 30(1), 1998: subdivision decided
  in model space (flatness), triangulation in parameter space; only C0 continuity assumed. Source (abstract):
  https://www.sciencedirect.com/science/article/abs/pii/S001044859700047X ; follow-up for multiple surfaces
  (shared boundaries): https://www.sciencedirect.com/science/article/abs/pii/S0010448500000956 .
- Guthe, Balázs, Klein: view-dependent trimmed-NURBS rendering, 2002; Balázs/Guthe/Klein "Efficient trimmed
  NURBS tessellation" (2004): grid/quadtree in (u, v) with trimmed cells and crack-free seams
  **[unverified: PDFs not retrievable]**: https://www.researchgate.net/publication/3998804 ,
  https://www.academia.edu/32435914/Efficient_trimmed_NURBS_tessellation .
- GPU direct trimming (Schollmeyer & Fröhlich, "Direct trimming of NURBS surfaces on the GPU", ACM TOG 28(3),
  2009, https://dl.acm.org/doi/abs/10.1145/1531326.1531353 ) trims per pixel instead of meshing: not
  applicable to a Blender mesh.
- Step size from derivative bounds: for a chord tolerance δ the parameter step in u is bounded by
  `h_u ≤ sqrt(8δ / M_uu)` with `M_uu` a bound on `|S_uu|` (Filip, Magedson, Markot, "Surface algorithms using
  bounds on derivatives", CAGD 3(4), 1986) **[unverified: formula from memory]**. The geometric version used
  below (chord of a circle of radius R: `L = 2·sqrt(δ(2R − δ))`, angle `L ≤ R·θ`) is elementary.

**The common recipe:** a (u, v) grid sized from curvature bounds; cells fully inside the trim loop are emitted
as regular cells; cells crossed by the trim loop are clipped (or dropped), and the band between the inner grid
and the trim polyline is triangulated; seams are made crack-free by sharing the trim polyline between faces.

---

## 4. Structured meshing of 4-sided faces (SMESH "Quadrangle: Mapping")

SALOME SMESH (`StdMeshers_Quadrangle_2D`, LGPL-2.1) — docs
https://docs.salome-platform.org/latest/gui/SMESH/quad_ijk_algo.html and
https://docs.salome-platform.org/latest/gui/SMESH/2d_meshing_hypo.html , source
https://raw.githubusercontent.com/SalomePlatform/smesh/master/src/StdMeshers/StdMeshers_Quadrangle_2D.cxx :

- **Scope:** faces without holes bounded by ≥ 3 edges; nodes placed by transfinite interpolation "in the
  parametric space of a face".
- **Corner selection** (`getCorners` → `uniteEdges`): with more than 4 edges, "four most sharp vertices are
  considered as corners". In code: the angle between consecutive edges at each vertex is computed
  (`SMESH_MesherHelper::GetAngle`, falling back to the angle between the mesh segments if the tangent angle is
  ≤ 5°); tolerance 5°, "sharp" = > 90° − 5°. If the number of convex (or sharp) vertices already equals 4, those
  are the corners; otherwise concave-angle edges are merged into the previous side and candidate corner sets
  are enumerated so that the segment count is split in halves between opposite sides, and the variants are
  ranked by quality (`QuadQuality`). User-fixed corners (Corner Vertices tab) override. A 3-edge face needs a
  "base vertex" used as a degenerate 4th side.
- **TFI in code** (`setNormalizedGrid`, citing P.L. George, *Génération automatique de maillages*, §6.4.1):
  boundary nodes get normalized coordinates x ∈ [0,1] along bottom/top and y along left/right (by normalized
  curve parameter); interior (x, y) is the intersection of the straight line joining bottom/top nodes i and the
  line joining left/right nodes j:
  `x = (x0 + y0·(x1−x0)) / (1 − (y1−y0)·(x1−x0))`, `y = y0 + x·(y1−y0)`; then the Coons formula maps it to (u, v):
  `uv = (1−y)·p0 + x·p1 + y·p2 + (1−x)·p3 − [(1−x)(1−y)·a0 + x(1−y)·a1 + x·y·a2 + (1−x)·y·a3]`
  (`calcUV`; p0..p3 = boundary points on bottom/right/top/left, a0..a3 = corners). This is directly
  vectorizable in numpy.
- **Unequal counts on opposite sides** (quad-dominant default): grid of size min(nb, nt) × min(nl, nr); the
  extra nodes ("nbNodeOut") on the finer side are absorbed by triangles "near the side with the maximal number
  of segments". Transition types (hypothesis): *Standard* (tris + quads in the transition row along the finer
  side), *Triangle preference* (only triangles there), *Quadrangle preference* (only quads, requires even total
  segment count), *Quadrangle preference (reversed)* (transition along the coarser side), *Reduced* ("only
  quadrangles and the transition between the sides is made gradually, layer by layer"; one pair of opposite
  sides equal, the other pair with even total; "three segments become one", needs ≥ log3(Nmax/Nmin) rows;
  otherwise falls back to Quadrangle preference reversed). The source contains ASCII diagrams of the simple
  3→1 and 2→1 ("10→8→6→4") reduction trees (`computeReduced`).

For **triangles** (our goal), transitions are simpler: between a row of n nodes and a row of m nodes, the
"zip" of two polylines by advancing on the side whose next node is closer in normalized parameter gives
well-shaped triangles (BlendSolid already does this, `worker/tessellate.py::_zip`) **[inferred]**. The real
fix for "one row of long triangles with different counts" is to **make the counts equal or proportional**
(section 7), not to zip better.

---

## 5. Why our current results look the way they do **[inferred]**

- *Mosaic on trimmed faces:* Delaunay of a regular lattice picks diagonals arbitrarily (co-circular cells); in
  a metric-scaled (u, v) the lattice is only approximately rectangular, so diagonals flip between neighbouring
  cells. Emitting grid triangles directly with a consistent (or alternating, Gmsh `Alternate`) diagonal removes
  it.
- *Cylinders trimmed by fillets:* the cylinder's straight edges have 2 nodes, its arcs many; if the face is 1
  segment "tall" the only interior is one row, and opposite arcs discretized independently (they belong to
  different fillets with different curvature) have different counts → fans. Remedy: v-lines of the cylinder
  should cross both arcs at the same u values (iso-lines), i.e. the arcs' discretizations should contain the
  cylinder's u-grid.
- *Fillet strips with slivers:* a rolling-ball band is naturally a tensor grid (u along the spine, v across);
  a Delaunay fill between two long boundary polylines produces slivers when the band is narrow relative to the
  node spacing. A grid with v-count ≥ 2 and u-lines matched across both long sides produces regular triangles.

---

## 6. Quad techniques (input for the future "convert to quads" feature)

- **Pair triangles of a structured grid:** if the display mesh is built from grid cells split along one
  diagonal, the quads are the cells: record `cell_id` per triangle and dissolve the diagonal. Exact, O(n).
- **Blender "Triangles to Quads" (Alt+J):** merges adjacent triangles with thresholds *Max Face Angle*
  (between triangle normals) and *Max Shape Angle* ("If set to 40°, corners between 50° and 130° are
  allowed"), *Topology Influence* ("prefer creating new quads that match the topology of existing quads"; tip:
  100–130 % with Max Angle 180°), and *Compare Sharp/Seam/Materials/UVs* (so CAD edges marked sharp are never
  dissolved). Source: https://docs.blender.org/manual/en/latest/modeling/meshes/editing/face/triangles_quads.html .
  `bpy.ops.mesh.tris_convert_to_quads` / bmesh `join_triangles` can be applied to a copy from Python.
- **Blossom matching** (Gmsh default recombination; min-cost perfect matching, Remacle et al. 2012) for
  full-quad results; SMESH Mapping + *Reduced* transitions for 4-sided faces (section 4); Gmsh algorithm 11
  (quasi-structured quads) for whole parts.

---

## 7. Recommended design for BlendSolid (triangle meshes)

Common foundation for all three options: **edge-first discretization**. Every BRep edge gets one sorted list of
curve parameters, computed once per recompute; faces take their boundary nodes from these lists (3D points
from the edge's 3D curve, (u, v) from the face's pcurve at the same parameters). This makes welding exact by
construction (same edge id + parameter index → same vertex) and is already how BRepMesh behaves (§1.4).

### A. Trimmed parametric grid with two-pass edge discretization ("MoI/Rhino recipe") — **recommended**

1. **Sizing per face:** evaluate the surface on a coarse sample grid over the face's (u, v) bounding box
   (numpy-batched: `BRepAdaptor_Surface.D2` loop, or native numpy evaluation for BSpline/analytic types);
   from normal curvature along u and v (`κ_u = |S_uu·N| / |S_u|²`, same for v) and the lengths `|S_u|`, `|S_v|`
   derive the allowed 3D step from chord δ (`L = 2·sqrt(δ(2R−δ))`) and angle θ (`L ≤ R·θ`); convert to a
   parameter step and place **global u-lines and v-lines** (tensor grid, non-uniform allowed: integrate the
   required density along u taking the max over v, and vice versa). Cap aspect ratio by adding lines in the
   coarse direction (Rhino's "Maximum aspect ratio"). Planes: no grid (Rhino's *Simple planes*; BlendSolid's
   ADR 0008 convex-polygon planes stay).
2. **Pass 1 — iso-crossings onto edges:** for each face, intersect its u-lines/v-lines with its trim loop in
   (u, v) (pcurves sampled finely, or `Geom2dAPI_InterCurveCurve` against iso-lines) and add the crossing
   parameters to each edge's candidate set. Also add the edge's own chord/angle-driven parameters.
3. **Merge per edge:** union the candidates from both adjacent faces and the edge's own; merge parameters
   closer than a fraction (e.g. 0.3) of the local target spacing (prefer iso-crossings, then keep chord
   tolerance). This is Parasolid's `topol` matching / MoI's matching vertices, done up front.
4. **Pass 2 — per face:** build the trim polygon from the merged edge nodes (in (u, v)); clip every grid cell
   against it (cells fully inside → 2 triangles with a consistent diagonal, e.g. the shorter 3D diagonal or
   Gmsh-style alternating; cut cells → convex/concave n-gon from Sutherland–Hodgman or a polygon clipper,
   triangulated by ear clipping or by a fan when convex). Points where grid lines meet the trim polygon are
   exactly the nodes inserted in pass 1, so no new boundary points appear. Drop or merge sliver pieces (cell
   fragments much smaller than the cell) by snapping the grid line locally to the boundary node instead.
5. **Check:** chord deviation at triangle centroids / edge midpoints (Rhino's criterion) on a sample; refine
   by splitting grid lines (not by point insertion) where exceeded.

- *Quality:* best of the three — the look the maintainer asked for (every edge along u, v or a trim edge);
  fillet bands and trimmed cylinders become regular rows automatically.
- *Robustness:* needs a robust point-in-polygon/clipping in (u, v) (pcurves are accurate but seams and periodic
  surfaces need unwrapping; degenerate edges at poles need a cap rule). Pass 1 couples neighbouring faces (a
  face's iso-lines add nodes to its neighbours' boundaries): a dense neighbour can over-refine a coarse face's
  edge — acceptable, and bounded by the merge step.
- *Cost:* medium–high (≈ 600–1000 lines of numpy code: sizing, iso-crossings, clipping, ear-clipping, periodic
  handling). *Speed:* grid evaluation and clipping vectorize well; the per-edge crossing search is O(lines ×
  pcurve samples) per face. Whole-part < 100 ms for typical parts is plausible **[unverified]**; surface
  evaluation through OCP is the bottleneck (~µs per point call overhead), so batch where possible.
- *Conformity:* exact by construction (shared edge parameter lists).

### B. Structured (transfinite) strips for 4-sided faces — **fast path for fillets and trimmed cylinders**

For faces whose boundary has 4 corners (SMESH corner rule: the 4 sharpest vertex angles, 5° tolerance; Gmsh
`cornerAngle = 2.35 rad`), mesh with TFI (SMESH `calcUV`/Coons formula, §4) using the edge nodes directly:
rows × columns = counts of opposite sides. Make opposite sides match by **propagating counts along chains of
opposite edges** (Gmsh's `setTransfiniteAutomatic` does this for "quadrangular surfaces"): the count of a chain
is the max required by any edge in it. Where counts still differ (chain conflicts, 3-sided faces), fall back to
the zip transition or to A.

- *Quality:* excellent on rolling-ball bands and cylinder strips (perfectly regular rows, Gmsh `Alternate`
  diagonals possible); poor on faces that are not topologically 4-sided (not applicable there).
- *Robustness:* TFI in (u, v) can fold if the pcurves bulge strongly (check triangle orientation in (u, v);
  fall back to A). Chain propagation is a global step but simple (union-find over edges).
- *Cost:* low (~200–300 lines). *Speed:* excellent (pure numpy).
- *Conformity:* exact (edge nodes are the boundary); but count propagation changes neighbours' edges, so it
  must run before any face is meshed — which fits the same edge-first pipeline as A.

### C. BRepMesh edges + BRepMesh interiors + post-processing — **fallback**

Keep `BRepMesh_IncrementalMesh` for edge discretization (parameters read via `PolygonOnTriangulation`) and for
faces A/B can't handle, and improve its output with edge flips toward the grid direction or toward 3D
Delaunay/shortest diagonal, plus sliver collapse.

- *Quality:* only modest improvement; the irregular band near trims remains.
- *Robustness:* highest (OCCT is battle-tested). *Cost:* low. *Speed:* fastest (C++).
- *Conformity:* as today.

### Ranking

| | Quality | Robustness | Cost | Speed (Python/numpy) | Conforming edges |
|---|---|---|---|---|---|
| **A** trimmed grid, two-pass edges | ★★★ | ★★ | high | ★★ | exact, by design |
| **B** TFI strips for 4-sided faces | ★★★ (where applicable) | ★★ | low | ★★★ | exact, needs count propagation |
| **C** BRepMesh + clean-up | ★ | ★★★ | low | ★★★ | exact (OCCT) |

**Suggested path:** implement the edge-first pipeline and **B** first (it fixes the three reported cases:
fillet bands, trimmed cylinders, narrow strips), with **C** as the fallback for every other face; then grow
**A** to cover arbitrary trimmed faces (it subsumes B: a 4-sided face whose trims lie on iso-lines is a clipped
grid with no cut cells). Do not write a C++ BRepMesh plug-in: OCP can't host it from Python and it would need
per-platform compiled code.

---

## 8. Sources

- OCCT mesh user guide: https://occt3d.com/dev/doc/overview/html/occt_user_guides__mesh.html
- OCCT source (master): `IMeshTools_Parameters.hxx`, `BRepMesh_CustomBaseMeshAlgo.hxx`,
  `BRepMesh_MeshAlgoFactory.cxx`, `BRepMesh_NURBSRangeSplitter.hxx` under
  https://github.com/Open-Cascade-SAS/OCCT/tree/master/src/ModelingAlgorithms/TKMesh
- Gmsh reference manual: https://gmsh.info/doc/texinfo/gmsh.html
- Gmsh quasi-structured quads: https://arxiv.org/abs/2103.04652
- SALOME SMESH: https://docs.salome-platform.org/latest/gui/SMESH/quad_ijk_algo.html ,
  https://docs.salome-platform.org/latest/gui/SMESH/2d_meshing_hypo.html ,
  https://raw.githubusercontent.com/SalomePlatform/smesh/master/src/StdMeshers/StdMeshers_Quadrangle_2D.cxx
- Rhino: http://docs.mcneel.com/rhino/6mac/help/en-us/popup_moreinformation/polygon_mesh_detailed_options.htm ,
  https://wiki.mcneel.com/rhino/meshfaq
- MoI: http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=11865.65 ,
  http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=630.2
- Parasolid facetting: http://www.q-solid.com/Parasolid_Docs/chapters/fd_chap.55.html
- Kumar & Manocha 1995: https://www.sciencedirect.com/science/article/abs/pii/001044859400003V ,
  http://gamma.cs.unc.edu/RENDER/abs.tech-8.html
- Piegl & Tiller 1998: https://www.sciencedirect.com/science/article/abs/pii/S001044859700047X ; multiple
  surfaces: https://www.sciencedirect.com/science/article/abs/pii/S0010448500000956
- Guthe et al. 2002: https://www.researchgate.net/publication/3998804 ; Balázs et al.:
  https://www.academia.edu/32435914/Efficient_trimmed_NURBS_tessellation
- Schollmeyer & Fröhlich 2009: https://dl.acm.org/doi/abs/10.1145/1531326.1531353
- Blender Triangles to Quads: https://docs.blender.org/manual/en/latest/modeling/meshes/editing/face/triangles_quads.html
